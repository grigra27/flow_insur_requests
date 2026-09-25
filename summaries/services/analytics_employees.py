"""Аналитика «Сотрудники»: нагрузка, присутствие и скорость на своих этапах за период.

Заменяет старый `analytics_managers` (docs/improvement_plans/analytics_redesign_2026_09.md, этап 4).

Кто в списке: все пользователи группы «Пользователи», включая тех, кто только смотрит,
плюс любой, у кого за период есть загрузки или смены статусов.

Атрибуция:
- заявки — по автору загрузки (`InsuranceRequest.created_by`); «файлов» — одна V2-загрузка
  с несколькими объектами (общий `source_batch_id`) считается одним файлом;
- предложения — по владельцу свода (`summary.request.created_by`) и дате ввода
  (`InsuranceOffer.received_at`): по аудиту предложения почти всегда вносит владелец заявки;
- собрано / отправлено клиенту / закрыто — по тому, кто сменил статус (`StatusEvent.changed_by`,
  журнал ведётся с 27.04.2026); автозакрытие (без автора) сюда не входит.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary, StatusEvent

EMPLOYEE_GROUP = 'Пользователи'
DEFAULT_PERIOD = '90'
PERIOD_CHOICES = [('90', '90 дней'), ('180', '180 дней'), ('365', '365 дней')]
STATUS_LOG_START = date(2026, 4, 27)

SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
OTHER_SERIES_COLOR = '#8a8985'

MONTH_SHORT_RU = {
    1: 'янв', 2: 'фев', 3: 'мар', 4: 'апр', 5: 'май', 6: 'июн',
    7: 'июл', 8: 'авг', 9: 'сен', 10: 'окт', 11: 'ноя', 12: 'дек',
}


@dataclass
class EmployeeFilters:
    period: str
    start_date: date
    end_date: date
    errors: List[str] = field(default_factory=list)

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def previous(self) -> 'EmployeeFilters':
        end = self.start_date - timedelta(days=1)
        return EmployeeFilters(period=self.period, start_date=end - timedelta(days=self.days - 1), end_date=end)

    def as_template(self) -> Dict[str, str]:
        return {
            'period': self.period,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
        }


def parse_filters(params) -> EmployeeFilters:
    """Быстрый период 90 / 180 / 365 дней (по умолчанию 90) или явные даты."""
    errors: List[str] = []
    today = timezone.localdate()

    def _parse(value: str, label: str) -> Optional[date]:
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            errors.append(f'Некорректная дата в поле «{label}»')
            return None

    start_raw = (params.get('start_date') or '').strip()
    end_raw = (params.get('end_date') or '').strip()
    if start_raw or end_raw:
        start = _parse(start_raw, 'С')
        end = _parse(end_raw, 'По') or today
        if start and start <= end:
            return EmployeeFilters(period='custom', start_date=start, end_date=end, errors=errors)
        if start and start > end:
            errors.append('Дата начала позже даты окончания')

    period = (params.get('period') or DEFAULT_PERIOD).strip()
    if period not in dict(PERIOD_CHOICES):
        period = DEFAULT_PERIOD
    return EmployeeFilters(
        period=period, start_date=today - timedelta(days=int(period) - 1), end_date=today, errors=errors,
    )


def _display_name(user: User) -> str:
    full_name = f"{(user.last_name or '').strip()} {(user.first_name or '').strip()}".strip()
    return full_name or user.username


def employee_colors(users: List[User]) -> Dict[int, str]:
    """Цвет закреплён за сотрудником (по порядку id), а не за местом в таблице."""
    ordered = sorted(users, key=lambda user: user.pk)
    return {
        user.pk: SERIES_COLORS[index] if index < len(SERIES_COLORS) else OTHER_SERIES_COLOR
        for index, user in enumerate(ordered)
    }


def _period_filter(prefix: str, filters: EmployeeFilters) -> Dict[str, date]:
    return {f'{prefix}__date__gte': filters.start_date, f'{prefix}__date__lte': filters.end_date}


def _bucket_key(day: date, weekly: bool) -> date:
    if weekly:
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _bucket_label(key: date, weekly: bool) -> str:
    if weekly:
        return f'{key:%d.%m}'
    return f'{MONTH_SHORT_RU[key.month]} {key:%y}'


def _bucket_keys(filters: EmployeeFilters, weekly: bool) -> List[date]:
    keys = []
    current = _bucket_key(filters.start_date, weekly)
    while current <= filters.end_date:
        keys.append(current)
        if weekly:
            current += timedelta(days=7)
        else:
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return keys


def _percent(numerator, denominator) -> Optional[Decimal]:
    if not denominator:
        return None
    return Decimal(numerator) / Decimal(denominator) * Decimal('100')


def _uploads(filters: EmployeeFilters) -> Dict[int, Dict]:
    """Заявки (объекты) и файлы по автору за период, плюс по неделям/месяцам."""
    stats: Dict[int, Dict] = defaultdict(lambda: {'requests': 0, 'files': set(), 'dates': []})
    rows = InsuranceRequest.objects.filter(
        created_by__isnull=False, **_period_filter('created_at', filters)
    ).values_list('pk', 'created_by_id', 'source_batch_id', 'created_at')
    for pk, user_id, batch_id, created_at in rows:
        item = stats[user_id]
        item['requests'] += 1
        item['files'].add(f'batch:{batch_id}' if batch_id else f'request:{pk}')
        item['dates'].append(timezone.localtime(created_at).date())
    return stats


def _offers(filters: EmployeeFilters) -> Counter:
    return Counter(
        InsuranceOffer.objects.filter(
            summary__request__created_by__isnull=False, **_period_filter('received_at', filters)
        ).values_list('summary__request__created_by_id', flat=True)
    )


def _status_actions(filters: EmployeeFilters) -> Dict[int, Counter]:
    """Смены статуса свода, сделанные сотрудником: собран, отправлен клиенту, акцепт, «не будет»."""
    summary_type = ContentType.objects.get_for_model(InsuranceSummary)
    actions: Dict[int, Counter] = defaultdict(Counter)
    for user_id, to_status in StatusEvent.objects.filter(
        content_type=summary_type, changed_by__isnull=False, **_period_filter('changed_at', filters)
    ).values_list('changed_by_id', 'to_status'):
        if to_status in ('ready', 'sent', 'completed_accepted', 'completed_rejected'):
            actions[user_id][to_status] += 1
    return actions


def _employees(user_ids) -> List[User]:
    return list(
        User.objects.filter(
            Q(is_active=True, groups__name=EMPLOYEE_GROUP) | Q(pk__in=list(user_ids))
        ).distinct()
    )


def build_load_block(filters: EmployeeFilters) -> Dict:
    """Блок «Нагрузка за период» (задача 4.2)."""
    uploads = _uploads(filters)
    offers = _offers(filters)
    actions = _status_actions(filters)
    previous_uploads = _uploads(filters.previous)

    users = _employees(set(uploads) | set(offers) | set(actions))
    colors = employee_colors(users)
    weeks = Decimal(filters.days) / Decimal(7)
    total_requests = sum(item['requests'] for item in uploads.values())

    rows = []
    for user in users:
        upload = uploads.get(user.pk, {'requests': 0, 'files': set()})
        user_actions = actions.get(user.pk, Counter())
        previous = previous_uploads.get(user.pk, {'requests': 0})['requests']
        requests_count = upload['requests']
        rows.append({
            'user_id': user.pk,
            'name': _display_name(user),
            'color': colors[user.pk],
            'requests': requests_count,
            'files': len(upload['files']),
            'share_pct': _percent(requests_count, total_requests),
            'per_week': (Decimal(requests_count) / weeks) if weeks else None,
            'offers': offers.get(user.pk, 0),
            'assembled': user_actions['ready'],
            'sent': user_actions['sent'],
            'accepted': user_actions['completed_accepted'],
            'rejected': user_actions['completed_rejected'],
            'previous_requests': previous,
            'change_pct': (_percent(requests_count - previous, previous) if previous else None),
            'is_reader': not (requests_count or offers.get(user.pk) or sum(user_actions.values())),
        })
    rows.sort(key=lambda row: (row['is_reader'], -row['requests'], -row['offers'], row['name']))

    weekly = filters.days <= 190
    keys = _bucket_keys(filters, weekly)
    series = []
    for row in rows:
        if row['is_reader'] or not row['requests']:
            continue
        per_bucket = Counter(_bucket_key(day, weekly) for day in uploads[row['user_id']]['dates'])
        series.append({'label': row['name'], 'color': row['color'], 'data': [per_bucket.get(key, 0) for key in keys]})

    totals = {
        'requests': total_requests,
        'files': sum(len(item['files']) for item in uploads.values()),
        'offers': sum(offers.values()),
        'assembled': sum(counter['ready'] for counter in actions.values()),
        'sent': sum(counter['sent'] for counter in actions.values()),
        'accepted': sum(counter['completed_accepted'] for counter in actions.values()),
        'rejected': sum(counter['completed_rejected'] for counter in actions.values()),
        'previous_requests': sum(item['requests'] for item in previous_uploads.values()),
        'per_week': (Decimal(total_requests) / weeks) if weeks else None,
    }
    totals['change_pct'] = _percent(totals['requests'] - totals['previous_requests'], totals['previous_requests'])

    return {
        'rows': rows,
        'totals': totals,
        'previous_period': {'start': filters.previous.start_date, 'end': filters.previous.end_date},
        'status_log_partial': filters.start_date < STATUS_LOG_START,
        'chart': {
            'granularity': 'week' if weekly else 'month',
            'labels': [_bucket_label(key, weekly) for key in keys],
            'series': series,
        },
    }


def build_payload(filters: EmployeeFilters) -> Dict:
    return {
        'filters': filters.as_template(),
        'period_choices': PERIOD_CHOICES,
        'load': build_load_block(filters),
    }

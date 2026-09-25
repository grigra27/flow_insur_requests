"""Дневной агрегат активности сотрудников из журналов easy-audit (UserDailyActivity).

Источники за день (по Europe/Moscow):
- LoginEvent — входы (login_type=0);
- RequestEvent — просмотры страниц (GET) и отправки форм (остальные методы), разделы;
- CRUDEvent — создания / изменения / удаления записей (кроме служебных обновлений User).

Активное время: все события дня сортируются, события с разрывом не больше
SESSION_GAP образуют сессию; длительность сессии = последнее − первое событие,
но не меньше SESSION_MIN (один просмотр страницы — тоже несколько минут работы).

RequestEvent хранится 1 день. День считается собранным «полностью», только если
самый ранний RequestEvent в журнале не позже начала этого дня. Если данных о
просмотрах за день уже нет, а строка ранее была собрана полностью — поля,
зависящие от просмотров, не перезаписываются (обновляются только входы и изменения).

docs/improvement_plans/analytics_redesign_2026_09.md, задача 4.1.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from summaries.models import UserDailyActivity

logger = logging.getLogger(__name__)

SESSION_GAP = timedelta(minutes=30)
SESSION_MIN = timedelta(minutes=5)

LOGIN = 0
CRUD_KINDS = {1: 'create', 2: 'update', 3: 'delete'}
# Обновления User — это last_login при входе, а не работа сотрудника.
CRUD_IGNORED_MODELS = {'user'}

SECTION_LABELS = {
    'upload': 'Загрузка заявок',
    'requests': 'Заявки',
    'summaries': 'Своды',
    'deals': 'Сделки',
    'analytics': 'Аналитика',
    'admin': 'Админка',
    'home': 'Главная и вход',
    'other': 'Прочее',
}


def section_for_url(url: str) -> str:
    path = (url or '').split('?', 1)[0]
    if path.startswith('/requests/upload'):
        return 'upload'
    if path.startswith('/requests/'):
        return 'requests'
    if path.startswith('/summaries/analytics/'):
        return 'analytics'
    if path.startswith('/summaries/deals/') or path.endswith('/deal-summary/'):
        return 'deals'
    if path.startswith('/summaries/'):
        return 'summaries'
    if path.startswith('/admin/'):
        return 'admin'
    if path in ('', '/') or path.startswith('/login/') or path.startswith('/logout/'):
        return 'home'
    return 'other'


def sessions_for(timestamps: Iterable[datetime]) -> Dict[str, int]:
    """Число сессий и активные минуты по отсортированным событиям."""
    ordered = sorted(timestamps)
    if not ordered:
        return {'sessions': 0, 'minutes': 0}
    sessions = 0
    total = timedelta()
    start = previous = ordered[0]
    for moment in ordered[1:]:
        if moment - previous > SESSION_GAP:
            sessions += 1
            total += max(previous - start, SESSION_MIN)
            start = moment
        previous = moment
    sessions += 1
    total += max(previous - start, SESSION_MIN)
    return {'sessions': sessions, 'minutes': int(total.total_seconds() // 60)}


def _day_bounds(day: date):
    tz = timezone.get_default_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def request_data_available(day: date) -> bool:
    from easyaudit.models import RequestEvent

    earliest = RequestEvent.objects.order_by('datetime').values_list('datetime', flat=True).first()
    if earliest is None:
        return False
    start, _ = _day_bounds(day)
    return earliest <= start


def aggregate_day(day: date) -> Dict[str, int]:
    """Пересобирает UserDailyActivity за день. Возвращает счётчики для отчёта."""
    from easyaudit.models import CRUDEvent, LoginEvent, RequestEvent

    start, end = _day_bounds(day)
    with_requests = request_data_available(day)

    timestamps: Dict[int, List[datetime]] = defaultdict(list)
    logins = Counter()
    for user_id, moment in LoginEvent.objects.filter(
        datetime__gte=start, datetime__lt=end, login_type=LOGIN, user__isnull=False,
    ).values_list('user_id', 'datetime'):
        logins[user_id] += 1
        timestamps[user_id].append(moment)

    crud_actions = Counter()
    crud_by_model: Dict[int, Dict[str, Dict[str, int]]] = defaultdict(dict)
    for user_id, event_type, model_name, moment in CRUDEvent.objects.filter(
        datetime__gte=start, datetime__lt=end, user__isnull=False,
    ).values_list('user_id', 'event_type', 'content_type__model', 'datetime'):
        if model_name in CRUD_IGNORED_MODELS:
            continue
        kind = CRUD_KINDS.get(event_type, 'update')
        counters = crud_by_model[user_id].setdefault(model_name, {'create': 0, 'update': 0, 'delete': 0})
        counters[kind] += 1
        crud_actions[user_id] += 1
        timestamps[user_id].append(moment)

    page_views = Counter()
    form_actions = Counter()
    sections: Dict[int, Counter] = defaultdict(Counter)
    request_timestamps: Dict[int, List[datetime]] = defaultdict(list)
    if with_requests:
        for user_id, method, url, moment in RequestEvent.objects.filter(
            datetime__gte=start, datetime__lt=end, user__isnull=False,
        ).values_list('user_id', 'method', 'url', 'datetime'):
            if (method or '').upper() == 'GET':
                page_views[user_id] += 1
            else:
                form_actions[user_id] += 1
            sections[user_id][section_for_url(url)] += 1
            request_timestamps[user_id].append(moment)

    user_ids = set(timestamps) | set(request_timestamps)
    existing = {row.user_id: row for row in UserDailyActivity.objects.filter(date=day, user_id__in=user_ids)}
    valid_user_ids = set(User.objects.filter(pk__in=user_ids).values_list('pk', flat=True))

    stats = Counter()
    with transaction.atomic():
        for user_id in sorted(valid_user_ids):
            row = existing.get(user_id) or UserDailyActivity(user_id=user_id, date=day)
            row.logins_count = logins[user_id]
            row.crud_actions = crud_actions[user_id]
            row.crud_by_model = crud_by_model.get(user_id, {})

            keep_request_fields = not with_requests and row.pk and row.has_request_data
            if keep_request_fields:
                stats['kept_request_fields'] += 1
            else:
                all_moments = timestamps[user_id] + request_timestamps[user_id]
                session_stats = sessions_for(all_moments)
                row.page_views = page_views[user_id]
                row.form_actions = form_actions[user_id]
                row.sections = dict(sections[user_id])
                row.first_seen_at = min(all_moments) if all_moments else None
                row.last_seen_at = max(all_moments) if all_moments else None
                row.sessions_count = session_stats['sessions']
                row.active_minutes = session_stats['minutes']
                row.has_request_data = with_requests
            stats['updated' if row.pk else 'created'] += 1
            row.save()

    stats['users'] = len(valid_user_ids)
    stats['with_request_data'] = int(with_requests)
    logger.info('aggregate_day %s: %s', day.isoformat(), dict(stats))
    return dict(stats)


def aggregate_range(first_day: date, last_day: date) -> List[Dict]:
    reports = []
    day = first_day
    while day <= last_day:
        reports.append({'date': day, **aggregate_day(day)})
        day += timedelta(days=1)
    return reports


def yesterday() -> date:
    return timezone.localdate() - timedelta(days=1)


def earliest_audit_day() -> Optional[date]:
    from easyaudit.models import CRUDEvent, LoginEvent

    candidates = [
        model.objects.order_by('datetime').values_list('datetime', flat=True).first()
        for model in (LoginEvent, CRUDEvent)
    ]
    candidates = [value for value in candidates if value is not None]
    if not candidates:
        return None
    return timezone.localtime(min(candidates)).date()

"""Сервис аналитики по сотрудникам (Django-юзерам, загружающим заявки).

Phase 1: filters, KPI, табличные метрики, time-to-*, charts, funnel, базовые алерты.
Phase 2: качество данных, портфель, heatmap-связи, аномалии цикла, просадка объёма,
композитный quality-score.

Реализация компромиссная: для прошлых данных нет точного таймстемпа смены статуса,
поэтому стадии funnel считаются по снимку (current status + наличие summary).
Будущие данные пишутся в StatusEvent — на них метрики time-to-* станут точными.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Iterable

from django.contrib.auth.models import User
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from ..models import InsuranceSummary

# --- Константы --------------------------------------------------------------

DEFAULT_PERIOD_DAYS = 365
PERIOD_CHOICES = ('all', '30', '90', '365', 'custom')

QUALITY_SCORE_WEIGHTS: dict[str, float] = {
    'completeness': 0.40,
    'win_rate': 0.30,
    'speed': 0.20,
    'volume': 0.10,
}

# Активные статусы (не завершённые) для подсчёта backlog’а.
ACTIVE_REQUEST_STATUSES = {'uploaded', 'email_generated'}
ACTIVE_SUMMARY_STATUSES = {'collecting', 'ready', 'sent'}
TERMINAL_SUMMARY_STATUSES = {'completed_accepted', 'completed_rejected'}

# Пороги алертов
NO_ACTIVITY_DAYS_DEFAULT = 14
STUCK_SUMMARY_DAYS_DEFAULT = 30
VOLUME_DROP_THRESHOLD_PCT = -30.0  # % изменения объёма к прошлому окну: алерт ≤ −30%
CYCLE_OUTLIER_FACTOR = 1.5  # threshold = factor * team_p75 (устойчиво к малым выборкам)
CYCLE_OUTLIER_FLOOR_HOURS = 7 * 24  # пол threshold’а — 7 дней, чтобы не ловить мелочёвку
EDIT_THRESHOLD_SECONDS = 60  # updated_at - created_at > порог → заявка считается отредактированной

# Группы полей для completeness-score
FIELDS_BASE = (
    'dfa_number', 'branch', 'manager_name', 'vehicle_info',
    'notes', 'insurance_period', 'response_deadline',
)
FIELDS_CASCO = (
    'key_completeness', 'pts_psm', 'creditor_bank',
    'usage_purposes', 'telematics_complex',
    'manufacturing_year', 'asset_status',
)
FIELDS_PROPERTY = ('insurance_territory',)
CASCO_INSURANCE_TYPES = {'КАСКО', 'страхование спецтехники'}
PROPERTY_INSURANCE_TYPES = {'страхование имущества'}

HEATMAP_TOP_LIMIT = 8  # сколько значений измерения показывать в heatmap’е
HEATMAP_OUTLIER_LIMIT = 50


# --- Парсер фильтров --------------------------------------------------------


def parse_filters(get_params) -> dict[str, Any]:
    """Разбирает request.GET. По умолчанию — период 365 дней.

    Возвращает dict, чтобы было легко передавать в шаблон без распаковки.
    """
    errors: list[str] = []
    period = (get_params.get('period') or str(DEFAULT_PERIOD_DAYS)).strip().lower()
    if period not in PERIOD_CHOICES:
        period = str(DEFAULT_PERIOD_DAYS)

    start_date_str = (get_params.get('start_date') or '').strip()
    end_date_str = (get_params.get('end_date') or '').strip()

    def _parse_date(value: str, field: str) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            errors.append(f'Некорректная дата в поле «{field}»')
            return None

    start_date: date | None = None
    end_date: date | None = None

    if start_date_str or end_date_str:
        start_date = _parse_date(start_date_str, 'Дата с')
        end_date = _parse_date(end_date_str, 'Дата по')
        period = 'custom'
    elif period in {'30', '90', '365'}:
        days = int(period)
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days - 1)
    elif period == 'all':
        start_date = None
        end_date = None

    if start_date and end_date and start_date > end_date:
        errors.append('Дата начала позже даты окончания')
        start_date = end_date = None
        period = 'all'

    user_ids: list[int] = []
    for raw in get_params.getlist('user_ids') if hasattr(get_params, 'getlist') else []:
        for token in str(raw).split(','):
            token = token.strip()
            if not token:
                continue
            try:
                user_ids.append(int(token))
            except ValueError:
                errors.append(f'Некорректный id сотрудника: {token!r}')

    return {
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'start_date_str': start_date.isoformat() if start_date else '',
        'end_date_str': end_date.isoformat() if end_date else '',
        'user_ids': user_ids,
        'branch': (get_params.get('branch') or '').strip(),
        'insurance_type': (get_params.get('insurance_type') or '').strip(),
        'deal_status': (get_params.get('deal_status') or '').strip(),
        'include_unassigned': (get_params.get('include_unassigned') or '1').strip() != '0',
        'errors': errors,
    }


# --- Helpers ----------------------------------------------------------------


def _apply_window(qs: QuerySet, field: str, filters: dict) -> QuerySet:
    if filters['start_date']:
        qs = qs.filter(**{f'{field}__date__gte': filters['start_date']})
    if filters['end_date']:
        qs = qs.filter(**{f'{field}__date__lte': filters['end_date']})
    return qs


def _build_request_qs(filters: dict) -> QuerySet:
    qs = InsuranceRequest.objects.select_related('created_by')
    qs = _apply_window(qs, 'created_at', filters)
    if filters['branch']:
        qs = qs.filter(branch=filters['branch'])
    if filters['insurance_type']:
        qs = qs.filter(insurance_type=filters['insurance_type'])
    if filters['deal_status']:
        qs = qs.filter(deal_status=filters['deal_status'])
    if filters['user_ids']:
        if filters['include_unassigned']:
            qs = qs.filter(Q(created_by_id__in=filters['user_ids']) | Q(created_by__isnull=True))
        else:
            qs = qs.filter(created_by_id__in=filters['user_ids'])
    elif not filters['include_unassigned']:
        qs = qs.filter(created_by__isnull=False)
    return qs


def _build_summary_qs(filters: dict) -> QuerySet:
    """Своды, чьи заявки попадают в окно и фильтры."""
    qs = InsuranceSummary.objects.select_related('request', 'request__created_by').prefetch_related('offers')
    request_ids = list(_build_request_qs(filters).values_list('id', flat=True))
    return qs.filter(request_id__in=request_ids)


def _user_display(user: User | None) -> str:
    if user is None:
        return 'Без автора'
    full = (user.get_full_name() or '').strip()
    return full or user.username


def _hours_between(start, end) -> float | None:
    if not start or not end:
        return None
    delta = end - start
    return delta.total_seconds() / 3600.0


def _avg(values: Iterable[float | None]) -> float | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _median(values: Iterable[float | None]) -> float | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return float(median(cleaned))


def _percentile(values: list[float], q: float) -> float | None:
    """Линейная интерполяция p-квантили. q ∈ [0, 1]."""
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_v = sorted(values)
    pos = q * (len(sorted_v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_v) - 1)
    frac = pos - lo
    return float(sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * frac)


def _is_field_filled(value) -> bool:
    """Поле считается заполненным, если есть непустое значение (без учёта пробелов)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool):
        # Булевы поля «заполнены» всегда — это часть схемы.
        return True
    return True


def _is_inn_valid(inn: str) -> bool:
    """Проверка длины ИНН: 10 (юрлицо) или 12 (ИП/физлицо)."""
    if not inn:
        return False
    cleaned = inn.strip()
    return len(cleaned) in (10, 12) and cleaned.isdigit()


def _completeness_for_request(req: InsuranceRequest) -> dict[str, Any]:
    """Возвращает заполненность полей для одной заявки.

    Возвращает:
        {
            'base_filled': int, 'base_total': int,
            'casco_filled': int|None, 'casco_total': int|None,  # None если не КАСКО
            'property_filled': int|None, 'property_total': int|None,
            'inn_valid': bool,
            'is_other_type': bool,
            'edited_after_create': bool,
        }
    """
    base_filled = sum(1 for f in FIELDS_BASE if _is_field_filled(getattr(req, f, None)))
    casco_filled = casco_total = None
    property_filled = property_total = None
    if req.insurance_type in CASCO_INSURANCE_TYPES:
        casco_filled = sum(1 for f in FIELDS_CASCO if _is_field_filled(getattr(req, f, None)))
        casco_total = len(FIELDS_CASCO)
    if req.insurance_type in PROPERTY_INSURANCE_TYPES:
        property_filled = sum(1 for f in FIELDS_PROPERTY if _is_field_filled(getattr(req, f, None)))
        property_total = len(FIELDS_PROPERTY)

    edited = False
    if req.created_at and req.updated_at:
        delta = (req.updated_at - req.created_at).total_seconds()
        edited = delta > EDIT_THRESHOLD_SECONDS

    return {
        'base_filled': base_filled,
        'base_total': len(FIELDS_BASE),
        'casco_filled': casco_filled,
        'casco_total': casco_total,
        'property_filled': property_filled,
        'property_total': property_total,
        'inn_valid': _is_inn_valid(req.inn),
        'is_other_type': req.insurance_type == 'другое',
        'edited_after_create': edited,
    }


def _aggregate_completeness(requests: list[InsuranceRequest]) -> dict[str, Any]:
    """Агрегирует completeness-метрики по списку заявок одного сотрудника."""
    if not requests:
        return {
            'base_pct': None, 'casco_pct': None, 'property_pct': None,
            'overall_pct': None,
            'inn_invalid_count': 0, 'inn_invalid_pct': None,
            'other_type_count': 0, 'other_type_pct': None,
            'edited_count': 0, 'edited_pct': None,
        }

    base_filled = base_total = 0
    casco_filled = casco_total = 0
    property_filled = property_total = 0
    inn_invalid = 0
    other_type = 0
    edited = 0

    for req in requests:
        c = _completeness_for_request(req)
        base_filled += c['base_filled']
        base_total += c['base_total']
        if c['casco_total']:
            casco_filled += c['casco_filled']
            casco_total += c['casco_total']
        if c['property_total']:
            property_filled += c['property_filled']
            property_total += c['property_total']
        if not c['inn_valid']:
            inn_invalid += 1
        if c['is_other_type']:
            other_type += 1
        if c['edited_after_create']:
            edited += 1

    base_pct = base_filled / base_total * 100 if base_total else None
    casco_pct = casco_filled / casco_total * 100 if casco_total else None
    property_pct = property_filled / property_total * 100 if property_total else None

    # Общий процент — среднее по доступным группам
    available = [pct for pct in (base_pct, casco_pct, property_pct) if pct is not None]
    overall_pct = sum(available) / len(available) if available else None

    n = len(requests)
    return {
        'base_pct': base_pct,
        'casco_pct': casco_pct,
        'property_pct': property_pct,
        'overall_pct': overall_pct,
        'inn_invalid_count': inn_invalid,
        'inn_invalid_pct': inn_invalid / n * 100,
        'other_type_count': other_type,
        'other_type_pct': other_type / n * 100,
        'edited_count': edited,
        'edited_pct': edited / n * 100,
    }


def _portfolio_for_user(requests: list[InsuranceRequest]) -> dict[str, Any]:
    """Распределение по типу страхования, deal_status и булевым флагам."""
    if not requests:
        return {
            'by_insurance_type': {},
            'prolongation_pct': None, 'new_deal_pct': None,
            'flag_pct': {},
        }

    by_type: dict[str, int] = defaultdict(int)
    new_count = prolong_count = 0
    flag_counters = {
        'has_franchise': 0, 'has_installment': 0,
        'has_autostart': 0, 'has_casco_ce': 0,
        'has_transportation': 0, 'has_construction_work': 0,
    }
    n = len(requests)
    for req in requests:
        by_type[req.insurance_type or 'не указан'] += 1
        if req.deal_status == 'prolongation':
            prolong_count += 1
        else:
            new_count += 1
        for flag in flag_counters:
            if getattr(req, flag, False):
                flag_counters[flag] += 1

    return {
        'by_insurance_type': dict(by_type),
        'new_deal_pct': new_count / n * 100,
        'prolongation_pct': prolong_count / n * 100,
        'flag_pct': {k: v / n * 100 for k, v in flag_counters.items()},
    }


def _accepted_premium(summary: InsuranceSummary) -> Decimal:
    """Σ премии accepted-свода по выбранной СК и варианту франшизы."""
    if summary.status != 'completed_accepted' or not summary.selected_company:
        return Decimal('0')
    variant = summary.selected_franchise_variant or 1
    total = Decimal('0')
    for offer in summary.offers.all():
        if not offer.is_valid or offer.company_name != summary.selected_company:
            continue
        premium = (
            offer.premium_with_franchise_2
            if variant == 2 and offer.premium_with_franchise_2 is not None
            else offer.premium_with_franchise_1
        )
        if premium is not None:
            total += premium
    return total


def _accepted_sum(summary: InsuranceSummary) -> Decimal:
    """Σ страховой суммы accepted-свода (по offers выбранной СК)."""
    if summary.status != 'completed_accepted' or not summary.selected_company:
        return Decimal('0')
    total = Decimal('0')
    for offer in summary.offers.all():
        if not offer.is_valid or offer.company_name != summary.selected_company:
            continue
        if offer.insurance_sum is not None:
            total += offer.insurance_sum
    return total


# --- Funnel / Time-to-* per summary -----------------------------------------


def _summary_time_to_metrics(summary: InsuranceSummary) -> dict[str, float | None]:
    """Считает доступные time-to-* интервалы (в часах)."""
    upload_at = summary.request.created_at if summary.request else None
    summary_at = summary.created_at
    sent_at = summary.sent_to_client_at
    completed_at = summary.completed_at if summary.status == 'completed_accepted' else None

    first_offer_at = None
    offers = list(summary.offers.all())
    if offers:
        valid_dates = [o.received_at for o in offers if o.received_at]
        if valid_dates:
            first_offer_at = min(valid_dates)

    return {
        'upload_to_summary_h': _hours_between(upload_at, summary_at),
        'summary_to_first_offer_h': _hours_between(summary_at, first_offer_at),
        'summary_to_sent_h': _hours_between(summary_at, sent_at),
        'sent_to_completed_h': _hours_between(sent_at, completed_at),
        'total_cycle_h': _hours_between(upload_at, completed_at),
    }


# --- Charts -----------------------------------------------------------------


def _daily_counts(request_qs: QuerySet, filters: dict) -> dict[str, list]:
    """Возвращает labels (даты) и series (по сотрудникам) для линии загрузок по дням."""
    if filters['start_date'] and filters['end_date']:
        start, end = filters['start_date'], filters['end_date']
    else:
        # period='all' и нет дат: показываем последние 90 дней.
        end = timezone.localdate()
        start = end - timedelta(days=89)

    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)

    rows = list(
        request_qs.values('created_at__date', 'created_by_id', 'created_by__username',
                          'created_by__first_name', 'created_by__last_name')
        .annotate(c=Count('id'))
    )
    # series_key → label
    series_keys: dict[str, str] = {}
    series_data: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if row['created_by_id'] is None:
            key = '__unassigned__'
            label = 'Без автора'
        else:
            key = f"u{row['created_by_id']}"
            full = (f"{row['created_by__first_name']} {row['created_by__last_name']}").strip()
            label = full or row['created_by__username'] or f'user#{row["created_by_id"]}'
        series_keys[key] = label
        series_data[key][row['created_at__date']] += row['c']

    series = []
    for key, label in sorted(series_keys.items(), key=lambda kv: kv[1].lower()):
        series.append({
            'key': key,
            'label': label,
            'data': [series_data[key].get(d, 0) for d in days],
        })

    cumulative_total = []
    running = 0
    for d in days:
        running += sum(series_data[k].get(d, 0) for k in series_data)
        cumulative_total.append(running)

    return {
        'labels': [d.isoformat() for d in days],
        'series': series,
        'cumulative_total': cumulative_total,
    }


def _weekly_stacked(request_qs: QuerySet) -> dict[str, list]:
    rows = list(
        request_qs.values('created_at__date', 'created_by_id', 'created_by__username',
                          'created_by__first_name', 'created_by__last_name')
    )
    if not rows:
        return {'labels': [], 'series': []}

    weeks: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    series_labels: dict[str, str] = {}
    week_set: set[str] = set()

    for row in rows:
        d = row['created_at__date']
        # Неделя как ISO «YYYY-Www»
        iso_year, iso_week, _ = d.isocalendar()
        week_key = f'{iso_year}-W{iso_week:02d}'
        week_set.add(week_key)
        if row['created_by_id'] is None:
            key = '__unassigned__'
            label = 'Без автора'
        else:
            key = f"u{row['created_by_id']}"
            full = (f"{row['created_by__first_name']} {row['created_by__last_name']}").strip()
            label = full or row['created_by__username'] or f'user#{row["created_by_id"]}'
        series_labels[key] = label
        weeks[week_key][key] += 1

    labels = sorted(week_set)
    series = []
    for key, label in sorted(series_labels.items(), key=lambda kv: kv[1].lower()):
        series.append({
            'key': key,
            'label': label,
            'data': [weeks[w].get(key, 0) for w in labels],
        })
    return {'labels': labels, 'series': series}


# --- Per-manager rows -------------------------------------------------------


def _build_manager_rows(filters: dict) -> tuple[list[dict], dict]:
    """Возвращает (rows, team_aggregate). Каждая строка — метрики на сотрудника."""
    request_qs = _build_request_qs(filters)
    summary_qs = _build_summary_qs(filters)

    # Группируем заявки по created_by
    requests_by_user: dict[int | None, list[InsuranceRequest]] = defaultdict(list)
    for req in request_qs:
        requests_by_user[req.created_by_id].append(req)

    summaries_by_user: dict[int | None, list[InsuranceSummary]] = defaultdict(list)
    for s in summary_qs:
        summaries_by_user[s.request.created_by_id if s.request else None].append(s)

    rows: list[dict] = []
    now = timezone.now()

    for user_id, requests in requests_by_user.items():
        user = requests[0].created_by if requests and requests[0].created_by_id else None
        summaries = summaries_by_user.get(user_id, [])

        accepted = [s for s in summaries if s.status == 'completed_accepted']
        rejected = [s for s in summaries if s.status == 'completed_rejected']
        completed = accepted + rejected
        active_summaries = [s for s in summaries if s.status in ACTIVE_SUMMARY_STATUSES]
        active_requests = [r for r in requests if r.status in ACTIVE_REQUEST_STATUSES]

        win_rate = (len(accepted) / len(completed) * 100) if completed else None

        premium_total = sum((_accepted_premium(s) for s in accepted), Decimal('0'))
        sum_total = sum((_accepted_sum(s) for s in accepted), Decimal('0'))
        avg_ticket = (premium_total / len(accepted)) if accepted else Decimal('0')

        # Time-to-*
        per_summary_metrics = [_summary_time_to_metrics(s) for s in summaries]
        cycle_values = [m['total_cycle_h'] for m in per_summary_metrics if m['total_cycle_h'] is not None]

        time_to = {
            'upload_to_summary_h': _avg(m['upload_to_summary_h'] for m in per_summary_metrics),
            'summary_to_first_offer_h': _avg(m['summary_to_first_offer_h'] for m in per_summary_metrics),
            'summary_to_sent_h': _avg(m['summary_to_sent_h'] for m in per_summary_metrics),
            'sent_to_completed_h': _avg(m['sent_to_completed_h'] for m in per_summary_metrics),
            'avg_cycle_h': _avg(cycle_values),
            'p50_cycle_h': _median(cycle_values),
            'p90_cycle_h': _percentile(cycle_values, 0.9),
        }

        # Просрочка по response_deadline (по активным заявкам)
        overdue_count = sum(
            1 for r in requests
            if r.response_deadline and r.response_deadline < now
            and r.status != 'emails_sent'
        )

        last_activity = max((r.created_at for r in requests), default=None)

        completeness = _aggregate_completeness(requests)
        portfolio = _portfolio_for_user(requests)

        rows.append({
            'user_id': user_id,
            'display': _user_display(user),
            'username': user.username if user else None,
            'is_unassigned': user_id is None,
            'requests_total': len(requests),
            'summaries_total': len(summaries),
            'accepted': len(accepted),
            'rejected': len(rejected),
            'win_rate': win_rate,
            'premium_total': premium_total,
            'sum_total': sum_total,
            'avg_ticket': avg_ticket,
            'time_to': time_to,
            'active_requests': len(active_requests),
            'active_summaries': len(active_summaries),
            'active_total': len(active_requests) + len(active_summaries),
            'overdue_count': overdue_count,
            'last_activity': last_activity,
            'completeness': completeness,
            'portfolio': portfolio,
        })

    # Сортируем: сначала реальные сотрудники по объёму, в конце «Без автора»
    rows.sort(key=lambda r: (r['is_unassigned'], -r['requests_total'], r['display']))

    # Команда (агрегация)
    real_rows = [r for r in rows if not r['is_unassigned']]
    all_requests = [req for reqs in requests_by_user.values() for req in reqs]

    team = {
        'requests_total': sum(r['requests_total'] for r in rows),
        'summaries_total': sum(r['summaries_total'] for r in rows),
        'accepted': sum(r['accepted'] for r in rows),
        'rejected': sum(r['rejected'] for r in rows),
        'premium_total': sum((r['premium_total'] for r in rows), Decimal('0')),
        'sum_total': sum((r['sum_total'] for r in rows), Decimal('0')),
        'active_total': sum(r['active_total'] for r in rows),
        'overdue_count': sum(r['overdue_count'] for r in rows),
        'managers_count': sum(1 for r in rows if not r['is_unassigned']),
        'completeness': _aggregate_completeness(all_requests),
        'portfolio': _portfolio_for_user(all_requests),
    }
    completed = team['accepted'] + team['rejected']
    team['win_rate'] = (team['accepted'] / completed * 100) if completed else None
    team['avg_ticket'] = (team['premium_total'] / team['accepted']) if team['accepted'] else Decimal('0')

    # Composite quality-score (нужны командные ориентиры)
    team_max_volume = max((r['requests_total'] for r in real_rows), default=0)
    cycle_values = [r['time_to']['avg_cycle_h'] for r in real_rows if r['time_to']['avg_cycle_h']]
    team_best_cycle = min(cycle_values) if cycle_values else None
    for row in rows:
        row['quality_score'] = _compute_quality_score(row, team_max_volume, team_best_cycle)
    if team_max_volume > 0:
        # Команда — невзвешенное среднее по реальным сотрудникам
        scores = [r['quality_score'] for r in real_rows if r['quality_score'] is not None]
        team['quality_score'] = sum(scores) / len(scores) if scores else None
    else:
        team['quality_score'] = None

    return rows, team


def _compute_quality_score(row: dict, team_max_volume: int, team_best_cycle: float | None) -> float | None:
    """Composite-score 0..100 по 4 компонентам (см. план §«Решения», п.4)."""
    completeness = row['completeness']['overall_pct']
    if completeness is None:
        completeness = 0.0
    win_rate = row['win_rate'] or 0.0
    avg_cycle = row['time_to']['avg_cycle_h']
    if avg_cycle and team_best_cycle and avg_cycle > 0:
        speed = min(100.0, 100.0 * team_best_cycle / avg_cycle)
    else:
        speed = 0.0
    if team_max_volume > 0:
        volume = min(100.0, 100.0 * row['requests_total'] / team_max_volume)
    else:
        volume = 0.0

    score = (
        QUALITY_SCORE_WEIGHTS['completeness'] * completeness
        + QUALITY_SCORE_WEIGHTS['win_rate'] * win_rate
        + QUALITY_SCORE_WEIGHTS['speed'] * speed
        + QUALITY_SCORE_WEIGHTS['volume'] * volume
    )
    return round(max(0.0, min(100.0, score)), 1)


# --- Funnel -----------------------------------------------------------------


def _build_funnel(filters: dict) -> dict[str, Any]:
    request_qs = _build_request_qs(filters)
    summary_qs = _build_summary_qs(filters)

    total_requests = request_qs.count()
    request_with_summary = request_qs.filter(summary__isnull=False).count()
    summaries_ready_plus = summary_qs.filter(
        status__in=['ready', 'sent', 'completed_accepted', 'completed_rejected']
    ).count()
    summaries_sent_plus = summary_qs.filter(
        status__in=['sent', 'completed_accepted', 'completed_rejected']
    ).count()
    summaries_completed = summary_qs.filter(status__in=list(TERMINAL_SUMMARY_STATUSES)).count()
    summaries_accepted = summary_qs.filter(status='completed_accepted').count()

    stages = [
        {'key': 'uploaded', 'label': 'Загружено', 'count': total_requests},
        {'key': 'sent_emails', 'label': 'Письма отправлены', 'count': request_with_summary},
        {'key': 'ready', 'label': 'Свод готов', 'count': summaries_ready_plus},
        {'key': 'sent_to_client', 'label': 'Отправлен клиенту', 'count': summaries_sent_plus},
        {'key': 'completed', 'label': 'Сделка закрыта', 'count': summaries_completed},
        {'key': 'accepted', 'label': 'Акцепт', 'count': summaries_accepted},
    ]
    # Доля от первой стадии и drop-off от предыдущей
    base = max(stages[0]['count'], 1)
    prev = stages[0]['count']
    for stage in stages:
        stage['pct_of_top'] = round(stage['count'] / base * 100, 1)
        stage['drop_off'] = max(prev - stage['count'], 0)
        prev = stage['count']

    return {
        'stages': stages,
        'win_rate': round(summaries_accepted / summaries_completed * 100, 1) if summaries_completed else None,
    }


# --- Heatmaps ---------------------------------------------------------------


def _build_heatmap(
    pairs: Iterable[tuple[str, str]],
    *,
    top_limit: int = HEATMAP_TOP_LIMIT,
) -> dict[str, Any]:
    """Принимает итератор пар (manager_label, dim_value) и собирает heatmap.

    Возвращает {rows, columns, cells, max_value}.
    rows: [{'label': str, 'total': int, 'cells': [int, ...]}],
    columns: [str, ...] (топ-N по сумме, остальное в «Прочее»).
    """
    grid: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    column_totals: dict[str, int] = defaultdict(int)
    row_labels: set[str] = set()

    for manager_label, dim_value in pairs:
        if not dim_value:
            dim_value = 'не указано'
        grid[manager_label][dim_value] += 1
        column_totals[dim_value] += 1
        row_labels.add(manager_label)

    if not grid:
        return {'rows': [], 'columns': [], 'cells': [], 'max_value': 0}

    sorted_cols = sorted(column_totals.items(), key=lambda kv: (-kv[1], kv[0]))
    head = [c for c, _ in sorted_cols[:top_limit]]
    tail = [c for c, _ in sorted_cols[top_limit:]]

    columns = list(head)
    has_other = bool(tail)
    if has_other:
        columns.append('Прочее')

    rows = []
    max_value = 0
    for label in sorted(row_labels, key=str.lower):
        cells = []
        for col in head:
            value = grid[label].get(col, 0)
            cells.append(value)
            if value > max_value:
                max_value = value
        if has_other:
            other_sum = sum(grid[label].get(c, 0) for c in tail)
            cells.append(other_sum)
            if other_sum > max_value:
                max_value = other_sum
        rows.append({'label': label, 'total': sum(cells), 'cells': cells})

    return {'rows': rows, 'columns': columns, 'cells': len(rows) * len(columns), 'max_value': max_value}


def _compute_heatmaps(filters: dict) -> dict[str, dict]:
    """4 heatmap’а: manager × branch / insurance_type / alliance / selected_company."""
    request_qs = _build_request_qs(filters).select_related('created_by')
    summary_qs = _build_summary_qs(filters).select_related('request', 'request__created_by')

    pairs_branch = (
        (_user_display(r.created_by), r.branch)
        for r in request_qs
    )
    pairs_type = (
        (_user_display(r.created_by), r.insurance_type)
        for r in request_qs
    )
    pairs_alliance = (
        (_user_display(r.created_by), r.manager_name)
        for r in request_qs if r.manager_name
    )
    pairs_company = (
        (
            _user_display(s.request.created_by) if s.request else 'Без автора',
            s.selected_company,
        )
        for s in summary_qs
        if s.status == 'completed_accepted' and s.selected_company
    )

    return {
        'branch': _build_heatmap(pairs_branch),
        'insurance_type': _build_heatmap(pairs_type),
        'alliance_manager': _build_heatmap(pairs_alliance),
        'selected_company': _build_heatmap(pairs_company),
    }


# --- Алерты -----------------------------------------------------------------


def build_alerts(filters: dict, *,
                 no_activity_days: int = NO_ACTIVITY_DAYS_DEFAULT,
                 stuck_days: int = STUCK_SUMMARY_DAYS_DEFAULT) -> dict[str, list]:
    now = timezone.now()
    no_activity_threshold = now - timedelta(days=no_activity_days)
    stuck_threshold = now - timedelta(days=stuck_days)

    # Просроченные active-заявки (response_deadline < now и статус ещё не emails_sent)
    overdue_qs = (
        _build_request_qs(filters)
        .filter(response_deadline__lt=now)
        .exclude(status='emails_sent')
        .order_by('response_deadline')
    )
    overdue = [
        {
            'request_id': r.id,
            'dfa_number': r.dfa_number or f'#{r.id}',
            'client_name': r.client_name,
            'manager': _user_display(r.created_by),
            'manager_id': r.created_by_id,
            'deadline': r.response_deadline,
            'overdue_hours': round((now - r.response_deadline).total_seconds() / 3600, 1),
            'status': r.get_status_display(),
        }
        for r in overdue_qs[:50]
    ]

    # Зависшие сделки: активные своды, у которых updated_at старше порога.
    stuck_qs = (
        _build_summary_qs(filters)
        .filter(status__in=list(ACTIVE_SUMMARY_STATUSES))
        .filter(updated_at__lt=stuck_threshold)
        .order_by('updated_at')
    )
    stuck = [
        {
            'summary_id': s.id,
            'request_id': s.request_id,
            'dfa_number': (s.request.dfa_number if s.request else None) or f'#{s.id}',
            'client_name': s.request.client_name if s.request else '',
            'manager': _user_display(s.request.created_by) if s.request else 'Без автора',
            'manager_id': s.request.created_by_id if s.request else None,
            'days_inactive': (now - s.updated_at).days,
            'status': s.get_status_display(),
        }
        for s in stuck_qs[:50]
    ]

    # Сотрудники без активности: были заявки в окне, но ни одной свежее threshold.
    request_qs = _build_request_qs(filters)
    user_ids = [
        uid for uid in request_qs.values_list('created_by_id', flat=True).distinct()
        if uid is not None
    ]
    inactive_users = []
    for user_id in user_ids:
        recent = request_qs.filter(
            created_by_id=user_id, created_at__gt=no_activity_threshold
        ).exists()
        if recent:
            continue
        user = User.objects.filter(pk=user_id).first()
        if not user:
            continue
        last_req = (
            InsuranceRequest.objects.filter(created_by_id=user_id)
            .order_by('-created_at').first()
        )
        inactive_users.append({
            'user_id': user_id,
            'display': _user_display(user),
            'last_activity': last_req.created_at if last_req else None,
        })

    volume_drop = _volume_drop_alert(filters)
    cycle_outliers = _cycle_outlier_alert(filters)

    return {
        'overdue': overdue,
        'overdue_total': overdue_qs.count(),
        'stuck': stuck,
        'stuck_total': stuck_qs.count(),
        'inactive_users': inactive_users,
        'no_activity_days': no_activity_days,
        'stuck_days': stuck_days,
        'volume_drop': volume_drop,
        'cycle_outliers': cycle_outliers,
    }


def _volume_drop_alert(filters: dict) -> dict[str, Any]:
    """Сравнивает объём текущего окна с предыдущим равной длины.

    Алерт срабатывает на сотрудника, если падение ≤ VOLUME_DROP_THRESHOLD_PCT.
    Не работает для period='all' (нет смысла сравнивать с «прошлым всем временем»).
    """
    if not (filters['start_date'] and filters['end_date']):
        return {'enabled': False, 'reason': 'Период «всё время» — сравнение недоступно', 'flagged': []}

    span_days = (filters['end_date'] - filters['start_date']).days + 1
    prev_end = filters['start_date'] - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span_days - 1)

    prev_filters = dict(filters)
    prev_filters['start_date'] = prev_start
    prev_filters['end_date'] = prev_end

    cur_qs = _build_request_qs(filters)
    prev_qs = _build_request_qs(prev_filters)

    cur_counts: dict[int | None, int] = defaultdict(int)
    for uid, c in cur_qs.values_list('created_by_id').annotate(c=Count('id')):
        cur_counts[uid] = c
    prev_counts: dict[int | None, int] = defaultdict(int)
    for uid, c in prev_qs.values_list('created_by_id').annotate(c=Count('id')):
        prev_counts[uid] = c

    flagged = []
    for uid in set(list(cur_counts.keys()) + list(prev_counts.keys())):
        if uid is None:
            continue
        prev = prev_counts.get(uid, 0)
        cur = cur_counts.get(uid, 0)
        if prev < 3:  # слишком мало данных для сравнения
            continue
        change_pct = (cur - prev) / prev * 100
        if change_pct <= VOLUME_DROP_THRESHOLD_PCT:
            user = User.objects.filter(pk=uid).first()
            flagged.append({
                'user_id': uid,
                'display': _user_display(user),
                'previous_count': prev,
                'current_count': cur,
                'change_pct': round(change_pct, 1),
            })

    flagged.sort(key=lambda x: x['change_pct'])
    return {
        'enabled': True,
        'threshold_pct': VOLUME_DROP_THRESHOLD_PCT,
        'previous_window': {'start': prev_start, 'end': prev_end},
        'flagged': flagged,
    }


def _cycle_outlier_alert(filters: dict) -> dict[str, Any]:
    """Аномально длинные сделки. Threshold = max(p75 × factor, 7 дней).

    p75 устойчив к одиночным выбросам, в отличие от p90. Floor — чтобы при
    очень коротких циклах не ловить тривиальные отклонения.
    """
    summary_qs = (
        _build_summary_qs(filters)
        .filter(status='completed_accepted')
        .select_related('request', 'request__created_by')
        .prefetch_related('offers')
    )

    cycles = []
    per_summary = []
    for s in summary_qs:
        cycle = _hours_between(
            s.request.created_at if s.request else None,
            s.completed_at,
        )
        if cycle is None:
            continue
        cycles.append(cycle)
        per_summary.append((s, cycle))

    if not cycles:
        return {'threshold_h': None, 'team_baseline_h': None, 'outliers': []}

    team_p75 = _percentile(cycles, 0.75)
    if team_p75 is None or team_p75 <= 0:
        return {'threshold_h': None, 'team_baseline_h': None, 'outliers': []}

    threshold = max(team_p75 * CYCLE_OUTLIER_FACTOR, CYCLE_OUTLIER_FLOOR_HOURS)
    outliers = []
    for s, cycle in per_summary:
        if cycle <= threshold:
            continue
        outliers.append({
            'summary_id': s.id,
            'request_id': s.request_id,
            'dfa_number': (s.request.dfa_number if s.request else None) or f'#{s.id}',
            'client_name': s.request.client_name if s.request else '',
            'manager': _user_display(s.request.created_by) if s.request else 'Без автора',
            'manager_id': s.request.created_by_id if s.request else None,
            'cycle_hours': round(cycle, 1),
            'cycle_days': round(cycle / 24, 1),
        })
    outliers.sort(key=lambda x: -x['cycle_hours'])
    return {
        'threshold_h': round(threshold, 1),
        'team_baseline_h': round(team_p75, 1),
        'outliers': outliers[:HEATMAP_OUTLIER_LIMIT],
    }


# --- Available filter values ------------------------------------------------


def _available_filters() -> dict[str, list]:
    branches = list(
        InsuranceRequest.objects
        .exclude(branch__isnull=True).exclude(branch__exact='')
        .values_list('branch', flat=True).distinct().order_by('branch')
    )
    insurance_types = [v for v, _ in InsuranceRequest.INSURANCE_TYPE_CHOICES]
    deal_statuses = [{'value': v, 'label': l} for v, l in InsuranceRequest.DEAL_STATUS_CHOICES]
    users = [
        {'id': u.pk, 'display': _user_display(u)}
        for u in User.objects.filter(insurancerequest__isnull=False).distinct().order_by('username')
    ]
    return {
        'branches': branches,
        'insurance_types': insurance_types,
        'deal_statuses': deal_statuses,
        'users': users,
    }


# --- Public API -------------------------------------------------------------


def build_overview_payload(filters: dict) -> dict[str, Any]:
    rows, team = _build_manager_rows(filters)
    funnel = _build_funnel(filters)
    request_qs = _build_request_qs(filters)
    daily = _daily_counts(request_qs, filters)
    weekly = _weekly_stacked(request_qs)

    if filters['start_date'] and filters['end_date']:
        days_span = max((filters['end_date'] - filters['start_date']).days + 1, 1)
    else:
        days_span = max(team['requests_total'] and 365 or 1, 1)
    avg_per_day = round(team['requests_total'] / days_span, 2) if days_span else 0
    avg_per_week = round(avg_per_day * 7, 2)
    avg_per_month = round(avg_per_day * 30, 2)

    heatmaps = _compute_heatmaps(filters)

    payload = {
        'filters': filters,
        'kpi': {
            'total_requests': team['requests_total'],
            'total_summaries': team['summaries_total'],
            'accepted': team['accepted'],
            'win_rate': team['win_rate'],
            'premium_total': team['premium_total'],
            'avg_ticket': team['avg_ticket'],
            'active_total': team['active_total'],
            'overdue_count': team['overdue_count'],
            'managers_count': team['managers_count'],
            'avg_per_day': avg_per_day,
            'avg_per_week': avg_per_week,
            'avg_per_month': avg_per_month,
            'team_quality_score': team.get('quality_score'),
        },
        'rows': rows,
        'team': team,
        'funnel': funnel,
        'charts': {
            'daily': daily,
            'weekly': weekly,
        },
        'heatmaps': heatmaps,
        'available_filters': _available_filters(),
    }
    payload['charts_json'] = json.dumps(
        {'daily': daily, 'weekly': weekly},
        ensure_ascii=False,
        default=str,
    )
    return payload


def build_manager_profile_payload(user_id: int, filters: dict) -> dict[str, Any]:
    """Phase 0 stub. Заполняется в Phase 4."""
    return {
        'filters': filters,
        'user_id': user_id,
        'profile': None,
        'phase': 0,
    }


def build_compare_payload(user_ids: list[int], filters: dict) -> dict[str, Any]:
    """Phase 0 stub. Заполняется в Phase 3."""
    return {
        'filters': filters,
        'user_ids': user_ids,
        'managers': [],
        'phase': 0,
    }


def build_leaderboard_payload(filters: dict) -> dict[str, Any]:
    """Phase 0 stub. Заполняется в Phase 3."""
    return {
        'filters': filters,
        'rows': [],
        'phase': 0,
    }

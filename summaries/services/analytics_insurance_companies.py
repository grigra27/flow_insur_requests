"""Сервис расчета аналитики по страховым компаниям."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, Iterable, List, Optional

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch
from django.db.models.functions import Coalesce

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary

DATE_MODE_SUMMARY_CREATED = 'summary_created'
DATE_MODE_COMPLETED_AT = 'completed_at'
DATE_MODE_RECEIVED_AT = 'received_at'

DATE_MODE_CHOICES = {
    DATE_MODE_SUMMARY_CREATED: 'По дате создания свода',
    DATE_MODE_COMPLETED_AT: 'По дате закрытия сделки',
    DATE_MODE_RECEIVED_AT: 'По дате получения предложений',
}

MONTH_NAMES_RU = {
    1: 'Январь',
    2: 'Февраль',
    3: 'Март',
    4: 'Апрель',
    5: 'Май',
    6: 'Июнь',
    7: 'Июль',
    8: 'Август',
    9: 'Сентябрь',
    10: 'Октябрь',
    11: 'Ноябрь',
    12: 'Декабрь',
}


def _safe_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _median_decimal(values: Iterable[Decimal]) -> Optional[Decimal]:
    values_list = sorted(values)
    if not values_list:
        return None

    middle_index = len(values_list) // 2
    if len(values_list) % 2 == 1:
        return values_list[middle_index]

    return (values_list[middle_index - 1] + values_list[middle_index]) / Decimal('2')


def _avg_decimal(values: Iterable[Decimal]) -> Optional[Decimal]:
    values_list = list(values)
    if not values_list:
        return None
    return sum(values_list, Decimal('0')) / Decimal(len(values_list))


def _avg_float(values: Iterable[float]) -> float:
    values_list = list(values)
    if not values_list:
        return 0.0
    return sum(values_list) / len(values_list)


def _percent(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal('0')
    return (Decimal(numerator) / Decimal(denominator)) * Decimal('100')


def _hours_between(dt_start, dt_end) -> Optional[float]:
    if not dt_start or not dt_end:
        return None
    delta = dt_end - dt_start
    return delta.total_seconds() / 3600


def _resolve_manager_online_name(insurance_request) -> str:
    created_by = getattr(insurance_request, 'created_by', None)
    if not created_by:
        return ''

    first_name = (created_by.first_name or '').strip()
    last_name = (created_by.last_name or '').strip()
    username = (created_by.username or '').strip()

    full_name = f"{last_name} {first_name}".strip()
    return full_name or username


def _date_to_month_key(value) -> Optional[str]:
    if not value:
        return None
    return value.strftime('%Y-%m')


def _date_to_month_label(value) -> str:
    if not value:
        return 'Без даты'
    return f"{MONTH_NAMES_RU.get(value.month, value.strftime('%B'))} {value.year}"


def _offer_supports_installment(offer: InsuranceOffer, selected_variant: int) -> bool:
    if selected_variant == 2:
        if offer.installment_variant_2 and (offer.payments_per_year_variant_2 or 0) > 1:
            return True
    else:
        if offer.installment_variant_1 and (offer.payments_per_year_variant_1 or 0) > 1:
            return True

    return bool(offer.installment_available and (offer.payments_per_year or 0) > 1)


def _sum_selected_total(selected_offers: List[InsuranceOffer], selected_variant: int) -> Optional[Decimal]:
    if not selected_offers:
        return None

    offers_by_year = {offer.insurance_year: offer for offer in selected_offers}
    total = Decimal('0')
    for year in sorted(offers_by_year.keys()):
        offer = offers_by_year[year]
        premium_raw = (
            offer.premium_with_franchise_2
            if selected_variant == 2
            else offer.premium_with_franchise_1
        )
        premium_value = _safe_decimal(premium_raw)
        if premium_value is None or premium_value <= 0:
            return None
        total += premium_value

    return total


def _get_date_anchor(summary: InsuranceSummary, valid_offers: List[InsuranceOffer], date_mode: str):
    if date_mode == DATE_MODE_COMPLETED_AT:
        return summary.completed_at or summary.updated_at

    if date_mode == DATE_MODE_RECEIVED_AT:
        if not valid_offers:
            return None
        return min((offer.received_at for offer in valid_offers), default=None)

    return summary.created_at


def _apply_date_filters(
    queryset,
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    date_mode: str,
):
    if date_mode == DATE_MODE_COMPLETED_AT:
        queryset = queryset.annotate(_analytics_closed_at=Coalesce('completed_at', 'updated_at'))
        if start_date:
            queryset = queryset.filter(_analytics_closed_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(_analytics_closed_at__date__lte=end_date)
        return queryset

    if date_mode == DATE_MODE_RECEIVED_AT:
        queryset = queryset.filter(offers__is_valid=True)
        if start_date:
            queryset = queryset.filter(offers__received_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(offers__received_at__date__lte=end_date)
        return queryset.distinct()

    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    return queryset


def _build_manager_online_choices(queryset) -> List[Dict[str, str]]:
    manager_rows = queryset.exclude(
        request__created_by__isnull=True
    ).order_by().values(
        'request__created_by_id',
        'request__created_by__username',
        'request__created_by__first_name',
        'request__created_by__last_name',
    ).distinct()

    managers = []
    for manager_row in manager_rows:
        first_name = (manager_row.get('request__created_by__first_name') or '').strip()
        last_name = (manager_row.get('request__created_by__last_name') or '').strip()
        username = (manager_row.get('request__created_by__username') or '').strip()
        display_name = f"{first_name} {last_name}".strip() or username

        managers.append({
            'id': str(manager_row.get('request__created_by_id')),
            'name': display_name,
        })

    return sorted(managers, key=lambda item: (item['name'] or '').lower())


def _build_available_filters(queryset) -> Dict[str, List]:
    branches = list(
        queryset.exclude(
            request__branch__isnull=True
        ).exclude(
            request__branch=''
        ).values_list('request__branch', flat=True).distinct().order_by('request__branch')
    )

    insurance_types = list(
        queryset.exclude(
            request__insurance_type__isnull=True
        ).exclude(
            request__insurance_type=''
        ).values_list('request__insurance_type', flat=True).distinct().order_by('request__insurance_type')
    )

    manager_alliance = list(
        queryset.exclude(
            request__manager_name__isnull=True
        ).exclude(
            request__manager_name=''
        ).values_list('request__manager_name', flat=True).distinct().order_by('request__manager_name')
    )

    selected_companies = list(
        queryset.exclude(
            selected_company__isnull=True
        ).exclude(
            selected_company=''
        ).values_list('selected_company', flat=True).distinct().order_by('selected_company')
    )

    return {
        'branches': branches,
        'insurance_types': insurance_types,
        'manager_online': _build_manager_online_choices(queryset),
        'manager_alliance': manager_alliance,
        'selected_companies': selected_companies,
        'deal_statuses': [
            {'value': value, 'label': label}
            for value, label in InsuranceRequest.DEAL_STATUS_CHOICES
        ],
    }


def _build_slice_rows(slice_counter, total_deals: int) -> List[Dict]:
    rows = []
    for (company_name, dimension_value), counters in slice_counter.items():
        offered = counters['offered']
        selected = counters['selected']
        rows.append({
            'company_name': company_name,
            'dimension_value': dimension_value,
            'offered_in_deals_count': offered,
            'selected_wins_count': selected,
            'win_rate_when_offered_pct': _percent(selected, offered),
            'coverage_pct': _percent(offered, total_deals),
        })

    rows.sort(
        key=lambda row: (
            row['offered_in_deals_count'],
            row['selected_wins_count'],
            row['company_name'],
            row['dimension_value'],
        ),
        reverse=True,
    )
    return rows


def _paginate_rows(rows: List[Dict], page: Optional[str], per_page: int):
    paginator = Paginator(rows, per_page)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return paginator, page_obj


def build_analytics_insurance_companies_payload(
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    date_mode: str,
    branch: str,
    insurance_type: str,
    manager_online: str,
    manager_alliance: str,
    selected_company: str,
    deal_status: str,
    comparison_mode: str,
    require_full_coverage: bool,
    page: Optional[str],
    per_page: int,
    price_row_builder: Callable,
):
    base_queryset = InsuranceSummary.objects.select_related('request', 'request__created_by').filter(
        status='completed_accepted'
    ).exclude(
        selected_company__isnull=True
    ).exclude(
        selected_company=''
    )

    queryset_with_period = _apply_date_filters(
        base_queryset,
        start_date=start_date,
        end_date=end_date,
        date_mode=date_mode,
    )

    # Для режима received_at сначала фиксируем id сводов периода, чтобы не повторять
    # тяжелый JOIN с offers на каждом DISTINCT-запросе фильтров.
    if date_mode == DATE_MODE_RECEIVED_AT:
        period_summary_ids = list(
            queryset_with_period.values_list('id', flat=True).distinct()
        )
        summaries_for_filters_queryset = base_queryset.filter(id__in=period_summary_ids)
    else:
        summaries_for_filters_queryset = queryset_with_period

    available_filters = _build_available_filters(summaries_for_filters_queryset)
    errors = []

    summaries_queryset = summaries_for_filters_queryset
    if branch:
        summaries_queryset = summaries_queryset.filter(request__branch=branch)
    if insurance_type:
        summaries_queryset = summaries_queryset.filter(request__insurance_type=insurance_type)
    if manager_online:
        try:
            summaries_queryset = summaries_queryset.filter(request__created_by_id=int(manager_online))
        except ValueError:
            manager_online = ''
            errors.append('Некорректный фильтр менеджера Онлайна был сброшен')
    if manager_alliance:
        summaries_queryset = summaries_queryset.filter(request__manager_name=manager_alliance)
    if selected_company:
        summaries_queryset = summaries_queryset.filter(selected_company=selected_company)
    if deal_status:
        summaries_queryset = summaries_queryset.filter(request__deal_status=deal_status)

    summaries_queryset = summaries_queryset.prefetch_related(
        Prefetch(
            'offers',
            queryset=InsuranceOffer.objects.filter(is_valid=True).order_by('company_name', 'insurance_year'),
            to_attr='valid_offers_prefetched',
        )
    ).order_by('-created_at')

    deal_rows = []
    comparable_rows = []

    rating_offered_map = defaultdict(set)
    rating_selected_map = defaultdict(list)

    slices_map = {
        'branch': defaultdict(lambda: {'offered': 0, 'selected': 0}),
        'manager_online': defaultdict(lambda: {'offered': 0, 'selected': 0}),
        'manager_alliance': defaultdict(lambda: {'offered': 0, 'selected': 0}),
        'insurance_type': defaultdict(lambda: {'offered': 0, 'selected': 0}),
        'deal_status': defaultdict(lambda: {'offered': 0, 'selected': 0}),
    }

    dynamics_map = {}

    request_to_summary_hours = []
    summary_to_close_hours = []

    distinct_offered_companies = set()
    distinct_selected_companies = set()

    for summary in summaries_queryset:
        insurance_request = summary.request
        valid_offers = list(getattr(summary, 'valid_offers_prefetched', []))

        selected_company_name = (summary.selected_company or '').strip()
        selected_variant_raw = summary.selected_franchise_variant
        selected_variant = selected_variant_raw if selected_variant_raw in (1, 2) else 1
        selected_variant_fallback_used = selected_variant_raw not in (1, 2)

        offers_by_company = defaultdict(list)
        for offer in valid_offers:
            offers_by_company[offer.company_name].append(offer)

        offered_companies = sorted(offers_by_company.keys())
        distinct_offered_companies.update(offered_companies)
        if selected_company_name:
            distinct_selected_companies.add(selected_company_name)

        selected_offers = sorted(
            offers_by_company.get(selected_company_name, []),
            key=lambda item: item.insurance_year,
        )
        selected_years = {offer.insurance_year for offer in selected_offers}
        selected_total = _sum_selected_total(selected_offers, selected_variant)
        selected_has_installment = any(
            _offer_supports_installment(offer, selected_variant)
            for offer in selected_offers
        )

        closed_at = summary.completed_at or summary.updated_at
        first_offer_received_at = min((offer.received_at for offer in valid_offers), default=None)
        date_anchor = _get_date_anchor(summary, valid_offers, date_mode)

        manager_online_name = _resolve_manager_online_name(insurance_request)
        manager_alliance_name = (insurance_request.manager_name or '').strip()
        branch_name = (insurance_request.branch or '').strip()
        insurance_type_name = (insurance_request.insurance_type or '').strip()
        deal_status_value = getattr(insurance_request, 'deal_status', '') or ''
        deal_status_name = insurance_request.get_deal_status_display() if deal_status_value else 'Не указан'

        price_row = price_row_builder(
            summary,
            comparison_mode=comparison_mode,
            require_full_coverage=require_full_coverage,
        )

        if price_row and selected_total is None:
            selected_total = price_row.get('selected_total')

        deal_row = {
            'summary': summary,
            'request': insurance_request,
            'selected_company': selected_company_name,
            'selected_variant': selected_variant,
            'selected_variant_fallback_used': selected_variant_fallback_used,
            'selected_total': selected_total,
            'selected_years_count': len(selected_years),
            'selected_has_installment': selected_has_installment,
            'has_selected_offer': bool(selected_offers),
            'manager_online': manager_online_name or 'Не указан',
            'manager_online_raw': manager_online_name,
            'manager_alliance': manager_alliance_name or 'Не указан',
            'manager_alliance_raw': manager_alliance_name,
            'branch': branch_name or 'Не указан',
            'branch_raw': branch_name,
            'insurance_type': insurance_type_name or 'Не указан',
            'insurance_type_raw': insurance_type_name,
            'deal_status': deal_status_name,
            'deal_status_raw': deal_status_value,
            'created_at': summary.created_at,
            'closed_at': closed_at,
            'first_offer_received_at': first_offer_received_at,
            'date_anchor': date_anchor,
            'offered_companies': offered_companies,
            'offered_companies_count': len(offered_companies),
            'is_comparable': bool(price_row),
            'selected_rank': price_row.get('selected_rank') if price_row else None,
            'delta_to_min_abs': price_row.get('delta_to_min_abs') if price_row else None,
            'delta_to_min_pct': price_row.get('delta_to_min_pct') if price_row else None,
            'is_min_selected': price_row.get('is_min_selected') if price_row else False,
            'comparable_companies_count': price_row.get('comparable_companies_count') if price_row else 0,
            'price_row': price_row,
        }
        deal_rows.append(deal_row)

        if price_row:
            comparable_rows.append(deal_row)

        for company_name in offered_companies:
            rating_offered_map[company_name].add(summary.id)

        if selected_company_name:
            rating_selected_map[selected_company_name].append(deal_row)

        branch_slice_value = branch_name or 'Не указан'
        manager_online_slice_value = manager_online_name or 'Не указан'
        manager_alliance_slice_value = manager_alliance_name or 'Не указан'
        insurance_type_slice_value = insurance_type_name or 'Не указан'
        deal_status_slice_value = deal_status_name or 'Не указан'

        for company_name in offered_companies:
            slices_map['branch'][(company_name, branch_slice_value)]['offered'] += 1
            slices_map['manager_online'][(company_name, manager_online_slice_value)]['offered'] += 1
            slices_map['manager_alliance'][(company_name, manager_alliance_slice_value)]['offered'] += 1
            slices_map['insurance_type'][(company_name, insurance_type_slice_value)]['offered'] += 1
            slices_map['deal_status'][(company_name, deal_status_slice_value)]['offered'] += 1

        if selected_company_name:
            slices_map['branch'][(selected_company_name, branch_slice_value)]['selected'] += 1
            slices_map['manager_online'][(selected_company_name, manager_online_slice_value)]['selected'] += 1
            slices_map['manager_alliance'][(selected_company_name, manager_alliance_slice_value)]['selected'] += 1
            slices_map['insurance_type'][(selected_company_name, insurance_type_slice_value)]['selected'] += 1
            slices_map['deal_status'][(selected_company_name, deal_status_slice_value)]['selected'] += 1

        month_key = _date_to_month_key(date_anchor)
        if month_key:
            bucket = dynamics_map.setdefault(month_key, {
                'month_key': month_key,
                'month_label': _date_to_month_label(date_anchor),
                'total_deals': 0,
                'comparable_deals': 0,
                'min_selected_count': 0,
                'selected_premiums': [],
                'selected_companies': set(),
            })
            bucket['total_deals'] += 1
            if price_row:
                bucket['comparable_deals'] += 1
                if price_row.get('is_min_selected'):
                    bucket['min_selected_count'] += 1
            if selected_total is not None:
                bucket['selected_premiums'].append(selected_total)
            if selected_company_name:
                bucket['selected_companies'].add(selected_company_name)

        request_to_summary = _hours_between(insurance_request.created_at, summary.created_at)
        if request_to_summary is not None:
            request_to_summary_hours.append(request_to_summary)

        summary_to_close = _hours_between(summary.created_at, closed_at)
        if summary_to_close is not None:
            summary_to_close_hours.append(summary_to_close)

    deal_rows.sort(
        key=lambda item: item['date_anchor'] or item['created_at'],
        reverse=True,
    )

    total_deals = len(deal_rows)
    comparable_deals = len(comparable_rows)

    min_selected_count = sum(1 for row in comparable_rows if row['is_min_selected'])
    comparable_ranks = [row['selected_rank'] for row in comparable_rows if row['selected_rank'] is not None]
    comparable_deltas_abs = [row['delta_to_min_abs'] for row in comparable_rows if row['delta_to_min_abs'] is not None]
    comparable_deltas_pct = [row['delta_to_min_pct'] for row in comparable_rows if row['delta_to_min_pct'] is not None]
    comparable_competitors = [
        max((row['comparable_companies_count'] or 0) - 1, 0)
        for row in comparable_rows
    ]

    selected_premiums = [row['selected_total'] for row in deal_rows if row['selected_total'] is not None]
    multiyear_count = sum(1 for row in deal_rows if row['selected_years_count'] > 1)
    installment_count = sum(1 for row in deal_rows if row['selected_has_installment'])

    sla_eligible_rows = [
        row for row in deal_rows
        if row['closed_at'] and getattr(row['request'], 'response_deadline', None)
    ]
    sla_before_deadline_count = sum(
        1 for row in sla_eligible_rows
        if row['closed_at'] <= row['request'].response_deadline
    )

    kpi = {
        'total_deals': total_deals,
        'comparable_deals': comparable_deals,
        'distinct_companies_offered': len(distinct_offered_companies),
        'distinct_companies_selected': len(distinct_selected_companies),
        'min_selected_count': min_selected_count,
        'min_selected_rate': _percent(min_selected_count, comparable_deals),
        'avg_competitors': _avg_float(comparable_competitors),
        'avg_selected_premium': _avg_decimal(selected_premiums),
        'median_delta_abs': _median_decimal(comparable_deltas_abs),
        'median_delta_pct': _median_decimal(comparable_deltas_pct),
        'avg_rank': _avg_float([float(rank) for rank in comparable_ranks]),
        'multiyear_rate': _percent(multiyear_count, total_deals),
        'installment_rate': _percent(installment_count, total_deals),
        'sla_before_deadline_rate': _percent(sla_before_deadline_count, len(sla_eligible_rows)),
        'avg_hours_request_to_summary': _avg_float(request_to_summary_hours),
        'avg_hours_summary_to_close': _avg_float(summary_to_close_hours),
        'insufficient_data': comparable_deals < 5,
        'sla_eligible_deals': len(sla_eligible_rows),
    }

    rating_rows = []
    for company_name, offered_ids in rating_offered_map.items():
        selected_rows = rating_selected_map.get(company_name, [])
        comparable_selected_rows = [row for row in selected_rows if row['is_comparable']]

        selected_count = len(selected_rows)
        offered_count = len(offered_ids)

        selected_company_premiums = [
            row['selected_total'] for row in selected_rows
            if row['selected_total'] is not None
        ]
        selected_company_ranks = [
            row['selected_rank'] for row in comparable_selected_rows
            if row['selected_rank'] is not None
        ]
        selected_company_deltas_abs = [
            row['delta_to_min_abs'] for row in comparable_selected_rows
            if row['delta_to_min_abs'] is not None
        ]
        min_selected_when_selected = sum(
            1 for row in comparable_selected_rows
            if row['is_min_selected']
        )

        rating_rows.append({
            'company_name': company_name,
            'offered_in_deals_count': offered_count,
            'selected_wins_count': selected_count,
            'coverage_pct': _percent(offered_count, total_deals),
            'win_rate_when_offered_pct': _percent(selected_count, offered_count),
            'win_share_pct': _percent(selected_count, total_deals),
            'selected_premium_sum': sum(selected_company_premiums, Decimal('0')),
            'selected_premium_avg': _avg_decimal(selected_company_premiums),
            'avg_rank_when_selected': _avg_float([float(value) for value in selected_company_ranks]),
            'median_delta_abs_when_selected': _median_decimal(selected_company_deltas_abs),
            'min_selected_rate_when_selected': _percent(
                min_selected_when_selected,
                len(comparable_selected_rows),
            ),
            'comparable_selected_deals_count': len(comparable_selected_rows),
        })

    rating_rows.sort(
        key=lambda row: (
            row['selected_wins_count'],
            row['offered_in_deals_count'],
            row['win_rate_when_offered_pct'],
            row['company_name'],
        ),
        reverse=True,
    )
    for idx, row in enumerate(rating_rows, start=1):
        row['position'] = idx

    competitiveness_rows = []
    for company_name, selected_rows in rating_selected_map.items():
        comparable_selected_rows = [row for row in selected_rows if row['is_comparable']]
        comparable_count = len(comparable_selected_rows)
        rank_values = [
            row['selected_rank'] for row in comparable_selected_rows
            if row['selected_rank'] is not None
        ]
        delta_abs_values = [
            row['delta_to_min_abs'] for row in comparable_selected_rows
            if row['delta_to_min_abs'] is not None
        ]
        delta_pct_values = [
            row['delta_to_min_pct'] for row in comparable_selected_rows
            if row['delta_to_min_pct'] is not None
        ]
        min_selected_company_count = sum(
            1 for row in comparable_selected_rows
            if row['is_min_selected']
        )

        competitors_values = [
            max((row['comparable_companies_count'] or 0) - 1, 0)
            for row in comparable_selected_rows
        ]

        competitiveness_rows.append({
            'company_name': company_name,
            'selected_deals_count': len(selected_rows),
            'comparable_selected_deals_count': comparable_count,
            'avg_rank': _avg_float([float(value) for value in rank_values]),
            'median_delta_abs': _median_decimal(delta_abs_values),
            'median_delta_pct': _median_decimal(delta_pct_values),
            'min_selected_rate': _percent(min_selected_company_count, comparable_count),
            'avg_competitors': _avg_float(competitors_values),
        })

    competitiveness_rows.sort(
        key=lambda row: (
            row['comparable_selected_deals_count'],
            row['selected_deals_count'],
            row['company_name'],
        ),
        reverse=True,
    )

    conversion_rows = [
        {
            'company_name': row['company_name'],
            'offered_in_deals_count': row['offered_in_deals_count'],
            'selected_wins_count': row['selected_wins_count'],
            'conversion_pct': row['win_rate_when_offered_pct'],
            'win_share_pct': row['win_share_pct'],
        }
        for row in rating_rows
    ]

    slices = {
        'branch': _build_slice_rows(slices_map['branch'], total_deals),
        'manager_online': _build_slice_rows(slices_map['manager_online'], total_deals),
        'manager_alliance': _build_slice_rows(slices_map['manager_alliance'], total_deals),
        'insurance_type': _build_slice_rows(slices_map['insurance_type'], total_deals),
        'deal_status': _build_slice_rows(slices_map['deal_status'], total_deals),
    }

    dynamics_rows = []
    for month_key in sorted(dynamics_map.keys()):
        bucket = dynamics_map[month_key]
        min_selected_month_rate = _percent(
            bucket['min_selected_count'],
            bucket['comparable_deals'],
        )

        dynamics_rows.append({
            'month_key': month_key,
            'month_label': bucket['month_label'],
            'total_deals': bucket['total_deals'],
            'comparable_deals': bucket['comparable_deals'],
            'min_selected_count': bucket['min_selected_count'],
            'min_selected_rate': min_selected_month_rate,
            'selected_premium_avg': _avg_decimal(bucket['selected_premiums']),
            'distinct_selected_companies': len(bucket['selected_companies']),
        })

    dynamics_rows_desc = sorted(dynamics_rows, key=lambda row: row['month_key'], reverse=True)

    data_quality_metrics = {
        'missing_selected_variant_count': sum(1 for row in deal_rows if row['selected_variant_fallback_used']),
        'missing_manager_alliance_count': sum(1 for row in deal_rows if not row['manager_alliance_raw']),
        'missing_manager_online_count': sum(1 for row in deal_rows if not row['manager_online_raw']),
        'missing_branch_count': sum(1 for row in deal_rows if not row['branch_raw']),
        'missing_selected_offer_count': sum(1 for row in deal_rows if not row['has_selected_offer']),
        'non_comparable_count': sum(1 for row in deal_rows if not row['is_comparable']),
        'missing_selected_total_count': sum(1 for row in deal_rows if row['selected_total'] is None),
        'missing_response_deadline_count': sum(
            1 for row in deal_rows
            if not getattr(row['request'], 'response_deadline', None)
        ),
        'missing_offer_received_at_count': sum(1 for row in deal_rows if not row['first_offer_received_at']),
    }

    data_quality_rows = [
        {
            'key': 'missing_selected_variant_count',
            'label': 'Не заполнен selected_franchise_variant (использован fallback = вариант 1)',
            'count': data_quality_metrics['missing_selected_variant_count'],
            'rate': _percent(data_quality_metrics['missing_selected_variant_count'], total_deals),
        },
        {
            'key': 'missing_manager_alliance_count',
            'label': 'Пустой manager_name (менеджер Альянса)',
            'count': data_quality_metrics['missing_manager_alliance_count'],
            'rate': _percent(data_quality_metrics['missing_manager_alliance_count'], total_deals),
        },
        {
            'key': 'missing_manager_online_count',
            'label': 'Не заполнен created_by (менеджер Онлайна)',
            'count': data_quality_metrics['missing_manager_online_count'],
            'rate': _percent(data_quality_metrics['missing_manager_online_count'], total_deals),
        },
        {
            'key': 'missing_branch_count',
            'label': 'Пустой филиал',
            'count': data_quality_metrics['missing_branch_count'],
            'rate': _percent(data_quality_metrics['missing_branch_count'], total_deals),
        },
        {
            'key': 'missing_selected_offer_count',
            'label': 'Нет валидного предложения выбранной СК',
            'count': data_quality_metrics['missing_selected_offer_count'],
            'rate': _percent(data_quality_metrics['missing_selected_offer_count'], total_deals),
        },
        {
            'key': 'non_comparable_count',
            'label': 'Несопоставимые сделки для ценового ранга',
            'count': data_quality_metrics['non_comparable_count'],
            'rate': _percent(data_quality_metrics['non_comparable_count'], total_deals),
        },
        {
            'key': 'missing_selected_total_count',
            'label': 'Нельзя посчитать итоговую премию выбранной СК',
            'count': data_quality_metrics['missing_selected_total_count'],
            'rate': _percent(data_quality_metrics['missing_selected_total_count'], total_deals),
        },
        {
            'key': 'missing_response_deadline_count',
            'label': 'Нет response_deadline для SLA',
            'count': data_quality_metrics['missing_response_deadline_count'],
            'rate': _percent(data_quality_metrics['missing_response_deadline_count'], total_deals),
        },
    ]

    paginator, deals_page = _paginate_rows(deal_rows, page, per_page)

    rating_chart_rows = rating_rows[:10]
    competitiveness_chart_rows = [
        row for row in competitiveness_rows
        if row['comparable_selected_deals_count'] > 0
    ][:10]

    charts = {
        'rating': {
            'labels': [row['company_name'] for row in rating_chart_rows],
            'offered': [row['offered_in_deals_count'] for row in rating_chart_rows],
            'wins': [row['selected_wins_count'] for row in rating_chart_rows],
        },
        'conversion': {
            'labels': [row['company_name'] for row in rating_chart_rows],
            'values': [float(row['win_rate_when_offered_pct']) for row in rating_chart_rows],
        },
        'competitiveness': {
            'labels': [row['company_name'] for row in competitiveness_chart_rows],
            'values': [float(row['min_selected_rate']) for row in competitiveness_chart_rows],
        },
        'dynamics': {
            'labels': [row['month_label'] for row in dynamics_rows],
            'total_deals': [row['total_deals'] for row in dynamics_rows],
            'min_selected_rate': [float(row['min_selected_rate']) for row in dynamics_rows],
        },
    }

    return {
        'filters': {
            'branch': branch,
            'insurance_type': insurance_type,
            'manager_online': manager_online,
            'manager_alliance': manager_alliance,
            'selected_company': selected_company,
            'deal_status': deal_status,
            'date_mode': date_mode,
            'comparison_mode': comparison_mode,
            'require_full_coverage': require_full_coverage,
        },
        'filter_errors': errors,
        'available_filters': available_filters,
        'kpi': kpi,
        'rating_rows': rating_rows,
        'competitiveness_rows': competitiveness_rows,
        'conversion_rows': conversion_rows,
        'slices': slices,
        'dynamics_rows': dynamics_rows_desc,
        'data_quality_rows': data_quality_rows,
        'deals_page': deals_page,
        'paginator': paginator,
        'charts': charts,
        'export_payload': {
            'kpi': kpi,
            'rating_rows': rating_rows,
            'competitiveness_rows': competitiveness_rows,
            'conversion_rows': conversion_rows,
            'slices': slices,
            'dynamics_rows': dynamics_rows_desc,
            'data_quality_rows': data_quality_rows,
            'deal_rows': deal_rows,
        },
    }

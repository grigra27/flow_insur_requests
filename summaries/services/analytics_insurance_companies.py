"""Аналитика «Страховые компании · куда уходит бизнес».

Сделка — акцептованный свод (`completed_accepted`) с выбранной СК. По каждой СК:
сколько сделок, какая страховая сумма и премия ушли в неё, по какому тарифу,
в скольких сделках она участвовала и насколько часто выигрывала, в том числе
будучи самой дешёвой. Плюс помесячная динамика долей и разрезы СК × филиал /
СК × тип страхования.

Правила расчёта (docs/analytics_insurance_companies_metrics.md):
- страховая сумма — по первому году выбранного предложения (многолетние сделки
  не удваиваются);
- премия — сумма по всем годам выбранного варианта франшизы (деньги, которые
  уходят в СК);
- тариф — премия первого года / страховая сумма первого года;
- «выбрана самая дешёвая» — по сопоставимым сделкам `_build_deal_price_row`.

Страница пересобрана по docs/improvement_plans/analytics_redesign_2026_09.md (задача 1.4).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, Iterable, List, Optional

from django.db.models import Prefetch

from summaries.models import InsuranceOffer, InsuranceSummary

NOT_SPECIFIED = 'Не указан'
OTHER_COMPANIES_LABEL = 'Прочие'
MONTHLY_TOP_COMPANIES = 6
INSUFFICIENT_COMPARABLE_DEALS = 5

INSURANCE_TYPE_ORDER = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']

# Категориальная палитра графика (порядок проверен на различимость, в т.ч. при дальтонизме).
# Цвет закреплён за СК, а не за местом в рейтинге: при смене фильтра цвета не «переезжают».
SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
OTHER_SERIES_COLOR = '#8a8985'
COMPANY_COLOR_SLOTS = {
    'Абсолют': 0,
    'Ингосстрах': 1,
    'Пари': 2,
    'Альфа': 3,
    'Росгосстрах': 4,
    'Согласие': 5,
    'Зетта': 6,
    'Согаз': 7,
}


def _series_colors(names: List[str]) -> Dict[str, str]:
    colors = {}
    used = set()
    for name in names:
        slot = COMPANY_COLOR_SLOTS.get(name)
        if slot is not None:
            colors[name] = SERIES_COLORS[slot]
            used.add(slot)
    free_slots = [slot for slot in range(len(SERIES_COLORS)) if slot not in used]
    for name in names:
        if name in colors:
            continue
        if name == OTHER_COMPANIES_LABEL or not free_slots:
            colors[name] = OTHER_SERIES_COLOR
        else:
            colors[name] = SERIES_COLORS[free_slots.pop(0)]
    return colors

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


def _safe_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _percent(numerator, denominator) -> Optional[Decimal]:
    if not denominator:
        return None
    return Decimal(numerator) / Decimal(denominator) * Decimal('100')


def _month_label(month_key: str) -> str:
    year, month = month_key.split('-')
    return f"{MONTH_NAMES_RU[int(month)]} {year}"


def _variant_premium(offer: InsuranceOffer, variant: int) -> Optional[Decimal]:
    raw = offer.premium_with_franchise_2 if variant == 2 else offer.premium_with_franchise_1
    value = _safe_decimal(raw)
    if value is None or value <= 0:
        return None
    return value


def _selected_money(selected_offers: List[InsuranceOffer], variant: int) -> Dict[str, Optional[Decimal]]:
    """Страховая сумма и премия 1-го года + премия за все годы для выбранной СК.

    Если премии нет хотя бы в одном году выбранного варианта — премия за все годы
    не считается (None), чтобы не занижать сумму; это видно в «Качестве данных».
    """
    if not selected_offers:
        return {'insured_sum': None, 'premium_year1': None, 'premium_total': None}

    offers = sorted(selected_offers, key=lambda offer: offer.insurance_year)
    first = offers[0]
    insured_sum = _safe_decimal(first.insurance_sum)
    if insured_sum is not None and insured_sum <= 0:
        insured_sum = None

    premiums = [_variant_premium(offer, variant) for offer in offers]
    premium_total = None if any(value is None for value in premiums) else sum(premiums, Decimal('0'))

    return {
        'insured_sum': insured_sum,
        'premium_year1': premiums[0],
        'premium_total': premium_total,
    }


def _build_heatmap(counter: Counter, row_order: List[str], column_order: List[str]) -> Dict:
    """Матрица «СК × измерение» по числу сделок."""
    max_value = max(counter.values(), default=0)
    rows = []
    for company in row_order:
        cells = [{'column': column, 'value': counter.get((company, column), 0)} for column in column_order]
        rows.append({'label': company, 'cells': cells, 'total': sum(cell['value'] for cell in cells)})
    column_totals = [sum(counter.get((company, column), 0) for company in row_order) for column in column_order]
    return {
        'columns': column_order,
        'rows': rows,
        'column_totals': column_totals,
        'max_value': max_value,
    }


def _ordered_by_count(values: Iterable[str]) -> List[str]:
    counts = Counter(values)
    return [value for value, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def build_available_filters(start_date: Optional[date], end_date: Optional[date]) -> Dict[str, List[str]]:
    queryset = _base_queryset(start_date, end_date)
    branches = list(
        queryset.exclude(request__branch__isnull=True).exclude(request__branch='')
        .values_list('request__branch', flat=True).distinct().order_by('request__branch')
    )
    insurance_types = list(
        queryset.exclude(request__insurance_type__isnull=True).exclude(request__insurance_type='')
        .values_list('request__insurance_type', flat=True).distinct().order_by('request__insurance_type')
    )
    return {'branches': branches, 'insurance_types': insurance_types}


def _base_queryset(start_date: Optional[date], end_date: Optional[date]):
    queryset = InsuranceSummary.objects.filter(status='completed_accepted').exclude(
        selected_company__isnull=True
    ).exclude(selected_company='')
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    return queryset


def build_analytics_insurance_companies_payload(
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    branch: str = '',
    insurance_type: str = '',
    price_row_builder: Callable,
) -> Dict:
    queryset = _base_queryset(start_date, end_date).select_related('request')
    if branch:
        queryset = queryset.filter(request__branch=branch)
    if insurance_type:
        queryset = queryset.filter(request__insurance_type=insurance_type)
    queryset = queryset.prefetch_related(
        Prefetch(
            'offers',
            queryset=InsuranceOffer.objects.filter(is_valid=True).order_by('company_name', 'insurance_year'),
            to_attr='valid_offers_prefetched',
        )
    ).order_by('created_at')

    company_stats = defaultdict(lambda: {
        'deals': 0,
        'offered': 0,
        'insured_sum': Decimal('0'),
        'insured_sum_year1_for_tariff': Decimal('0'),
        'premium_year1_for_tariff': Decimal('0'),
        'premium_total': Decimal('0'),
        'comparable_wins': 0,
        'cheapest_wins': 0,
    })
    monthly_deals = defaultdict(Counter)
    monthly_sums = defaultdict(lambda: defaultdict(Decimal))
    branch_counter = Counter()
    type_counter = Counter()
    branch_values = []
    type_values = []

    totals = {
        'deals': 0,
        'insured_sum': Decimal('0'),
        'premium_total': Decimal('0'),
        'insured_sum_year1_for_tariff': Decimal('0'),
        'premium_year1_for_tariff': Decimal('0'),
        'comparable_deals': 0,
        'cheapest_deals': 0,
    }
    quality = Counter()

    for summary in queryset:
        insurance_request = summary.request
        valid_offers = list(getattr(summary, 'valid_offers_prefetched', []))
        company = summary.selected_company.strip()
        raw_variant = summary.selected_franchise_variant
        variant = raw_variant if raw_variant in (1, 2) else 1
        if raw_variant not in (1, 2):
            quality['missing_variant'] += 1

        offers_by_company = defaultdict(list)
        for offer in valid_offers:
            offers_by_company[offer.company_name].append(offer)
        for offered_company in offers_by_company:
            company_stats[offered_company]['offered'] += 1

        money = _selected_money(offers_by_company.get(company, []), variant)
        stats = company_stats[company]
        stats['deals'] += 1
        totals['deals'] += 1

        if money['insured_sum'] is not None:
            stats['insured_sum'] += money['insured_sum']
            totals['insured_sum'] += money['insured_sum']
        else:
            quality['missing_insured_sum'] += 1
        if money['premium_total'] is not None:
            stats['premium_total'] += money['premium_total']
            totals['premium_total'] += money['premium_total']
        else:
            quality['missing_premium'] += 1
        if money['insured_sum'] is not None and money['premium_year1'] is not None:
            stats['insured_sum_year1_for_tariff'] += money['insured_sum']
            stats['premium_year1_for_tariff'] += money['premium_year1']
            totals['insured_sum_year1_for_tariff'] += money['insured_sum']
            totals['premium_year1_for_tariff'] += money['premium_year1']

        price_row = price_row_builder(summary)
        if price_row:
            totals['comparable_deals'] += 1
            stats['comparable_wins'] += 1
            if price_row['is_min_selected']:
                totals['cheapest_deals'] += 1
                stats['cheapest_wins'] += 1
        else:
            quality['not_comparable'] += 1

        month_key = summary.created_at.strftime('%Y-%m')
        monthly_deals[month_key][company] += 1
        if money['insured_sum'] is not None:
            monthly_sums[month_key][company] += money['insured_sum']

        branch_name = (insurance_request.branch or '').strip() or NOT_SPECIFIED
        type_name = (insurance_request.insurance_type or '').strip() or NOT_SPECIFIED
        if branch_name == NOT_SPECIFIED:
            quality['missing_branch'] += 1
        branch_counter[(company, branch_name)] += 1
        type_counter[(company, type_name)] += 1
        branch_values.append(branch_name)
        type_values.append(type_name)

    total_deals = totals['deals']

    company_rows = []
    for company, stats in company_stats.items():
        company_rows.append({
            'company_name': company,
            'deals': stats['deals'],
            'deals_share_pct': _percent(stats['deals'], total_deals),
            'insured_sum': stats['insured_sum'] if stats['deals'] else None,
            'insured_sum_share_pct': _percent(stats['insured_sum'], totals['insured_sum']) if stats['deals'] else None,
            'premium_total': stats['premium_total'] if stats['deals'] else None,
            'premium_share_pct': _percent(stats['premium_total'], totals['premium_total']) if stats['deals'] else None,
            'tariff_pct': _percent(stats['premium_year1_for_tariff'], stats['insured_sum_year1_for_tariff']),
            'offered': stats['offered'],
            'win_rate_pct': _percent(stats['deals'], stats['offered']),
            'comparable_wins': stats['comparable_wins'],
            'cheapest_wins': stats['cheapest_wins'],
            'is_winner': stats['deals'] > 0,
        })
    company_rows.sort(key=lambda row: (-row['deals'], -row['offered'], row['company_name']))

    winners = [row['company_name'] for row in company_rows if row['is_winner']]

    kpi = {
        'total_deals': total_deals,
        'insured_sum_total': totals['insured_sum'],
        'premium_total': totals['premium_total'],
        'avg_tariff_pct': _percent(totals['premium_year1_for_tariff'], totals['insured_sum_year1_for_tariff']),
        'winners_count': len(winners),
        'participants_count': len(company_rows),
        'comparable_deals': totals['comparable_deals'],
        'cheapest_deals': totals['cheapest_deals'],
        'cheapest_rate_pct': _percent(totals['cheapest_deals'], totals['comparable_deals']),
        'insufficient_data': totals['comparable_deals'] < INSUFFICIENT_COMPARABLE_DEALS,
    }

    # Помесячная динамика: топ-N СК по числу сделок за период + «Прочие».
    month_keys = sorted(monthly_deals.keys())
    top_companies = winners[:MONTHLY_TOP_COMPANIES]
    has_other = len(winners) > MONTHLY_TOP_COMPANIES
    series_names = top_companies + ([OTHER_COMPANIES_LABEL] if has_other else [])

    def _month_series(source, as_float):
        series = []
        for name in series_names:
            values = []
            for month_key in month_keys:
                if name == OTHER_COMPANIES_LABEL:
                    value = sum(
                        amount for company, amount in source[month_key].items()
                        if company not in top_companies
                    )
                else:
                    value = source[month_key].get(name, 0)
                values.append(float(value) if as_float else int(value))
            series.append({'label': name, 'data': values})
        return series

    monthly = {
        'colors': _series_colors(series_names),
        'labels': [_month_label(month_key) for month_key in month_keys],
        'deals': _month_series(monthly_deals, as_float=False),
        'insured_sum': _month_series(monthly_sums, as_float=True),
    }
    monthly_rows = [
        {
            'month_label': _month_label(month_key),
            'deals': sum(monthly_deals[month_key].values()),
            'insured_sum': sum(monthly_sums[month_key].values(), Decimal('0')),
            'leader': monthly_deals[month_key].most_common(1)[0][0],
        }
        for month_key in reversed(month_keys)
    ]

    type_columns = [value for value in INSURANCE_TYPE_ORDER if value in set(type_values)]
    type_columns += [value for value in _ordered_by_count(type_values) if value not in type_columns]
    heatmaps = {
        'branch': _build_heatmap(branch_counter, winners, _ordered_by_count(branch_values)),
        'insurance_type': _build_heatmap(type_counter, winners, type_columns),
    }

    data_quality_rows = [
        {
            'key': 'missing_variant',
            'label': 'Не выбран вариант франшизы — расчёт по варианту 1',
            'count': quality['missing_variant'],
        },
        {
            'key': 'not_comparable',
            'label': 'Цены нельзя сопоставить (меньше двух СК с ценой за те же годы) — сделка не входит в «выбрана самая дешёвая»',
            'count': quality['not_comparable'],
        },
        {
            'key': 'missing_insured_sum',
            'label': 'Нет страховой суммы у выбранной СК — сделка не входит в страховую сумму',
            'count': quality['missing_insured_sum'],
        },
        {
            'key': 'missing_premium',
            'label': 'Нет премии выбранной СК хотя бы за один год — сделка не входит в премию',
            'count': quality['missing_premium'],
        },
        {
            'key': 'missing_branch',
            'label': 'Филиал не указан',
            'count': quality['missing_branch'],
        },
    ]
    for row in data_quality_rows:
        row['rate_pct'] = _percent(row['count'], total_deals)

    charts = {'monthly': monthly}

    return {
        'kpi': kpi,
        'company_rows': company_rows,
        'monthly_rows': monthly_rows,
        'heatmaps': heatmaps,
        'data_quality_rows': data_quality_rows,
        'data_quality_issues': sum(row['count'] for row in data_quality_rows),
        'charts': charts,
    }

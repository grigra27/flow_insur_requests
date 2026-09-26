"""Карточка страховой компании (docs/improvement_plans/analytics_redesign_2026_09.md, этап 3).

Сделка — акцептованный свод (`completed_accepted`) с выбранной СК; период — по дате создания
свода, как на странице «Куда уходит бизнес». Правила денег те же
(docs/analytics_insurance_companies_metrics.md): страховая сумма — 1-й год выбранного
предложения, премия — все годы выбранного варианта, тариф — премия 1-го года / СС 1-го года.

Блоки:
- 3.1 объём: сделки, СС, премия, тариф по типам (и рынок для сравнения), доля СК, месяцы;
- 3.2 что пришло: филиалы, типы, вид лизинга по коду ДФА (§4.6), новое / б/у, возраст объекта,
  страховая сумма по диапазонам, марки (только заявки V2), крупнейшие лизингополучатели;
- 3.3 цена: участие → выигрыш, выигрыши ценой и не ценой, средний ранг и отрыв от минимума,
  «была самой дешёвой, но проиграла» и кому, разрез по филиалам. Цены сравниваются
  `_build_deal_price_row` (те же годы, вариант франшизы выбранной сделки);
- 3.4 воронка по статусам СК в своде (этап 2): запрошена → предложение / отказ / нет ответа →
  выигрыш; доля отказов по типам, филиалам, виду лизинга;
- 3.5 список сделок, где СК участвовала, со ссылками на своды.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from django.db.models import Min, Prefetch, Q

from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary, SummaryCompanyStatus

from .analytics_insurance_companies import (
    INSURANCE_TYPE_ORDER,
    NOT_SPECIFIED,
    _base_queryset,
    _month_label,
    _percent,
    _selected_money,
    _series_colors,
)

DFA_KIND_RE = re.compile(r'-(ЛА|ГА|ЛТ|ЛО)(?![А-ЯЁа-яё])')
DFA_KIND_LABELS = {
    'ЛА': 'Легковые (ЛА)',
    'ГА': 'Грузовые (ГА)',
    'ЛТ': 'Спецтехника (ЛТ)',
    'ЛО': 'Оборудование, имущество (ЛО)',
}
KIND_ORDER = list(DFA_KIND_LABELS.values())
INSURED_SUM_BUCKETS = [
    (Decimal('3000000'), 'до 3 млн'),
    (Decimal('10000000'), '3–10 млн'),
    (Decimal('30000000'), '10–30 млн'),
    (None, 'от 30 млн'),
]
AGE_ORDER = ['0–1 год', '2–4 года', '5 лет и старше']
TOP_CLIENTS = 10
TOP_BRANDS = 10
TOP_LIMIT_ROWS = 12


def dfa_kind(insurance_request) -> str:
    """Вид лизинга по коду в номере ДФА; если кода нет — по типу страхования, где он однозначен."""
    match = DFA_KIND_RE.search(insurance_request.dfa_number or '')
    if match:
        return DFA_KIND_LABELS[match.group(1)]
    if insurance_request.insurance_type == 'страхование спецтехники':
        return DFA_KIND_LABELS['ЛТ']
    if insurance_request.insurance_type == 'страхование имущества':
        return DFA_KIND_LABELS['ЛО']
    return NOT_SPECIFIED


def _condition(insurance_request) -> str:
    label = (insurance_request.condition_label or '').strip().lower()
    if label in ('новое', 'new'):
        return 'Новое'
    if label in ('б/у', 'бу', 'used'):
        return 'Б/у'
    return NOT_SPECIFIED


def _age(insurance_request, deal_year: int) -> str:
    match = re.search(r'(19|20)\d{2}', insurance_request.manufacturing_year or '')
    if not match:
        return NOT_SPECIFIED
    age = deal_year - int(match.group(0))
    if age < 0:
        return NOT_SPECIFIED
    if age <= 1:
        return AGE_ORDER[0]
    if age <= 4:
        return AGE_ORDER[1]
    return AGE_ORDER[2]


def _sum_bucket(insured_sum: Optional[Decimal]) -> str:
    if insured_sum is None:
        return NOT_SPECIFIED
    for limit, label in INSURED_SUM_BUCKETS:
        if limit is None or insured_sum < limit:
            return label
    return NOT_SPECIFIED


def _dimension_rows(counter: Counter, money: Dict[str, Decimal], order: Optional[List[str]] = None) -> List[Dict]:
    total = sum(counter.values())
    keys = [key for key in (order or []) if key in counter]
    keys += [key for key, _ in counter.most_common() if key not in keys and key != NOT_SPECIFIED]
    if NOT_SPECIFIED in counter:
        keys.append(NOT_SPECIFIED)
    return [
        {'label': key, 'deals': counter[key], 'share_pct': _percent(counter[key], total), 'insured_sum': money.get(key)}
        for key in keys
    ]


def _refusal_rows(stats: Dict[str, Counter], order: Optional[List[str]] = None) -> List[Dict]:
    keys = [key for key in (order or []) if key in stats]
    keys += sorted(key for key in stats if key not in keys)
    rows = []
    for key in keys:
        counts = stats[key]
        asked = counts['offered'] + counts['declined'] + counts['requested']
        rows.append({
            'label': key,
            'asked': asked,
            'offered': counts['offered'],
            'declined': counts['declined'],
            'no_answer': counts['requested'],
            'declined_pct': _percent(counts['declined'], asked),
        })
    return rows


def company_choices() -> List[str]:
    names = list(InsuranceCompany.objects.filter(is_active=True).order_by('sort_order', 'name')
                 .values_list('name', flat=True))
    extra = (InsuranceSummary.objects.filter(status='completed_accepted').exclude(selected_company__isnull=True)
             .exclude(selected_company='').values_list('selected_company', flat=True).distinct())
    return names + sorted(name for name in set(extra) if name not in names)


def company_exists(company: str) -> bool:
    return (
        InsuranceCompany.objects.filter(name=company).exists()
        or InsuranceOffer.objects.filter(company_name=company).exists()
    )


def build_card_payload(company: str, filters: Dict, price_row_builder: Callable) -> Dict:
    queryset = _base_queryset(filters['start_date'], filters['end_date']).select_related('request')
    if filters.get('branch'):
        queryset = queryset.filter(request__branch=filters['branch'])
    if filters.get('insurance_type'):
        queryset = queryset.filter(request__insurance_type=filters['insurance_type'])
    queryset = queryset.prefetch_related(
        Prefetch(
            'offers',
            queryset=InsuranceOffer.objects.filter(is_valid=True).order_by('company_name', 'insurance_year'),
            to_attr='valid_offers_prefetched',
        )
    ).order_by('created_at')

    market = {'deals': 0, 'insured_sum': Decimal('0'), 'premium_total': Decimal('0')}
    market_tariff = defaultdict(lambda: [Decimal('0'), Decimal('0')])  # тип → [премия 1-го года, СС]
    own = {'deals': 0, 'insured_sum': Decimal('0'), 'premium_total': Decimal('0'),
           'premium_year1': Decimal('0'), 'insured_sum_for_tariff': Decimal('0')}
    own_tariff = defaultdict(lambda: [Decimal('0'), Decimal('0')])
    monthly_all, monthly_own, monthly_sum = Counter(), Counter(), defaultdict(Decimal)

    dims = {name: Counter() for name in ('branch', 'type', 'kind', 'condition', 'age', 'sum_bucket', 'brand')}
    dims_money = {name: defaultdict(Decimal) for name in dims}
    v2_deals = 0
    clients = defaultdict(lambda: {'deals': 0, 'insured_sum': Decimal('0')})

    price = {'participated': 0, 'comparable': 0, 'won': 0, 'won_cheapest': 0, 'won_not_cheapest': 0,
             'won_not_comparable': 0, 'cheapest_lost': 0, 'ranks': [], 'deltas': []}
    lost_to, cheapest_lost_to = Counter(), Counter()
    branch_price = defaultdict(lambda: Counter())
    deal_rows = []

    for summary in queryset:
        insurance_request = summary.request
        offers_by_company = defaultdict(list)
        for offer in getattr(summary, 'valid_offers_prefetched', []):
            offers_by_company[offer.company_name].append(offer)
        winner = summary.selected_company.strip()
        variant = summary.selected_franchise_variant if summary.selected_franchise_variant in (1, 2) else 1
        winner_money = _selected_money(offers_by_company.get(winner, []), variant)
        insurance_type = (insurance_request.insurance_type or '').strip() or NOT_SPECIFIED
        branch = (insurance_request.branch or '').strip() or NOT_SPECIFIED
        month_key = summary.created_at.strftime('%Y-%m')

        market['deals'] += 1
        monthly_all[month_key] += 1
        if winner_money['insured_sum'] is not None:
            market['insured_sum'] += winner_money['insured_sum']
        if winner_money['premium_total'] is not None:
            market['premium_total'] += winner_money['premium_total']
        if winner_money['insured_sum'] is not None and winner_money['premium_year1'] is not None:
            market_tariff[insurance_type][0] += winner_money['premium_year1']
            market_tariff[insurance_type][1] += winner_money['insured_sum']

        won = winner == company
        participated = company in offers_by_company
        if not (won or participated):
            continue

        price_row = price_row_builder(summary) if participated else None
        point = None
        if price_row:
            point = next((p for p in price_row['points'] if p['company_name'] == company), None)

        if won:
            own['deals'] += 1
            monthly_own[month_key] += 1
            insured_sum = winner_money['insured_sum']
            if insured_sum is not None:
                own['insured_sum'] += insured_sum
                monthly_sum[month_key] += insured_sum
            if winner_money['premium_total'] is not None:
                own['premium_total'] += winner_money['premium_total']
            if insured_sum is not None and winner_money['premium_year1'] is not None:
                own['premium_year1'] += winner_money['premium_year1']
                own['insured_sum_for_tariff'] += insured_sum
                own_tariff[insurance_type][0] += winner_money['premium_year1']
                own_tariff[insurance_type][1] += insured_sum

            values = {
                'branch': branch,
                'type': insurance_type,
                'kind': dfa_kind(insurance_request),
                'condition': _condition(insurance_request),
                'age': _age(insurance_request, summary.created_at.year),
                'sum_bucket': _sum_bucket(insured_sum),
            }
            if (insurance_request.brand or '').strip():
                v2_deals += 1
                values['brand'] = insurance_request.brand.strip().upper()
            for name, value in values.items():
                dims[name][value] += 1
                if insured_sum is not None:
                    dims_money[name][value] += insured_sum
            client = clients[insurance_request.client_name.strip() or NOT_SPECIFIED]
            client['deals'] += 1
            if insured_sum is not None:
                client['insured_sum'] += insured_sum

        if participated:
            price['participated'] += 1
            branch_price[branch]['participated'] += 1
            if won:
                price['won'] += 1
                branch_price[branch]['won'] += 1
            else:
                lost_to[winner] += 1
            is_cheapest = False
            if point is not None:
                price['comparable'] += 1
                rank = 1 + sum(1 for other in price_row['points'] if other['total'] < point['total'])
                is_cheapest = point['total'] == price_row['min_total']
                price['ranks'].append(rank)
                if price_row['min_total'] > 0:
                    price['deltas'].append((point['total'] - price_row['min_total']) / price_row['min_total'] * 100)
                if won:
                    price['won_cheapest' if is_cheapest else 'won_not_cheapest'] += 1
                elif is_cheapest:
                    price['cheapest_lost'] += 1
                    cheapest_lost_to[winner] += 1
                    branch_price[branch]['cheapest_lost'] += 1
            elif won:
                price['won_not_comparable'] += 1

            own_offers = offers_by_company[company]
            own_money = _selected_money(own_offers, variant)
            deal_rows.append({
                'summary': summary,
                'request': insurance_request,
                'created_at': summary.created_at,
                'branch': branch,
                'insurance_type': insurance_type,
                'kind': dfa_kind(insurance_request),
                'won': won,
                'winner': winner,
                'own_total': point['total'] if point else own_money['premium_total'],
                'min_total': price_row['min_total'] if point else None,
                'rank': (1 + sum(1 for other in price_row['points'] if other['total'] < point['total'])) if point else None,
                'compared': len(price_row['points']) if point else None,
                'delta_pct': ((point['total'] - price_row['min_total']) / price_row['min_total'] * 100)
                if point and price_row['min_total'] > 0 else None,
                'is_cheapest': is_cheapest,
                'insured_sum': _selected_money(own_offers, variant)['insured_sum'],
                'years': len(own_offers),
            })

    month_keys = sorted(monthly_all)
    colors = _series_colors([company])
    tariff_rows = []
    type_keys = [key for key in INSURANCE_TYPE_ORDER if key in own_tariff or key in market_tariff]
    type_keys += sorted(key for key in set(own_tariff) | set(market_tariff) if key not in type_keys)
    for key in type_keys:
        own_premium, own_sum = own_tariff.get(key, (Decimal('0'), Decimal('0')))
        market_premium, market_sum = market_tariff.get(key, (Decimal('0'), Decimal('0')))
        if not own_sum and not market_sum:
            continue
        tariff_rows.append({
            'label': key,
            'deals': dims['type'].get(key, 0),
            'own_pct': _percent(own_premium, own_sum),
            'market_pct': _percent(market_premium, market_sum),
        })

    ranks, deltas = price['ranks'], price['deltas']
    price_kpi = {
        **{key: value for key, value in price.items() if key not in ('ranks', 'deltas')},
        'win_rate_pct': _percent(price['won'], price['participated']),
        'avg_rank': (Decimal(sum(ranks)) / len(ranks)) if ranks else None,
        'avg_delta_pct': (sum(deltas, Decimal('0')) / len(deltas)) if deltas else None,
        'lost': price['participated'] - price['won'],
    }
    branch_price_rows = sorted(
        ({'label': key, 'participated': counts['participated'], 'won': counts['won'],
          'win_rate_pct': _percent(counts['won'], counts['participated']), 'cheapest_lost': counts['cheapest_lost']}
         for key, counts in branch_price.items()),
        key=lambda row: (-row['participated'], row['label']),
    )

    deal_rows.sort(key=lambda row: row['created_at'], reverse=True)
    return {
        'company': company,
        'color': colors[company],
        'kpi': {
            'deals': own['deals'],
            'deals_share_pct': _percent(own['deals'], market['deals']),
            'insured_sum': own['insured_sum'],
            'insured_sum_share_pct': _percent(own['insured_sum'], market['insured_sum']),
            'premium_total': own['premium_total'],
            'premium_share_pct': _percent(own['premium_total'], market['premium_total']),
            'tariff_pct': _percent(own['premium_year1'], own['insured_sum_for_tariff']),
            'market_deals': market['deals'],
        },
        'tariff_rows': tariff_rows,
        'monthly_rows': [
            {
                'label': _month_label(key),
                'deals': monthly_own[key],
                'market_deals': monthly_all[key],
                'share_pct': _percent(monthly_own[key], monthly_all[key]),
                'insured_sum': monthly_sum.get(key, Decimal('0')),
            }
            for key in reversed(month_keys)
        ],
        'charts': {
            'labels': [_month_label(key) for key in month_keys],
            'deals': [monthly_own[key] for key in month_keys],
            'share': [float(_percent(monthly_own[key], monthly_all[key]) or 0) for key in month_keys],
            'color': colors[company],
        },
        'dimensions': [
            ('Филиалы', _dimension_rows(dims['branch'], dims_money['branch'])),
            ('Типы страхования', _dimension_rows(dims['type'], dims_money['type'], INSURANCE_TYPE_ORDER)),
            ('Вид лизинга (код ДФА)', _dimension_rows(dims['kind'], dims_money['kind'], KIND_ORDER)),
            ('Новое / б/у', _dimension_rows(dims['condition'], dims_money['condition'], ['Новое', 'Б/у'])),
            ('Возраст объекта', _dimension_rows(dims['age'], dims_money['age'], AGE_ORDER)),
            ('Страховая сумма', _dimension_rows(dims['sum_bucket'], dims_money['sum_bucket'],
                                                [label for _, label in INSURED_SUM_BUCKETS])),
        ],
        'brand_rows': _dimension_rows(dims['brand'], dims_money['brand'])[:TOP_BRANDS],
        'brand_coverage': {'with_brand': v2_deals, 'deals': own['deals']},
        'client_rows': sorted(
            ({'label': name, **data} for name, data in clients.items()),
            key=lambda row: (-row['insured_sum'], -row['deals'], row['label']),
        )[:TOP_CLIENTS],
        'price': price_kpi,
        'lost_to': lost_to.most_common(TOP_LIMIT_ROWS),
        'cheapest_lost_to': cheapest_lost_to.most_common(TOP_LIMIT_ROWS),
        'branch_price_rows': branch_price_rows,
        'deal_rows': deal_rows,
        'funnel': build_funnel(company, filters),
    }


def build_funnel(company: str, filters: Dict) -> Dict:
    """Воронка по статусам СК в сводах (этап 2): все своды периода, не только акцептованные."""
    # Своды, где статусы действительно проставлены: новые (обязательные), восстановленные строки и старые
    # своды, где сотрудник сам отмечал статусы. Старый свод, у которого строка «предложение» появилась
    # только автоматически при догрузке предложения, не учитывается — отказов у него нет, воронка бы исказилась.
    engaged_legacy = SummaryCompanyStatus.objects.filter(
        summary__company_statuses_required=False,
        status__in=SummaryCompanyStatus.MANUAL_STATUSES,
    ).values('summary_id')
    rows = SummaryCompanyStatus.objects.filter(company__name=company).filter(
        Q(summary__company_statuses_required=True) | Q(restored=True) | Q(summary_id__in=engaged_legacy)
    ).select_related('summary__request')
    if filters.get('start_date'):
        rows = rows.filter(summary__created_at__date__gte=filters['start_date'])
    if filters.get('end_date'):
        rows = rows.filter(summary__created_at__date__lte=filters['end_date'])
    if filters.get('branch'):
        rows = rows.filter(summary__request__branch=filters['branch'])
    if filters.get('insurance_type'):
        rows = rows.filter(summary__request__insurance_type=filters['insurance_type'])

    counts = Counter()
    by_type, by_branch, by_kind = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    restored = 0
    for row in rows:
        counts[row.status] += 1
        restored += row.restored
        if row.status == 'offered' and row.summary.status == 'completed_accepted' \
                and (row.summary.selected_company or '').strip() == company:
            counts['won'] += 1
        insurance_request = row.summary.request
        for stats, key in (
            (by_type, (insurance_request.insurance_type or '').strip() or NOT_SPECIFIED),
            (by_branch, (insurance_request.branch or '').strip() or NOT_SPECIFIED),
            (by_kind, dfa_kind(insurance_request)),
        ):
            stats[key][row.status] += 1

    asked = counts['offered'] + counts['declined'] + counts['requested']
    started = SummaryCompanyStatus.objects.filter(summary__company_statuses_required=True).aggregate(
        first=Min('summary__created_at'))['first']
    return {
        'has_data': asked > 0,
        'summaries': sum(counts[key] for key in ('offered', 'declined', 'requested', 'not_requested', 'undefined')),
        'asked': asked,
        'offered': counts['offered'],
        'declined': counts['declined'],
        'no_answer': counts['requested'],
        'not_requested': counts['not_requested'],
        'undefined': counts['undefined'],
        'won': counts['won'],
        'offered_pct': _percent(counts['offered'], asked),
        'declined_pct': _percent(counts['declined'], asked),
        'no_answer_pct': _percent(counts['requested'], asked),
        'won_pct': _percent(counts['won'], counts['offered']),
        'restored': restored,
        'tracking_started': started,
        'by_type': _refusal_rows(by_type, INSURANCE_TYPE_ORDER),
        'by_branch': _refusal_rows(by_branch),
        'by_kind': _refusal_rows(by_kind, KIND_ORDER),
    }

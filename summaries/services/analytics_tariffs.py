"""Аналитика тарифов по классам, маркам и видам машин (docs/improvement_plans/tariffs_analytics_2026_09.md).

Точка данных — предложение страховой компании (все предложения, не только выигравшие), тариф 1-го года:
- режим «без франшизы» (по умолчанию) — премия-1 / страховая сумма при франшизе-1 = 0;
- режим «с франшизой» — каждый вариант с франшизой > 0 (премия варианта / страховая сумма).
Отсекаются явные ошибки данных — тариф вне 0,05–20%. Период — по дате создания свода.

Группа объекта: для спецтехники — вид машины, для остальных классов — марка (справочник техники,
`insurance_requests.object_catalog`). Статистика — медиана и «обычный диапазон» (25–75-й процентили);
меньше MIN_REQUESTS заявок — «мало данных». Это описание прошлого, а не прогноз цены.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from insurance_requests.object_catalog import BRANDS, OBJECT_CLASS_LABELS, OBJECT_CLASSES, SPECIAL, request_object_text
from summaries.models import InsuranceOffer

MODE_NO_FRANCHISE = 'no_franchise'
MODE_FRANCHISE = 'franchise'
MODES = [(MODE_NO_FRANCHISE, 'Без франшизы'), (MODE_FRANCHISE, 'С франшизой')]
TARIFF_MIN = 0.05
TARIFF_MAX = 20.0
MIN_REQUESTS = 3        # меньше — «мало данных»
MIN_CELL_OFFERS = 2     # для ячейки «группа × страховая»
# «Дешевле всех» — только при устойчивых данных: ≥ 3 предложений из ≥ 2 разных заявок; «другое» — не страховая.
CHEAPEST_MIN_OFFERS = 3
CHEAPEST_MIN_REQUESTS = 2
OTHER_COMPANY = 'другое'
HEATMAP_ROWS = 15
UNKNOWN_BRAND = 'Марка не узнана'
SUM_RANGES = [
    ('lt3', 'до 3 млн', None, 3_000_000),
    ('3to6', '3–6 млн', 3_000_000, 6_000_000),
    ('6to15', '6–15 млн', 6_000_000, 15_000_000),
    ('gte15', 'от 15 млн', 15_000_000, None),
]
CONDITIONS = [('new', 'Новое'), ('used', 'Б/у')]
DIMENSION_BRAND = 'brand'
DIMENSION_KIND = 'kind'
_GENERIC_WORDS = {'автомобиль', 'а/м', 'автофургон', 'новый', 'новое', 'б/у', 'бу', 'б-у', 'грузовой', 'легковой',
                  'седельный', 'тягач', 'самосвал', 'экскаватор', 'гусеничный', 'колесный', 'колёсный', 'и', 'с', 'на',
                  'модель', 'марки', '-', '—', 'ооо', 'автобус'}


@dataclass
class TariffPoint:
    offer_id: int
    summary_id: int
    request_id: int
    company: str
    tariff: float
    insured_sum: float
    premium: float
    franchise: float
    created_at: datetime
    object_class: str
    brand: str
    machine_kind: str
    condition: str
    branch: str
    insurance_type: str
    won: bool
    object_text: str       # для показа (краткое описание объекта)
    catalog_text: str      # полный текст объекта — для поиска модели после марки
    client: str
    dfa_number: str

    @property
    def dimension(self) -> str:
        return DIMENSION_KIND if self.object_class == SPECIAL else DIMENSION_BRAND

    @property
    def group(self) -> str:
        if self.object_class == SPECIAL:
            return self.machine_kind or 'Прочая спецтехника'
        return self.brand or UNKNOWN_BRAND


def _condition(insurance_request) -> str:
    label = (insurance_request.condition_label or '').strip().lower()
    if label in ('новое', 'new'):
        return 'new'
    if label in ('б/у', 'бу', 'used'):
        return 'used'
    return ''


def _points_from_offer(offer, mode: str) -> Iterable[Tuple[float, float, float]]:
    """(тариф, премия, франшиза) для предложения в выбранном режиме."""
    insured_sum = float(offer.insurance_sum or 0)
    if insured_sum <= 0:
        return []
    variants = [(offer.franchise_1, offer.premium_with_franchise_1), (offer.franchise_2, offer.premium_with_franchise_2)]
    result = []
    for index, (franchise, premium) in enumerate(variants):
        franchise, premium = float(franchise or 0), float(premium or 0)
        if premium <= 0:
            continue
        if mode == MODE_NO_FRANCHISE and (index != 0 or franchise != 0):
            continue
        if mode == MODE_FRANCHISE and franchise <= 0:
            continue
        tariff = premium / insured_sum * 100
        if TARIFF_MIN <= tariff <= TARIFF_MAX:
            result.append((tariff, premium, franchise))
    return result


def collect_points(filters: Dict, *, exclude_summary_id: Optional[int] = None) -> List[TariffPoint]:
    """Точки тарифа по фильтрам: период, тип, класс, группа, новое / б/у, диапазон СС, филиал, режим."""
    queryset = InsuranceOffer.objects.filter(is_valid=True, insurance_year=1, insurance_sum__gt=0) \
        .select_related('summary__request')
    if filters.get('start_date'):
        queryset = queryset.filter(summary__created_at__date__gte=filters['start_date'])
    if filters.get('end_date'):
        queryset = queryset.filter(summary__created_at__date__lte=filters['end_date'])
    if filters.get('branch'):
        queryset = queryset.filter(summary__request__branch=filters['branch'])
    if filters.get('insurance_type'):
        queryset = queryset.filter(summary__request__insurance_type=filters['insurance_type'])
    if filters.get('object_class'):
        queryset = queryset.filter(summary__request__object_class=filters['object_class'])
    if exclude_summary_id:
        queryset = queryset.exclude(summary_id=exclude_summary_id)
    sum_range = dict((key, (low, high)) for key, _, low, high in SUM_RANGES).get(filters.get('sum_range') or '')
    if sum_range:
        low, high = sum_range
        if low is not None:
            queryset = queryset.filter(insurance_sum__gte=low)
        if high is not None:
            queryset = queryset.filter(insurance_sum__lt=high)

    mode = filters.get('mode') or MODE_NO_FRANCHISE
    points = []
    for offer in queryset:
        summary, insurance_request = offer.summary, offer.summary.request
        condition = _condition(insurance_request)
        if filters.get('condition') and condition != filters['condition']:
            continue
        won = summary.status == 'completed_accepted' and (summary.selected_company or '').strip() == offer.company_name
        for tariff, premium, franchise in _points_from_offer(offer, mode):
            points.append(TariffPoint(
                offer_id=offer.pk, summary_id=summary.pk, request_id=insurance_request.pk, company=offer.company_name,
                tariff=tariff, insured_sum=float(offer.insurance_sum), premium=premium, franchise=franchise,
                created_at=summary.created_at, object_class=insurance_request.object_class or 'other',
                brand=insurance_request.object_brand, machine_kind=insurance_request.machine_kind,
                condition=condition, branch=(insurance_request.branch or '').strip(),
                insurance_type=insurance_request.insurance_type or '', won=won,
                object_text=insurance_request.object_summary or request_object_text(insurance_request),
                catalog_text=request_object_text(insurance_request), client=insurance_request.client_name,
                dfa_number=insurance_request.dfa_number or '',
            ))
    group = filters.get('group')
    if group:
        dimension = filters.get('dimension') or DIMENSION_BRAND
        points = [point for point in points if point.dimension == dimension and point.group == group]
    return points


def stats(points: List[TariffPoint]) -> Dict:
    values = sorted(point.tariff for point in points)
    requests = len({point.request_id for point in points})
    if not values:
        return {'offers': 0, 'requests': 0, 'median': None, 'p25': None, 'p75': None, 'min': None, 'max': None,
                'low_data': True}
    if len(values) >= 2:
        p25, _, p75 = statistics.quantiles(values, n=4, method='inclusive')
    else:
        p25 = p75 = values[0]
    return {
        'offers': len(values),
        'requests': requests,
        'median': statistics.median(values),
        'p25': p25,
        'p75': p75,
        'min': values[0],
        'max': values[-1],
        'low_data': requests < MIN_REQUESTS,
    }


def company_rows(points: List[TariffPoint]) -> List[Dict]:
    """Страховые по медианному тарифу (дешёвые сверху)."""
    by_company = defaultdict(list)
    for point in points:
        by_company[point.company].append(point)
    rows = []
    for company, company_points in by_company.items():
        row = {'company': company, **stats(company_points),
               'wins': len({point.summary_id for point in company_points if point.won})}
        row['low_data'] = (row['offers'] < CHEAPEST_MIN_OFFERS or row['requests'] < CHEAPEST_MIN_REQUESTS
                           or company == OTHER_COMPANY)
        rows.append(row)
    rows.sort(key=lambda row: (row['low_data'], row['median'], row['company']))
    return rows


def cheapest_companies(points: List[TariffPoint], limit: int = 1) -> List[Dict]:
    return [row for row in company_rows(points) if not row['low_data']][:limit]


def _group_rows(points: List[TariffPoint]) -> List[Dict]:
    groups = defaultdict(list)
    for point in points:
        groups[(point.dimension, point.group)].append(point)
    rows = []
    for (dimension, group), group_points in groups.items():
        classes = Counter(point.object_class for point in group_points)
        cheapest = cheapest_companies(group_points)
        rows.append({
            'dimension': dimension,
            'group': group,
            'class_label': OBJECT_CLASS_LABELS.get(classes.most_common(1)[0][0], ''),
            **stats(group_points),
            'cheapest': cheapest[0] if cheapest else None,
        })
    rows.sort(key=lambda row: (-row['requests'], -row['offers'], row['group']))
    return rows


def _class_rows(points: List[TariffPoint]) -> List[Dict]:
    by_class = defaultdict(list)
    for point in points:
        by_class[point.object_class].append(point)
    rows = []
    for key, label in OBJECT_CLASSES:
        if key not in by_class:
            continue
        cheapest = cheapest_companies(by_class[key])
        rows.append({'key': key, 'label': label, **stats(by_class[key]), 'cheapest': cheapest[0] if cheapest else None})
    return rows


def _heatmap(points: List[TariffPoint], group_rows: List[Dict]) -> Dict:
    """Медиана «группа × страховая» для групп с достаточными данными; цвет — относительно медианы группы."""
    rows_meta = [row for row in group_rows if not row['low_data'] and row['group'] != UNKNOWN_BRAND][:HEATMAP_ROWS]
    company_counts = Counter(point.company for point in points)
    columns = [company for company, _ in company_counts.most_common()]
    cells = defaultdict(list)
    for point in points:
        cells[(point.dimension, point.group, point.company)].append(point.tariff)
    rows = []
    for meta in rows_meta:
        row_cells = []
        for company in columns:
            values = cells.get((meta['dimension'], meta['group'], company), [])
            if len(values) >= MIN_CELL_OFFERS:
                median = statistics.median(values)
                row_cells.append({'company': company, 'median': median, 'offers': len(values),
                                  'ratio': median / meta['median'] if meta['median'] else None})
            else:
                row_cells.append({'company': company, 'median': None, 'offers': len(values), 'ratio': None})
        rows.append({'group': meta['group'], 'dimension': meta['dimension'], 'median': meta['median'], 'cells': row_cells})
    used_columns = [index for index, _ in enumerate(columns) if any(row['cells'][index]['median'] is not None for row in rows)]
    return {
        'columns': [columns[index] for index in used_columns],
        'rows': [{**row, 'cells': [row['cells'][index] for index in used_columns]} for row in rows],
    }


def with_bars(rows: List[Dict]) -> List[Dict]:
    """Полоска «обычный диапазон + медиана» на общей шкале таблицы (проценты ширины)."""
    scale = max((row['p75'] for row in rows if row.get('p75') is not None), default=0) * 1.1
    for row in rows:
        if scale and row.get('median') is not None:
            row['bar'] = {
                'left': round(row['p25'] / scale * 100, 1),
                'width': max(round((row['p75'] - row['p25']) / scale * 100, 1), 0.8),
                'median': round(row['median'] / scale * 100, 1),
            }
        else:
            row['bar'] = None
    return rows


def build_payload(filters: Dict) -> Dict:
    points = collect_points(filters)
    group_rows = with_bars(_group_rows(points))
    return {
        'kpi': {**stats(points), 'companies': len({point.company for point in points})},
        'class_rows': with_bars(_class_rows(points)),
        'group_rows': group_rows,
        'heatmap': _heatmap(points, group_rows),
        'points': points,
    }


def _quarter(value: datetime) -> str:
    return f'{value.year} · {(value.month - 1) // 3 + 1} кв.'


def _model_token(point: TariffPoint) -> str:
    """Модель — первое значимое слово после марки в описании (для марок) или марка (для видов машин)."""
    if point.dimension == DIMENSION_KIND:
        return point.brand or UNKNOWN_BRAND
    text = point.catalog_text or point.object_text or ''
    variants = next((aliases for brand, aliases, _ in BRANDS if brand == point.brand), ())
    lowered = text.lower()
    start = None
    for variant in sorted(variants, key=len, reverse=True):
        match = re.search(r'(?<![0-9a-zа-яё])' + re.escape(variant) + r'(?![a-zа-яё])', lowered)
        if match and (start is None or match.end() < start):
            start = match.end()
    if start is None:
        return ''
    for word in re.findall(r'[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё\-]*', text[start:])[:3]:
        if word.lower() not in _GENERIC_WORDS:
            return word.upper()
    return ''


def build_group_payload(filters: Dict, dimension: str, group: str) -> Dict:
    points = collect_points({**filters, 'dimension': dimension, 'group': group})
    quarters = defaultdict(list)
    models = defaultdict(list)
    conditions = defaultdict(list)
    for point in points:
        quarters[_quarter(point.created_at)].append(point)
        model = _model_token(point)
        if model:
            models[model].append(point)
        conditions[point.condition or ''].append(point)
    model_rows = sorted(
        ({'label': label, **stats(model_points)} for label, model_points in models.items()),
        key=lambda row: (-row['requests'], row['label']),
    )
    return {
        'dimension': dimension,
        'group': group,
        'kpi': stats(points),
        'company_rows': with_bars(company_rows(points)),
        'quarter_rows': [{'label': key, **stats(quarters[key])} for key in sorted(quarters)],
        'model_rows': [row for row in model_rows if row['requests'] >= 2],
        'condition_rows': [
            {'label': label, **stats(conditions[key])} for key, label in CONDITIONS + [('', 'Не указано')]
            if conditions.get(key)
        ],
        'points': sorted(points, key=lambda point: (point.created_at, point.company), reverse=True),
    }


def hint_for_request(insurance_request, *, exclude_summary_id: Optional[int] = None) -> Optional[Dict]:
    """Ориентир по тарифу для карточки свода: марка (вид машины), а при нехватке данных — класс.

    Режим «без франшизы», весь период, без текущего свода. None — если класс объекта не определён.
    """
    object_class = insurance_request.object_class
    if not object_class:
        return None
    class_points = collect_points({'object_class': object_class}, exclude_summary_id=exclude_summary_id)
    if object_class == SPECIAL:
        dimension, group = DIMENSION_KIND, insurance_request.machine_kind or 'Прочая спецтехника'
    else:
        dimension, group = DIMENSION_BRAND, insurance_request.object_brand
    group_points = [p for p in class_points if p.dimension == dimension and p.group == group] if group else []
    group_stats = stats(group_points)
    if group and not group_stats['low_data']:
        level, label, points = 'group', group, group_points
    else:
        level, label, points = 'class', OBJECT_CLASS_LABELS.get(object_class, ''), class_points
    level_stats = stats(points)
    if not level_stats['offers']:
        return None
    return {
        'level': level,
        'label': label,
        'dimension': dimension,
        'group': group,
        'group_requests': group_stats['requests'],
        'class_label': OBJECT_CLASS_LABELS.get(object_class, ''),
        **level_stats,
        'cheapest': cheapest_companies(points, limit=3),
        'companies': company_rows(points),
    }

"""Аналитика ручных правок оператора над распознаванием парсера V2.

Источник данных:
- RequestFieldEdit — нормализованные строки правок (что и как правили);
- InsuranceRequest.parser_confidence / manual_edits_count — денормализованные
  показатели для долей и динамики без разбора JSON.

Популяция «V2-заявок» определяется как заявки с проставленной
parser_confidence (его выставляет только новый загрузчик при создании) —
это кросс-СУБД и не требует JSON-запросов.
"""
from datetime import timedelta

from django.db.models import Avg, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from insurance_requests.models import InsuranceRequest, RequestFieldEdit

from . import parser_edit_reasons

DEFAULT_DAYS = 90
MAX_DAYS = 3650
TOP_LIMIT = 20
EXAMPLES_LIMIT = 50

EDIT_TYPE_LABELS = dict(RequestFieldEdit.EDIT_TYPE_CHOICES)
SCOPE_LABELS = dict(RequestFieldEdit.SCOPE_CHOICES)

# Подписи сегментов шаблона заявки (см. core.excel_utils.ExcelReader).
FORMAT_LABELS = {
    'casco_equipment': 'КАСКО/спецтехника',
    'property': 'Имущество',
    'unknown': 'Не указан',
}
TYPE_LABELS = {
    'legal_entity': 'Юрлицо',
    'individual_entrepreneur': 'ИП',
    'unknown': 'Не указан',
}


def parse_filters(params):
    """Разобрать GET-параметры периода (?days=N) и дрилл-дауна (?field=…)."""
    try:
        days = int(params.get('days', DEFAULT_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    days = max(1, min(days, MAX_DAYS))
    field = (params.get('field') or '').strip()[:100]
    return {
        'days': days,
        'since': timezone.now() - timedelta(days=days),
        'field': field,
    }


def _segment(requests_values, key_name, labels):
    """Сегментировать V2-заявки по полю шаблона (формат/тип).

    Считаем по денормализованному manual_edits_count, без JSON-запросов:
    сколько заявок в сегменте, в скольких были правки на входе и какова доля
    ошибок парсера (= доля заявок, где оператор что-то поправил).
    """
    buckets = {}
    for row in requests_values:
        ad = row['additional_data'] or {}
        value = ad.get(key_name) or 'unknown'
        mec = row['manual_edits_count'] or 0
        bucket = buckets.setdefault(value, {'requests': 0, 'with_edits': 0, 'edits': 0})
        bucket['requests'] += 1
        bucket['edits'] += mec
        if mec > 0:
            bucket['with_edits'] += 1
    out = []
    for value, bucket in buckets.items():
        requests = bucket['requests']
        out.append({
            'value': value,
            'label': labels.get(value, value),
            'requests': requests,
            'with_edits': bucket['with_edits'],
            'edits': bucket['edits'],
            'error_rate_percent': round(bucket['with_edits'] / requests * 100, 1) if requests else 0.0,
            'avg_edits': round(bucket['edits'] / requests, 2) if requests else 0.0,
        })
    return sorted(out, key=lambda r: (-r['error_rate_percent'], -r['requests']))


def _by_version(requests_values):
    """Доля заявок без правок по версии парсера (additional_data.parser_v2.version).

    Главный способ увидеть, помогло ли исправление парсера: версию поднимают при
    каждом изменении логики разбора (см. PARSER_V2_VERSION).
    """
    buckets = {}
    for row in requests_values:
        parser_v2 = (row['additional_data'] or {}).get('parser_v2') or {}
        version = parser_v2.get('version') or 'не записана'
        edits = row['manual_edits_count'] or 0
        bucket = buckets.setdefault(version, {
            'requests': 0, 'with_edits': 0, 'edits': 0, 'builds': set(), 'first': None, 'last': None,
        })
        bucket['requests'] += 1
        bucket['edits'] += edits
        bucket['with_edits'] += 1 if edits else 0
        if parser_v2.get('build'):
            bucket['builds'].add(parser_v2['build'])
        created = row['created_at']
        bucket['first'] = created if bucket['first'] is None else min(bucket['first'], created)
        bucket['last'] = created if bucket['last'] is None else max(bucket['last'], created)
    rows = []
    for version, bucket in buckets.items():
        requests = bucket['requests']
        rows.append({
            'version': version,
            'requests': requests,
            'with_edits': bucket['with_edits'],
            'clean_percent': round((requests - bucket['with_edits']) / requests * 100, 1),
            'avg_edits': round(bucket['edits'] / requests, 2),
            'builds': len(bucket['builds']),
            'first': bucket['first'],
            'last': bucket['last'],
        })
    return sorted(rows, key=lambda row: row['first'], reverse=True)


def _reasons_and_forecast(request_values, edits_qs):
    """Правки по причинам (5.3) и прогноз доли заявок без правок после исправлений этапа 6.

    Считается по строкам RequestFieldEdit заявок периода: заявка «с правками», если у неё
    есть хотя бы одна правка на входе (общие правки партии записаны на первую заявку).
    """
    file_names = {
        row['pk']: parser_edit_reasons.source_file_name(row['additional_data']) for row in request_values
    }
    reasons = {}
    kinds_by_request = {}
    for request_id, field_name, field_label in edits_qs.filter(request_id__in=file_names).values_list(
        'request_id', 'field_name', 'field_label'
    ):
        key = parser_edit_reasons.classify(field_name, file_names.get(request_id, ''))
        bucket = reasons.setdefault(key, {'edits': 0, 'requests': set(), 'fields': {}})
        bucket['edits'] += 1
        bucket['requests'].add(request_id)
        bucket['fields'][field_label or field_name] = bucket['fields'].get(field_label or field_name, 0) + 1
        kinds_by_request.setdefault(request_id, set()).add(parser_edit_reasons.REASONS[key]['kind'])

    rows = []
    for key, bucket in reasons.items():
        info = parser_edit_reasons.reason_info(key)
        top_fields = sorted(bucket['fields'].items(), key=lambda item: -item[1])[:3]
        rows.append({
            **info,
            'edits': bucket['edits'],
            'requests': len(bucket['requests']),
            'fields': ', '.join(f'{label} {count}' for label, count in top_fields),
        })
    kind_order = {'parser': 0, 'scenario': 1, 'other': 2}
    rows.sort(key=lambda row: (kind_order[row['kind']], -row['edits']))

    total = len(file_names)
    edited = len(kinds_by_request)
    after_parser_fix = sum(1 for kinds in kinds_by_request.values() if kinds & {'scenario', 'other'})
    after_all_fixes = sum(1 for kinds in kinds_by_request.values() if 'other' in kinds)

    def _share(with_edits):
        return round((total - with_edits) / total * 100, 1) if total else None

    forecast = {
        'total': total,
        'clean_now': total - edited,
        'clean_now_percent': _share(edited),
        'clean_after_parser_percent': _share(after_parser_fix),
        'clean_after_all_percent': _share(after_all_fixes),
        'seized_requests': sum(1 for name in file_names.values() if parser_edit_reasons.is_seized_file(name)),
    }
    return rows, forecast


def _operator_label(row):
    last_name = (row.get('request__created_by__last_name') or '').strip()
    first_name = (row.get('request__created_by__first_name') or '').strip()
    username = row.get('request__created_by__username')
    full = f"{last_name} {first_name}".strip()
    return full or username or 'Не указан'


def _percent(value):
    return round(value * 100, 1) if value is not None else None


def build_payload(filters):
    """Собрать полный payload дашборда правок за выбранный период."""
    since = filters['since']

    v2_requests = InsuranceRequest.objects.filter(
        parser_confidence__isnull=False, created_at__gte=since
    )
    total_v2 = v2_requests.count()
    requests_with_edits = v2_requests.filter(manual_edits_count__gt=0).count()

    # Только правки на входе (превью): правки после создания — отдельная страница (scope='post').
    edits = RequestFieldEdit.objects.filter(created_at__gte=since, scope__in=RequestFieldEdit.INTAKE_SCOPES)
    total_edits = edits.count()

    # Топ полей с метрикой точности парсера: доля заявок, где оператор
    # поправил поле на входе (error_rate). Это и есть основной сигнал
    # «где парсер чаще всего ошибается».
    top_fields = [
        {
            'field_name': row['field_name'],
            'field_label': row['field_label'] or row['field_name'],
            'count': row['count'],
            'requests': row['requests'],
            'error_rate_percent': round(row['requests'] / total_v2 * 100, 1) if total_v2 else 0.0,
        }
        for row in edits.values('field_name', 'field_label')
        .annotate(count=Count('id'), requests=Count('request', distinct=True))
        .order_by('-requests', '-count', 'field_name')[:TOP_LIMIT]
    ]

    # По типу правки и области.
    by_type = [
        {'type': row['edit_type'], 'label': EDIT_TYPE_LABELS.get(row['edit_type'], row['edit_type']),
         'count': row['count']}
        for row in edits.values('edit_type').annotate(count=Count('id')).order_by('-count')
    ]
    by_scope = [
        {'scope': row['scope'], 'label': SCOPE_LABELS.get(row['scope'], row['scope']),
         'count': row['count']}
        for row in edits.values('scope').annotate(count=Count('id')).order_by('-count')
    ]

    # По филиалам.
    by_branch = [
        {
            'branch': row['request__branch'] or 'Не указан',
            'count': row['count'],
            'requests': row['requests'],
        }
        for row in edits.values('request__branch')
        .annotate(count=Count('id'), requests=Count('request', distinct=True))
        .order_by('-count')[:TOP_LIMIT]
    ]

    # По операторам (кто создавал заявку из превью).
    by_operator = [
        {'operator': _operator_label(row), 'count': row['count']}
        for row in edits.values(
            'request__created_by__username',
            'request__created_by__last_name',
            'request__created_by__first_name',
        ).annotate(count=Count('id')).order_by('-count')[:TOP_LIMIT]
    ]

    # Помесячная динамика: число правок + средняя уверенность парсера.
    monthly_edits = {
        row['month']: row['count']
        for row in edits.annotate(month=TruncMonth('created_at'))
        .values('month').annotate(count=Count('id'))
    }
    monthly_conf = {
        row['month']: row
        for row in v2_requests.annotate(month=TruncMonth('created_at'))
        .values('month').annotate(avg=Avg('parser_confidence'), requests=Count('id'))
    }
    months = sorted(set(monthly_edits) | set(monthly_conf))
    timeline = []
    for month in months:
        conf = monthly_conf.get(month, {})
        timeline.append({
            'month': month,
            'label': month.strftime('%m.%Y') if month else '—',
            'edits': monthly_edits.get(month, 0),
            'requests': conf.get('requests', 0),
            'avg_confidence_percent': _percent(conf.get('avg')),
        })

    # Сегментация по шаблону заявки: на каком формате/типе парсер слабее.
    request_values = list(v2_requests.values('pk', 'additional_data', 'manual_edits_count', 'created_at'))
    by_reason, forecast = _reasons_and_forecast(request_values, edits)
    by_format = _segment(request_values, 'application_format', FORMAT_LABELS)
    by_app_type = _segment(request_values, 'application_type', TYPE_LABELS)

    # Дрилл-даун в конкретное поле: примеры пар «распознано → исправлено»
    # как готовый материал для тест-кейсов парсера.
    selected_field = filters.get('field')
    field_examples = []
    selected_field_label = ''
    if selected_field:
        example_qs = (
            edits.filter(field_name=selected_field)
            .order_by('-created_at')[:EXAMPLES_LIMIT]
        )
        for edit in example_qs:
            selected_field_label = edit.field_label or selected_field
            field_examples.append({
                'request_id': edit.request_id,
                'original_value': edit.original_value,
                'modified_value': edit.modified_value,
                'edit_type': edit.edit_type,
                'edit_type_label': EDIT_TYPE_LABELS.get(edit.edit_type, edit.edit_type),
                'created_at': edit.created_at,
            })

    avg_conf = v2_requests.aggregate(avg=Avg('parser_confidence'))['avg']
    avg_conf_with = v2_requests.filter(manual_edits_count__gt=0).aggregate(
        avg=Avg('parser_confidence'))['avg']
    avg_conf_without = v2_requests.filter(manual_edits_count=0).aggregate(
        avg=Avg('parser_confidence'))['avg']

    return {
        'filters': filters,
        'totals': {
            'total_v2': total_v2,
            'requests_with_edits': requests_with_edits,
            'requests_clean': total_v2 - requests_with_edits,
            'edited_share_percent': round(requests_with_edits / total_v2 * 100, 1) if total_v2 else 0.0,
            'total_edits': total_edits,
            'avg_edits_per_request': round(total_edits / total_v2, 2) if total_v2 else 0.0,
            'avg_confidence_percent': _percent(avg_conf),
            'avg_confidence_with_edits_percent': _percent(avg_conf_with),
            'avg_confidence_without_edits_percent': _percent(avg_conf_without),
        },
        'top_fields': top_fields,
        'by_type': by_type,
        'by_scope': by_scope,
        'by_branch': by_branch,
        'by_operator': by_operator,
        'by_format': by_format,
        'by_app_type': by_app_type,
        'by_version': _by_version(request_values),
        'by_reason': by_reason,
        'forecast': forecast,
        'timeline': timeline,
        'selected_field': selected_field,
        'selected_field_label': selected_field_label,
        'field_examples': field_examples,
    }

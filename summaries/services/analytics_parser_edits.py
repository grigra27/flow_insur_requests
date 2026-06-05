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

DEFAULT_DAYS = 90
MAX_DAYS = 3650
TOP_LIMIT = 20

EDIT_TYPE_LABELS = dict(RequestFieldEdit.EDIT_TYPE_CHOICES)
SCOPE_LABELS = dict(RequestFieldEdit.SCOPE_CHOICES)


def parse_filters(params):
    """Разобрать GET-параметры периода (?days=N)."""
    try:
        days = int(params.get('days', DEFAULT_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    days = max(1, min(days, MAX_DAYS))
    return {'days': days, 'since': timezone.now() - timedelta(days=days)}


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

    edits = RequestFieldEdit.objects.filter(created_at__gte=since)
    total_edits = edits.count()

    # Топ часто правимых полей.
    top_fields = [
        {
            'field_name': row['field_name'],
            'field_label': row['field_label'] or row['field_name'],
            'count': row['count'],
        }
        for row in edits.values('field_name', 'field_label')
        .annotate(count=Count('id'))
        .order_by('-count', 'field_name')[:TOP_LIMIT]
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
        'timeline': timeline,
    }

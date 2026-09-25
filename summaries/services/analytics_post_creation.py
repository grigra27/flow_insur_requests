"""Аналитика правок ПОСЛЕ создания заявки (контроль операторов и процесса).

Источник — RequestFieldEdit(scope='post'): правки уже сохранённой V2-заявки, которые
пишет сигнал `insurance_requests.signals.record_post_creation_edits` (с 2026-09,
история до этого перенесена из журнала easy-audit командой import_post_creation_edits).
Раньше страница читала CRUDEvent напрямую и теряла историю вместе с чисткой журнала
(docs/improvement_plans/analytics_redesign_2026_09.md, задача 5.1).

- операционный дрейф — что и кто меняет после создания;
- «подозрения на пропущенную ошибку парсера» — поля, которые НЕ правили на входе
  (оператор принял значение парсера), но изменили позже. Это либо ошибка парсера,
  не замеченная при проверке, либо бизнес-изменение — список для ручной разметки.
"""
from datetime import timedelta

from django.utils import timezone

from insurance_requests.models import RequestFieldEdit

DEFAULT_DAYS = 90
MAX_DAYS = 3650
TOP_LIMIT = 20
SUSPECTED_LIMIT = 50


def parse_filters(params):
    """Разобрать GET-параметр периода (?days=N)."""
    try:
        days = int(params.get('days', DEFAULT_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    days = max(1, min(days, MAX_DAYS))
    return {'days': days, 'since': timezone.now() - timedelta(days=days)}


def _editor_label(user):
    if user is None:
        return 'Без автора'
    full = f"{(user.last_name or '').strip()} {(user.first_name or '').strip()}".strip()
    return full or user.username


def build_payload(filters):
    """Собрать дашборд правок после создания за выбранный период."""
    edits = list(
        RequestFieldEdit.objects.filter(scope='post', created_at__gte=filters['since'])
        .select_related('edited_by')
        .order_by('-created_at')
    )
    intake_pairs = set(
        RequestFieldEdit.objects.filter(
            scope__in=RequestFieldEdit.INTAKE_SCOPES,
            request_id__in={edit.request_id for edit in edits},
        ).values_list('request_id', 'field_name')
    )

    by_field = {}
    by_editor = {}
    suspected = []
    seen_pairs = set()
    for edit in edits:
        editor = _editor_label(edit.edited_by)
        field_stats = by_field.setdefault(edit.field_name, {'label': edit.field_label, 'edits': 0, 'requests': set()})
        field_stats['edits'] += 1
        field_stats['requests'].add(edit.request_id)
        editor_stats = by_editor.setdefault(editor, {'edits': 0, 'requests': set()})
        editor_stats['edits'] += 1
        editor_stats['requests'].add(edit.request_id)

        pair = (edit.request_id, edit.field_name)
        if pair in seen_pairs:
            continue  # идём от свежих правок — в подозрения попадает последнее значение
        seen_pairs.add(pair)
        if pair not in intake_pairs and len(suspected) < SUSPECTED_LIMIT:
            suspected.append({
                'request_id': edit.request_id,
                'field_name': edit.field_name,
                'field_label': edit.field_label,
                'old_value': edit.original_value,
                'new_value': edit.modified_value,
                'editor': editor,
                'changed_at': edit.created_at,
            })

    by_field_rows = sorted(
        ({'field_name': name, 'field_label': data['label'], 'edits': data['edits'], 'requests': len(data['requests'])}
         for name, data in by_field.items()),
        key=lambda row: (-row['requests'], -row['edits']),
    )[:TOP_LIMIT]
    by_editor_rows = sorted(
        ({'editor': editor, 'edits': data['edits'], 'requests': len(data['requests'])}
         for editor, data in by_editor.items()),
        key=lambda row: (-row['edits'], -row['requests']),
    )[:TOP_LIMIT]

    return {
        'filters': filters,
        'audit_available': True,
        'totals': {
            'requests_with_post_edits': len({edit.request_id for edit in edits}),
            'total_post_edits': len(edits),
            'suspected_count': len(suspected),
        },
        'by_field': by_field_rows,
        'by_editor': by_editor_rows,
        'suspected': suspected,
    }

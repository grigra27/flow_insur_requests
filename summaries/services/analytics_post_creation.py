"""Аналитика правок ПОСЛЕ создания заявки (контроль операторов и процесса).

Источник — журнал django-easy-audit (CRUDEvent, UPDATE по InsuranceRequest).
В отличие от RequestFieldEdit (правки на входе = чистый сигнал качества
парсера), здесь фиксируются изменения уже сохранённой заявки:
- операционный дрейф — что и кто меняет после создания;
- «подозрения на пропущенную ошибку парсера» — поля, которые НЕ правили на
  входе (1=2), но изменили позже (поэтому 1≠3). Это либо ошибка парсера,
  не замеченная при проверке, либо бизнес-изменение — список для ручной
  разметки, а не автоматический сигнал качества.

Популяция — V2-заявки (parser_confidence проставлен): по ним есть и снимок
распознавания, и intake-правки в RequestFieldEdit для сверки.
"""
import json
from datetime import timedelta

from django.utils import timezone

from insurance_requests.edit_tracking import get_object_field_meta, get_scalar_field_meta
from insurance_requests.models import InsuranceRequest, RequestFieldEdit

DEFAULT_DAYS = 90
MAX_DAYS = 3650
TOP_LIMIT = 20
SUSPECTED_LIMIT = 50
# Хвост самого создания: статусные сейвы в одной транзакции, не «поздние» правки.
POST_CREATE_EPSILON = timedelta(seconds=5)
# Поля, изменения которых не относятся к данным заявки.
IGNORED_FIELDS = {'updated_at', 'status', 'email_subject', 'email_body'}


def parse_filters(params):
    """Разобрать GET-параметр периода (?days=N)."""
    try:
        days = int(params.get('days', DEFAULT_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    days = max(1, min(days, MAX_DAYS))
    return {'days': days, 'since': timezone.now() - timedelta(days=days)}


def _field_labels():
    """Карта {имя_поля: подпись} по полям, которые производит парсер."""
    labels = {}
    for meta in (get_scalar_field_meta(), get_object_field_meta()):
        for name, field_meta in meta.items():
            labels[name] = field_meta.get('label', name)
    return labels


def _editor_label(event):
    if not event.user_id:
        return 'Без автора'
    full = f"{(event.user.last_name or '').strip()} {(event.user.first_name or '').strip()}".strip()
    return full or event.user.username


def _empty_payload(filters, audit_available):
    return {
        'filters': filters,
        'audit_available': audit_available,
        'totals': {
            'requests_with_post_edits': 0,
            'total_post_edits': 0,
            'suspected_count': 0,
        },
        'by_field': [],
        'by_editor': [],
        'suspected': [],
    }


def build_payload(filters):
    """Собрать дашборд правок после создания за выбранный период."""
    try:
        from django.contrib.contenttypes.models import ContentType
        from easyaudit.models import CRUDEvent
    except Exception:  # noqa: BLE001
        return _empty_payload(filters, audit_available=False)

    since = filters['since']
    labels = _field_labels()
    tracked = set(labels)

    # V2-заявки: id → служебные поля для атрибуции и отсечения хвоста создания.
    req_meta = {
        row['id']: row
        for row in InsuranceRequest.objects.filter(parser_confidence__isnull=False).values(
            'id', 'created_at'
        )
    }
    if not req_meta:
        return _empty_payload(filters, audit_available=True)

    # (заявка, поле), которые правили на входе — для отсева из «подозрений».
    intake_pairs = set(
        RequestFieldEdit.objects.filter(request_id__in=req_meta.keys())
        .values_list('request_id', 'field_name')
    )

    events = (
        CRUDEvent.objects
        .filter(content_type=ContentType.objects.get_for_model(InsuranceRequest),
                event_type=CRUDEvent.UPDATE, datetime__gte=since)
        .select_related('user')
        .order_by('-datetime')
    )

    by_field = {}
    by_editor = {}
    requests_with_post = set()
    total_post_edits = 0
    suspected = []
    seen_pairs = set()

    for event in events:
        try:
            rid = int(event.object_id)
        except (TypeError, ValueError):
            continue
        meta = req_meta.get(rid)
        if not meta:
            continue
        created = meta['created_at']
        if created and event.datetime and event.datetime <= created + POST_CREATE_EPSILON:
            continue  # хвост создания, не поздняя правка
        try:
            delta = json.loads(event.changed_fields) if event.changed_fields else {}
        except (TypeError, ValueError):
            continue
        if not isinstance(delta, dict):
            continue

        editor = _editor_label(event)
        for field_name, change in delta.items():
            if field_name in IGNORED_FIELDS or field_name not in tracked:
                continue
            if isinstance(change, list) and len(change) == 2:
                old_value, new_value = change
            else:
                old_value, new_value = '', change

            total_post_edits += 1
            requests_with_post.add(rid)
            bf = by_field.setdefault(field_name, {'edits': 0, 'requests': set()})
            bf['edits'] += 1
            bf['requests'].add(rid)
            be = by_editor.setdefault(editor, {'edits': 0, 'requests': set()})
            be['edits'] += 1
            be['requests'].add(rid)

            pair = (rid, field_name)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            # Не правили на входе, но изменили позже → кандидат в пропущенные
            # ошибки парсера (idём от свежих событий, поэтому значения — последние).
            if pair not in intake_pairs and len(suspected) < SUSPECTED_LIMIT:
                suspected.append({
                    'request_id': rid,
                    'field_name': field_name,
                    'field_label': labels.get(field_name, field_name),
                    'old_value': old_value,
                    'new_value': new_value,
                    'editor': editor,
                    'changed_at': event.datetime,
                })

    by_field_rows = sorted(
        ({'field_name': name, 'field_label': labels.get(name, name),
          'edits': data['edits'], 'requests': len(data['requests'])}
         for name, data in by_field.items()),
        key=lambda r: (-r['requests'], -r['edits']),
    )[:TOP_LIMIT]
    by_editor_rows = sorted(
        ({'editor': editor, 'edits': data['edits'], 'requests': len(data['requests'])}
         for editor, data in by_editor.items()),
        key=lambda r: (-r['edits'], -r['requests']),
    )[:TOP_LIMIT]

    return {
        'filters': filters,
        'audit_available': True,
        'totals': {
            'requests_with_post_edits': len(requests_with_post),
            'total_post_edits': total_post_edits,
            'suspected_count': len(suspected),
        },
        'by_field': by_field_rows,
        'by_editor': by_editor_rows,
        'suspected': suspected,
    }

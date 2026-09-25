"""Лента действий по записям сотрудника: смены статусов (StatusEvent) и правки (easy-audit CRUDEvent).

Перенесено из прежнего сервиса аналитики по сотрудникам без изменения логики
(docs/improvement_plans/analytics_redesign_2026_09.md, задача 4.5).
"""
from __future__ import annotations

import json
from typing import Any

from django.db.models import Q

from insurance_requests.models import InsuranceRequest
from ..models import InsuranceSummary


# Шумные поля, которые не показываем в timeline’е (auto-now / служебное / большие FileField’ы)
TIMELINE_NOISY_FIELDS = {
    'updated_at', 'created_at',
    'object_json_repr',
    'summary_file', 'attachment_file', 'file',
    'email_body', 'original_email_subject',
}

# Поля, для которых показываем «было → стало» (всё, что не FileField и не TextField/JSON огромных)
# Если поле не в этом списке и не в noisy — отображаем raw диф.

TIMELINE_VALUE_TRUNCATE = 60


def _field_label(model, field_name: str) -> str:
    """Verbose_name поля или само имя при отсутствии."""
    try:
        return str(model._meta.get_field(field_name).verbose_name)
    except Exception:  # noqa: BLE001
        return field_name


def _truncate_value(value) -> str:
    if value is None:
        return '—'
    s = str(value)
    if len(s) > TIMELINE_VALUE_TRUNCATE:
        return s[:TIMELINE_VALUE_TRUNCATE] + '…'
    return s


def _normalize_changed_fields(model, changed_fields_raw: str, *, drop_status: bool = True) -> list[dict[str, str]]:
    """Парсит JSON changed_fields и форматирует под отображение.

    drop_status=True — не показываем смену status (для неё есть отдельный StatusEvent).
    """
    if not changed_fields_raw:
        return []
    try:
        delta = json.loads(changed_fields_raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(delta, dict):
        return []

    out: list[dict[str, str]] = []
    for field_name, change in delta.items():
        if field_name in TIMELINE_NOISY_FIELDS:
            continue
        if drop_status and field_name == 'status':
            continue
        if isinstance(change, list) and len(change) == 2:
            old_v, new_v = change
        else:
            old_v, new_v = '', change
        out.append({
            'field': field_name,
            'label': _field_label(model, field_name),
            'old': _truncate_value(old_v),
            'new': _truncate_value(new_v),
        })
    return out


def _personal_timeline(user_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """Объединённый timeline: StatusEvent + easyaudit CRUDEvent.

    События — для записей сотрудника (заявки/своды/предложения, привязанные к его
    `created_by`). Status-смены идут через StatusEvent; CRUDEvent даёт CREATE,
    DELETE и UPDATE по не-status полям.
    """
    from django.contrib.contenttypes.models import ContentType
    from ..models import StatusEvent

    try:
        from easyaudit.models import CRUDEvent
        easyaudit_available = True
    except ImportError:
        easyaudit_available = False

    from .. import models as summaries_models  # locally to avoid circular at import time

    request_ct = ContentType.objects.get_for_model(InsuranceRequest)
    summary_ct = ContentType.objects.get_for_model(InsuranceSummary)
    offer_ct = ContentType.objects.get_for_model(summaries_models.InsuranceOffer)

    request_ids = list(InsuranceRequest.objects.filter(created_by_id=user_id).values_list('id', flat=True))
    summary_ids = list(
        InsuranceSummary.objects.filter(request__created_by_id=user_id).values_list('id', flat=True)
    )
    offer_ids = list(
        summaries_models.InsuranceOffer.objects.filter(summary_id__in=summary_ids).values_list('id', flat=True)
    )

    request_map = {
        r.id: r
        for r in InsuranceRequest.objects.filter(id__in=request_ids).only(
            'id', 'dfa_number', 'client_name'
        )
    }
    summary_map = {
        s.id: s
        for s in InsuranceSummary.objects.filter(id__in=summary_ids).select_related('request').only(
            'id', 'request_id', 'request__dfa_number', 'request__client_name'
        )
    }

    def _resolve_target(content_type_id: int, object_id) -> dict[str, Any]:
        try:
            obj_pk = int(object_id)
        except (TypeError, ValueError):
            obj_pk = object_id
        if content_type_id == request_ct.id:
            req = request_map.get(obj_pk)
            if req:
                return {
                    'target_kind': 'request',
                    'target_id': req.id,
                    'request_id': req.id,
                    'target_label': req.dfa_number or f'#{req.id}',
                    'client_name': req.client_name,
                    'model': InsuranceRequest,
                }
        elif content_type_id == summary_ct.id:
            sm = summary_map.get(obj_pk)
            if sm:
                return {
                    'target_kind': 'summary',
                    'target_id': sm.id,
                    'request_id': sm.request_id,
                    'target_label': (sm.request.dfa_number if sm.request else None) or f'#{sm.id}',
                    'client_name': sm.request.client_name if sm.request else '',
                    'model': InsuranceSummary,
                }
        elif content_type_id == offer_ct.id:
            # Для предложения покажем привязку к своду
            from ..models import InsuranceOffer
            offer = InsuranceOffer.objects.filter(pk=obj_pk).select_related('summary__request').first()
            if offer and offer.summary_id in summary_map:
                sm = summary_map[offer.summary_id]
                return {
                    'target_kind': 'offer',
                    'target_id': offer.id,
                    'request_id': sm.request_id,
                    'target_label': f"{sm.request.dfa_number if sm.request else '#'+str(sm.id)} · {offer.company_name}",
                    'client_name': sm.request.client_name if sm.request else '',
                    'model': InsuranceOffer,
                }
        return {
            'target_kind': 'other',
            'target_id': None,
            'request_id': None,
            'target_label': f'#{object_id}',
            'client_name': '',
            'model': None,
        }

    entries: list[dict[str, Any]] = []

    # 1. StatusEvent
    status_events = StatusEvent.objects.filter(
        Q(content_type=request_ct, object_id__in=request_ids)
        | Q(content_type=summary_ct, object_id__in=summary_ids)
    ).order_by('-changed_at')[:limit]

    for evt in status_events:
        target = _resolve_target(evt.content_type_id, evt.object_id)
        entries.append({
            'changed_at': evt.changed_at,
            'kind': 'status',
            'kind_label': 'смена статуса',
            'target_kind': target['target_kind'],
            'target_id': target['target_id'],
            'request_id': target['request_id'],
            'target_label': target['target_label'],
            'client_name': target['client_name'],
            'from_status': evt.from_status,
            'to_status': evt.to_status,
            'changes': [],
            'changed_by_id': evt.changed_by_id,
        })

    # 2. CRUDEvent — CREATE / UPDATE (не-status) / DELETE
    if easyaudit_available:
        crud_qs = CRUDEvent.objects.filter(
            Q(content_type=request_ct, object_id__in=[str(i) for i in request_ids])
            | Q(content_type=summary_ct, object_id__in=[str(i) for i in summary_ids])
            | Q(content_type=offer_ct, object_id__in=[str(i) for i in offer_ids])
        ).order_by('-datetime')[:limit * 3]  # с запасом, после фильтрации может ужаться

        for evt in crud_qs:
            target = _resolve_target(evt.content_type_id, evt.object_id)
            model = target['model']
            kind: str
            kind_label: str
            changes: list[dict[str, str]] = []

            if evt.event_type == CRUDEvent.CREATE:
                kind = 'create'
                kind_label = 'создано'
            elif evt.event_type == CRUDEvent.DELETE:
                kind = 'delete'
                kind_label = 'удалено'
            elif evt.event_type == CRUDEvent.UPDATE:
                kind = 'edit'
                kind_label = 'правка полей'
                if model is not None:
                    changes = _normalize_changed_fields(model, evt.changed_fields, drop_status=True)
                if not changes:
                    # Только status поменялся или всё в noisy → пропускаем
                    continue
            else:
                continue

            entries.append({
                'changed_at': evt.datetime,
                'kind': kind,
                'kind_label': kind_label,
                'target_kind': target['target_kind'],
                'target_id': target['target_id'],
                'request_id': target['request_id'],
                'target_label': target['target_label'],
                'client_name': target['client_name'],
                'from_status': None,
                'to_status': None,
                'changes': changes,
                'changed_by_id': evt.user_id,
            })

    entries.sort(key=lambda e: e['changed_at'], reverse=True)
    return entries[:limit]

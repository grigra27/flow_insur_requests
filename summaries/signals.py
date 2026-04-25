"""Сигналы для аудита смены статуса InsuranceRequest и InsuranceSummary.

Логика:
- pre_save определяет, изменился ли `status` относительно сохранённого в БД.
- post_save создаёт StatusEvent, если изменение было (или это создание объекта).
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from insurance_requests.models import InsuranceRequest

from ._current_user import get_current_user
from .models import InsuranceSummary, StatusEvent

logger = logging.getLogger(__name__)

_FLAG_FROM = '_status_event_from'
_FLAG_TO = '_status_event_to'
_FLAG_IS_CREATE = '_status_event_is_create'


def _capture_status_change(sender: type[models.Model], instance) -> None:
    """Сравнивает текущий status с сохранённым и помечает instance флагами."""
    if not instance.pk:
        # новый объект: фиксируем как «событие создания»
        setattr(instance, _FLAG_FROM, '')
        setattr(instance, _FLAG_TO, instance.status)
        setattr(instance, _FLAG_IS_CREATE, True)
        return

    try:
        old_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    except Exception:  # noqa: BLE001 — не хотим ронять save из-за аудита
        logger.exception('StatusEvent: failed to read previous status for %s#%s', sender.__name__, instance.pk)
        return

    if old_status is None or old_status == instance.status:
        return

    setattr(instance, _FLAG_FROM, old_status)
    setattr(instance, _FLAG_TO, instance.status)
    setattr(instance, _FLAG_IS_CREATE, False)


def _emit_status_event(sender: type[models.Model], instance, created: bool) -> None:
    if not hasattr(instance, _FLAG_TO):
        return

    from_status = getattr(instance, _FLAG_FROM)
    to_status = getattr(instance, _FLAG_TO)
    is_create = getattr(instance, _FLAG_IS_CREATE, False)

    # Чистим флаги, чтобы не сработать второй раз при последующих save()
    for attr in (_FLAG_FROM, _FLAG_TO, _FLAG_IS_CREATE):
        try:
            delattr(instance, attr)
        except AttributeError:
            pass

    # Не пишем «создание» как событие смены, если это пустой статус.
    if is_create and not to_status:
        return

    try:
        StatusEvent.objects.create(
            content_type=ContentType.objects.get_for_model(sender),
            object_id=instance.pk,
            from_status=from_status or '',
            to_status=to_status,
            changed_by=get_current_user(),
        )
    except Exception:  # noqa: BLE001
        logger.exception('StatusEvent: failed to record status change for %s#%s', sender.__name__, instance.pk)


@receiver(pre_save, sender=InsuranceRequest)
def insurance_request_pre_save(sender, instance, **kwargs):
    _capture_status_change(sender, instance)


@receiver(post_save, sender=InsuranceRequest)
def insurance_request_post_save(sender, instance, created, **kwargs):
    _emit_status_event(sender, instance, created)


@receiver(pre_save, sender=InsuranceSummary)
def insurance_summary_pre_save(sender, instance, **kwargs):
    _capture_status_change(sender, instance)


@receiver(post_save, sender=InsuranceSummary)
def insurance_summary_post_save(sender, instance, created, **kwargs):
    _emit_status_event(sender, instance, created)

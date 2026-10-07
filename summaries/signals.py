"""Сигналы для аудита смены статуса InsuranceRequest и InsuranceSummary.

Логика:
- pre_save определяет, изменился ли `status` относительно сохранённого в БД.
- post_save создаёт StatusEvent, если изменение было (или это создание объекта).
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from insurance_requests.models import InsuranceRequest

from ._current_user import get_current_user
from .models import InsuranceCompany, InsuranceOffer, InsuranceSummary, StatusEvent, SummaryCompanyStatus

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
    # Строки статусов СК создаются пачкой «не определён» при создании свода — это не смена.
    if is_create and sender is SummaryCompanyStatus and to_status == SummaryCompanyStatus.UNDEFINED:
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


# Статусы СК в своде (analytics_redesign_2026_09, этап 2): смены статуса — в тот же журнал,
# «предложение» — синхронно с наличием предложений.
@receiver(pre_save, sender=SummaryCompanyStatus)
def company_status_pre_save(sender, instance, **kwargs):
    _capture_status_change(sender, instance)


@receiver(post_save, sender=SummaryCompanyStatus)
def company_status_post_save(sender, instance, created, **kwargs):
    _emit_status_event(sender, instance, created)


_FLAG_OLD_COMPANY = '_company_status_old_company'
_FLAG_TERRITORY = '_offer_territory_change'


@receiver(pre_save, sender=InsuranceOffer)
def offer_pre_save(sender, instance, **kwargs):
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).values_list('summary_id', 'company_name', 'coverage_territory').first()
        if old and old[:2] != (instance.summary_id, instance.company_name):
            setattr(instance, _FLAG_OLD_COMPANY, old[:2])
        # (новое ли предложение для компании в своде, изменилась ли территория) — для синхронизации лет
        is_new_in_company = old is None or old[:2] != (instance.summary_id, instance.company_name)
        territory_changed = old is not None and (old[2] or '') != (instance.coverage_territory or '')
        setattr(instance, _FLAG_TERRITORY, (is_new_in_company, territory_changed))
    else:
        setattr(instance, _FLAG_TERRITORY, (True, False))


def _sync_territory(instance):
    from .services.offer_territory import sync_after_save

    flags = getattr(instance, _FLAG_TERRITORY, None)
    if flags is None:
        return
    delattr(instance, _FLAG_TERRITORY)
    try:
        sync_after_save(instance, is_new_in_company=flags[0], territory_changed=flags[1])
    except Exception:  # noqa: BLE001 — синхронизация территории не должна ронять сохранение предложения
        logger.exception('Territory sync failed for offer #%s', instance.pk)


def _sync_offered(summary_id, company_name):
    from .services.company_statuses import sync_offered

    try:
        sync_offered(summary_id, company_name)
    except Exception:  # noqa: BLE001 — статус СК не должен ронять сохранение предложения
        logger.exception('Company status sync failed for summary #%s, %s', summary_id, company_name)


def _sync_insurer_response(summary_id, company_name):
    from .services.insurer_response import sync_after_offer_removed

    try:
        sync_after_offer_removed(summary_id, company_name)
    except Exception:  # noqa: BLE001 — «Ответ СК» не должен ронять удаление предложения
        logger.exception('Insurer response sync failed for summary #%s, %s', summary_id, company_name)


@receiver(post_save, sender=InsuranceOffer)
def offer_post_save(sender, instance, **kwargs):
    old = getattr(instance, _FLAG_OLD_COMPANY, None)
    if old:
        delattr(instance, _FLAG_OLD_COMPANY)
        _sync_offered(*old)  # предложение перенесли на другую СК — у прежней могло не остаться предложений
        _sync_insurer_response(*old)
    _sync_offered(instance.summary_id, instance.company_name)
    _sync_territory(instance)  # территория одна на компанию в своде (services/offer_territory.py)


@receiver(post_delete, sender=InsuranceOffer)
def offer_post_delete(sender, instance, **kwargs):
    _sync_offered(instance.summary_id, instance.company_name)
    _sync_insurer_response(instance.summary_id, instance.company_name)


@receiver(post_save, sender=InsuranceCompany)
@receiver(post_delete, sender=InsuranceCompany)
def insurance_company_changed(sender, **kwargs):
    """Логотипы СК кэшируются в процессе — после правки компании словарь перечитается."""
    from .services.insurer_logos import clear_cache

    clear_cache()

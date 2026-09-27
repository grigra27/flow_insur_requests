"""Территория страхования — одна на страховую компанию в своде (решение владельца 2026-09-27).

Страховая подтверждает территорию на весь полис, не на отдельный год: в шаблоне ответа страховщика
это одна ячейка (B3), и загрузка файла пишет её во все годы. Хранится территория по-прежнему в каждом
предложении (`InsuranceOffer.coverage_territory`), но держится одинаковой у всех лет компании в своде:

- новый год без территории наследует территорию компании;
- изменили территорию у любого года (в т. ч. очистили) — она обновляется у всех лет компании;
- предложение перенесли в другую компанию — для него действуют правила нового года.

Синхронизация вызывается сигналами `InsuranceOffer` (summaries/signals.py), поэтому работает для
формы, копирования, загрузки файлов и админки. Соседние годы обновляются через `update()` — это
не действия сотрудника, в журнал правок они не пишутся.
"""
from __future__ import annotations

from typing import Optional

from ..models import InsuranceOffer


def _siblings(offer):
    return InsuranceOffer.objects.filter(summary_id=offer.summary_id, company_name=offer.company_name) \
        .exclude(pk=offer.pk)


def company_territory(summary_id: int, company_name: str, *, exclude_pk: Optional[int] = None) -> Optional[str]:
    """Территория компании в своде: первое непустое значение по годам (или None, если не указана нигде)."""
    queryset = InsuranceOffer.objects.filter(summary_id=summary_id, company_name=company_name) \
        .exclude(coverage_territory__isnull=True).exclude(coverage_territory='').order_by('insurance_year')
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.values_list('coverage_territory', flat=True).first()


def sync_after_save(offer, *, is_new_in_company: bool, territory_changed: bool) -> None:
    """Выровнять территорию лет компании после сохранения предложения."""
    own = offer.coverage_territory
    if is_new_in_company and not (own or '').strip():
        inherited = company_territory(offer.summary_id, offer.company_name, exclude_pk=offer.pk)
        if inherited:
            InsuranceOffer.objects.filter(pk=offer.pk).update(coverage_territory=inherited)
            offer.coverage_territory = inherited
        return
    if is_new_in_company or territory_changed:
        _siblings(offer).exclude(coverage_territory=own).update(coverage_territory=own)


def set_company_territory(summary_id: int, company_name: str, territory: str) -> int:
    """Задать территорию компании в своде сразу для всех лет. Возвращает число обновлённых предложений."""
    return InsuranceOffer.objects.filter(summary_id=summary_id, company_name=company_name) \
        .update(coverage_territory=(territory or '').strip())

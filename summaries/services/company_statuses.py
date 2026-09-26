"""Статусы страховых компаний в своде (docs/improvement_plans/analytics_redesign_2026_09.md, этап 2).

По каждому своду — какие СК запрошены, какие отказали, какие дали предложение, какие не
запрашивались. Правила (решения владельца 2026-09-25/26):

- при создании свода строки создаются для всех активных СК справочника, кроме «другое»,
  со статусом «не определён»; свод помечается `company_statuses_required`;
- «предложение» ставится автоматически, когда по СК есть хоть одно предложение (любой путь
  загрузки), и снимается (→ «запрошена»), когда удалено последнее; вручную его не выставить
  и не снять;
- «другое» в таблицу не выводится; при загрузке предложения по «другое» строка создаётся
  сразу со статусом «предложение»;
- статус свода нельзя менять, пока у какой-либо СК «не определён» (`missing_companies`);
  исключения — ночное автозакрытие и Django-админка;
- своды, созданные до запуска, правилом не блокируются.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .._current_user import get_current_user
from ..models import InsuranceCompany, InsuranceOffer, InsuranceSummary, SummaryCompanyStatus

UNDEFINED = SummaryCompanyStatus.UNDEFINED
NOT_REQUESTED = SummaryCompanyStatus.NOT_REQUESTED
REQUESTED = SummaryCompanyStatus.REQUESTED
DECLINED = SummaryCompanyStatus.DECLINED
OFFERED = SummaryCompanyStatus.OFFERED
MANUAL_STATUSES = SummaryCompanyStatus.MANUAL_STATUSES
STATUS_LABELS = dict(SummaryCompanyStatus.STATUS_CHOICES)


class CompanyStatusError(ValueError):
    """Недопустимая смена статуса СК (сообщение — для сотрудника)."""


def _company_by_name(company_name: str) -> Optional[InsuranceCompany]:
    return InsuranceCompany.objects.filter(name=company_name).first()


def init_for_summary(summary: InsuranceSummary) -> None:
    """Создать строки «не определён» по всем активным СК (кроме «другое») и включить обязательность."""
    companies = InsuranceCompany.objects.filter(is_active=True, is_other=False)
    existing = set(summary.company_statuses.values_list('company_id', flat=True))
    SummaryCompanyStatus.objects.bulk_create([
        SummaryCompanyStatus(summary=summary, company=company, status=UNDEFINED)
        for company in companies if company.pk not in existing
    ])
    if not summary.company_statuses_required:
        summary.company_statuses_required = True
        summary.save(update_fields=['company_statuses_required'])
    for company_name in set(summary.offers.values_list('company_name', flat=True)):
        sync_offered(summary.pk, company_name)


def _save_status(row: SummaryCompanyStatus, status: str, user=None) -> None:
    row.status = status
    row.status_changed_at = timezone.now()
    user = user or get_current_user()  # автосинхронизация: кто загрузил или удалил предложение
    row.changed_by = user if getattr(user, 'is_authenticated', False) else None
    row.save()


def sync_offered(summary_id: int, company_name: str) -> None:
    """Привести статус СК к наличию предложений: есть предложение → «предложение», нет → «запрошена»."""
    company = _company_by_name(company_name)
    if company is None or not InsuranceSummary.objects.filter(pk=summary_id).exists():
        return  # свод удаляется каскадом или СК нет в справочнике
    has_offers = InsuranceOffer.objects.filter(summary_id=summary_id, company_name=company_name).exists()
    row = SummaryCompanyStatus.objects.filter(summary_id=summary_id, company=company).first()
    if has_offers:
        if row is None:
            row = SummaryCompanyStatus(summary_id=summary_id, company=company)
        if row.status != OFFERED:
            _save_status(row, OFFERED)
    elif row is not None and row.status == OFFERED:
        _save_status(row, REQUESTED)  # предложение удалено: СК запрашивали, ответа в своде больше нет


def set_status(summary: InsuranceSummary, company_id: int, status: str, user=None) -> SummaryCompanyStatus:
    """Ручная смена статуса СК сотрудником."""
    if status not in MANUAL_STATUSES:
        raise CompanyStatusError('Недопустимый статус страховой компании.')
    company = InsuranceCompany.objects.filter(pk=company_id).first()
    if company is None:
        raise CompanyStatusError('Страховая компания не найдена.')
    with transaction.atomic():
        row, _ = SummaryCompanyStatus.objects.select_for_update().get_or_create(summary=summary, company=company)
        if row.status == OFFERED:
            raise CompanyStatusError(
                f'По «{company}» есть предложение — статус ставится автоматически. '
                'Чтобы изменить его, удалите предложения этой компании.'
            )
        if row.status != status:
            _save_status(row, status, user)
    return row


def set_undefined_to(summary: InsuranceSummary, status: str, user=None) -> int:
    """Массово: все СК со статусом «не определён» → status. Возвращает число изменённых."""
    if status not in MANUAL_STATUSES:
        raise CompanyStatusError('Недопустимый статус страховой компании.')
    changed = 0
    with transaction.atomic():
        for row in summary.company_statuses.select_for_update().filter(status=UNDEFINED):
            _save_status(row, status, user)  # по одной — чтобы каждая смена попала в журнал
            changed += 1
    return changed


def missing_companies(summary: InsuranceSummary) -> List[str]:
    """СК без статуса, блокирующие смену статуса свода (пусто — можно менять)."""
    if not summary.company_statuses_required:
        return []
    return [
        str(row.company)
        for row in summary.company_statuses.select_related('company').filter(status=UNDEFINED)
    ]


def missing_message(missing: List[str]) -> str:
    return ('Сначала укажите статус каждой страховой компании в блоке «Статусы страховых компаний». '
            f'Без статуса: {", ".join(missing)}.')


def rows_for_display(summary: InsuranceSummary) -> List[Dict]:
    """Строки таблицы на карточке свода: активные СК справочника (без «другое») + СК со строками."""
    rows = {row.company_id: row for row in summary.company_statuses.select_related('company', 'changed_by')}
    companies = list(InsuranceCompany.objects.filter(is_active=True, is_other=False))
    companies += [row.company for row in rows.values() if row.company not in companies]
    result = []
    for company in sorted(companies, key=lambda c: (c.sort_order, c.name)):
        row = rows.get(company.pk)
        status = row.status if row else UNDEFINED
        result.append({
            'company': company,
            'status': status,
            'status_label': STATUS_LABELS[status],
            'row': row,
            'locked': status == OFFERED,
        })
    return result


def declined_company_names(summary: InsuranceSummary) -> List[str]:
    """Отказавшие СК по алфавиту — для блока отказов на карточке и в Excel-своде (задача 2.6)."""
    names = [
        str(row.company)
        for row in summary.company_statuses.select_related('company').filter(status=DECLINED)
    ]
    return sorted(names, key=str.lower)


def counts(summary: InsuranceSummary) -> Dict[str, int]:
    result = {key: 0 for key in STATUS_LABELS}
    for row in rows_for_display(summary):
        result[row['status']] += 1
    return result

"""«Ответ СК» (InsurerResponse): контур V2, сохранение данных дополнительных блоков, синхронизация.

docs/improvement_plans/insurer_response_v2.md, §6 и §8. Пока RESPONSE_TEMPLATE_V2_FOR_ALL выключен,
проверки дополнительных блоков (отказ при пустом обязательном блоке, при старом шаблоне) действуют
только для суперпользователя; сотрудники загружают ответы как раньше. Чтение блоков из файла —
ExcelResponseProcessor.extract_response_sections.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from django.conf import settings

from ..models import InsuranceOffer, InsuranceSummary, InsurerResponse
from ..response_sections import all_fields

logger = logging.getLogger(__name__)


def v2_contour(user) -> bool:
    """Работает ли для пользователя контур V2 (строгие проверки дополнительных блоков)."""
    if getattr(settings, 'RESPONSE_TEMPLATE_V2_FOR_ALL', False):
        return True
    return bool(user is not None and getattr(user, 'is_superuser', False))


def save_response(summary: InsuranceSummary, company_name: str, values: Dict, template_version: int,
                  user=None) -> InsurerResponse:
    """Создаёт или обновляет «Ответ СК». В values — только поля блоков, нужных по заявке;
    поля, которых нет в values, сбрасываются к пустым (новый файл заменяет прежний ответ)."""
    defaults = {fld.name: values.get(fld.name, None if fld.kind == 'money' else '') for fld in all_fields()}
    defaults['template_version'] = template_version
    if user is not None and getattr(user, 'is_authenticated', False):
        defaults['created_by'] = user
    response, created = InsurerResponse.objects.update_or_create(
        summary=summary, company_name=company_name, defaults=defaults,
    )
    logger.info(
        "Ответ СК %s: свод #%s, %s, шаблон V%s, поля: %s",
        'создан' if created else 'обновлён', summary.pk, company_name, template_version,
        {k: v for k, v in values.items() if v not in (None, '')},
    )
    return response


def attach_source_file(summary_id: int, company_name: str, stored_name: Optional[str]) -> None:
    """Ссылка на уже сохранённый исходный файл (тот же, что у годовых предложений)."""
    if stored_name:
        InsurerResponse.objects.filter(summary_id=summary_id, company_name=company_name).update(
            source_file=stored_name,
        )


def sync_after_offer_removed(summary_id: int, company_name: str) -> None:
    """У СК в своде не осталось предложений — ответа СК тоже нет."""
    if not InsuranceOffer.objects.filter(summary_id=summary_id, company_name=company_name).exists():
        deleted, _ = InsurerResponse.objects.filter(summary_id=summary_id, company_name=company_name).delete()
        if deleted:
            logger.info("Ответ СК удалён вместе с последним предложением: свод #%s, %s", summary_id, company_name)


def display_lines(summary: InsuranceSummary, company_names) -> Dict[str, list]:
    """Строки дополнительных блоков для карточки свода: {компания: [{label, text, missing}]}.

    Только блоки, нужные по заявке свода; если ответа СК или значения нет — «нет данных».
    """
    from ..response_sections import CHOICE, MONEY, required_sections

    sections = required_sections(summary.request)
    if not sections:
        return {}
    responses = {r.company_name: r for r in InsurerResponse.objects.filter(summary=summary)}
    lines = {}
    for company in company_names:
        response = responses.get(company)
        company_lines = []
        for section in sections:
            main, *extra = section.fields
            value = getattr(response, main.name, None) if response else None
            if value in (None, ''):
                company_lines.append({'label': section.short_title or section.title, 'text': 'нет данных', 'missing': True})
                continue
            if main.kind == CHOICE:
                text = dict(main.choices).get(value, value)
            elif main.kind == MONEY:
                text = f'{value:,.0f} ₽'.replace(',', ' ')
            else:
                text = str(value)
            details = [getattr(response, f.name, '') for f in extra if getattr(response, f.name, '')]
            if details:
                text = f"{text} · {' · '.join(details)}"
            company_lines.append({'label': section.short_title or section.title, 'text': text, 'missing': False})
        lines[company] = company_lines
    return lines

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


def v2_visible(user) -> bool:
    """Видно ли новое по шаблону ответа V2: комплект для страховщика, блоки на карточке свода, формы.
    Суперпользователю — всегда; остальным — когда включён RESPONSE_TEMPLATE_V2_FOR_ALL."""
    if user is not None and getattr(user, 'is_superuser', False):
        return True
    return bool(getattr(settings, 'RESPONSE_TEMPLATE_V2_FOR_ALL', False))


def _v2_since():
    """Дата переключения на шаблон V2 (RESPONSE_TEMPLATE_V2_SINCE, ГГГГ-ММ-ДД); None — без переходного периода."""
    from datetime import date

    raw = (getattr(settings, 'RESPONSE_TEMPLATE_V2_SINCE', '') or '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.error("RESPONSE_TEMPLATE_V2_SINCE='%s' — не дата ГГГГ-ММ-ДД, переходный период не действует", raw)
        return None


def v2_strict(user, request=None) -> bool:
    """Строгие проверки блоков (пустой обязательный блок или старый шаблон — отказ).

    При включённом флаге — для всех одинаково (суперпользователь тоже, решение 2026-10-07): только для заявок,
    созданных не раньше даты переключения; запросы, разосланные со старым шаблоном, загружаются как раньше.
    Флаг выключен — строго только у суперпользователя (тестовый контур).
    """
    if not getattr(settings, 'RESPONSE_TEMPLATE_V2_FOR_ALL', False):
        return bool(user is not None and getattr(user, 'is_superuser', False))
    since = _v2_since()
    created = getattr(request, 'created_at', None)
    if since is None or created is None:
        return True
    from django.utils import timezone

    return timezone.localtime(created).date() >= since


def v2_contour(user) -> bool:
    """Устаревшее имя: строгий режим без учёта заявки."""
    return v2_strict(user)


def v1_comment_note(response) -> str:
    """Ответы блоков одной строкой для комментария свода V1:
    «Осмотр: требуется осмотр. Риски РНПК будут прописаны в полисе. Перевозка: 5 330 ₽ (условия).»"""
    if response is None:
        return ''
    parts = []
    if response.inspection_status:
        label = response.get_inspection_status_display()
        parts.append(f'Осмотр: {label[:1].lower()}{label[1:]}.')
    if response.rnpk_status:
        parts.append(f'Риски РНПК {response.get_rnpk_status_display().lower()}.')
    if response.transport_cost is not None:
        amount = f'{response.transport_cost:,.0f}'.replace(',', ' ')
        terms = f' ({response.transport_terms.strip()})' if response.transport_terms.strip() else ''
        parts.append(f'Перевозка: {amount} ₽{terms}.')
    return ' '.join(parts)


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


def display_lines(summary: InsuranceSummary, company_names) -> Dict[str, dict]:
    """Блоки ответа V2 для карточки свода: {компания: {'lines': [...], 'fields': [...]}}.

    lines — строки для показа (если ответа СК или значения нет — «нет данных»); fields — поля формы
    ручной правки с текущими значениями. Только блоки, нужные по заявке свода.
    """
    from ..response_sections import CHOICE, MONEY, required_sections

    sections = required_sections(summary.request)
    if not sections:
        return {}
    responses = {r.company_name: r for r in InsurerResponse.objects.filter(summary=summary)}
    result = {}
    for company in company_names:
        response = responses.get(company)
        lines, fields = [], []
        for section in sections:
            main, *extra = section.fields
            label = section.short_title or section.title
            value = getattr(response, main.name, None) if response else None
            if value in (None, ''):
                lines.append({'label': label, 'text': 'нет данных', 'missing': True})
            else:
                if main.kind == CHOICE:
                    text = dict(main.choices).get(value, value)
                elif main.kind == MONEY:
                    text = f'{value:,.0f} ₽'.replace(',', ' ')
                else:
                    text = str(value)
                details = [getattr(response, f.name, '') for f in extra if getattr(response, f.name, '')]
                if details:
                    text = f"{text} · {' · '.join(details)}"
                lines.append({'label': label, 'text': text, 'missing': False})
            for fld in section.fields:
                current = getattr(response, fld.name, None) if response else None
                fields.append({
                    'name': fld.name, 'label': fld.label, 'kind': fld.kind, 'required': fld.required,
                    'choices': fld.choices, 'section': label,
                    'value': '' if current is None else (f'{current:.0f}' if fld.kind == MONEY else current),
                })
        result[company] = {'lines': lines, 'fields': fields}
    return result


class ResponseFormError(ValueError):
    """Неверное значение в форме ручной правки «Ответа СК» (сообщение — для сотрудника)."""


def parse_form_values(summary: InsuranceSummary, data, strict: bool) -> Dict:
    """Значения блоков из формы (ручной ввод): только блоки, нужные по заявке; проверка по реестру
    так же, как при загрузке файла. strict — пустое обязательное поле тоже ошибка (контур V2 при
    добавлении предложения); без strict пустое значение очищает поле, а отсутствующее не меняется."""
    from decimal import Decimal, InvalidOperation

    from ..response_sections import CHOICE, MONEY, required_sections
    from .excel_services import ExcelResponseProcessor

    values = {}
    for section in required_sections(summary.request):
        for fld in section.fields:
            if not strict and fld.name not in data:
                continue  # правка на карточке: поля, которых нет в запросе, не трогаем
            raw = (data.get(fld.name) or '').strip()
            if not any(char.isalnum() for char in raw):
                if strict and fld.required:
                    title = section.short_title or section.title
                    field = '' if fld.label == title else f' (поле «{fld.label}»)'
                    raise ResponseFormError(
                        f'Не заполнен блок «{title}»{field}. Если страховщик его не указал — запросите у него.')
                values[fld.name] = None if fld.kind == MONEY else ''
            elif fld.kind == CHOICE:
                code = fld.match_choice(raw)
                if code is None:
                    raise ResponseFormError(
                        f'«{fld.label}»: выберите одно из значений — {", ".join(fld.choice_labels)}.')
                values[fld.name] = code
            elif fld.kind == MONEY:
                try:
                    amount = Decimal(ExcelResponseProcessor()._normalize_decimal_input(raw)).quantize(Decimal('0.01'))
                except (InvalidOperation, ValueError, TypeError):
                    amount = None
                if amount is None or amount < 0:
                    raise ResponseFormError(f'«{fld.label}»: укажите сумму в рублях, например 5 330.')
                values[fld.name] = amount
            else:
                values[fld.name] = raw
    return values


def apply_values(summary: InsuranceSummary, company_name: str, values: Dict, user=None) -> InsurerResponse:
    """Записать значения блоков в «Ответ СК» (создать строку, если её нет); версию шаблона не трогает."""
    response, created = InsurerResponse.objects.get_or_create(summary=summary, company_name=company_name)
    for name, value in values.items():
        setattr(response, name, value)
    if user is not None and getattr(user, 'is_authenticated', False) and not response.created_by_id:
        response.created_by = user
    response.save()
    logger.info("Ответ СК %s вручную: свод #%s, %s, %s", 'создан' if created else 'изменён',
                summary.pk, company_name, {k: v for k, v in values.items() if v not in (None, '')})
    return response


def existing_values(summary: InsuranceSummary) -> Dict[str, Dict[str, str]]:
    """{компания: {поле: значение для формы}} — подставить в форму добавления при выборе СК."""
    result = {}
    for response in InsurerResponse.objects.filter(summary=summary):
        row = {}
        for fld in all_fields():
            value = getattr(response, fld.name)
            if value not in (None, ''):
                row[fld.name] = f'{value:.0f}' if fld.kind == 'money' else str(value)
        result[response.company_name] = row
    return result


def update_from_form(summary: InsuranceSummary, company_name: str, data, user=None) -> InsurerResponse:
    """Ручная правка блоков «Ответа СК» на карточке свода (кнопка «изменить» у компании).

    Принимаются только поля блоков, нужных по заявке; пустое значение очищает поле.
    Строка «Ответ СК» создаётся, если её ещё нет.
    """
    from ..response_sections import required_sections

    if not InsuranceOffer.objects.filter(summary=summary, company_name=company_name).exists():
        raise ResponseFormError('У этой страховой нет предложений в своде.')
    if not required_sections(summary.request):
        raise ResponseFormError('По этой заявке дополнительные блоки ответа не нужны.')
    return apply_values(summary, company_name, parse_form_values(summary, data, strict=False), user=user)

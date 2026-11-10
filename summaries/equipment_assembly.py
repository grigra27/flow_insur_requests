"""Единые правила монтажа/демонтажа для Excel, ручного ввода и модели ответа СК."""
from decimal import Decimal, DecimalException
import re

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator

from .response_sections import EQUIPMENT_ASSEMBLY

FIELDS = tuple(f.name for f in EQUIPMENT_ASSEMBLY.fields)


class EquipmentAssemblyError(ValueError):
    pass


def _text(value):
    return '' if value is None else str(value).strip()


def _number(raw, *, rate=False, percent_rate=False):
    text = '' if raw is None else str(raw).strip()
    if not text or text in ('—', '-', '–'):
        return None
    label = 'Дополнительный тариф' if rate else 'Дополнительная премия'
    try:
        if isinstance(raw, bool):
            raise ValueError
        if rate:
            # Для процентов 0,125 — десятичная дробь, а не разделитель тысяч.
            text = re.sub(r'\s+', '', text).removesuffix('%').replace(',', '.')
        else:
            from .services.excel_services import ExcelResponseProcessor
            text = ExcelResponseProcessor()._normalize_decimal_input(raw)
        number = Decimal(text)
        if not number.is_finite() or number < 0:
            raise ValueError
        if rate and percent_rate and isinstance(raw, (int, float, Decimal)):
            number *= 100  # числовая ячейка Excel 0.0015 с форматом % → 0,15% в БД
        number = number.normalize() if number else Decimal('0')
        DecimalValidator(9 if rate else 15, 4 if rate else 2)(number)
        return number
    except (DecimalException, ValueError, TypeError, ValidationError):
        example = '0,15%' if rate else '15 000 ₽'
        raise EquipmentAssemblyError(f'Монтаж/демонтаж: «{label}» — укажите неотрицательное число, например {example}.') from None


def clean_values(values, *, required=False, percent_rate=False):
    """Полный снимок блока. Противоречащая статусу стоимость сбрасывается.

    required=False разрешает пустой исторический ответ; заполненный блок всегда проверяется целиком.
    Для частичного ручного обновления вызывающий объединяет values с сохранёнными полями компании.
    """
    raw_status = _text(values.get('equipment_assembly_status'))
    status = EQUIPMENT_ASSEMBLY.fields[0].match_choice(raw_status) if raw_status else ''
    if status is None:
        raise EquipmentAssemblyError('Монтаж/демонтаж: выберите допустимый статус покрытия.')
    rate = _number(values.get('equipment_assembly_rate'), rate=True, percent_rate=percent_rate)
    cost = _number(values.get('equipment_assembly_cost'))
    basis = _text(values.get('equipment_assembly_cost_basis'))
    terms = _text(values.get('equipment_assembly_terms'))
    if not status and (required or rate is not None or cost is not None or basis or terms):
        raise EquipmentAssemblyError('Не заполнен блок «Монтаж/демонтаж спецтехники»: укажите статус покрытия.')
    if status == 'separate':
        if not any(v is not None and v > 0 for v in (rate, cost)):
            raise EquipmentAssemblyError('Монтаж/демонтаж: за доплату укажите положительный дополнительный тариф или премию.')
        if not any(c.isalnum() for c in basis):
            raise EquipmentAssemblyError('Монтаж/демонтаж: укажите порядок и базу начисления дополнительной стоимости.')
    else:
        rate, cost, basis = None, None, ''
    if status == 'not_applicable' and not any(c.isalnum() for c in terms):
        raise EquipmentAssemblyError('Монтаж/демонтаж: для «Не применимо» обязательно укажите причину в ограничениях и условиях.')
    return dict(zip(FIELDS, (status, rate, cost, basis, terms)))


def format_number(value):
    text = format(value, ',f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace(',', ' ').replace('.', ',')


def coverage_text(response):
    """Короткая колонка свода. Обе величины сохраняются, стоимость ни с чем не суммируется."""
    status = getattr(response, 'equipment_assembly_status', '')
    if status == 'separate':
        parts = []
        if response.equipment_assembly_rate is not None:
            parts.append(f'Доп. тариф {format_number(response.equipment_assembly_rate)}%')
        if response.equipment_assembly_cost is not None:
            parts.append(f'Доп. премия {format_number(response.equipment_assembly_cost)} ₽')
        return '\n'.join(parts) or 'Нет данных'
    return {'included': 'Включено', 'declined': 'Не страхуем', 'not_applicable': 'Не применимо'}.get(status, 'Нет данных')

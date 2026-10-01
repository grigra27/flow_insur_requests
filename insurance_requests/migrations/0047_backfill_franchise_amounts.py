"""Заполняет размеры франшизы у уже загруженных заявок Parser V2.

Парсер и раньше находил ячейку с суммой франшизы (служебная запись source_map['franchise_type'],
например «D29=Х (D28: Нет франшизы); F29=30000 (F28: Абсолютная сумма)»), но поля для суммы
не было. Берём суммы оттуда («30 000, 50 000» — два варианта); тип франшизы и заявки без суммы
в бланке не трогаем. Логика разбора намеренно скопирована сюда из insurance_requests/franchise.py:
миграция не должна зависеть от будущих изменений кода.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from django.db import migrations

_SPLIT_RE = re.compile(r'\s*(?:;|/|\bи\b|,\s+|\n)\s*')
_UNIT_RE = re.compile(r'(?i)(рубл\w*|руб\.?|р\.|%)')
_NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')


def _to_decimal(text: str) -> Optional[Decimal]:
    text = re.sub(r'[\s ]', '', text).replace(',', '.')
    if not _NUMBER_RE.fullmatch(text):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def parse_amounts(value) -> List[Decimal]:
    """«30 000, 50 000» → [30000, 50000]; «1,5%» → [1.5]; отметка «Х» или пусто → []."""
    text = _UNIT_RE.sub('', str(value or '')).strip()
    if not text:
        return []
    parts = []
    for chunk in _SPLIT_RE.split(text):
        # «1,5» / «30 000,00» — десятичная запятая; иначе запятая разделяет варианты («30 000,50 000»).
        if ',' in chunk and not re.fullmatch(r'[\d\s ]*\d,\d{1,2}', chunk.strip()):
            parts.extend(chunk.split(','))
        else:
            parts.append(chunk)
    amounts = []
    for part in parts:
        if not part.strip():
            continue
        amount = _to_decimal(part)
        if amount is None:
            return []  # что-то нечисловое — не угадываем
        amounts.append(amount)
    return amounts


PART_RE = re.compile(r'^([A-Z]+)(\d+)=(.*?)(?: \(([A-Z]+\d+): (.*)\))?$')


def amounts_from_source(source):
    """'…; F29=30 000, 50 000 (F28: Абсолютная сумма)' → (['30000', '50000'], 'rub')."""
    found = {}
    for part in (source or '').split('; '):
        match = PART_RE.match(part.strip())
        if not match:
            continue
        column, _row, value, _label_coord, label = match.groups()
        label = (label or '').lower()
        if 'абсолют' in label or (not label and column == 'F'):
            unit = 'rub'
        elif '%' in label or 'процент' in label or (not label and column == 'E'):
            unit = 'percent'
        else:
            continue
        amounts = parse_amounts(value)
        if amounts and unit not in found:
            found[unit] = [format(amount.normalize(), 'f') for amount in amounts]
    for unit in ('rub', 'percent'):
        if unit in found:
            return found[unit], unit
    return [], None


def backfill(apps, schema_editor):
    InsuranceRequest = apps.get_model('insurance_requests', 'InsuranceRequest')
    for request in InsuranceRequest.objects.exclude(franchise_type='none').iterator():
        if request.franchise_amounts:
            continue
        source_map = ((request.additional_data or {}).get('parser_v2', {}) or {}).get('source_map', {}) or {}
        amounts, unit = amounts_from_source(source_map.get('franchise_type', ''))
        if amounts:
            InsuranceRequest.objects.filter(pk=request.pk).update(franchise_amounts=amounts, franchise_unit=unit)


class Migration(migrations.Migration):

    dependencies = [
        ('insurance_requests', '0046_franchise_amounts'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]

"""Заполняет размер франшизы у уже загруженных заявок Parser V2.

Парсер и раньше находил ячейку с суммой франшизы (служебная запись source_map['franchise_type'],
например «D29=Х (D28: Нет франшизы); F29=30000 (F28: Абсолютная сумма)»), но поля для суммы
не было. Берём сумму оттуда; тип франшизы и заявки без суммы в бланке не трогаем.
Логика намеренно скопирована сюда, а не импортирована из парсера: миграция не должна зависеть
от будущих изменений кода.
"""
import re
from decimal import Decimal, InvalidOperation

from django.db import migrations

PART_RE = re.compile(r'^([A-Z]+)(\d+)=(.*?)(?: \(([A-Z]+\d+): (.*)\))?$')


def parse_amount(text):
    text = re.sub(r'(?i)(рубл\w*|руб\.?|р\.|%)', '', str(text or ''))
    text = re.sub(r'[\s ]', '', text).replace(',', '.')
    if not re.fullmatch(r'\d+(\.\d+)?', text):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def amount_from_source(source):
    """'D29=Х (D28: Нет франшизы); F29=30000 (F28: Абсолютная сумма)' → (Decimal('30000'), 'rub')."""
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
        amount = parse_amount(value)
        if amount is not None and unit not in found:
            found[unit] = amount
    if 'rub' in found:
        return found['rub'], 'rub'
    if 'percent' in found:
        return found['percent'], 'percent'
    return None, None


def backfill(apps, schema_editor):
    InsuranceRequest = apps.get_model('insurance_requests', 'InsuranceRequest')
    queryset = InsuranceRequest.objects.exclude(franchise_type='none').filter(franchise_amount__isnull=True)
    for request in queryset.iterator():
        source_map = ((request.additional_data or {}).get('parser_v2', {}) or {}).get('source_map', {}) or {}
        amount, unit = amount_from_source(source_map.get('franchise_type', ''))
        if amount is not None:
            InsuranceRequest.objects.filter(pk=request.pk).update(franchise_amount=amount, franchise_unit=unit)


class Migration(migrations.Migration):

    dependencies = [
        ('insurance_requests', '0046_franchise_amount'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]

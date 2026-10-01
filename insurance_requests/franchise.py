"""Размеры франшизы: разбор из ячейки бланка / поля формы и вывод одной строкой.

В бланке в колонке «Абсолютная сумма» (или «% от страховой суммы») бывает одно число
(«30 000») или несколько вариантов («30 000, 50 000»). Каждое число — отдельный вариант
франшизы; вместе с «без франшизы» (тип both_variants) это и есть список вариантов расчёта.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional

UNIT_LABELS = {'rub': 'руб.', 'percent': '% от страховой суммы'}

# Разделители вариантов: «;», «/», « и », запятая. Запятая — десятичная, только если после неё
# одна-две цифры до конца числа («1,5%», «30 000,00»); иначе она разделяет варианты.
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


def format_amount(value, unit: str = 'rub') -> str:
    """Decimal('30000') → «30 000 руб.»; Decimal('1.5'), 'percent' → «1,5 % от страховой суммы»."""
    value = Decimal(str(value))
    if value == value.to_integral_value():
        number = f'{value:,.0f}'.replace(',', ' ')
    else:
        number = f'{value:,.2f}'.replace(',', ' ').rstrip('0').replace('.', ',')
    if unit == 'percent':
        return f'{number} % от страховой суммы'
    return f'{number} руб.'


def amounts_to_text(amounts: Iterable) -> str:
    """Для поля формы: [30000, 50000] → «30000; 50000»."""
    return '; '.join(format(Decimal(str(a)).normalize(), 'f') for a in amounts or [])

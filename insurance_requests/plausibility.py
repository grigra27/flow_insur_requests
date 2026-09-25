"""Проверки правдоподобия значений заявки — ловят ошибки, которые сотрудник мог не заметить.

docs/improvement_plans/analytics_redesign_2026_09.md, задача 5.4. Правила выведены из
аудита парсера (§4.5): дата рождения ИП «20.02.61» → 2061 год, перепутанные столбцы
мощности и стоимости у спецтехники, год из даты заявки вместо номера ДФА.

`check_values` принимает значения полей заявки (модель, форма превью или объект
из разбора) и возвращает предупреждения в формате предупреждений парсера:
{'level': 'check', 'field': ..., 'label': ..., 'message': ..., 'source': ''}.
Используется на превью загрузки (предупреждение сотруднику) и на странице
«Правки распознавания» (срабатывания на сохранённых заявках).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

LEVEL = 'check'

MIN_AGE, MAX_AGE = 18, 100
MIN_MANUFACTURING_YEAR = 1950
MIN_COST_RUB = Decimal('100000')
# Поле «мощность / грузоподъёмность»: грузоподъёмность в кг законно бывает десятками тысяч,
# поэтому подозрительной считаем только величину, похожую на деньги (перепутанные столбцы).
MONEY_LIKE_POWER = Decimal('1000000')
YEAR_ONLY_RE = re.compile(r'^(19|20)\d{2}$')

LABELS = {
    'birth_date': 'Дата рождения',
    'manufacturing_year': 'Год выпуска',
    'acquisition_cost_value': 'Стоимость',
    'power_or_capacity': 'Мощность',
    'dfa_number': 'Номер ДФА',
    'inn': 'ИНН',
}


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        for pattern in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                return datetime.strptime(value.strip(), pattern).date()
            except ValueError:
                continue
    return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == '':
        return None
    text = str(value).replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _format_amount(value: Decimal) -> str:
    return f'{value:,.0f}'.replace(',', ' ')


def inn_checksum_ok(inn: str) -> bool:
    """Контрольные цифры ИНН (10 цифр — юрлицо, 12 — физлицо/ИП)."""
    digits = [int(char) for char in inn]

    def _control(weights):
        return sum(weight * digit for weight, digit in zip(weights, digits)) % 11 % 10

    if len(digits) == 10:
        return _control([2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
    if len(digits) == 12:
        return (
            _control([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[10]
            and _control([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[11]
        )
    return False


def _warning(field: str, message: str) -> Dict[str, str]:
    return {'level': LEVEL, 'field': field, 'label': LABELS.get(field, field), 'message': message, 'source': ''}


def check_values(values: Dict[str, Any], *, today: Optional[date] = None) -> List[Dict[str, str]]:
    """Предупреждения по значениям заявки или объекта. Пустые значения не проверяются."""
    today = today or date.today()
    warnings: List[Dict[str, str]] = []

    birth_date = _to_date(values.get('birth_date'))
    if birth_date:
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        if birth_date > today:
            warnings.append(_warning('birth_date', f'Дата рождения {birth_date:%d.%m.%Y} в будущем — '
                                                   'похоже на двузначный год в бланке (например, 61 → 2061).'))
        elif not MIN_AGE <= age <= MAX_AGE:
            warnings.append(_warning('birth_date', f'Дата рождения {birth_date:%d.%m.%Y}: возраст {age} лет — проверьте.'))

    year_text = str(values.get('manufacturing_year') or '').strip()
    if year_text.isdigit():
        year = int(year_text)
        if year > today.year + 1 or year < MIN_MANUFACTURING_YEAR:
            warnings.append(_warning('manufacturing_year', f'Год выпуска {year} — проверьте.'))

    cost = _to_decimal(values.get('acquisition_cost_value'))
    currency = (values.get('acquisition_cost_currency') or 'RUB') or 'RUB'
    if cost is not None and cost > 0 and currency == 'RUB' and cost < MIN_COST_RUB:
        warnings.append(_warning(
            'acquisition_cost_value',
            f'Стоимость {_format_amount(cost)} ₽ — слишком мала для предмета лизинга; '
            'возможно, столбцы мощности и стоимости перепутаны.',
        ))

    power = _to_decimal(values.get('power_or_capacity'))
    if power is not None and power >= MONEY_LIKE_POWER:
        warnings.append(_warning(
            'power_or_capacity',
            f'Мощность {_format_amount(power)} — похоже на стоимость; проверьте столбцы.',
        ))

    dfa = str(values.get('dfa_number') or '').strip()
    if YEAR_ONLY_RE.match(dfa):
        warnings.append(_warning('dfa_number', f'Номер ДФА «{dfa}» похож на год, а не на номер договора.'))

    inn = re.sub(r'\D', '', str(values.get('inn') or ''))
    if len(inn) in (10, 12) and not inn_checksum_ok(inn):
        warnings.append(_warning('inn', f'ИНН {inn}: не сходится контрольная сумма — проверьте цифры.'))

    return warnings

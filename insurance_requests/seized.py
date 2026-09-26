"""Сценарий «Изъятое имущество»: лизингодатель страхует изъятый у клиента предмет лизинга.

docs/improvement_plans/analytics_redesign_2026_09.md, задача 6.8. Бланк обычный, поэтому
парсер распознаёт клиента-лизингополучателя, тип и срок из бланка, а сотрудник вручную
переписывал ~10 полей (36% всех ручных правок). Правила подтверждены владельцем 2026-09-25
и сверены с 6 оформленными заявками: клиент — ЗАО «Альянс-Лизинг», страхователь —
лизингодатель, тип — имущество, срок — 1 год, менеджер — Овдина Е.М. (головной офис),
к номеру ДФА дописывается «Изъятое», реквизиты бывшего лизингополучателя очищаются.

Слово «изъят» в имени файла — только подсказка: в корпусе есть заявка («ЗаявкаДЛ …
изъятое»), оформленная как обычная. Поэтому по имени файла на превью предлагается
кнопка, а применяется предзаполнение сразу только по флажку на странице загрузки.
Территория страхования (адрес стоянки) — пока вручную: правило уточняет владелец.
"""
from __future__ import annotations

from typing import Any, Dict

SEIZED_MARKER = 'изъят'
DFA_SUFFIX = 'Изъятое'

PRESET: Dict[str, Any] = {
    'client_name': 'ЗАО "Альянс-Лизинг"',
    'inn': '7825496985',
    'insured_party': 'lessor',
    'insurance_type': 'страхование имущества',
    'insurance_period': '1 год',
    'manager_name': 'Овдина Е.М.',
}
# Реквизиты бывшего лизингополучателя — к страхованию изъятого не относятся.
CLEARED_FIELDS = ('legal_address', 'postal_address', 'business_activity', 'birth_date')


def is_seized_filename(file_name: str) -> bool:
    return SEIZED_MARKER in (file_name or '').lower()


def seized_dfa_number(dfa_number: str) -> str:
    dfa_number = (dfa_number or '').strip()
    if SEIZED_MARKER in dfa_number.lower():
        return dfa_number
    return f'{dfa_number} {DFA_SUFFIX}'.strip()


def apply_seized_preset(parse_result) -> None:
    """Применяет предзаполнение «Изъятое» к результату разбора (флажок на странице загрузки)."""
    data = parse_result.data
    data.update(PRESET)
    data['dfa_number'] = seized_dfa_number(data.get('dfa_number', ''))
    for field in CLEARED_FIELDS:
        data[field] = ''
    parse_result.warnings.append({
        'level': 'info',
        'field': 'seized',
        'message': 'Режим «Изъятое имущество»: клиент — ЗАО «Альянс-Лизинг», страхователь — лизингодатель, '
                   'тип — имущество, срок — 1 год, менеджер — Овдина Е.М. Территорию (адрес стоянки) укажите вручную.',
        'source': '',
    })


def preset_for_form() -> Dict[str, Any]:
    """Значения для кнопки «Заполнить как „Изъятое“» на превью (поля формы → значение)."""
    values = dict(PRESET)
    values.update({field: '' for field in CLEARED_FIELDS})
    return values

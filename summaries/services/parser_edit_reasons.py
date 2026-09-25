"""Причины ручных правок распознавания (docs/improvement_plans/analytics_redesign_2026_09.md, задача 5.3).

Правка относится к одной причине по правилам ниже (порядок важен: сценарий «Изъятое»
определяется по имени файла и перекрывает поле). Причины сгруппированы по виду:

- parser   — известная ошибка парсера, есть задача этапа 6;
- scenario — другой бизнес-сценарий на обычном бланке («Изъятое»);
- other    — прочее: бизнес-уточнения и разовые правки (или новые, ещё не разобранные ошибки).

Классификация — по полю и имени исходного файла; сверена с аудитом правок (§4.5).
"""
from __future__ import annotations

from typing import Dict

SEIZED_MARKER = 'изъят'

KIND_LABELS = {
    'parser': 'Известная ошибка парсера',
    'scenario': 'Другой бизнес-сценарий',
    'other': 'Прочее',
}

REASONS = {
    'seized': {'label': 'Сценарий «Изъятое»', 'kind': 'scenario', 'task': '6.8'},
    'period': {'label': 'Срок страхования', 'kind': 'parser', 'task': '6.1'},
    'autostart': {'label': 'Автозапуск', 'kind': 'parser', 'task': '6.2'},
    'payment': {'label': 'Порядок уплаты и рассрочка', 'kind': 'parser', 'task': '6.3'},
    'birth_date': {'label': 'Дата рождения', 'kind': 'parser', 'task': '6.4'},
    'dfa': {'label': 'Номер ДФА', 'kind': 'parser', 'task': '6.5'},
    'object': {'label': 'Объект: марка, модель, стоимость, категория', 'kind': 'parser', 'task': '6.6'},
    'branch': {'label': 'Филиал не распознан', 'kind': 'parser', 'task': '6.7'},
    'other': {'label': 'Прочее: уточнения и разовые правки', 'kind': 'other', 'task': ''},
}

FIELD_REASONS = {
    'insurance_period': 'period',
    'has_autostart': 'autostart',
    'premium_frequency': 'payment',
    'has_installment': 'payment',
    'birth_date': 'birth_date',
    'dfa_number': 'dfa',
    'brand': 'object',
    'model': 'object',
    'condition': 'object',
    'equipment_type': 'object',
    'power_or_capacity': 'object',
    'acquisition_cost_value': 'object',
    'acquisition_cost_currency': 'object',
    'source_object_count': 'object',
    'manufacturing_year': 'object',
    'vehicle_info': 'object',
    'has_casco_ce': 'object',
    'branch': 'branch',
}


def is_seized_file(file_name: str) -> bool:
    return SEIZED_MARKER in (file_name or '').lower()


def classify(field_name: str, file_name: str = '') -> str:
    """Ключ причины правки для поля и имени исходного файла заявки."""
    if is_seized_file(file_name):
        return 'seized'
    return FIELD_REASONS.get(field_name, 'other')


def reason_info(key: str) -> Dict[str, str]:
    info = REASONS[key]
    return {'key': key, **info, 'kind_label': KIND_LABELS[info['kind']]}


def source_file_name(additional_data) -> str:
    return ((additional_data or {}).get('parser_v2') or {}).get('source_file_name') or ''

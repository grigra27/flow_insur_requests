"""Реестр дополнительных блоков ответа страховщика V2.

docs/improvement_plans/insurer_response_v2.md, §4. Блок описывается здесь один раз; из реестра
работают генератор шаблона (summaries/response_template.py), разбор и валидация ответа, карточка свода,
ручная форма и свод V2. Новый блок — новая запись в SECTIONS.

Модуль без зависимостей от Django: условие получает объект заявки (InsuranceRequest или любой объект
с теми же атрибутами) и смотрит только на его поля.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

CHOICE = 'choice'
MONEY = 'money'
TEXT = 'text'


@dataclass(frozen=True)
class SectionField:
    name: str  # имя поля модели InsurerResponse и (с префиксом resp_) именованной ячейки шаблона
    label: str
    kind: str
    required: bool = True
    choices: Tuple[Tuple[str, str], ...] = ()  # (код в БД, подпись в шаблоне)
    aliases: Tuple[Tuple[str, str], ...] = ()  # (как пишут вручную, код) — для списка значений
    hint: str = ''

    @property
    def cell_name(self) -> str:
        return f'resp_{self.name}'

    @property
    def choice_labels(self) -> Tuple[str, ...]:
        return tuple(label for _code, label in self.choices)

    def match_choice(self, text: str) -> Optional[str]:
        """Код значения по подписи, коду или синониму без учёта регистра; None — не из списка."""
        key = ' '.join(str(text).split()).casefold().rstrip('.')
        for code, label in self.choices:
            if key in (code.casefold(), label.casefold()):
                return code
        return next((code for alias, code in self.aliases if key == alias.casefold()), None)


@dataclass(frozen=True)
class ResponseSection:
    key: str
    title: str
    condition: Callable[[object], bool]
    condition_text: str  # для общего шаблона: «Заполняется, если …»
    fields: Tuple[SectionField, ...] = field(default_factory=tuple)
    summary_column: str = ''  # подпись колонки в своде V2

    def is_required(self, request) -> bool:
        return bool(request is not None and self.condition(request))


RNPK_INCLUDED, RNPK_NOT_INCLUDED, RNPK_APPROVAL = 'included', 'not_included', 'approval'
RNPK_CHOICES = (
    (RNPK_INCLUDED, 'Включены в полис'),
    (RNPK_NOT_INCLUDED, 'Не включены'),
    (RNPK_APPROVAL, 'Требуется согласование'),
)
RNPK_TYPES = ('страхование спецтехники', 'страхование имущества')

RNPK = ResponseSection(
    key='rnpk',
    title='Риски РНПК',
    condition=lambda request: getattr(request, 'insurance_type', None) in RNPK_TYPES,
    condition_text='Заполняется, если вид страхования — спецтехника или имущество',
    fields=(
        SectionField('rnpk_status', 'Риски РНПК в полисе', CHOICE, choices=RNPK_CHOICES, aliases=(
            ('включены', RNPK_INCLUDED), ('включено', RNPK_INCLUDED), ('да', RNPK_INCLUDED),
            ('не включены', RNPK_NOT_INCLUDED), ('не включено', RNPK_NOT_INCLUDED), ('нет', RNPK_NOT_INCLUDED),
            ('согласование', RNPK_APPROVAL), ('требуется согласование рисков рнпк', RNPK_APPROVAL),
            ('нужно согласование', RNPK_APPROVAL),
        )),
        SectionField('rnpk_comment', 'Комментарий (необязательно)', TEXT, required=False),
    ),
    summary_column='Риски РНПК',
)

TRANSPORT = ResponseSection(
    key='transport',
    title='Перевозка (транспортировка) предмета лизинга',
    condition=lambda request: bool(getattr(request, 'has_transportation', False)),
    condition_text='Заполняется, если в запросе указана перевозка',
    fields=(
        SectionField('transport_cost', 'Стоимость страхования перевозки, ₽', MONEY,
                     hint='Одна сумма за перевозку по маршруту из запроса.'),
        SectionField('transport_terms', 'Условия перевозки (необязательно)', TEXT, required=False),
    ),
    summary_column='Перевозка, ₽',
)

SECTIONS: Tuple[ResponseSection, ...] = (RNPK, TRANSPORT)


def required_sections(request) -> List[ResponseSection]:
    """Блоки, обязательные для ответа по этой заявке."""
    return [section for section in SECTIONS if section.is_required(request)]


def all_fields() -> List[SectionField]:
    return [f for section in SECTIONS for f in section.fields]


def transport_route(request) -> str:
    """«Откуда → куда · ориентировочно N дн.» из заявки; пусто, если маршрута нет."""
    departure = (getattr(request, 'transportation_departure', '') or '').strip()
    destination = (getattr(request, 'transportation_destination', '') or '').strip()
    days = getattr(request, 'transportation_days', None)
    route = ' → '.join(part for part in (departure, destination) if part)
    if days:
        route = f'{route} · ориентировочно {days} дн.' if route else f'ориентировочно {days} дн.'
    return route


def section_by_key(key: str) -> Optional[ResponseSection]:
    return next((section for section in SECTIONS if section.key == key), None)

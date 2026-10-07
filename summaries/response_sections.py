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
    short_title: str = ''  # короткое название для карточки свода (по умолчанию — title)
    always: bool = False  # нужен в любом ответе (и в общем шаблоне — «обязательно», а не по условию)

    def is_required(self, request) -> bool:
        if self.always:
            return True
        return bool(request is not None and self.condition(request))


# Осмотр — во всех ответах (решение владельца 2026-10-07): отвечает страховщик, правило «б/у → осмотр»
# в своде V2 не используется (в своде V1 системная фраза про осмотр остаётся как была)
INSPECTION_NOT_REQUIRED, INSPECTION_REQUIRED, INSPECTION_PHOTO = 'not_required', 'required', 'photo'
INSPECTION_CHOICES = (
    (INSPECTION_NOT_REQUIRED, 'Осмотр не требуется'),
    (INSPECTION_REQUIRED, 'Требуется осмотр'),
    (INSPECTION_PHOTO, 'Требуется осмотр, возможен осмотр по фотографиям'),
)

INSPECTION = ResponseSection(
    key='inspection',
    title='Осмотр предмета лизинга',
    condition=lambda request: True,
    condition_text='Заполняется во всех ответах',
    fields=(
        SectionField('inspection_status', 'Осмотр', CHOICE, choices=INSPECTION_CHOICES, aliases=(
            ('не требуется', INSPECTION_NOT_REQUIRED), ('без осмотра', INSPECTION_NOT_REQUIRED),
            ('нет', INSPECTION_NOT_REQUIRED),
            ('требуется', INSPECTION_REQUIRED), ('обязателен', INSPECTION_REQUIRED),
            ('обязателен осмотр', INSPECTION_REQUIRED), ('да', INSPECTION_REQUIRED),
            ('по фото', INSPECTION_PHOTO), ('по фотографиям', INSPECTION_PHOTO),
            ('осмотр по фотографиям', INSPECTION_PHOTO), ('возможен осмотр по фотографиям', INSPECTION_PHOTO),
            ('требуется осмотр (возможен по фото)', INSPECTION_PHOTO),
        )),
    ),
    summary_column='Осмотр',
    short_title='Осмотр',
    always=True,
)


# Ровно два варианта и без комментария (решение владельца 2026-10-07): читается одной фразой с названием
# поля — «Риски РНПК будут прописаны в полисе» / «Риски РНПК не будут прописаны в полисе»
RNPK_INCLUDED, RNPK_NOT_INCLUDED = 'included', 'not_included'
RNPK_CHOICES = (
    (RNPK_INCLUDED, 'Будут прописаны в полисе'),
    (RNPK_NOT_INCLUDED, 'Не будут прописаны в полисе'),
)
RNPK_TYPES = ('страхование спецтехники', 'страхование имущества')

RNPK = ResponseSection(
    key='rnpk',
    title='Риски РНПК',
    condition=lambda request: getattr(request, 'insurance_type', None) in RNPK_TYPES,
    condition_text='Заполняется, если вид страхования — спецтехника или имущество',
    fields=(
        SectionField('rnpk_status', 'Риски РНПК', CHOICE, choices=RNPK_CHOICES, aliases=(
            ('риски рнпк будут прописаны в полисе', RNPK_INCLUDED), ('будут прописаны', RNPK_INCLUDED),
            ('прописаны', RNPK_INCLUDED), ('будут', RNPK_INCLUDED), ('да', RNPK_INCLUDED),
            ('риски рнпк не будут прописаны в полисе', RNPK_NOT_INCLUDED), ('не будут прописаны', RNPK_NOT_INCLUDED),
            ('не прописаны', RNPK_NOT_INCLUDED), ('не будут', RNPK_NOT_INCLUDED), ('нет', RNPK_NOT_INCLUDED),
            # прежние подписи списка — в шаблонах, скачанных до 2026-10-07
            ('включены в полис', RNPK_INCLUDED), ('включены', RNPK_INCLUDED), ('включено', RNPK_INCLUDED),
            ('не включены', RNPK_NOT_INCLUDED), ('не включено', RNPK_NOT_INCLUDED),
        )),
    ),
    summary_column='Риски РНПК',
    short_title='Риски РНПК',
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
    short_title='Перевозка',
)

# Порядок — порядок блоков в шаблоне, колонок в своде V2 и строк на карточке свода
SECTIONS: Tuple[ResponseSection, ...] = (INSPECTION, RNPK, TRANSPORT)


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

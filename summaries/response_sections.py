"""Реестр дополнительных блоков ответа страховщика V2.

docs/improvement_plans/insurer_response_v2.md, §4. Блок описывается здесь один раз; из реестра
работают генератор шаблона (summaries/response_template.py), разбор и валидация ответа, карточка свода,
ручная форма и свод V2. Новый блок — новая запись в SECTIONS.

Модуль без зависимостей от Django: условие получает объект заявки (InsuranceRequest или любой объект
с теми же атрибутами) и смотрит только на его поля.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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
    (INSPECTION_PHOTO, 'Требуется осмотр (возможен по фотографиям)'),
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
            # прежняя подпись (с запятой: в списке Excel/Numbers резалась на два пункта) — шаблоны до 2026-10-07 вечера
            ('требуется осмотр, возможен осмотр по фотографиям', INSPECTION_PHOTO),
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

# Доп. риски КАСКО C/E (решение владельца 2026-10-14): письмо просит расширенные риски, но ≈ 95% ответов
# о них молчат — по своду не видно, включены ли они в цену. Подписи без запятых: в списке Excel/Numbers
# запятая режет пункт на два. Обязателен только для заявок, созданных с даты выката блока: в шаблонах,
# скачанных раньше, блока нет — такие ответы не должны отклоняться.
CE_RISKS_ALL, CE_RISKS_PARTIAL, CE_RISKS_NONE = 'all', 'partial', 'none'
CE_RISKS_CHOICES = (
    (CE_RISKS_ALL, 'Включены все'),
    (CE_RISKS_PARTIAL, 'Включены частично'),
    (CE_RISKS_NONE, 'Не включены'),
)
CE_RISKS_SINCE = date(2026, 10, 15)


def _ce_risks_needed(request) -> bool:
    if not getattr(request, 'has_casco_ce', False):
        return False
    created = getattr(request, 'created_at', None)
    return created is None or created.date() >= CE_RISKS_SINCE


CE_RISKS = ResponseSection(
    key='ce_risks',
    title='Доп. риски КАСКО категории C/E',
    condition=_ce_risks_needed,
    condition_text='Заполняется, если техника категории C/E (запрошены расширенные риски)',
    fields=(
        SectionField('ce_risks_status', 'Расширенные риски', CHOICE, choices=CE_RISKS_CHOICES,
                     hint='Вне дорог общего пользования, провал грунта, переворот, опрокидывание.',
                     aliases=(
                         ('все', CE_RISKS_ALL), ('включены', CE_RISKS_ALL), ('да', CE_RISKS_ALL),
                         ('частично', CE_RISKS_PARTIAL), ('включены не все', CE_RISKS_PARTIAL),
                         ('нет', CE_RISKS_NONE), ('не включено', CE_RISKS_NONE),
                     )),
        SectionField('ce_risks_comment', 'Какие риски включены (если частично)', TEXT, required=False),
    ),
    summary_column='Доп. риски C/E',
    short_title='Доп. риски C/E',
)

TRANSPORT = ResponseSection(
    key='transport',
    title='Перевозка (транспортировка) предмета лизинга',
    condition=lambda request: bool(getattr(request, 'has_transportation', False)),
    condition_text='Заполняется, если в запросе указана перевозка',
    fields=(
        SectionField('transport_cost', 'Премия за перевозку, ₽ (отдельно)', MONEY,
                     hint='Отдельная премия за перевозку по маршруту из запроса. Не включайте её в премию по годам.'),
        SectionField('transport_terms', 'Условия перевозки (необязательно)', TEXT, required=False),
    ),
    summary_column='Перевозка, ₽',
    short_title='Перевозка',
)

# СМР — страхование монтажных (строительно-монтажных) работ на площадке ЛП (решение владельца 2026-10-15).
# Письмо просит его строкой «требуется страхование монтажных работ», ответ приходил только в примечании.
# Подписи без запятых: запятая в списке Excel режет пункт на два.
SMR_SEPARATE, SMR_INCLUDED, SMR_DECLINED = 'separate', 'included', 'declined'
SMR_CHOICES = (
    (SMR_SEPARATE, 'Страхуем — премия отдельно'),
    (SMR_INCLUDED, 'Включено в премию по годам'),
    (SMR_DECLINED, 'Не страхуем'),
)
# Обязателен для заявок со дня выката: ответы на шаблонах, скачанных раньше, не отклоняются
SMR_SINCE = date(2026, 10, 16)


def _smr_needed(request) -> bool:
    if not getattr(request, 'has_construction_work', False):
        return False
    created = getattr(request, 'created_at', None)
    return created is None or created.date() >= SMR_SINCE


SMR = ResponseSection(
    key='smr',
    title='Страхование монтажных работ (СМР)',
    condition=_smr_needed,
    condition_text='Заполняется, если в запросе требуется страхование монтажных (строительно-монтажных) работ',
    fields=(
        SectionField('smr_status', 'Монтажные работы', CHOICE, choices=SMR_CHOICES,
                     hint='Страхование монтажа предмета лизинга на площадке лизингополучателя.', aliases=(
                         ('отдельно', SMR_SEPARATE), ('страхуем', SMR_SEPARATE), ('да', SMR_SEPARATE),
                         ('включено', SMR_INCLUDED), ('включено в премию', SMR_INCLUDED),
                         ('нет', SMR_DECLINED), ('не страхуем', SMR_DECLINED), ('отказ', SMR_DECLINED),
                     )),
        SectionField('smr_cost', 'Премия за СМР, ₽ (если отдельно)', MONEY, required=False,
                     hint='Отдельная премия за страхование монтажа. Не включайте её в премию по годам.'),
        SectionField('smr_terms', 'Условия СМР (необязательно)', TEXT, required=False),
    ),
    summary_column='СМР',
    short_title='СМР',
)

# ОСВР — риски ущерба от военных действий (обстрелы, БПЛА, работа ПВО). Только филиал «Краснодар»
# (решение владельца 2026-10-15): с 20.08.2026 там его указывают все СК, в других филиалах — вручную.
# Альфа даёт ОСВР вторым вариантом (+16–23% к премии) — для этого отдельное значение.
OSVR_INCLUDED, OSVR_LIMITED, OSVR_VARIANT_2, OSVR_NONE = 'included', 'limited', 'variant_2', 'none'
OSVR_CHOICES = (
    (OSVR_INCLUDED, 'Включены'),
    (OSVR_LIMITED, 'Включены с ограничениями'),
    (OSVR_VARIANT_2, 'Только во втором варианте'),
    (OSVR_NONE, 'Не включены'),
)
# Короткие подписи для колонки свода V2
OSVR_SHORT = {OSVR_INCLUDED: 'Включены', OSVR_LIMITED: 'С ограничениями', OSVR_VARIANT_2: 'Во 2-м варианте',
              OSVR_NONE: 'Не включены'}
OSVR_BRANCH = 'Краснодар'  # в т. ч. Ставропольское подразделение (BRANCH_MAPPING)
OSVR_SINCE = date(2026, 10, 16)


def _osvr_needed(request) -> bool:
    if (getattr(request, 'branch', '') or '').strip() != OSVR_BRANCH:
        return False
    created = getattr(request, 'created_at', None)
    return created is None or created.date() >= OSVR_SINCE


OSVR = ResponseSection(
    key='osvr',
    title='Риски ОСВР',
    condition=_osvr_needed,
    condition_text='Заполняется по запросам филиала «Краснодар»',
    fields=(
        SectionField('osvr_status', 'ОСВР', CHOICE, choices=OSVR_CHOICES,
                     hint='ОСВР отдельным вариантом — дайте его во втором варианте.',
                     aliases=(
                         ('с освр', OSVR_INCLUDED), ('да', OSVR_INCLUDED), ('включено', OSVR_INCLUDED),
                         ('с ограничениями', OSVR_LIMITED), ('частично', OSVR_LIMITED),
                         ('во втором варианте', OSVR_VARIANT_2), ('вариант 2', OSVR_VARIANT_2),
                         ('без освр', OSVR_NONE), ('нет', OSVR_NONE), ('не включено', OSVR_NONE),
                     )),
        SectionField('osvr_terms', 'Ограничения и лимит по ОСВР (необязательно)', TEXT, required=False,
                     hint='Регионы-исключения, без БПЛА / ПВО, лимит выплаты.'),
    ),
    summary_column='ОСВР',
    short_title='ОСВР',
)

# Порядок — порядок блоков в шаблоне, колонок в своде V2 и строк на карточке свода
SECTIONS: Tuple[ResponseSection, ...] = (INSPECTION, RNPK, OSVR, CE_RISKS, TRANSPORT, SMR)


def required_sections(request) -> List[ResponseSection]:
    """Блоки, обязательные для ответа по этой заявке."""
    return [section for section in SECTIONS if section.is_required(request)]


def shown_sections(request, responses=()) -> List[ResponseSection]:
    """Блоки для показа (свод V2, карточка свода): нужные по заявке и те, на которые ответ уже есть —
    например, ОСВР, перенесённый из примечаний старых сводов. Проверка загрузки смотрит только на нужные."""
    def answered(section):
        return any(getattr(r, section.fields[0].name, None) not in (None, '') for r in responses)
    return [section for section in SECTIONS if section.is_required(request) or answered(section)]


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

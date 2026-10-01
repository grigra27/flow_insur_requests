"""Выгрузка «Заявка для страховой» в PDF.

В отличие от полной выгрузки карточки (``exporters.py``), которая дампит ВСЕ
поля заявки из базы (включая системные, парсерные и технические), здесь
формируется чистый документ с тем набором данных, который нужен андеррайтеру
страховой компании для расчёта тарифа.

Документ фирменный («ОН-ЛАЙН брокер»: логотип, красный #BA122B и графитовый
#495E5F) и рассчитан на одну альбомную страницу A4. Отбор и группировка полей
живут в ``build_application_context`` и его помощниках, а шаблон только
раскладывает готовые блоки. Пустые и нерелевантные текущему типу страхования
поля в документ не попадают.

Роль документа (решение 2026-10-01 по отзыву сотрудников): это анкета по данным
лизингополучателя — замена исходного Excel. Вопросы к страховщику, просьбы и срок
ответа живут только в сопроводительном письме, поэтому в PDF их нет: иначе документ
дублирует письмо и расходится с ним (срок ответа, территория, период).
"""
from __future__ import annotations

import os
from decimal import Decimal
from io import BytesIO
from typing import Optional

import pytz
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import get_valid_filename


MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Шрифты с кириллицей (PT Sans, OFL) и логотип для xhtml2pdf: reportlab под
# капотом не имеет кириллицы в стандартных Type1-шрифтах. Лежат в репозитории —
# Dockerfile трогать не нужно.
CORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'core')
FONT_DIR = os.path.join(CORE_DIR, 'fonts')
BRAND_DIR = os.path.join(CORE_DIR, 'brand')


# --- помощники извлечения значений -------------------------------------------

def _text(value) -> Optional[str]:
    """Непустой текст или None (строку с одними пробелами считаем пустой)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _display(insurance_request, field_name: str) -> Optional[str]:
    """Человекочитаемое значение поля с choices (get_FOO_display)."""
    raw = getattr(insurance_request, field_name, None)
    if not _text(raw):
        return None
    getter = getattr(insurance_request, f'get_{field_name}_display', None)
    if callable(getter):
        return _text(getter())
    return _text(raw)


def _yes(value) -> Optional[str]:
    """«Да» для взведённого флага, иначе ничего (False = просто отсутствие)."""
    return 'Да' if value else None


def _date(value) -> Optional[str]:
    return value.strftime('%d.%m.%Y') if value else None


def _franchise(insurance_request) -> Optional[str]:
    """Франшиза с размером, без просьб к страховщику: «Оба варианта: без франшизы и с франшизой 30 000 руб.»."""
    if not _text(insurance_request.franchise_type):
        return None
    text = insurance_request.franchise_display
    if (insurance_request.franchise_type != 'none' and not insurance_request.franchise_amounts
            and not insurance_request.is_parser_v2):
        text = f'{text} (размер — в исходном Excel)'
    return text


# --- состав документа ---------------------------------------------------------
# Документ — одна альбомная страница A4 в фирменном стиле «ОН-ЛАЙН брокер»:
# шапка с логотипом и пометкой «приложение к запросу», полоса реквизитов сделки,
# три колонки (лизингополучатель / объект / условия) и плитки параметров и рисков
# на всю ширину. Каждая строка показывается, только если её значение непустое;
# флаги рисков выводятся явно — и «Да», и «Нет».

PROPERTY_TYPE = 'страхование имущества'

# Длинные значения (условия охраны и т.п.) не влезают в плитку — они уходят
# отдельной строкой на всю ширину под плитками.
LONG_VALUE_THRESHOLD = 45

# Плиток параметров в одном ряду (блок на всю ширину страницы).
TILES_PER_ROW = 6


def _rows(pairs):
    """Оставляет только пары (подпись, значение) с непустым значением."""
    return [(label, value) for label, value in pairs if _text(value)]


def _capitalize(text: Optional[str]) -> Optional[str]:
    return text[:1].upper() + text[1:] if text else text


def _money(value, currency) -> Optional[str]:
    if value is None:
        return None
    amount = f'{value:,.0f}'.replace(',', ' ')
    if (currency or 'RUB') == 'RUB':
        return f'{amount} руб.'
    return f'{amount} {currency}'


def _premium(insurance_request) -> Optional[str]:
    label = _display(insurance_request, 'premium_frequency')
    if label and insurance_request.has_installment:
        return f'{label} (рассрочка)'
    return label


def _flag(label, on) -> dict:
    return {'label': label, 'value': 'Да' if on else 'Нет', 'state': 'on' if on else 'off'}


def _info(label, value) -> Optional[dict]:
    value = _text(value)
    return {'label': label, 'value': value, 'state': 'info'} if value else None


def _insured_rows(r):
    postal = _text(r.postal_address)
    if postal and postal == _text(r.legal_address):
        postal = 'совпадает с юридическим'
    return _rows([
        ('Наименование', _text(r.client_name)),
        ('ИНН', _text(r.inn)),
        ('Дата рождения (ИП)', _date(r.birth_date)),
        ('Юридический адрес', _text(r.legal_address)),
        ('Почтовый адрес', postal),
        ('Вид деятельности', _text(r.business_activity)),
    ])


# Колонка L бланка общая: мощность (кат. B), грузоподъёмность (кат. C, прицепы),
# количество мест (кат. D), мощность/производительность (спецтехника) — подписываем по категории.
POWER_LABELS = {
    'категория b': 'Мощность, л.с.',
    'категория c': 'Грузоподъёмность',
    'категория е': 'Грузоподъёмность',  # кириллическая «Е», как в бланках
    'категория e': 'Грузоподъёмность',
    'прицепы': 'Грузоподъёмность',
    'категория d': 'Количество мест',
}


def power_label(insurance_request) -> str:
    kind = (_text(insurance_request.equipment_type) or '').lower()
    return POWER_LABELS.get(kind, 'Мощность / производ.')


def _units_label(count: int) -> str:
    """6 → «6 единиц», 2 → «2 единицы», 21 → «21 единица»."""
    if count % 10 == 1 and count % 100 != 11:
        word = 'единица'
    elif 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        word = 'единицы'
    else:
        word = 'единиц'
    return f'{count} {word}'


def _object_facts(r):
    return _rows([
        ('Год выпуска', _text(r.manufacturing_year)),
        ('Состояние', _text(r.condition_label)),
        ('Тип / категория', _text(r.equipment_type)),
        (power_label(r), _text(r.power_or_capacity)),
    ])


def _terms_rows(r):
    return _rows([
        ('Тип страхования', _capitalize(_text(r.insurance_type))),
        ('Срок страхования', _capitalize(_text(r.insurance_period))),
        ('Территория', _text(r.insurance_territory)),
        ('Франшиза', _franchise(r)),
        ('Уплата премии', _premium(r)),
        ('Страхователь', _display(r, 'insured_party')),
        ('Страховая сумма', _display(r, 'insured_sum_type')),
        ('Банк-кредитор', _text(r.creditor_bank)),
        ('Место расположения', _display(r, 'property_location_right_holder')),
    ])


def _risk_items(r):
    """Плитки параметров: флаги (Да/Нет) и короткие справочные значения."""
    from .seized import is_seized_request

    # У изъятого «охрана и хранение» — условия прежнего клиента; хранение описывается в письме.
    guard = None if is_seized_request(r) else r.guard_conditions
    if r.insurance_type == PROPERTY_TYPE:
        items = [
            _flag('Перевозка', r.has_transportation),
            _flag('Строительно-монтажные работы', r.has_construction_work),
            _info('Цели использования', r.usage_purposes),
            _info('Охрана и хранение', guard),
        ]
    else:
        items = [
            _flag('Автозапуск', r.has_autostart),
            _flag('КАСКО кат. C/E', r.has_casco_ce),
            _flag('Перевозка', r.has_transportation),
            _flag('Строительно-монтажные работы', True) if r.has_construction_work else None,
            _info('Комплектов ключей', r.key_completeness),
            _info('ПТС / ПСМ', r.pts_psm),
            _info('Телематика', r.telematics_complex),
            _info('Цели использования', r.usage_purposes),
            _info('Охрана и хранение', guard),
        ]
    return [item for item in items if item]


def _transport_row(r):
    if not r.has_transportation:
        return None
    route = ' — '.join(
        part for part in (_text(r.transportation_departure), _text(r.transportation_destination)) if part
    )
    if r.transportation_days:
        route = f'{route} · {r.transportation_days} дн.' if route else f'{r.transportation_days} дн.'
    return ('Маршрут перевозки', route) if route else None


def build_application_context(insurance_request) -> dict:
    """Готовит контекст фирменного PDF-шаблона заявки для страховой."""
    r = insurance_request
    title = _capitalize(_text(r.object_display_name)) or 'Объект не указан'

    kind = [part for part in (
        _text(r.machine_kind),
        f'марка {r.object_brand}' if _text(r.object_brand) else None,
    ) if part]

    risk_items = _risk_items(r)
    long_rows = [
        (item['label'], item['value']) for item in risk_items
        if item['state'] == 'info' and len(item['value']) > LONG_VALUE_THRESHOLD
    ]
    tiles = [item for item in risk_items
             if not (item['state'] == 'info' and len(item['value']) > LONG_VALUE_THRESHOLD)]
    tile_rows = [tiles[i:i + TILES_PER_ROW] for i in range(0, len(tiles), TILES_PER_ROW)]
    if tile_rows and len(tile_rows[-1]) < TILES_PER_ROW:
        tile_rows[-1] = tile_rows[-1] + [None] * (TILES_PER_ROW - len(tile_rows[-1]))
    transport = _transport_row(r)
    if transport:
        long_rows.append(transport)

    facts = _object_facts(r)
    quantity = max(r.source_object_count or 1, 1)
    # Старый загрузчик (до июня 2026) не разбирал стоимость и характеристики объекта —
    # честно говорим об этом вместо «не указана» (решение по отзыву сотрудников 2026-10-01).
    legacy = not r.is_parser_v2
    cost = _money(r.acquisition_cost_value, r.acquisition_cost_currency)
    cost_known = bool(cost)
    if not cost:
        cost = 'не разбиралась — см. исходный Excel' if legacy else 'не указана'
    author = (r.created_by.get_full_name() or r.created_by.username) if r.created_by_id else None
    generated_at = timezone.localtime(timezone.now(), MOSCOW_TZ).strftime('%d.%m.%Y %H:%M')
    return {
        'request': r,
        'title': r.get_display_name(),
        'type_label': _text(r.insurance_type) or '',
        'object_title': title,
        'object_kind': ' · '.join(kind),
        'client_name': _text(r.client_name),
        'batch_label': f'объект {r.item_no} из {r.item_count} по ДФА' if (r.item_count or 0) > 1 else None,
        'strip': _rows([
            ('Номер ДФА', _text(r.dfa_number)),
            ('Филиал', _text(r.branch)),
            ('Сделка', _display(r, 'deal_status')),
            ('Дата подачи', _date(r.submission_date)),
            # Менеджер сделки — наш сотрудник, загрузивший заявку (кому отвечать),
            # а не менеджер лизинговой компании из бланка.
            ('Менеджер сделки', author),
        ]),
        'insured_rows': _insured_rows(r),
        'facts': facts,
        'facts_width': 100 // max(len(facts), 1),
        'cost': cost,
        'cost_known': cost_known,
        'legacy_note': (
            'Заявка загружена старым загрузчиком: стоимость и характеристики объекта не разбирались — '
            'сверяйте с исходным Excel лизингополучателя.'
        ) if legacy else None,
        # Несколько одинаковых единиц (одна строка ×N в бланке) — выделяем ярко: страховщик
        # должен сразу видеть, что считает N единиц, а цена указана за одну (2026-10-01).
        'quantity_count': quantity if quantity > 1 else None,
        'quantity_label': _units_label(quantity) if quantity > 1 else None,
        'cost_total': (
            _money(Decimal(str(r.acquisition_cost_value)) * quantity, r.acquisition_cost_currency)
            if quantity > 1 and r.acquisition_cost_value is not None else None
        ),
        'terms_rows': _terms_rows(r),
        'tile_rows': tile_rows,
        'long_rows': long_rows,
        'author': author,
        'generated_at': generated_at,
    }


def batch_members(insurance_request) -> list:
    """Все заявки-объекты партии по порядку; для одиночной заявки — она сама."""
    from .models import InsuranceRequest

    if not insurance_request.source_batch_id or (insurance_request.item_count or 0) <= 1:
        return [insurance_request]
    members = list(
        InsuranceRequest.objects.filter(source_batch_id=insurance_request.source_batch_id)
        .select_related('created_by').order_by('item_no')
    )
    return members or [insurance_request]


def build_batch_application_context(insurance_request) -> dict:
    """Контекст PDF «на всю партию»: общие данные — как у обычной заявки, объекты — таблицей.

    Решение 2026-10-01 по отзыву сотрудников: одна заявка лизингополучателя на 8 единиц техники
    превращалась в 5 заявок и 5 PDF; страховщику удобнее один документ. Заявки и своды
    по-прежнему отдельные на каждый объект.
    """
    members = batch_members(insurance_request)
    context = build_application_context(insurance_request)

    rows, units, total, currencies, total_known = [], 0, Decimal('0'), set(), True
    for member in members:
        qty = max(member.source_object_count or 1, 1)
        units += qty
        cost = member.acquisition_cost_value
        currency = member.acquisition_cost_currency
        if cost is None:
            total_known = False
        else:
            total += Decimal(str(cost)) * qty
            currencies.add(currency or 'RUB')
        rows.append({
            'name': _capitalize(_text(member.object_display_name)) or 'Объект не указан',
            'year': _text(member.manufacturing_year),
            'condition': _text(member.condition_label),
            'kind': _text(member.equipment_type),
            'power': (
                f'{power_label(member).split(",")[0].lower()}: {member.power_or_capacity}'
                if _text(member.power_or_capacity) else None
            ),
            'qty': qty,
            'cost': _money(cost, currency) or '—',
            'sum': _money(Decimal(str(cost)) * qty, currency) if cost is not None else '—',
        })

    # КАСКО C/E — флаг объекта: в партии он «Да», если он есть хотя бы у одного объекта.
    if any(member.has_casco_ce for member in members):
        for line in context['tile_rows']:
            for tile in line:
                if tile and tile['label'] == 'КАСКО кат. C/E':
                    tile.update(value='Да', state='on')

    context.update({
        'object_title': f'Партия: {len(members)} поз. · {units} ед.',
        'batch_label': None,
        'batch_rows': rows,
        'batch_positions': len(members),
        'batch_units': units,
        'batch_total': (
            _money(total, currencies.pop() if currencies else 'RUB')
            if total_known and len(currencies) <= 1 else None
        ),
        'legacy_note': None,
        # Количество одной позиции — в таблице партии, не в шапке.
        'quantity_count': None,
        'quantity_label': None,
        'cost_total': None,
    })
    return context


def build_application_filename(insurance_request, batch: bool = False) -> str:
    base_name = insurance_request.dfa_number or f'request_{insurance_request.pk}'
    safe_name = get_valid_filename(base_name) or f'request_{insurance_request.pk}'
    safe_name = safe_name[:80]
    timestamp = timezone.localtime(timezone.now(), MOSCOW_TZ).strftime('%Y%m%d_%H%M')
    prefix = 'application_batch' if batch else 'application'
    return f'{prefix}_{safe_name}_{timestamp}.pdf'


def _link_callback(uri: str, rel: str) -> str:
    """Резолвит ссылки шаблона (шрифты, логотип) в абсолютные пути файловой системы."""
    for prefix, directory in (('fonts/', FONT_DIR), ('brand/', BRAND_DIR)):
        if uri.startswith(prefix):
            path = os.path.join(directory, os.path.basename(uri))
            if os.path.exists(path):
                return path
    return uri


def render_application_pdf(insurance_request, batch: bool = False) -> bytes:
    """Рендерит заявку для страховой в PDF (bytes); batch=True — один документ на всю партию."""
    # Импорт внутри функции, чтобы отсутствие пакета не ломало импорт views.
    from xhtml2pdf import pisa

    if batch:
        context = build_batch_application_context(insurance_request)
        html = render_to_string('insurance_requests/application_batch_pdf.html', context)
    else:
        context = build_application_context(insurance_request)
        html = render_to_string('insurance_requests/application_pdf.html', context)

    buffer = BytesIO()
    status = pisa.CreatePDF(
        src=html,
        dest=buffer,
        link_callback=_link_callback,
        encoding='utf-8',
    )
    if status.err:
        raise RuntimeError(f'xhtml2pdf вернул {status.err} ошибок при генерации PDF заявки')
    return buffer.getvalue()

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
    return insurance_request.franchise_display


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


def _object_facts(r):
    return _rows([
        ('Год выпуска', _text(r.manufacturing_year)),
        ('Состояние', _text(r.condition_label)),
        ('Тип / категория', _text(r.equipment_type)),
        ('Мощность / производ.', _text(r.power_or_capacity)),
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
    if r.insurance_type == PROPERTY_TYPE:
        items = [
            _flag('Перевозка', r.has_transportation),
            _flag('Строительно-монтажные работы', r.has_construction_work),
            _info('Цели использования', r.usage_purposes),
            _info('Охрана и хранение', r.guard_conditions),
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
            _info('Охрана и хранение', r.guard_conditions),
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
        'cost': _money(r.acquisition_cost_value, r.acquisition_cost_currency),
        'quantity': (
            f'× {r.source_object_count} одинаковых объекта'
            if (r.source_object_count or 0) > 1 else None
        ),
        'terms_rows': _terms_rows(r),
        'tile_rows': tile_rows,
        'long_rows': long_rows,
        'author': author,
        'generated_at': generated_at,
    }


def build_application_filename(insurance_request) -> str:
    base_name = insurance_request.dfa_number or f'request_{insurance_request.pk}'
    safe_name = get_valid_filename(base_name) or f'request_{insurance_request.pk}'
    safe_name = safe_name[:80]
    timestamp = timezone.localtime(timezone.now(), MOSCOW_TZ).strftime('%Y%m%d_%H%M')
    return f'application_{safe_name}_{timestamp}.pdf'


def _link_callback(uri: str, rel: str) -> str:
    """Резолвит ссылки шаблона (шрифты, логотип) в абсолютные пути файловой системы."""
    for prefix, directory in (('fonts/', FONT_DIR), ('brand/', BRAND_DIR)):
        if uri.startswith(prefix):
            path = os.path.join(directory, os.path.basename(uri))
            if os.path.exists(path):
                return path
    return uri


def render_application_pdf(insurance_request) -> bytes:
    """Рендерит заявку для страховой в PDF (bytes)."""
    # Импорт внутри функции, чтобы отсутствие пакета не ломало импорт views.
    from xhtml2pdf import pisa

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

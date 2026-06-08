"""Выгрузка «Заявка для страховой» в PDF.

В отличие от полной выгрузки карточки (``exporters.py``), которая дампит ВСЕ
поля заявки из базы (включая системные, парсерные и технические), здесь
формируется чистый документ с тем набором данных, который нужен андеррайтеру
страховой компании для расчёта тарифа.

Логика отбора полей собрана в одном декларативном манифесте ``SECTIONS``:
каждая секция — это набор строк, а каждая строка знает, как достать своё
значение из заявки и показывать ли себя вообще. Пустые и нерелевантные
текущему типу страхования поля в документ не попадают — секция без строк
не выводится. Так логика «что класть в заявку» не размазана по шаблону и
переиспользуема, если позже понадобится JSON/Excel-вариант той же заявки.
"""
from __future__ import annotations

import os
from io import BytesIO
from typing import Callable, List, NamedTuple, Optional

import pytz
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import get_valid_filename


MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Шрифты с кириллицей для xhtml2pdf (reportlab под капотом не имеет кириллицы
# в стандартных Type1-шрифтах). Лежат в репозитории — Dockerfile трогать не нужно.
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'core', 'fonts')


class Row(NamedTuple):
    """Одна строка документа: подпись и функция, достающая значение."""

    label: str
    value: Callable[['object'], Optional[str]]


class Section(NamedTuple):
    """Логический блок заявки с заголовком и строками."""

    title: str
    rows: List[Row]


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


def _deadline(insurance_request) -> Optional[str]:
    moscow = insurance_request.response_deadline_moscow
    return moscow.strftime('%H:%M %d.%m.%Y') if moscow else None


def _date(value) -> Optional[str]:
    return value.strftime('%d.%m.%Y') if value else None


def _franchise(insurance_request) -> Optional[str]:
    """Франшиза; для both_variants просим явно два расчёта."""
    label = _display(insurance_request, 'franchise_type')
    if not label:
        return None
    if insurance_request.franchise_type == 'both_variants':
        return f'{label} (просьба рассчитать оба варианта — с франшизой и без)'
    return label


def _transportation(insurance_request) -> Optional[str]:
    """Маршрут перевозки одной строкой, если перевозка требуется."""
    if not insurance_request.has_transportation:
        return None
    departure = _text(insurance_request.transportation_departure)
    destination = _text(insurance_request.transportation_destination)
    parts = []
    if departure or destination:
        parts.append(f'{departure or "—"} → {destination or "—"}')
    if insurance_request.transportation_days:
        parts.append(f'срок {insurance_request.transportation_days} дн.')
    return ', '.join(parts) if parts else 'Да'


# --- манифест секций ----------------------------------------------------------
# Порядок строк = порядок в документе. Строка показывается, только если её
# value(...) вернул непустую строку; пустая секция целиком не выводится.

SECTIONS: List[Section] = [
    Section('Заявка', [
        Row('Номер ДФА', lambda r: _text(r.dfa_number)),
        Row('Филиал', lambda r: _text(r.branch)),
        Row('Статус сделки', lambda r: _display(r, 'deal_status')),
        Row('Дата подачи', lambda r: _date(r.submission_date)),
        Row('Менеджер', lambda r: _text(r.manager_name)),
        Row('Срок ответа (МСК)', _deadline),
    ]),
    Section('Страхователь', [
        Row('Наименование', lambda r: _text(r.client_name)),
        Row('ИНН', lambda r: _text(r.inn)),
        Row('Дата рождения (ИП)', lambda r: _date(r.birth_date)),
        Row('Юридический адрес', lambda r: _text(r.legal_address)),
        Row('Почтовый адрес', lambda r: _text(r.postal_address)),
        Row('Основной вид деятельности', lambda r: _text(r.business_activity)),
    ]),
    Section('Объект страхования', [
        Row('Объект', lambda r: _text(r.object_display_name)),
        Row('Год выпуска', lambda r: _text(r.manufacturing_year)),
        Row('Состояние', lambda r: _text(r.condition_label)),
        Row('Тип/категория техники', lambda r: _text(r.equipment_type)),
        Row('Мощность/производительность', lambda r: _text(r.power_or_capacity)),
        Row('Стоимость приобретения', lambda r: _text(r.acquisition_cost_display)),
        Row('Количество одинаковых объектов',
            lambda r: str(r.source_object_count) if (r.source_object_count or 0) > 1 else None),
        Row('Описание объекта', lambda r: _text(r.object_description)),
    ]),
    Section('Условия страхования', [
        Row('Тип страхования', lambda r: _text(r.insurance_type)),
        Row('Срок страхования', lambda r: _text(r.insurance_period)),
        Row('Территория страхования', lambda r: _text(r.insurance_territory)),
        Row('Франшиза', _franchise),
        Row('Частота уплаты премии', lambda r: _display(r, 'premium_frequency')),
        Row('Рассрочка', lambda r: _yes(r.has_installment)),
    ]),
    Section('Дополнительные риски и параметры', [
        Row('Автозапуск', lambda r: _yes(r.has_autostart)),
        Row('КАСКО кат. C/E', lambda r: _yes(r.has_casco_ce)),
        Row('Комплектность ключей', lambda r: _text(r.key_completeness)),
        Row('ПТС/ПСМ', lambda r: _text(r.pts_psm)),
        Row('Телематический комплекс', lambda r: _text(r.telematics_complex)),
        Row('Банк-кредитор', lambda r: _text(r.creditor_bank)),
        Row('Цели использования', lambda r: _text(r.usage_purposes)),
        Row('Перевозка', _transportation),
        Row('Строительно-монтажные работы (СМР)', lambda r: _yes(r.has_construction_work)),
    ]),
    Section('Условия страхования имущества', [
        Row('Страхователь', lambda r: _display(r, 'insured_party')),
        Row('Тип страховой суммы', lambda r: _display(r, 'insured_sum_type')),
        Row('Условия охраны/хранения', lambda r: _text(r.guard_conditions)),
        Row('Правообладатель места расположения',
            lambda r: _display(r, 'property_location_right_holder')),
    ]),
]


def build_application_context(insurance_request) -> dict:
    """Готовит контекст для PDF-шаблона: только непустые строки и секции."""
    sections = []
    for section in SECTIONS:
        rows = []
        for row in section.rows:
            value = row.value(insurance_request)
            if _text(value):
                rows.append({'label': row.label, 'value': value})
        if rows:
            sections.append({'title': section.title, 'rows': rows})

    generated_at = timezone.localtime(timezone.now(), MOSCOW_TZ).strftime('%d.%m.%Y %H:%M')
    return {
        'request': insurance_request,
        'title': insurance_request.get_display_name(),
        'sections': sections,
        'deadline': _deadline(insurance_request),
        'generated_at': generated_at,
    }


def build_application_filename(insurance_request) -> str:
    base_name = insurance_request.dfa_number or f'request_{insurance_request.pk}'
    safe_name = get_valid_filename(base_name) or f'request_{insurance_request.pk}'
    safe_name = safe_name[:80]
    timestamp = timezone.localtime(timezone.now(), MOSCOW_TZ).strftime('%Y%m%d_%H%M')
    return f'application_{safe_name}_{timestamp}.pdf'


def _link_callback(uri: str, rel: str) -> str:
    """Резолвит ссылки шаблона (шрифты) в абсолютные пути файловой системы."""
    if uri.startswith('fonts/'):
        path = os.path.join(FONT_DIR, os.path.basename(uri))
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

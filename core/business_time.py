"""Рабочее время офиса и срок ответа страховщика.

Срок ответа = момент загрузки заявки + RESPONSE_DEADLINE_WORK_HOURS рабочих часов.
Нерабочее время пропускается, остаток переносится на следующий рабочий день.

Рабочие дни берутся из производственного календаря РФ (isdayoff.ru: один запрос
на год, ответ кэшируется на сутки). Если сервис недоступен или календарь на год
ещё не опубликован, считаем по обычной неделе с фиксированными праздниками
ст. 112 ТК РФ — без переносов и сокращённых дней — и пишем warning в лог.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo('Europe/Moscow')

# Коды isdayoff.ru (pre=1)
WORKING = '0'
NOT_WORKING = '1'
SHORTENED = '2'

# Нерабочие праздничные дни по ст. 112 ТК РФ (месяц, день)
FIXED_HOLIDAYS = frozenset(
    [(1, day) for day in range(1, 9)] + [(2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)]
)

CACHE_TTL_OK = 24 * 3600
CACHE_TTL_FAILED = 3600  # чтобы при недоступном сервисе не ждать таймаут на каждой загрузке
REQUEST_TIMEOUT = 3
# В опубликованном календаре выходных за год не меньше ~118; меньше 100 — данных нет
# (за неопубликованный год isdayoff отвечает 200 и строкой из одних нулей)
MIN_DAYS_OFF_PER_YEAR = 100


def _fetch_year(year: int) -> Optional[str]:
    """Строка кодов дней года с isdayoff.ru или None, если данных нет."""
    url_template = getattr(settings, 'PRODUCTION_CALENDAR_URL', '')
    if not url_template:
        return None
    try:
        response = requests.get(url_template.format(year=year), timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.text.strip()
    except requests.RequestException as exc:
        logger.warning("Производственный календарь %s: isdayoff.ru недоступен (%s)", year, exc)
        return None

    expected_days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    if len(data) != expected_days or set(data) - set('0124'):
        logger.warning("Производственный календарь %s: неожиданный ответ isdayoff.ru: %r", year, data[:40])
        return None
    if data.count(NOT_WORKING) < MIN_DAYS_OFF_PER_YEAR:
        logger.warning("Производственный календарь %s ещё не опубликован на isdayoff.ru", year)
        return None
    return data


def _year_codes(year: int) -> Optional[str]:
    key = f'production_calendar:ru:{year}'
    cached = cache.get(key)
    if cached is not None:
        return cached or None  # '' — закэшированная неудача
    data = _fetch_year(year)
    cache.set(key, data or '', CACHE_TTL_OK if data else CACHE_TTL_FAILED)
    if not data:
        logger.warning(
            "Производственный календарь %s: считаем по обычной неделе и праздникам ст. 112 ТК", year
        )
    return data


def day_kind(day: date) -> str:
    """Тип дня: WORKING, NOT_WORKING или SHORTENED."""
    codes = _year_codes(day.year)
    if codes:
        code = codes[day.timetuple().tm_yday - 1]
        return SHORTENED if code == SHORTENED else (NOT_WORKING if code == NOT_WORKING else WORKING)
    if day.weekday() >= 5 or (day.month, day.day) in FIXED_HOLIDAYS:
        return NOT_WORKING
    return WORKING


def work_window(day: date) -> Optional[Tuple[datetime, datetime]]:
    """Начало и конец рабочего дня по Москве или None для нерабочего дня."""
    kind = day_kind(day)
    if kind == NOT_WORKING:
        return None
    start_hour = settings.WORKDAY_START_HOUR
    end_hour = settings.WORKDAY_END_HOURS[day.weekday()]
    if kind == SHORTENED:
        end_hour -= 1
    return (
        datetime.combine(day, time(start_hour), tzinfo=MOSCOW_TZ),
        datetime.combine(day, time(end_hour), tzinfo=MOSCOW_TZ),
    )


def add_business_hours(start: datetime, hours: float) -> datetime:
    """start + hours рабочих часов (по Москве); результат — aware datetime в МСК."""
    current = timezone.localtime(start, MOSCOW_TZ)
    remaining = timedelta(hours=hours)
    for _ in range(366):
        window = work_window(current.date())
        if window:
            opens, closes = window
            current = max(current, opens)
            if current < closes:
                available = closes - current
                if remaining <= available:
                    return current + remaining
                remaining -= available
        current = datetime.combine(current.date() + timedelta(days=1), time(0), tzinfo=MOSCOW_TZ)
    # Год без рабочих дней — испорченные данные календаря; не блокируем загрузку заявки
    logger.error("Не найдено рабочее время в течение года от %s, срок посчитан по часам", start)
    return timezone.localtime(start, MOSCOW_TZ) + timedelta(hours=hours)


def response_deadline(start: Optional[datetime] = None) -> datetime:
    """Срок ответа страховщика для заявки, загруженной в момент start (по умолчанию — сейчас)."""
    return add_business_hours(start or timezone.now(), settings.RESPONSE_DEADLINE_WORK_HOURS)

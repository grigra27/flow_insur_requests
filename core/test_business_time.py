"""Срок ответа страховщика в рабочих часах по производственному календарю."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from core import business_time
from core.business_time import MOSCOW_TZ, add_business_hours, response_deadline

# Календарь 2026 как его отдаёт isdayoff.ru (pre=1), сверено с ответом API
DAYS_OFF_2026 = {
    date(2026, 1, d) for d in (1, 2, 5, 6, 7, 8, 9)
} | {date(2026, 2, 23), date(2026, 3, 9), date(2026, 5, 1), date(2026, 5, 11),
     date(2026, 6, 12), date(2026, 11, 4), date(2026, 12, 31)}
SHORTENED_2026 = {date(2026, 4, 30), date(2026, 5, 8), date(2026, 6, 11), date(2026, 11, 3)}


def _codes(year, days_off=frozenset(), shortened=frozenset(), working_weekends=frozenset()):
    day, codes = date(year, 1, 1), []
    while day.year == year:
        if day in shortened:
            codes.append('2')
        elif day in days_off or (day.weekday() >= 5 and day not in working_weekends):
            codes.append('1')
        else:
            codes.append('0')
        day += timedelta(days=1)
    return ''.join(codes)


CODES_2026 = _codes(2026, DAYS_OFF_2026, SHORTENED_2026)


def msk(*args):
    return datetime(*args, tzinfo=MOSCOW_TZ)


@override_settings(RESPONSE_DEADLINE_WORK_HOURS=4)
class AddBusinessHoursTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        # 2026 — опубликован, 2027 — ещё нет (как сейчас на isdayoff.ru)
        patcher = mock.patch.object(
            business_time, '_fetch_year', side_effect=lambda year: CODES_2026 if year == 2026 else None
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(cache.clear)

    def assertDeadline(self, start, expected):
        self.assertEqual(response_deadline(start), expected)

    def test_friday_evening_rolls_remainder_to_monday(self):
        # Пятница до 17:00: 1 час в пятницу + 3 часа в понедельник
        self.assertDeadline(msk(2026, 10, 2, 16, 0), msk(2026, 10, 5, 13, 0))

    def test_weekday_afternoon_rolls_to_next_morning(self):
        self.assertDeadline(msk(2026, 10, 6, 15, 30), msk(2026, 10, 7, 11, 30))

    def test_before_opening_counts_from_ten(self):
        self.assertDeadline(msk(2026, 10, 6, 8, 45), msk(2026, 10, 6, 14, 0))

    def test_ending_exactly_at_close_stays_same_day(self):
        self.assertDeadline(msk(2026, 10, 7, 14, 0), msk(2026, 10, 7, 18, 0))

    def test_after_close_and_weekend_upload(self):
        self.assertDeadline(msk(2026, 10, 7, 19, 15), msk(2026, 10, 8, 14, 0))
        self.assertDeadline(msk(2026, 10, 3, 12, 0), msk(2026, 10, 5, 14, 0))

    def test_minutes_kept_without_rounding(self):
        self.assertDeadline(msk(2026, 10, 6, 11, 37, 20), msk(2026, 10, 6, 15, 37, 20))

    def test_shortened_pre_holiday_day_ends_hour_earlier(self):
        # 29.04 до 18:00 — 2 часа, 30.04 сокращённый (до 17:00) — ещё 2
        self.assertDeadline(msk(2026, 4, 29, 16, 0), msk(2026, 4, 30, 12, 0))
        # 30.04 15:00: 2 часа до 17:00, 1–3 мая выходные, 4.05 с 10:00 — ещё 2
        self.assertDeadline(msk(2026, 4, 30, 15, 0), msk(2026, 5, 4, 12, 0))

    def test_shortened_friday_ends_at_sixteen(self):
        # 8.05 — сокращённая пятница (до 16:00), 9–11.05 выходные
        self.assertDeadline(msk(2026, 5, 8, 15, 0), msk(2026, 5, 12, 13, 0))

    def test_transferred_day_off(self):
        # 9.03.2026 (понедельник) — перенесённый выходной
        self.assertDeadline(msk(2026, 3, 6, 16, 30), msk(2026, 3, 10, 13, 30))

    def test_new_year_with_unpublished_next_year_uses_labour_code_holidays(self):
        # 31.12.2026 — выходной; 2027 не опубликован: 1–8 января нерабочие по ст. 112 ТК
        self.assertDeadline(msk(2026, 12, 30, 17, 0), msk(2027, 1, 11, 13, 0))

    def test_working_saturday_from_calendar(self):
        codes = _codes(2026, working_weekends={date(2026, 10, 3)})
        with mock.patch.object(business_time, '_year_codes', return_value=codes):
            self.assertDeadline(msk(2026, 10, 2, 16, 0), msk(2026, 10, 3, 13, 0))

    def test_utc_input_is_converted_to_moscow(self):
        start = datetime(2026, 10, 2, 13, 0, tzinfo=dt_timezone.utc)  # 16:00 МСК
        result = response_deadline(start)
        self.assertEqual(result, msk(2026, 10, 5, 13, 0))
        self.assertEqual(result.utcoffset(), timedelta(hours=3))

    @override_settings(RESPONSE_DEADLINE_WORK_HOURS=3)
    def test_hours_come_from_settings(self):
        self.assertDeadline(msk(2026, 10, 6, 10, 0), msk(2026, 10, 6, 13, 0))

    def test_add_business_hours_spans_long_holiday(self):
        # 1–11 января 2026 нерабочие (каникулы + выходные)
        self.assertEqual(add_business_hours(msk(2026, 1, 1, 12, 0), 4),
                         msk(2026, 1, 12, 14, 0))


@override_settings(PRODUCTION_CALENDAR_URL='https://isdayoff.test/api/getdata?year={year}&pre=1')
class FetchProductionCalendarTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _response(self, text):
        response = mock.Mock(text=text)
        response.raise_for_status.return_value = None
        return response

    def test_published_year_is_used_and_cached(self):
        with mock.patch.object(business_time.requests, 'get', return_value=self._response(CODES_2026)) as get:
            self.assertEqual(business_time.day_kind(date(2026, 3, 9)), business_time.NOT_WORKING)
            self.assertEqual(business_time.day_kind(date(2026, 4, 30)), business_time.SHORTENED)
            self.assertEqual(business_time.day_kind(date(2026, 3, 10)), business_time.WORKING)
        get.assert_called_once()
        self.assertIn('year=2026', get.call_args.args[0])

    def test_unpublished_year_of_zeros_is_rejected(self):
        with mock.patch.object(business_time.requests, 'get', return_value=self._response('0' * 365)):
            self.assertIsNone(business_time._fetch_year(2027))
            # фолбэк: выходные и праздники ТК
            self.assertEqual(business_time.day_kind(date(2027, 1, 4)), business_time.NOT_WORKING)
            self.assertEqual(business_time.day_kind(date(2027, 1, 9)), business_time.NOT_WORKING)
            self.assertEqual(business_time.day_kind(date(2027, 1, 11)), business_time.WORKING)

    def test_malformed_answer_is_rejected(self):
        with mock.patch.object(business_time.requests, 'get', return_value=self._response('error')):
            self.assertIsNone(business_time._fetch_year(2026))

    def test_service_down_falls_back_and_failure_is_cached(self):
        with mock.patch.object(business_time.requests, 'get', side_effect=requests.ConnectionError('down')) as get:
            self.assertEqual(business_time.day_kind(date(2026, 3, 9)), business_time.WORKING)  # перенос не знаем
            self.assertEqual(business_time.day_kind(date(2026, 3, 8)), business_time.NOT_WORKING)
            business_time.day_kind(date(2026, 3, 10))
        get.assert_called_once()

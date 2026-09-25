"""Phase 3 — паттерны, тренд, MA (радар, compare и leaderboard удалены в задаче 1.1)."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from insurance_requests.models import InsuranceRequest

from .models import InsuranceCompany
from .services import analytics_managers


class PatternMetricsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='p', password='x')
        self.now = timezone.now()

    def _mk_request(self, days_ago: int, hour: int | None = None, weekday_offset: int = 0):
        # weekday_offset позволяет сдвинуть на нужный день недели
        r = InsuranceRequest.objects.create(
            client_name='X', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        dt = self.now - timedelta(days=days_ago)
        if hour is not None:
            local = timezone.localtime(dt)
            dt = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        InsuranceRequest.objects.filter(pk=r.pk).update(created_at=dt)
        r.refresh_from_db()
        return r

    def test_cadence_two_requests(self):
        self._mk_request(10)
        self._mk_request(5)
        requests = list(InsuranceRequest.objects.filter(created_by=self.user))
        m = analytics_managers._pattern_metrics_for_user(requests, now=self.now)
        # cadence = 5 дней = 120 ч
        self.assertAlmostEqual(m['cadence_hours'], 120.0, delta=1.0)

    def test_late_and_weekend_pct(self):
        # 4 заявки: 2 поздних (в 22 ч), 2 в обычное
        for hour in (10, 14, 22, 23):
            self._mk_request(0, hour=hour)
        requests = list(InsuranceRequest.objects.filter(created_by=self.user))
        m = analytics_managers._pattern_metrics_for_user(requests, now=self.now)
        # поздних 2 из 4 = 50%
        self.assertAlmostEqual(m['late_pct'], 50.0, delta=0.1)


class BacklogAgeTests(TestCase):
    def test_backlog_buckets(self):
        user = User.objects.create_user(username='b', password='x')
        InsuranceCompany.objects.get_or_create(
            name='Альфа', defaults={'display_name': 'Альфа', 'sort_order': 10})
        now = timezone.now()
        # 3 активные заявки в разном возрасте
        for d in (1, 5, 10):
            r = InsuranceRequest.objects.create(
                client_name=f'A{d}', inn='1234567890',
                insurance_type='КАСКО', created_by=user, status='uploaded',
            )
            InsuranceRequest.objects.filter(pk=r.pk).update(created_at=now - timedelta(days=d))

        filters = analytics_managers.parse_filters({'period': '365'})
        backlog = analytics_managers._backlog_age_buckets(filters, now=now)
        self.assertEqual(backlog['total'], 3)
        # 1 в 0-3, 1 в 4-7, 1 в 8-14
        labels_to_count = {b['label']: b['count'] for b in backlog['buckets']}
        self.assertEqual(labels_to_count['0-3 дн.'], 1)
        self.assertEqual(labels_to_count['4-7 дн.'], 1)
        self.assertEqual(labels_to_count['8-14 дн.'], 1)


class DayHourHeatmapTests(TestCase):
    def test_grid_shape_and_count(self):
        user = User.objects.create_user(username='dh', password='x')
        for _ in range(3):
            InsuranceRequest.objects.create(
                client_name='A', inn='1234567890',
                insurance_type='КАСКО', created_by=user,
            )
        filters = analytics_managers.parse_filters({'period': 'all'})
        dh = analytics_managers._day_hour_heatmap(filters)
        self.assertEqual(len(dh['rows']), 7)
        self.assertEqual(len(dh['rows'][0]['cells']), 24)
        self.assertEqual(dh['total'], 3)


class MovingAverageTests(TestCase):
    def test_moving_average_with_window(self):
        out = analytics_managers._moving_average([1, 2, 3, 4, 5, 6], window=3)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)
        self.assertAlmostEqual(out[5], 5.0)

    def test_moving_average_window_one(self):
        self.assertEqual(analytics_managers._moving_average([1, 2, 3], window=1), [1.0, 2.0, 3.0])


class TeamTrendTests(TestCase):
    def test_trend_returns_week_and_month(self):
        user = User.objects.create_user(username='t', password='x')
        now = timezone.now()
        for d in (3, 4, 10, 12):
            r = InsuranceRequest.objects.create(
                client_name=f'T{d}', inn='1234567890',
                insurance_type='КАСКО', created_by=user,
            )
            InsuranceRequest.objects.filter(pk=r.pk).update(created_at=now - timedelta(days=d))
        filters = analytics_managers.parse_filters({})
        trend = analytics_managers._team_trend(filters)
        self.assertIn('week', trend)
        self.assertIn('month', trend)
        # current week (последние 7 дн.) — 2 заявки (d=3, d=4)
        self.assertEqual(trend['week']['current']['requests'], 2)
        # previous week (дни 7-13) — 2 заявки (d=10, d=12)
        self.assertEqual(trend['week']['previous']['requests'], 2)


class IntegrationOverviewPhase3Tests(TestCase):
    def test_overview_includes_phase3_keys(self):
        user = User.objects.create_user(username='p', password='x')
        InsuranceRequest.objects.create(
            client_name='X', inn='1234567890',
            insurance_type='КАСКО', created_by=user,
        )
        filters = analytics_managers.parse_filters({'period': '365'})
        payload = analytics_managers.build_overview_payload(filters)
        for key in ('backlog', 'day_hour', 'trend'):
            self.assertIn(key, payload, msg=f'Missing key: {key}')
        for key in ('radar', 'team_radar'):
            self.assertNotIn(key, payload, msg=f'Unexpected key: {key}')
        # daily charts получили MA
        self.assertIn('moving_average_28d', payload['charts']['daily'])

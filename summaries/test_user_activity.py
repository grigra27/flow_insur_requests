"""Дневной агрегат активности сотрудников (analytics_redesign_2026_09, задача 4.1)."""
from datetime import datetime, time, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from summaries.models import InsuranceOffer, UserDailyActivity
from summaries.services import user_activity


def _at(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), timezone.get_default_timezone())


class HelpersTests(TestCase):
    def test_section_for_url(self):
        cases = {
            '/requests/upload/': 'upload',
            '/requests/15/': 'requests',
            '/summaries/analytics/insurance-companies/': 'analytics',
            '/summaries/deals/': 'deals',
            '/summaries/12/deal-summary/': 'deals',
            '/summaries/12/': 'summaries',
            '/admin/easyaudit/': 'admin',
            '/': 'home',
            '/login/?next=/': 'home',
            '/landing/': 'other',
        }
        for url, section in cases.items():
            with self.subTest(url=url):
                self.assertEqual(user_activity.section_for_url(url), section)

    def test_sessions_split_on_gap_and_credit_minimum(self):
        day = timezone.localdate()
        stamps = [_at(day, 9, 0), _at(day, 9, 20), _at(day, 9, 45),  # сессия 45 мин
                  _at(day, 14, 0)]                                     # одиночное событие → 5 мин
        self.assertEqual(user_activity.sessions_for(stamps), {'sessions': 2, 'minutes': 50})
        self.assertEqual(user_activity.sessions_for([]), {'sessions': 0, 'minutes': 0})


class AggregateDayTests(TestCase):
    def setUp(self):
        from easyaudit.models import CRUDEvent, LoginEvent, RequestEvent

        self.CRUDEvent, self.LoginEvent, self.RequestEvent = CRUDEvent, LoginEvent, RequestEvent
        for model in (CRUDEvent, LoginEvent, RequestEvent):
            model.objects.all().delete()
        self.user = User.objects.create_user(username='worker', password='p')
        self.day = timezone.localdate() - timedelta(days=1)

    def _event(self, model, moment, **fields):
        event = model.objects.create(**fields)
        model.objects.filter(pk=event.pk).update(datetime=moment)

    def _login(self, moment):
        self._event(self.LoginEvent, moment, login_type=0, username=self.user.username, user=self.user)

    def _request(self, moment, url, method='GET', user='default'):
        self._event(self.RequestEvent, moment, url=url, method=method, remote_ip='127.0.0.1',
                    user=self.user if user == 'default' else user)

    def _crud(self, moment, model, event_type):
        self._event(self.CRUDEvent, moment, event_type=event_type, object_id='1',
                    content_type=ContentType.objects.get_for_model(model), object_repr='x', user=self.user)

    def test_full_day_with_request_data(self):
        # Журнал просмотров начинается раньше дня → день собран полностью.
        self._request(_at(self.day, 0, 0) - timedelta(hours=2), '/', user=None)
        self._login(_at(self.day, 9, 0))
        self._request(_at(self.day, 9, 1), '/summaries/12/')
        self._request(_at(self.day, 9, 10), '/summaries/12/offer/add/', method='POST')
        self._request(_at(self.day, 9, 30), '/summaries/analytics/')
        self._crud(_at(self.day, 9, 10), InsuranceOffer, 1)
        self._crud(_at(self.day, 9, 11), InsuranceOffer, 2)
        self._crud(_at(self.day, 9, 0), User, 2)  # last_login — не работа
        self._request(_at(self.day, 16, 0), '/requests/')

        report = user_activity.aggregate_day(self.day)

        self.assertEqual(report['users'], 1)
        row = UserDailyActivity.objects.get(user=self.user, date=self.day)
        self.assertTrue(row.has_request_data)
        self.assertEqual(row.logins_count, 1)
        self.assertEqual((row.page_views, row.form_actions), (3, 1))
        self.assertEqual(row.crud_actions, 2)
        self.assertEqual(row.crud_by_model, {'insuranceoffer': {'create': 1, 'update': 1, 'delete': 0}})
        self.assertEqual(row.sections, {'summaries': 2, 'analytics': 1, 'requests': 1})
        self.assertEqual(timezone.localtime(row.first_seen_at).time(), time(9, 0))
        self.assertEqual(timezone.localtime(row.last_seen_at).time(), time(16, 0))
        # 9:00–9:30 = 30 мин + одиночное событие в 16:00 = 5 мин.
        self.assertEqual((row.sessions_count, row.active_minutes), (2, 35))

    def test_day_without_request_data_uses_logins_and_changes(self):
        self._login(_at(self.day, 10, 0))
        self._crud(_at(self.day, 10, 25), InsuranceOffer, 1)

        user_activity.aggregate_day(self.day)

        row = UserDailyActivity.objects.get(user=self.user, date=self.day)
        self.assertFalse(row.has_request_data)
        self.assertEqual((row.page_views, row.logins_count, row.crud_actions), (0, 1, 1))
        self.assertEqual((row.sessions_count, row.active_minutes), (1, 25))

    def test_recompute_without_request_data_keeps_collected_views(self):
        UserDailyActivity.objects.create(
            user=self.user, date=self.day, page_views=50, form_actions=5, sections={'summaries': 55},
            active_minutes=240, sessions_count=3, has_request_data=True,
        )
        self._login(_at(self.day, 10, 0))
        self._crud(_at(self.day, 11, 0), InsuranceOffer, 1)

        report = user_activity.aggregate_day(self.day)

        row = UserDailyActivity.objects.get(user=self.user, date=self.day)
        self.assertEqual(report['kept_request_fields'], 1)
        self.assertTrue(row.has_request_data)
        self.assertEqual((row.page_views, row.active_minutes), (50, 240))
        self.assertEqual((row.logins_count, row.crud_actions), (1, 1))

    def test_aggregation_is_idempotent_and_not_audited(self):
        self._request(_at(self.day, 0, 0) - timedelta(hours=1), '/', user=None)
        self._request(_at(self.day, 12, 0), '/requests/')
        crud_before = self.CRUDEvent.objects.count()

        user_activity.aggregate_day(self.day)
        user_activity.aggregate_day(self.day)

        self.assertEqual(UserDailyActivity.objects.filter(user=self.user, date=self.day).count(), 1)
        # Агрегат не должен сам попадать в журнал изменений easy-audit.
        self.assertEqual(self.CRUDEvent.objects.count(), crud_before)

    def test_command_backfill_and_range(self):
        self._login(_at(self.day - timedelta(days=2), 10, 0))
        self._login(_at(self.day, 10, 0))

        out = StringIO()
        call_command('aggregate_user_activity', '--backfill', stdout=out)

        self.assertEqual(UserDailyActivity.objects.filter(user=self.user).count(), 2)
        self.assertIn('Готово: дней 3.', out.getvalue())


class PurgeAggregatesFirstTests(TestCase):
    def setUp(self):
        from easyaudit.models import RequestEvent

        self.RequestEvent = RequestEvent
        RequestEvent.objects.all().delete()
        self.user = User.objects.create_user(username='night', password='p')
        old = self.RequestEvent.objects.create(url='/requests/', method='GET', remote_ip='127.0.0.1', user=self.user)
        self.RequestEvent.objects.filter(pk=old.pk).update(datetime=timezone.now() - timedelta(days=2))

    def test_purge_aggregates_yesterday_before_deleting(self):
        with mock.patch('summaries.services.user_activity.aggregate_day', return_value={'users': 1}) as aggregate:
            call_command('purge_audit_log', stdout=StringIO())

        aggregate.assert_called_once_with(user_activity.yesterday())
        self.assertEqual(self.RequestEvent.objects.count(), 0)

    def test_purge_keeps_request_events_when_aggregation_fails(self):
        with mock.patch('summaries.services.user_activity.aggregate_day', side_effect=RuntimeError('boom')):
            call_command('purge_audit_log', stdout=StringIO())

        self.assertEqual(self.RequestEvent.objects.count(), 1)

    def test_dry_run_does_not_aggregate(self):
        with mock.patch('summaries.services.user_activity.aggregate_day') as aggregate:
            call_command('purge_audit_log', '--dry-run', stdout=StringIO())

        aggregate.assert_not_called()

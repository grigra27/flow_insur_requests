"""Тесты Phase 1 для аналитики по сотрудникам.

Сетап: 3 пользователя (3 реальных менеджера + 1 «Без автора»),
разные комбинации заявок/сводов/предложений с известными датами и статусами,
чтобы проверить counts, win-rate, premium и time-to-*.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from insurance_requests.models import InsuranceRequest

from .models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from .services import analytics_managers


def _make_aware(year, month, day, hour=12, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute))


class ManagerAnalyticsOverviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username='alice', password='p', first_name='Алиса')
        cls.bob = User.objects.create_user(username='bob', password='p', first_name='Боб')
        cls.carol = User.objects.create_user(username='carol', password='p', first_name='Кэрол')

        # Регистрируем СК, чтобы InsuranceOffer.full_clean() не падал.
        InsuranceCompany.objects.get_or_create(
            name='Альфа',
            defaults={'display_name': 'Альфа', 'is_active': True, 'sort_order': 10},
        )

        now = timezone.now()

        # --- Alice: 3 заявки, 2 свода, 1 accepted с премией ---
        alice_req1 = InsuranceRequest.objects.create(
            client_name='Клиент А1', inn='1234567890',
            insurance_type='КАСКО', branch='Москва',
            created_by=cls.alice, status='emails_sent',
        )
        # Подменяем created_at — auto_now_add не даст в .create(), нужно update.
        InsuranceRequest.objects.filter(pk=alice_req1.pk).update(
            created_at=now - timedelta(days=10)
        )
        alice_req1.refresh_from_db()

        alice_summary1 = InsuranceSummary.objects.create(
            request=alice_req1, status='completed_accepted',
            selected_company='Альфа', selected_franchise_variant=1,
        )
        InsuranceSummary.objects.filter(pk=alice_summary1.pk).update(
            created_at=now - timedelta(days=9),
            sent_to_client_at=now - timedelta(days=8),
            completed_at=now - timedelta(days=5),
        )
        alice_summary1.refresh_from_db()

        InsuranceOffer.objects.create(
            summary=alice_summary1, company_name='Альфа',
            insurance_sum=Decimal('1000000'), insurance_year=1,
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000'),
        )

        # Alice заявка #2 — активная, на стадии email_generated (нет свода)
        alice_req2 = InsuranceRequest.objects.create(
            client_name='Клиент А2', inn='1234567890',
            insurance_type='КАСКО', branch='Москва',
            created_by=cls.alice, status='email_generated',
        )
        InsuranceRequest.objects.filter(pk=alice_req2.pk).update(
            created_at=now - timedelta(days=2)
        )

        # Alice заявка #3 — отказ
        alice_req3 = InsuranceRequest.objects.create(
            client_name='Клиент А3', inn='1234567890',
            insurance_type='КАСКО', branch='Москва',
            created_by=cls.alice, status='emails_sent',
        )
        InsuranceRequest.objects.filter(pk=alice_req3.pk).update(
            created_at=now - timedelta(days=20)
        )
        alice_summary3 = InsuranceSummary.objects.create(
            request=alice_req3, status='completed_rejected',
        )
        InsuranceSummary.objects.filter(pk=alice_summary3.pk).update(
            created_at=now - timedelta(days=18),
        )

        # --- Bob: 1 заявка, активный свод (collecting) ---
        bob_req1 = InsuranceRequest.objects.create(
            client_name='Клиент Б1', inn='1234567890',
            insurance_type='страхование имущества', branch='Казань',
            created_by=cls.bob, status='emails_sent',
        )
        InsuranceRequest.objects.filter(pk=bob_req1.pk).update(
            created_at=now - timedelta(days=3)
        )
        InsuranceSummary.objects.create(request=bob_req1, status='collecting')

        # --- Carol: 1 заявка, просроченный response_deadline ---
        carol_req1 = InsuranceRequest.objects.create(
            client_name='Клиент К1', inn='1234567890',
            insurance_type='КАСКО', branch='Краснодар',
            created_by=cls.carol, status='uploaded',
        )
        InsuranceRequest.objects.filter(pk=carol_req1.pk).update(
            created_at=now - timedelta(days=1),
            response_deadline=now - timedelta(hours=4),
        )
        cls.now = now

    def _filters(self, **overrides):
        f = analytics_managers.parse_filters({})
        f.update(overrides)
        return f

    def test_overview_counts_per_manager(self):
        payload = analytics_managers.build_overview_payload(self._filters())
        rows = {row['display']: row for row in payload['rows']}

        self.assertIn('Алиса', rows)
        self.assertIn('Боб', rows)
        self.assertIn('Кэрол', rows)
        self.assertEqual(rows['Алиса']['requests_total'], 3)
        self.assertEqual(rows['Алиса']['summaries_total'], 2)
        self.assertEqual(rows['Алиса']['accepted'], 1)
        self.assertEqual(rows['Алиса']['rejected'], 1)
        # win-rate = 1/(1+1) = 50%
        self.assertAlmostEqual(rows['Алиса']['win_rate'], 50.0)

        self.assertEqual(rows['Боб']['requests_total'], 1)
        self.assertEqual(rows['Боб']['summaries_total'], 1)
        self.assertEqual(rows['Боб']['accepted'], 0)

        self.assertEqual(rows['Кэрол']['requests_total'], 1)
        self.assertEqual(rows['Кэрол']['overdue_count'], 1)

    def test_team_aggregate(self):
        payload = analytics_managers.build_overview_payload(self._filters())
        team = payload['team']
        self.assertEqual(team['requests_total'], 5)
        self.assertEqual(team['summaries_total'], 3)
        self.assertEqual(team['accepted'], 1)
        self.assertEqual(team['rejected'], 1)
        self.assertEqual(team['premium_total'], Decimal('50000'))
        # 1 accepted + 1 rejected → win-rate 50%
        self.assertAlmostEqual(team['win_rate'], 50.0)

    def test_funnel_counts(self):
        payload = analytics_managers.build_overview_payload(self._filters())
        stages = {s['key']: s['count'] for s in payload['funnel']['stages']}
        # 5 заявок, 3 свода (для всех со status=emails_sent), 0 ready, 0 sent_to_client (sent),
        # 2 завершено (accepted+rejected), 1 accepted
        self.assertEqual(stages['uploaded'], 5)
        self.assertEqual(stages['sent_emails'], 3)
        self.assertEqual(stages['completed'], 2)
        self.assertEqual(stages['accepted'], 1)

    def test_alerts_overdue_and_active(self):
        alerts = analytics_managers.build_alerts(self._filters())
        # У Кэрол просроченный deadline
        self.assertGreaterEqual(alerts['overdue_total'], 1)
        managers = {a['manager'] for a in alerts['overdue']}
        self.assertIn('Кэрол', managers)

    def test_filter_by_branch_narrows_results(self):
        payload = analytics_managers.build_overview_payload(self._filters(branch='Москва'))
        rows = {r['display']: r for r in payload['rows']}
        self.assertIn('Алиса', rows)
        self.assertNotIn('Боб', rows)
        self.assertNotIn('Кэрол', rows)

    def test_filter_by_user_ids(self):
        payload = analytics_managers.build_overview_payload(
            self._filters(user_ids=[self.bob.pk], include_unassigned=False)
        )
        rows = {r['display']: r for r in payload['rows']}
        self.assertEqual(list(rows.keys()), ['Боб'])

    def test_premium_uses_selected_variant(self):
        # Создаём accepted-сделку с вариантом 2
        req = InsuranceRequest.objects.create(
            client_name='V2', inn='1234567890', insurance_type='КАСКО',
            created_by=self.bob, status='emails_sent',
        )
        summary = InsuranceSummary.objects.create(
            request=req, status='completed_accepted',
            selected_company='Альфа', selected_franchise_variant=2,
        )
        InsuranceOffer.objects.create(
            summary=summary, company_name='Альфа',
            insurance_sum=Decimal('500000'), insurance_year=1,
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('30000'),
            franchise_2=Decimal('20000'),
            premium_with_franchise_2=Decimal('22000'),
        )
        payload = analytics_managers.build_overview_payload(
            self._filters(user_ids=[self.bob.pk], include_unassigned=False)
        )
        bob = payload['rows'][0]
        # Боб теперь должен иметь премию = 22000 (вариант 2), не 30000.
        self.assertEqual(bob['premium_total'], Decimal('22000'))


class ManagerAnalyticsParseFiltersTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_default_period_is_365(self):
        req = self.factory.get('/x/')
        filters = analytics_managers.parse_filters(req.GET)
        self.assertEqual(filters['period'], '365')
        self.assertIsNotNone(filters['start_date'])
        self.assertIsNotNone(filters['end_date'])

    def test_explicit_period_30(self):
        req = self.factory.get('/x/?period=30')
        filters = analytics_managers.parse_filters(req.GET)
        self.assertEqual(filters['period'], '30')
        delta = (filters['end_date'] - filters['start_date']).days
        self.assertEqual(delta, 29)

    def test_invalid_date_records_error(self):
        req = self.factory.get('/x/?start_date=2020-13-40')
        filters = analytics_managers.parse_filters(req.GET)
        self.assertTrue(filters['errors'])

    def test_user_ids_parsing(self):
        req = self.factory.get('/x/?user_ids=1&user_ids=5,7')
        filters = analytics_managers.parse_filters(req.GET)
        self.assertEqual(sorted(filters['user_ids']), [1, 5, 7])

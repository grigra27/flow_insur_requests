"""Phase 2 — тесты качества данных, портфеля, heatmap’ов и новых алертов."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from insurance_requests.models import InsuranceRequest

from .models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from .services import analytics_managers


class CompletenessAndPortfolioTests(TestCase):
    def test_inn_validation_rules(self):
        self.assertTrue(analytics_managers._is_inn_valid('1234567890'))
        self.assertTrue(analytics_managers._is_inn_valid('123456789012'))
        self.assertFalse(analytics_managers._is_inn_valid('123'))
        self.assertFalse(analytics_managers._is_inn_valid(''))
        self.assertFalse(analytics_managers._is_inn_valid('12345abcd0'))

    def test_completeness_for_request_base_only(self):
        user = User.objects.create_user(username='c', password='p')
        req = InsuranceRequest.objects.create(
            client_name='X', inn='1234567890',
            insurance_type='другое',
            created_by=user, status='uploaded',
            dfa_number='DFA1', branch='Москва',
            manager_name='Иванов', vehicle_info='описание',
            notes='заметки', insurance_period='1 год',
        )
        c = analytics_managers._completeness_for_request(req)
        # 7 базовых полей: response_deadline ставится auto в save() → все заполнены
        self.assertEqual(c['base_filled'], 7)
        self.assertEqual(c['base_total'], 7)
        self.assertIsNone(c['casco_total'])
        self.assertIsNone(c['property_total'])
        self.assertTrue(c['inn_valid'])
        self.assertTrue(c['is_other_type'])

    def test_completeness_casco_partial(self):
        user = User.objects.create_user(username='cc', password='p')
        req = InsuranceRequest.objects.create(
            client_name='X', inn='1234567890',
            insurance_type='КАСКО', created_by=user,
            key_completeness='2 ключа', pts_psm='ПТС',
            # creditor_bank, usage_purposes, telematics_complex, manufacturing_year, asset_status — пусто
        )
        c = analytics_managers._completeness_for_request(req)
        self.assertEqual(c['casco_total'], 7)
        self.assertEqual(c['casco_filled'], 2)

    def test_aggregate_completeness_pct(self):
        user = User.objects.create_user(username='ag', password='p')
        # 1 заявка КАСКО, 1 имущественная
        InsuranceRequest.objects.create(
            client_name='A', inn='1234567890',
            insurance_type='КАСКО', created_by=user,
            dfa_number='D1', branch='B', manager_name='M', vehicle_info='V',
            notes='N', insurance_period='1 год',
        )
        InsuranceRequest.objects.create(
            client_name='B', inn='12',  # битый
            insurance_type='страхование имущества', created_by=user,
            insurance_territory='Россия',
        )
        agg = analytics_managers._aggregate_completeness(list(InsuranceRequest.objects.all()))
        self.assertEqual(agg['inn_invalid_count'], 1)
        self.assertAlmostEqual(agg['inn_invalid_pct'], 50.0)
        self.assertIsNotNone(agg['casco_pct'])
        self.assertIsNotNone(agg['property_pct'])
        self.assertEqual(agg['property_pct'], 100.0)


class QualityScoreTests(TestCase):
    def test_quality_score_components(self):
        row = {
            'completeness': {'overall_pct': 100.0},
            'win_rate': 100.0,
            'time_to': {'avg_cycle_h': 10.0},
            'requests_total': 5,
        }
        # max_volume = 5, best_cycle = 10 → speed=100, volume=100
        score = analytics_managers._compute_quality_score(row, 5, 10.0)
        self.assertAlmostEqual(score, 100.0)

    def test_quality_score_partial(self):
        row = {
            'completeness': {'overall_pct': 50.0},
            'win_rate': 60.0,
            'time_to': {'avg_cycle_h': 20.0},
            'requests_total': 2,
        }
        # max_volume=4, best=10 → speed=50 (10/20*100), volume=50 (2/4*100)
        # 0.4*50 + 0.3*60 + 0.2*50 + 0.1*50 = 20 + 18 + 10 + 5 = 53
        score = analytics_managers._compute_quality_score(row, 4, 10.0)
        self.assertAlmostEqual(score, 53.0, places=1)

    def test_quality_score_no_data(self):
        row = {
            'completeness': {'overall_pct': None},
            'win_rate': None,
            'time_to': {'avg_cycle_h': None},
            'requests_total': 0,
        }
        score = analytics_managers._compute_quality_score(row, 0, None)
        self.assertEqual(score, 0.0)


class HeatmapTests(TestCase):
    def test_heatmap_basic(self):
        pairs = [
            ('Алиса', 'Москва'), ('Алиса', 'Москва'),
            ('Алиса', 'Казань'), ('Боб', 'Москва'),
        ]
        hm = analytics_managers._build_heatmap(pairs)
        self.assertEqual(set(hm['columns']), {'Москва', 'Казань'})
        self.assertEqual(hm['max_value'], 2)
        labels = [r['label'] for r in hm['rows']]
        self.assertEqual(set(labels), {'Алиса', 'Боб'})

    def test_heatmap_top_limit_collapses_tail(self):
        pairs = [(f'M{i % 2}', f'C{i}') for i in range(20)]
        hm = analytics_managers._build_heatmap(pairs, top_limit=3)
        # 3 топ-колонки + «Прочее»
        self.assertIn('Прочее', hm['columns'])
        self.assertEqual(len(hm['columns']), 4)


class Phase2OverviewIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username='alice', password='p', first_name='Алиса')
        cls.bob = User.objects.create_user(username='bob', password='p', first_name='Боб')
        InsuranceCompany.objects.get_or_create(
            name='Альфа',
            defaults={'display_name': 'Альфа', 'is_active': True, 'sort_order': 10},
        )
        now = timezone.now()
        cls.now = now

        # Alice: 2 КАСКО, 1 имущество
        for i, branch in enumerate(['Москва', 'Москва', 'Казань']):
            r = InsuranceRequest.objects.create(
                client_name=f'A{i}', inn='1234567890',
                insurance_type='КАСКО' if i < 2 else 'страхование имущества',
                created_by=cls.alice, branch=branch,
                manager_name='Иванов А.А.',
                status='emails_sent',
            )
            InsuranceRequest.objects.filter(pk=r.pk).update(created_at=now - timedelta(days=10 + i))

        # Bob: 1 КАСКО, 1 «другое»
        for i, t in enumerate(['КАСКО', 'другое']):
            r = InsuranceRequest.objects.create(
                client_name=f'B{i}', inn='12' if i == 1 else '1234567890',  # битый ИНН у второго
                insurance_type=t, created_by=cls.bob,
                branch='Москва', status='emails_sent',
            )
            InsuranceRequest.objects.filter(pk=r.pk).update(created_at=now - timedelta(days=2 + i))

    def _filters(self, **overrides):
        f = analytics_managers.parse_filters({})
        f.update(overrides)
        return f

    def test_overview_includes_completeness(self):
        payload = analytics_managers.build_overview_payload(self._filters())
        rows = {r['display']: r for r in payload['rows']}
        self.assertIn('Алиса', rows)
        # Боб имеет 1 битый ИНН и 1 «другое»
        self.assertEqual(rows['Боб']['completeness']['inn_invalid_count'], 1)
        self.assertEqual(rows['Боб']['completeness']['other_type_count'], 1)

    def test_overview_has_heatmaps(self):
        payload = analytics_managers.build_overview_payload(self._filters())
        self.assertIn('heatmaps', payload)
        self.assertIn('branch', payload['heatmaps'])
        # У Алисы 2 заявки в Москве, 1 в Казани
        branch_hm = payload['heatmaps']['branch']
        alice_row = next(r for r in branch_hm['rows'] if r['label'] == 'Алиса')
        moscow_idx = branch_hm['columns'].index('Москва')
        self.assertEqual(alice_row['cells'][moscow_idx], 2)

    def test_quality_score_on_rows(self):
        payload = analytics_managers.build_overview_payload(self._filters())
        for row in payload['rows']:
            self.assertIn('quality_score', row)
            if row['quality_score'] is not None:
                self.assertGreaterEqual(row['quality_score'], 0.0)
                self.assertLessEqual(row['quality_score'], 100.0)


class VolumeDropAlertTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vd', password='p')
        InsuranceCompany.objects.get_or_create(
            name='Альфа', defaults={'display_name': 'Альфа', 'sort_order': 10})
        now = timezone.now()
        # Прошлое окно: 5 заявок
        for i in range(5):
            r = InsuranceRequest.objects.create(
                client_name=f'P{i}', inn='1234567890',
                insurance_type='КАСКО', created_by=self.user,
            )
            InsuranceRequest.objects.filter(pk=r.pk).update(
                created_at=now - timedelta(days=40 + i),
            )
        # Текущее окно: 1 заявка → -80%
        r = InsuranceRequest.objects.create(
            client_name='C', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        InsuranceRequest.objects.filter(pk=r.pk).update(created_at=now - timedelta(days=5))
        self.now = now

    def test_drop_detected(self):
        # 30-дневное окно: текущее → 1 заявка, предыдущее (дни 31-60) → 5 заявок
        filters = analytics_managers.parse_filters({'period': '30'})
        alerts = analytics_managers.build_alerts(filters)
        flagged_ids = [f['user_id'] for f in alerts['volume_drop']['flagged']]
        self.assertIn(self.user.pk, flagged_ids)

    def test_disabled_for_all_period(self):
        filters = analytics_managers.parse_filters({'period': 'all'})
        alerts = analytics_managers.build_alerts(filters)
        self.assertFalse(alerts['volume_drop']['enabled'])


class CycleOutlierAlertTests(TestCase):
    def test_outliers_flagged(self):
        user = User.objects.create_user(username='co', password='p')
        InsuranceCompany.objects.get_or_create(
            name='Альфа', defaults={'display_name': 'Альфа', 'sort_order': 10})
        now = timezone.now()

        # 3 нормальные accepted-сделки (cycle ~= 24h)
        for i in range(3):
            req = InsuranceRequest.objects.create(
                client_name=f'N{i}', inn='1234567890',
                insurance_type='КАСКО', created_by=user, status='emails_sent',
            )
            InsuranceRequest.objects.filter(pk=req.pk).update(
                created_at=now - timedelta(days=10 + i, hours=24),
            )
            s = InsuranceSummary.objects.create(
                request=req, status='completed_accepted',
                selected_company='Альфа', selected_franchise_variant=1,
            )
            InsuranceSummary.objects.filter(pk=s.pk).update(
                created_at=now - timedelta(days=10 + i, hours=12),
                completed_at=now - timedelta(days=9 + i, hours=12),
            )

        # 1 аномалия — цикл 30 дней
        outlier_req = InsuranceRequest.objects.create(
            client_name='OUT', inn='1234567890',
            insurance_type='КАСКО', created_by=user, status='emails_sent',
        )
        InsuranceRequest.objects.filter(pk=outlier_req.pk).update(
            created_at=now - timedelta(days=40),
        )
        os_summary = InsuranceSummary.objects.create(
            request=outlier_req, status='completed_accepted',
            selected_company='Альфа', selected_franchise_variant=1,
        )
        InsuranceSummary.objects.filter(pk=os_summary.pk).update(
            created_at=now - timedelta(days=39),
            completed_at=now - timedelta(days=10),
        )

        filters = analytics_managers.parse_filters({'period': '365'})
        alerts = analytics_managers.build_alerts(filters)
        outlier_ids = [o['summary_id'] for o in alerts['cycle_outliers']['outliers']]
        self.assertIn(os_summary.pk, outlier_ids)

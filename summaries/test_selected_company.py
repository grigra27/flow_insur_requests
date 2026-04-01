"""
Тесты выбора страховой компании и варианта франшизы при завершении свода
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class SelectedCompanyAndVariantTestCase(TestCase):
    """Тесты для selected_company и selected_franchise_variant"""

    def setUp(self):
        """Подготовка тестовых данных"""
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')

        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.users_group)

        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

        self.request = InsuranceRequest.objects.create(
            dfa_number='TEST-001',
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            branch='msk',
            status='uploaded',
            created_by=self.user,
        )

        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='collecting'
        )

        # Компания с двумя вариантами франшизы
        self.offer_with_two_variants = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000.00'),
            franchise_2=Decimal('30000.00'),
            premium_with_franchise_2=Decimal('45000.00'),
        )

        # Компания только с первым вариантом
        self.offer_with_single_variant = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Альфа',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('47000.00'),
        )

    def test_get_companies_choices(self):
        """Проверка списка компаний для выбора"""
        choices = self.summary.get_companies_choices()

        self.assertEqual(choices[0], ('', 'Выберите страховую компанию'))
        company_names = [choice[0] for choice in choices[1:]]
        self.assertIn('Абсолют', company_names)
        self.assertIn('Альфа', company_names)

    def test_multiyear_company_appears_once(self):
        """Многолетнее предложение от одной СК отображается один раз"""
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=2,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('51000.00'),
            franchise_2=Decimal('30000.00'),
            premium_with_franchise_2=Decimal('46000.00'),
        )

        companies = self.summary.get_unique_companies_list()
        self.assertEqual(companies.count('Абсолют'), 1)
        self.assertEqual(len(companies), 2)

    def test_company_variants_helpers(self):
        """Проверка helper-методов доступности вариантов"""
        self.assertEqual(self.summary.get_company_available_variants('Абсолют'), [1, 2])
        self.assertTrue(self.summary.requires_variant_choice('Абсолют'))
        self.assertIsNone(self.summary.get_default_variant('Абсолют'))

        self.assertEqual(self.summary.get_company_available_variants('Альфа'), [1])
        self.assertFalse(self.summary.requires_variant_choice('Альфа'))
        self.assertEqual(self.summary.get_default_variant('Альфа'), 1)

    def test_change_status_requires_variant_when_two_variants_available(self):
        """Если у СК два варианта, выбор варианта обязателен"""
        response = self.client.post(
            reverse('summaries:change_summary_status', args=[self.summary.pk]),
            {
                'status': 'completed_accepted',
                'selected_company': 'Абсолют',
            }
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('вариант франшизы', payload['error'])

    def test_change_status_saves_explicit_variant_when_two_variants_available(self):
        """При двух вариантах сохраняется явно выбранный вариант"""
        response = self.client.post(
            reverse('summaries:change_summary_status', args=[self.summary.pk]),
            {
                'status': 'completed_accepted',
                'selected_company': 'Абсолют',
                'selected_franchise_variant': '2',
            }
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'completed_accepted')
        self.assertEqual(self.summary.selected_company, 'Абсолют')
        self.assertEqual(self.summary.selected_franchise_variant, 2)

    def test_change_status_autoselects_single_available_variant(self):
        """Если доступен только один вариант, он выбирается автоматически"""
        response = self.client.post(
            reverse('summaries:change_summary_status', args=[self.summary.pk]),
            {
                'status': 'completed_accepted',
                'selected_company': 'Альфа',
            }
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'completed_accepted')
        self.assertEqual(self.summary.selected_company, 'Альфа')
        self.assertEqual(self.summary.selected_franchise_variant, 1)

    def test_change_status_rejects_invalid_variant(self):
        """Нельзя сохранить недоступный для СК вариант"""
        response = self.client.post(
            reverse('summaries:change_summary_status', args=[self.summary.pk]),
            {
                'status': 'completed_accepted',
                'selected_company': 'Альфа',
                'selected_franchise_variant': '2',
            }
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('недоступен', payload['error'])

    def test_change_status_to_other_status_clears_selected_fields(self):
        """При выходе из completed_accepted выбранные СК/вариант очищаются"""
        self.summary.status = 'completed_accepted'
        self.summary.selected_company = 'Абсолют'
        self.summary.selected_franchise_variant = 1
        self.summary.save()

        response = self.client.post(
            reverse('summaries:change_summary_status', args=[self.summary.pk]),
            {'status': 'ready'}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'ready')
        self.assertIsNone(self.summary.selected_company)
        self.assertIsNone(self.summary.selected_franchise_variant)

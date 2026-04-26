"""
Базовые интеграционные тесты для проверки компонентов
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class BasicIntegrationTest(TestCase):
    """Базовые интеграционные тесты"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        # Создаем группы пользователей
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')
        
        # Создаем пользователя
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.users_group)
        
        # Создаем клиент для тестирования
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        
        # Создаем тестовую заявку
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='ООО "Тест"',
            inn='1234567890',
            insurance_type='КАСКО',
            vehicle_info='Тестовый автомобиль',
            branch='Москва',
            dfa_number='DFA-2025-001',
            status='uploaded',
            created_by=self.user
        )
        
        # Создаем свод
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
        
        # Создаем тестовое предложение
        self.offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('45000.00'),
            notes='Тестовое примечание'
        )

    def test_summary_detail_page_loads(self):
        """Тест загрузки страницы детального свода"""
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Свод к')

    def test_copy_offer_page_loads(self):
        """Тест загрузки страницы копирования предложения"""
        response = self.client.get(reverse('summaries:copy_offer', args=[self.offer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Копировать предложение')

    def test_copy_offer_functionality(self):
        """Тест функциональности копирования предложения"""
        copy_url = reverse('summaries:copy_offer', args=[self.offer.pk])
        
        copy_data = {
            'company_name': 'ВСК',
            'insurance_year': 2,
            'insurance_sum': '1500000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '55000.00',
            'franchise_2': '30000.00',
            'premium_with_franchise_2': '50000.00',
            'installment_variant_1': False,
            'payments_per_year_variant_1': 1,
            'installment_variant_2': False,
            'payments_per_year_variant_2': 1,
            'notes': 'Скопированное предложение'
        }
        
        initial_count = InsuranceOffer.objects.count()
        response = self.client.post(copy_url, copy_data)
        
        # Проверяем редирект
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что новое предложение создано
        self.assertEqual(InsuranceOffer.objects.count(), initial_count + 1)
        
        # Проверяем данные нового предложения
        new_offer = InsuranceOffer.objects.get(company_name='ВСК')
        self.assertEqual(new_offer.insurance_year, 2)
        self.assertEqual(new_offer.insurance_sum, Decimal('1500000.00'))

    def test_color_coding_css_present(self):
        """Тест наличия CSS для цветового кодирования"""
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем наличие CSS классов
        self.assertContains(response, 'franchise-variant-1')
        self.assertContains(response, 'franchise-variant-2')
        self.assertContains(response, 'company-total-row')

    def test_company_notes_display(self):
        """Тест отображения примечаний компании"""
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем отображение примечаний
        self.assertContains(response, 'company-notes')
        self.assertContains(response, 'Тестовое примечание')

    def test_summary_detail_displays_compact_analytics(self):
        """Тест компактной аналитики в блоке сводной информации"""
        self.insurance_request.franchise_type = 'both_variants'
        self.insurance_request.has_installment = True
        self.insurance_request.save(update_fields=['franchise_type', 'has_installment'])

        self.summary.status = 'completed_accepted'
        self.summary.selected_company = 'ВСК'
        self.summary.selected_franchise_variant = 1
        self.summary.save(update_fields=['status', 'selected_company', 'selected_franchise_variant'])

        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=2,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('48000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('43000.00'),
        )
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='ВСК',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('60000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('54000.00'),
            installment_variant_1=True,
            payments_per_year_variant_1=4,
        )
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='ВСК',
            insurance_year=2,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('62000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('55000.00'),
            installment_variant_1=True,
            payments_per_year_variant_1=4,
        )
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Согаз',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('70000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('63000.00'),
        )

        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'summary-mini-kpis')
        self.assertContains(response, 'js-summary-analytics-faq')
        self.assertContains(response, 'Как собирается сводная информация')
        self.assertContains(response, '2/3')
        self.assertContains(response, 'оба варианта')
        self.assertContains(response, '98 000 ₽ - 122 000 ₽')
        self.assertContains(response, '88 000 ₽ - 109 000 ₽')
        self.assertContains(response, '1/3 СК')
        self.assertContains(response, 'до 4 пл./год')
        self.assertContains(response, 'Разброс')
        self.assertContains(response, 'есть дешевле')
        self.assertContains(response, '+24 000 ₽')

    def test_summary_compact_analytics_uses_first_variant_for_single_franchise_request(self):
        """Тест трактовки одиночного запроса с франшизой как первого варианта"""
        self.insurance_request.franchise_type = 'with_franchise'
        self.insurance_request.save(update_fields=['franchise_type'])

        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)

        analytics = response.context['summary_analytics']
        self.assertEqual(analytics['required_variants'], [1])
        self.assertEqual(analytics['required_variants_label'], 'с франшизой')

    def test_model_methods_integration(self):
        """Тест интеграции методов модели"""
        # Тестируем get_company_notes
        company_notes = self.summary.get_company_notes()
        self.assertIn('Абсолют', company_notes)
        
        # Тестируем get_offers_grouped_by_company
        grouped_offers = self.summary.get_offers_grouped_by_company()
        self.assertIn('Абсолют', grouped_offers)
        
        # Тестируем get_unique_companies_count
        companies_count = self.summary.get_unique_companies_count()
        self.assertEqual(companies_count, 1)

    def tearDown(self):
        """Очистка после тестов"""
        InsuranceOffer.objects.all().delete()
        InsuranceSummary.objects.all().delete()
        InsuranceRequest.objects.all().delete()
        User.objects.all().delete()
        Group.objects.all().delete()

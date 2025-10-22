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
            company_name='Тестовая Страховая',
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
        self.assertContains(response, self.summary.request.client_name)

    def test_copy_offer_page_loads(self):
        """Тест загрузки страницы копирования предложения"""
        response = self.client.get(reverse('summaries:copy_offer', args=[self.offer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Копировать предложение')

    def test_copy_offer_functionality(self):
        """Тест функциональности копирования предложения"""
        copy_url = reverse('summaries:copy_offer', args=[self.offer.pk])
        
        copy_data = {
            'company_name': 'Новая Страховая',
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
        new_offer = InsuranceOffer.objects.get(company_name='Новая Страховая')
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

    def test_model_methods_integration(self):
        """Тест интеграции методов модели"""
        # Тестируем get_company_notes
        company_notes = self.summary.get_company_notes()
        self.assertIn('Тестовая Страховая', company_notes)
        
        # Тестируем get_offers_grouped_by_company
        grouped_offers = self.summary.get_offers_grouped_by_company()
        self.assertIn('Тестовая Страховая', grouped_offers)
        
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
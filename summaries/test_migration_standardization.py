"""
Тесты для миграции стандартизации названий страховых компаний
"""

from django.test import TestCase
from django.db import connection
from django.core.management import call_command
from django.test.utils import override_settings
from summaries.models import InsuranceOffer, InsuranceSummary
from insurance_requests.models import InsuranceRequest
from django.contrib.auth.models import User
from summaries.constants import get_company_names, is_valid_company_name


class CompanyNameStandardizationMigrationTest(TestCase):
    """Тесты для миграции стандартизации названий компаний"""
    
    def setUp(self):
        """Подготовка тестовых данных"""
        # Создаем пользователя
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Создаем заявку
        self.request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            created_by=self.user,
            branch='ТС',
            dfa_number='12345'
        )
        
        # Создаем свод
        self.summary = InsuranceSummary.objects.create(
            request=self.request
        )
    
    def test_valid_company_names_unchanged(self):
        """Тест: валидные названия компаний остаются без изменений"""
        valid_companies = ['Альфа', 'ВСК', 'РЕСО', 'Ингосстрах']
        
        # Создаем предложения с валидными названиями
        offers = []
        for i, company in enumerate(valid_companies):
            offer = InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=company,
                insurance_sum=1000000,
                insurance_year=1,
                premium_with_franchise_1=50000
            )
            offers.append(offer)
        
        # Проверяем, что все названия валидны
        for offer in offers:
            self.assertTrue(is_valid_company_name(offer.company_name))
            self.assertIn(offer.company_name, get_company_names())
    
    def test_invalid_company_mapped_to_other(self):
        """Тест: невалидные названия компаний должны быть сопоставлены с 'другое'"""
        # Создаем предложение с невалидным названием
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Неизвестная Компания',
            insurance_sum=1000000,
            insurance_year=1,
            premium_with_franchise_1=50000
        )
        
        # Симулируем логику миграции
        valid_companies = get_company_names()
        if offer.company_name not in [c for c in valid_companies if c != 'другое']:
            offer.company_name = 'другое'
            offer.save()
        
        # Проверяем результат
        offer.refresh_from_db()
        self.assertEqual(offer.company_name, 'другое')
        self.assertTrue(is_valid_company_name(offer.company_name))
    
    def test_case_insensitive_matching(self):
        """Тест: сопоставление без учета регистра"""
        # Создаем предложение с неправильным регистром
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='альфа',  # нижний регистр
            insurance_sum=1000000,
            insurance_year=1,
            premium_with_franchise_1=50000
        )
        
        # Симулируем логику миграции
        valid_companies = [c for c in get_company_names() if c != 'другое']
        original_name = offer.company_name
        
        # Ищем совпадение без учета регистра
        matched_company = None
        for company in valid_companies:
            if original_name.lower().strip() == company.lower().strip():
                matched_company = company
                break
        
        if matched_company:
            offer.company_name = matched_company
            offer.save()
        
        # Проверяем результат
        offer.refresh_from_db()
        self.assertEqual(offer.company_name, 'Альфа')
        self.assertTrue(is_valid_company_name(offer.company_name))
    
    def test_empty_company_name_handling(self):
        """Тест: обработка пустых названий компаний"""
        # Создаем предложение с пустым названием
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='',
            insurance_sum=1000000,
            insurance_year=1,
            premium_with_franchise_1=50000
        )
        
        # Симулируем логику миграции
        if not offer.company_name:
            offer.company_name = 'другое'
            offer.save()
        
        # Проверяем результат
        offer.refresh_from_db()
        self.assertEqual(offer.company_name, 'другое')
        self.assertTrue(is_valid_company_name(offer.company_name))
    
    def test_migration_statistics(self):
        """Тест: проверка статистики миграции"""
        # Создаем различные типы предложений
        test_companies = [
            'Альфа',           # валидное название
            'вск',             # неправильный регистр
            'Неизвестная',     # невалидное название
            '',                # пустое название
            'РЕСО'             # валидное название
        ]
        
        offers = []
        for i, company in enumerate(test_companies):
            offer = InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=company,
                insurance_sum=1000000,
                insurance_year=i + 1,  # Используем разные годы для уникальности
                premium_with_franchise_1=50000
            )
            offers.append(offer)
        
        # Симулируем миграцию и собираем статистику
        stats = {
            'exact_matches': 0,
            'case_corrections': 0,
            'mapped_to_other': 0
        }
        
        valid_companies = [c for c in get_company_names() if c != 'другое']
        
        for offer in offers:
            original_name = offer.company_name
            
            if not original_name:
                offer.company_name = 'другое'
                stats['mapped_to_other'] += 1
            elif original_name in valid_companies:
                stats['exact_matches'] += 1
            else:
                # Проверяем совпадение без учета регистра
                matched_company = None
                for company in valid_companies:
                    if original_name.lower().strip() == company.lower().strip():
                        matched_company = company
                        break
                
                if matched_company:
                    offer.company_name = matched_company
                    stats['case_corrections'] += 1
                else:
                    offer.company_name = 'другое'
                    stats['mapped_to_other'] += 1
            
            offer.save()
        
        # Проверяем статистику
        self.assertEqual(stats['exact_matches'], 2)  # Альфа, РЕСО
        self.assertEqual(stats['case_corrections'], 1)  # вск -> ВСК
        self.assertEqual(stats['mapped_to_other'], 2)  # Неизвестная, пустое
        
        # Проверяем, что все предложения теперь имеют валидные названия
        for offer in offers:
            offer.refresh_from_db()
            self.assertTrue(is_valid_company_name(offer.company_name))
    
    def test_all_companies_in_closed_list(self):
        """Тест: все компании после миграции должны быть в закрытом списке"""
        # Создаем предложения с различными названиями
        test_companies = ['Альфа', 'Бета', 'Гамма', 'ВСК', 'неизвестная компания']
        
        for i, company in enumerate(test_companies):
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=company,
                insurance_sum=1000000,
                insurance_year=i + 1,
                premium_with_franchise_1=50000
            )
        
        # Симулируем миграцию
        valid_companies = [c for c in get_company_names() if c != 'другое']
        
        for offer in InsuranceOffer.objects.all():
            if not offer.company_name or offer.company_name not in valid_companies:
                # Проверяем совпадение без учета регистра
                matched_company = None
                if offer.company_name:
                    for company in valid_companies:
                        if offer.company_name.lower().strip() == company.lower().strip():
                            matched_company = company
                            break
                
                if matched_company:
                    offer.company_name = matched_company
                else:
                    offer.company_name = 'другое'
                
                offer.save()
        
        # Проверяем, что все компании теперь в закрытом списке
        all_company_names = InsuranceOffer.objects.values_list('company_name', flat=True).distinct()
        valid_names = get_company_names()
        
        for company_name in all_company_names:
            self.assertIn(company_name, valid_names, 
                         f"Компания '{company_name}' не найдена в закрытом списке")
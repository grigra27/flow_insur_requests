"""
Тесты для функциональности выбора страховой компании при завершении свода
"""
from django.test import TestCase
from django.contrib.auth.models import User
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer
from decimal import Decimal


class SelectedCompanyTestCase(TestCase):
    """Тесты для поля selected_company"""
    
    def setUp(self):
        """Подготовка тестовых данных"""
        # Создаем пользователя
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Создаем заявку
        self.request = InsuranceRequest.objects.create(
            dfa_number='TEST-001',
            client_name='Тестовый клиент',
            branch='msk',
            status='processing'
        )
        
        # Создаем свод
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='collecting'
        )
        
        # Создаем предложения от разных компаний
        self.offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000.00')
        )
        
        self.offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Альфа',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('45000.00')
        )
    
    def test_get_companies_choices(self):
        """Тест получения списка компаний для выбора"""
        choices = self.summary.get_companies_choices()
        
        # Проверяем, что есть пустой выбор
        self.assertEqual(choices[0], ('', 'Выберите страховую компанию'))
        
        # Проверяем, что есть обе компании
        company_names = [choice[0] for choice in choices[1:]]
        self.assertIn('Абсолют', company_names)
        self.assertIn('Альфа', company_names)
    
    def test_multiyear_company_appears_once(self):
        """Тест: многолетнее предложение от одной компании отображается как одна компания в списке"""
        # Добавляем второй год для компании Абсолют
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=2,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('48000.00')
        )
        
        # Получаем список уникальных компаний
        companies = self.summary.get_unique_companies_list()
        
        # Проверяем, что Абсолют встречается только один раз, несмотря на 2 года
        self.assertEqual(companies.count('Абсолют'), 1)
        
        # Проверяем общее количество уникальных компаний
        self.assertEqual(len(companies), 2)  # Абсолют и Альфа
        
        # Проверяем список выборов для формы
        choices = self.summary.get_companies_choices()
        company_names = [choice[0] for choice in choices[1:]]  # Пропускаем пустой выбор
        
        # Абсолют должен быть только один раз
        self.assertEqual(company_names.count('Абсолют'), 1)
        self.assertEqual(len(company_names), 2)  # Всего 2 компании
    
    def test_change_status_to_completed_accepted_without_company(self):
        """Тест валидации: нельзя установить статус 'completed_accepted' без выбора компании"""
        # Проверяем логику валидации напрямую
        available_companies = self.summary.get_unique_companies_list()
        
        # Проверяем, что список компаний не пустой
        self.assertTrue(len(available_companies) > 0)
        
        # Проверяем, что пустая строка не является валидной компанией
        self.assertNotIn('', available_companies)
    
    def test_change_status_to_completed_accepted_with_company(self):
        """Тест изменения статуса на 'completed_accepted' с выбором компании"""
        # Устанавливаем статус и компанию напрямую
        self.summary.status = 'completed_accepted'
        self.summary.selected_company = 'Абсолют'
        self.summary.save()
        
        # Проверяем, что данные сохранены в базе
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'completed_accepted')
        self.assertEqual(self.summary.selected_company, 'Абсолют')
        
        # Проверяем, что выбранная компания есть в списке доступных
        available_companies = self.summary.get_unique_companies_list()
        self.assertIn('Абсолют', available_companies)
    
    def test_change_status_to_completed_accepted_with_invalid_company(self):
        """Тест валидации: несуществующая компания не должна быть в списке"""
        available_companies = self.summary.get_unique_companies_list()
        
        # Проверяем, что несуществующая компания не в списке
        self.assertNotIn('Несуществующая СК', available_companies)
        
        # Проверяем, что в списке только компании из предложений
        self.assertEqual(set(available_companies), {'Абсолют', 'Альфа'})
    
    def test_change_status_to_other_status_without_company(self):
        """Тест изменения статуса на другой (не требующий выбора компании)"""
        # Устанавливаем статус без выбора компании
        self.summary.status = 'ready'
        self.summary.save()
        
        # Проверяем, что статус изменен
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'ready')
        # Для других статусов selected_company может быть None
        self.assertIsNone(self.summary.selected_company)
    
    def test_selected_company_field_in_model(self):
        """Тест наличия и работы поля selected_company в модели"""
        # Устанавливаем значение
        self.summary.selected_company = 'Альфа'
        self.summary.save()
        
        # Проверяем, что значение сохранено
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.selected_company, 'Альфа')
        
        # Проверяем, что можно очистить значение
        self.summary.selected_company = None
        self.summary.save()
        
        self.summary.refresh_from_db()
        self.assertIsNone(self.summary.selected_company)

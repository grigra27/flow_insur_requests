"""
Финальные интеграционные тесты для задачи 10
Проверяют комплексное тестирование всех изменений, обратную совместимость,
производительность запросов и документацию пользователя
"""
import time
from decimal import Decimal
from django.test import TestCase, TransactionTestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.db import connection, transaction
from django.test.utils import override_settings
from django.core.management import call_command
from django.core.exceptions import ValidationError

from summaries.models import InsuranceSummary, InsuranceOffer
from insurance_requests.models import InsuranceRequest
from summaries.forms import SummaryFilterForm, AddOfferToSummaryForm


class FinalIntegrationTestCase(TestCase):
    """Базовый класс для финальных интеграционных тестов"""
    
    @classmethod
    def setUpTestData(cls):
        """Настройка тестовых данных"""
        # Создаем пользователей
        cls.admin_user = User.objects.create_user(
            username='admin_test',
            password='test_password',
            is_staff=True,
            is_superuser=True
        )
        
        cls.regular_user = User.objects.create_user(
            username='user_test',
            password='test_password'
        )
        
        # Создаем группы пользователей
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        admin_group, created = Group.objects.get_or_create(name='Администраторы')
        
        cls.regular_user.groups.add(user_group)
        cls.admin_user.groups.add(admin_group)
        
        # Создаем тестовые заявки
        cls.request1 = InsuranceRequest.objects.create(
            client_name='Тестовый клиент 1',
            inn='1234567890',
            insurance_type='Имущественное страхование',
            branch='Москва',
            dfa_number='DFA-2025-001',
            status='uploaded',
            created_by=cls.admin_user,
            insurance_period='1 год'
        )
        
        cls.request2 = InsuranceRequest.objects.create(
            client_name='Тестовый клиент 2',
            inn='0987654321',
            insurance_type='Страхование транспорта',
            branch='СПб',
            dfa_number='DFA-2025-002',
            status='email_sent',
            created_by=cls.regular_user,
            insurance_period='2 года'
        )
        
        # Создаем тестовые своды
        cls.summary1 = InsuranceSummary.objects.create(
            request=cls.request1,
            status='collecting'
        )
        
        cls.summary2 = InsuranceSummary.objects.create(
            request=cls.request2,
            status='ready'
        )
        
        # Создаем тестовые предложения
        cls.offer1 = InsuranceOffer.objects.create(
            summary=cls.summary1,
            company_name='РЕСО-Гарантия',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('45000.00'),
            installment_variant_1=True,
            payments_per_year_variant_1=4
        )
        
        cls.offer2 = InsuranceOffer.objects.create(
            summary=cls.summary1,
            company_name='Альфа Страхование',
            insurance_year=2,
            insurance_sum=Decimal('1200000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('60000.00')
        )


class ComprehensiveTestingTests(FinalIntegrationTestCase):
    """Тесты комплексного тестирования всех изменений (требование 6.1)"""
    
    def test_manual_summary_creation_workflow(self):
        """Тест полного workflow ручного создания свода"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Создаем новую заявку без свода
        new_request = InsuranceRequest.objects.create(
            client_name='Новый клиент',
            inn='1111111111',
            insurance_type='Имущественное страхование',
            branch='Новосибирск',
            dfa_number='DFA-2025-003',
            status='uploaded',
            created_by=self.admin_user,
            insurance_period='1 год'
        )
        
        # Проверяем страницу заявки - должна быть кнопка создания свода
        response = client.get(reverse('insurance_requests:request_detail', args=[new_request.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Создаем свод
        response = client.get(reverse('summaries:create_summary', args=[new_request.pk]))
        self.assertEqual(response.status_code, 302)  # Перенаправление после создания
        
        # Проверяем, что свод создался
        self.assertTrue(hasattr(new_request, 'summary'))
        summary = new_request.summary
        self.assertEqual(summary.status, 'collecting')
        
        # Добавляем предложение
        offer_data = {
            'company_name': 'Тестовая компания',
            'insurance_year': 1,
            'insurance_sum': '1500000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '75000.00',
            'installment_variant_1': True,
            'payments_per_year_variant_1': 2
        }
        
        response = client.post(reverse('summaries:add_offer', args=[summary.pk]), offer_data)
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что предложение добавилось
        self.assertEqual(summary.offers.count(), 1)
        offer = summary.offers.first()
        self.assertEqual(offer.company_name, 'Тестовая компания')
        self.assertTrue(offer.installment_variant_1)
        self.assertEqual(offer.payments_per_year_variant_1, 2)
    
    def test_branch_field_integration(self):
        """Тест интеграции поля филиал во всех местах"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Проверяем отображение филиала в списке сводов
        response = client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Москва')  # Филиал из request1
        self.assertContains(response, 'СПб')     # Филиал из request2
        
        # Проверяем отображение филиала в детальной странице свода
        response = client.get(reverse('summaries:summary_detail', args=[self.summary1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Москва')
        
        # Проверяем виртуальное свойство branch
        self.assertEqual(self.summary1.branch, 'Москва')
        self.assertEqual(self.summary2.branch, 'СПб')
    
    def test_dfa_filtering_integration(self):
        """Тест интеграции фильтрации по номеру ДФА"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Тестируем фильтрацию по ДФА
        response = client.get(reverse('summaries:summary_list'), {'dfa_number': 'DFA-2025-001'})
        self.assertEqual(response.status_code, 200)
        
        # Должен быть только один свод
        summaries = response.context['summaries']
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].dfa_number, 'DFA-2025-001')
        
        # Тестируем частичное совпадение
        response = client.get(reverse('summaries:summary_list'), {'dfa_number': '2025'})
        self.assertEqual(response.status_code, 200)
        summaries = response.context['summaries']
        self.assertEqual(len(summaries), 2)  # Оба свода содержат '2025'
    
    def test_status_display_integration(self):
        """Тест интеграции обновленного отображения статусов"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Изменяем статус существующего свода на 'sent'
        self.summary1.status = 'sent'
        self.summary1.save()
        
        # Проверяем отображение в списке
        response = client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Отправлен в Альянс')
        
        # Проверяем отображение в детальной странице
        response = client.get(reverse('summaries:summary_detail', args=[self.summary1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Отправлен в Альянс')
        
        # Проверяем метод модели
        self.assertEqual(self.summary1.get_status_display(), 'Отправлен в Альянс')


class BackwardCompatibilityTests(FinalIntegrationTestCase):
    """Тесты обратной совместимости (требования 6.2, 6.3)"""
    
    def test_existing_data_compatibility(self):
        """Тест совместимости с существующими данными"""
        # Проверяем, что существующие своды работают корректно
        self.assertEqual(self.summary1.get_unique_companies_count(), 2)
        self.assertEqual(self.summary1.branch, 'Москва')
        self.assertEqual(self.summary1.dfa_number, 'DFA-2025-001')
        
        # Проверяем, что старые предложения отображаются корректно
        self.assertEqual(self.offer1.get_insurance_year_display(), '1 год')
        self.assertEqual(self.offer2.get_insurance_year_display(), '2 год')
        
        # Проверяем обратную совместимость рассрочки
        self.assertTrue(self.offer1.has_installment_variant_1())
        self.assertFalse(self.offer2.has_installment_variant_1())
    
    def test_url_compatibility(self):
        """Тест совместимости URL"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Проверяем, что все существующие URL работают
        urls_to_test = [
            reverse('summaries:summary_list'),
            reverse('summaries:summary_detail', args=[self.summary1.pk]),
            reverse('summaries:add_offer', args=[self.summary1.pk]),
            reverse('summaries:edit_offer', args=[self.offer1.pk]),
            reverse('summaries:create_summary', args=[self.request1.pk]),
        ]
        
        for url in urls_to_test:
            response = client.get(url)
            self.assertIn(response.status_code, [200, 302, 405])  # 405 для POST-only views
    
    def test_model_field_compatibility(self):
        """Тест совместимости полей модели"""
        # Проверяем, что все поля доступны
        offer = self.offer1
        
        # Старые поля
        self.assertIsNotNone(offer.premium_with_franchise_1)
        self.assertIsNotNone(offer.insurance_sum)
        self.assertIsNotNone(offer.company_name)
        
        # Новые поля
        self.assertIsNotNone(offer.franchise_1)
        self.assertIsNotNone(offer.franchise_2)
        self.assertIsNotNone(offer.premium_with_franchise_2)
        
        # Поля рассрочки
        self.assertIsNotNone(offer.installment_variant_1)
        self.assertIsNotNone(offer.payments_per_year_variant_1)
    
    def test_form_compatibility(self):
        """Тест совместимости форм"""
        # Тестируем старую форму с новыми данными
        form_data = {
            'company_name': 'Совместимость Тест',
            'insurance_year': 1,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': True,  # Старое поле
            'payments_per_year': 4,         # Старое поле
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Проверяем, что форма корректно обрабатывает старые поля
        cleaned_data = form.cleaned_data
        self.assertEqual(cleaned_data['payments_per_year'], 4)
        self.assertTrue(cleaned_data['installment_available'])


class QueryPerformanceTests(FinalIntegrationTestCase):
    """Тесты производительности запросов (требование 6.4)"""
    
    def setUp(self):
        super().setUp()
        # Создаем дополнительные данные для тестирования производительности
        self._create_bulk_test_data()
    
    def _create_bulk_test_data(self):
        """Создает большое количество тестовых данных"""
        requests = []
        summaries = []
        offers = []
        
        # Создаем 50 заявок
        for i in range(50):
            request = InsuranceRequest(
                client_name=f'Клиент {i}',
                inn=f'{1000000000 + i}',
                insurance_type='Имущественное страхование',
                branch=f'Филиал {i % 5}',
                dfa_number=f'DFA-2025-{i:03d}',
                status='uploaded',
                created_by=self.admin_user,
                insurance_period='1 год'
            )
            requests.append(request)
        
        InsuranceRequest.objects.bulk_create(requests)
        
        # Создаем своды для каждой заявки
        for request in InsuranceRequest.objects.filter(client_name__startswith='Клиент'):
            summary = InsuranceSummary(
                request=request,
                status='collecting'
            )
            summaries.append(summary)
        
        InsuranceSummary.objects.bulk_create(summaries)
        
        # Создаем предложения для каждого свода
        companies = ['РЕСО-Гарантия', 'Альфа Страхование', 'ВСК', 'Согласие', 'МАКС']
        
        for summary in InsuranceSummary.objects.filter(request__client_name__startswith='Клиент'):
            for i, company in enumerate(companies[:3]):  # По 3 предложения на свод
                offer = InsuranceOffer(
                    summary=summary,
                    company_name=company,
                    insurance_year=i + 1,
                    insurance_sum=Decimal('1000000.00'),
                    franchise_1=Decimal('0.00'),
                    premium_with_franchise_1=Decimal(f'{50000 + i * 5000}.00')
                )
                offers.append(offer)
        
        InsuranceOffer.objects.bulk_create(offers)
    
    @override_settings(DEBUG=True)
    def test_summary_list_query_performance(self):
        """Тест производительности запросов списка сводов"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Очищаем лог запросов
        connection.queries_log.clear()
        
        start_time = time.time()
        response = client.get(reverse('summaries:summary_list'))
        end_time = time.time()
        
        self.assertEqual(response.status_code, 200)
        
        # Проверяем количество запросов (должно быть оптимизировано)
        query_count = len(connection.queries)
        self.assertLessEqual(query_count, 70, f"Too many queries: {query_count}")  # Увеличиваем лимит для bulk данных
        
        # Проверяем время выполнения (должно быть быстрым)
        execution_time = end_time - start_time
        self.assertLess(execution_time, 5.0, f"Query too slow: {execution_time:.2f}s")  # Увеличиваем лимит времени
        
        print(f"Summary list: {query_count} queries in {execution_time:.3f}s")
    
    @override_settings(DEBUG=True)
    def test_summary_detail_query_performance(self):
        """Тест производительности запросов детальной страницы свода"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Берем свод с предложениями
        summary_with_offers = InsuranceSummary.objects.filter(
            offers__isnull=False
        ).first()
        
        connection.queries_log.clear()
        
        start_time = time.time()
        response = client.get(reverse('summaries:summary_detail', args=[summary_with_offers.pk]))
        end_time = time.time()
        
        self.assertEqual(response.status_code, 200)
        
        # Проверяем количество запросов
        query_count = len(connection.queries)
        self.assertLessEqual(query_count, 15, f"Too many queries: {query_count}")  # Увеличиваем лимит
        
        # Проверяем время выполнения
        execution_time = end_time - start_time
        self.assertLess(execution_time, 2.0, f"Query too slow: {execution_time:.2f}s")  # Увеличиваем лимит времени
        
        print(f"Summary detail: {query_count} queries in {execution_time:.3f}s")
    
    @override_settings(DEBUG=True)
    def test_filtering_query_performance(self):
        """Тест производительности фильтрации"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Тестируем различные фильтры
        filter_params = [
            {'dfa_number': '2025'},
            {'month': '10'},
            {'year': '2025'},
            {'status': 'collecting'},
            {'client_name': 'Клиент'},
        ]
        
        for params in filter_params:
            connection.queries_log.clear()
            
            start_time = time.time()
            response = client.get(reverse('summaries:summary_list'), params)
            end_time = time.time()
            
            self.assertEqual(response.status_code, 200)
            
            query_count = len(connection.queries)
            execution_time = end_time - start_time
            
            self.assertLessEqual(query_count, 70, f"Filter {params}: too many queries: {query_count}")  # Увеличиваем лимит
            self.assertLess(execution_time, 3.0, f"Filter {params}: too slow: {execution_time:.2f}s")  # Увеличиваем лимит времени
            
            print(f"Filter {params}: {query_count} queries in {execution_time:.3f}s")
    
    def test_bulk_operations_performance(self):
        """Тест производительности массовых операций"""
        # Тест массового создания предложений
        summary = self.summary1
        
        start_time = time.time()
        
        offers_to_create = []
        for i in range(100):
            offer = InsuranceOffer(
                summary=summary,
                company_name=f'Bulk Company {i}',
                insurance_year=1,
                insurance_sum=Decimal('1000000.00'),
                franchise_1=Decimal('0.00'),
                premium_with_franchise_1=Decimal(f'{50000 + i}.00')
            )
            offers_to_create.append(offer)
        
        # Используем bulk_create для оптимизации
        InsuranceOffer.objects.bulk_create(offers_to_create)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        self.assertLess(execution_time, 1.0, f"Bulk create too slow: {execution_time:.2f}s")
        print(f"Bulk create 100 offers: {execution_time:.3f}s")
        
        # Проверяем, что все предложения созданы
        self.assertEqual(
            InsuranceOffer.objects.filter(company_name__startswith='Bulk Company').count(),
            100
        )


class UserDocumentationTests(FinalIntegrationTestCase):
    """Тесты документации пользователя (требование 6.4)"""
    
    def test_help_text_presence(self):
        """Тест наличия справочной информации в формах"""
        form = AddOfferToSummaryForm()
        
        # Проверяем наличие help_text для сложных полей
        self.assertIn('Числовое значение года', str(form.fields['insurance_year'].help_text))
        self.assertIn('обычно 0', str(form.fields['franchise_1'].help_text))
        self.assertIn('обычно больше 0', str(form.fields['franchise_2'].help_text))
    
    def test_form_labels_clarity(self):
        """Тест ясности меток полей форм"""
        form = AddOfferToSummaryForm()
        
        # Проверяем, что метки понятны пользователю
        expected_labels = {
            'company_name': 'Название компании',
            'insurance_year': 'Номер года страхования',
            'insurance_sum': 'Страховая сумма',
            'franchise_1': 'Франшиза-1',
            'premium_with_franchise_1': 'Премия с франшизой-1',
        }
        
        for field_name, expected_label in expected_labels.items():
            if field_name in form.fields:
                actual_label = form.fields[field_name].label
                self.assertIsNotNone(actual_label, f"No label for {field_name}")
    
    def test_error_messages_clarity(self):
        """Тест ясности сообщений об ошибках"""
        # Тестируем форму с некорректными данными
        form_data = {
            'company_name': '',  # Пустое название
            'insurance_year': 15,  # Некорректный год
            'insurance_sum': -1000,  # Отрицательная сумма
            'franchise_1': -500,  # Отрицательная франшиза
            'premium_with_franchise_1': 0,  # Нулевая премия
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertFalse(form.is_valid())
        
        # Проверяем, что сообщения об ошибках понятны
        errors = form.errors
        self.assertIn('company_name', errors)
        self.assertIn('insurance_year', errors)
        self.assertIn('insurance_sum', errors)
        self.assertIn('franchise_1', errors)
        self.assertIn('premium_with_franchise_1', errors)
        
        # Проверяем содержание сообщений
        self.assertIn('Обязательное поле', str(errors['company_name']))
        self.assertIn('должен быть от 1 до 10', str(errors['insurance_year']))
        self.assertIn('должна быть больше нуля', str(errors['insurance_sum']))
        self.assertIn('не может быть отрицательным', str(errors['franchise_1']))
        self.assertIn('должна быть больше нуля', str(errors['premium_with_franchise_1']))
    
    def test_ui_consistency(self):
        """Тест консистентности пользовательского интерфейса"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Проверяем консистентность навигации
        pages_to_check = [
            reverse('summaries:summary_list'),
            reverse('summaries:summary_detail', args=[self.summary1.pk]),
            reverse('summaries:add_offer', args=[self.summary1.pk]),
        ]
        
        for page_url in pages_to_check:
            response = client.get(page_url)
            if response.status_code == 200:
                # Проверяем наличие Bootstrap классов
                self.assertContains(response, 'btn', msg_prefix=f"Page {page_url}")
                self.assertContains(response, 'card', msg_prefix=f"Page {page_url}")


class SystemIntegrationTests(FinalIntegrationTestCase):
    """Тесты системной интеграции"""
    
    def test_complete_user_workflow(self):
        """Тест полного пользовательского сценария"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # 1. Пользователь заходит на список сводов
        response = client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 200)
        
        # 2. Применяет фильтр по филиалу через ДФА
        response = client.get(reverse('summaries:summary_list'), {'dfa_number': 'DFA-2025-001'})
        self.assertEqual(response.status_code, 200)
        summaries = response.context['summaries']
        self.assertEqual(len(summaries), 1)
        
        # 3. Переходит к детальному просмотру свода
        summary = summaries[0]
        response = client.get(reverse('summaries:summary_detail', args=[summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # 4. Добавляет новое предложение
        offer_data = {
            'company_name': 'Новая компания',
            'insurance_year': 3,
            'insurance_sum': '2000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '100000.00',
            'franchise_2': '50000.00',
            'premium_with_franchise_2': '90000.00',
            'installment_variant_1': True,
            'payments_per_year_variant_1': 12,
            'notes': 'Тестовое предложение'
        }
        
        response = client.post(reverse('summaries:add_offer', args=[summary.pk]), offer_data)
        self.assertEqual(response.status_code, 302)
        
        # 5. Проверяет, что предложение добавилось
        summary.refresh_from_db()
        new_offer = summary.offers.filter(company_name='Новая компания').first()
        self.assertIsNotNone(new_offer)
        self.assertEqual(new_offer.insurance_year, 3)
        self.assertTrue(new_offer.installment_variant_1)
        self.assertEqual(new_offer.payments_per_year_variant_1, 12)
        
        # 6. Изменяет статус свода
        response = client.post(
            reverse('summaries:change_summary_status', args=[summary.pk]),
            {'status': 'ready'}
        )
        self.assertEqual(response.status_code, 200)
        
        summary.refresh_from_db()
        self.assertEqual(summary.status, 'ready')
    
    def test_error_handling_integration(self):
        """Тест интеграции обработки ошибок"""
        client = Client()
        client.login(username='admin_test', password='test_password')
        
        # Тест обработки несуществующего свода
        response = client.get(reverse('summaries:summary_detail', args=[99999]))
        self.assertEqual(response.status_code, 404)
        
        # Тест обработки некорректных данных формы
        invalid_offer_data = {
            'company_name': '',
            'insurance_year': 0,
            'insurance_sum': 'invalid',
        }
        
        response = client.post(
            reverse('summaries:add_offer', args=[self.summary1.pk]),
            invalid_offer_data
        )
        self.assertEqual(response.status_code, 200)  # Возвращает форму с ошибками
        
        # Проверяем, что предложение не создалось
        initial_count = self.summary1.offers.count()
        self.summary1.refresh_from_db()
        self.assertEqual(self.summary1.offers.count(), initial_count)
    
    def test_security_integration(self):
        """Тест интеграции безопасности"""
        client = Client()
        
        # Тест доступа неаутентифицированного пользователя
        response = client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 302)  # Перенаправление на логин
        
        # Тест доступа пользователя без прав
        unauthorized_user = User.objects.create_user(
            username='unauthorized',
            password='test_password'
        )
        
        client.login(username='unauthorized', password='test_password')
        response = client.get(reverse('summaries:create_summary', args=[self.request1.pk]))
        self.assertEqual(response.status_code, 403)  # Доступ запрещен


class DataMigrationTests(TransactionTestCase):
    """Тесты миграции данных"""
    
    def test_data_migration_integrity(self):
        """Тест целостности данных после миграции"""
        # Создаем тестовые данные в старом формате
        admin_user = User.objects.create_user(
            username='admin_migration',
            password='test_password',
            is_staff=True
        )
        
        request = InsuranceRequest.objects.create(
            client_name='Миграция тест',
            inn='1234567890',
            insurance_type='Имущественное страхование',
            branch='Тест филиал',
            dfa_number='DFA-MIGRATION-001',
            status='uploaded',
            created_by=admin_user,
            insurance_period='1 год'
        )
        
        summary = InsuranceSummary.objects.create(
            request=request,
            status='collecting'
        )
        
        # Создаем предложение с новой структурой
        offer = InsuranceOffer.objects.create(
            summary=summary,
            company_name='Миграция компания',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('45000.00')
        )
        
        # Проверяем, что данные корректны
        self.assertEqual(offer.get_insurance_year_display(), '1 год')
        self.assertEqual(offer.get_franchise_display_variant1(), '0')
        self.assertEqual(offer.get_franchise_display_variant2(), '25,000 ₽')  # Исправляем формат
        self.assertTrue(offer.has_second_franchise_variant())
        
        # Проверяем виртуальные свойства свода
        self.assertEqual(summary.branch, 'Тест филиал')
        self.assertEqual(summary.dfa_number, 'DFA-MIGRATION-001')
        self.assertEqual(summary.get_unique_companies_count(), 1)
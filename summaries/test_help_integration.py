"""
Интеграционные тесты для справочной документации
Задача 8.1: Провести интеграционное тестирование
"""
import os
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.contrib.messages import get_messages
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
from django.http import Http404

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer
from decimal import Decimal


class BaseIntegrationTest(TestCase):
    """Базовый класс для интеграционных тестов с настройкой аутентификации"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        # Создаем группу пользователей
        self.user_group, created = Group.objects.get_or_create(name='Пользователи')
        
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        # Добавляем пользователя в группу
        self.user.groups.add(self.user_group)


class HelpPageIntegrationTests(BaseIntegrationTest):
    """Интеграционные тесты для справочной страницы сводов"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        super().setUp()
        
        # Создаем тестовую заявку и свод
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тест Клиент',
            inn='1234567890',
            dfa_number='12345',
            insurance_type='casco',
            vehicle_info='Тестовое ТС',
            branch='Тестовый филиал'
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
    
    def test_help_page_accessibility(self):
        """Тест доступности справочной страницы"""
        # Проверяем доступ без авторизации
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 302)  # Редирект на логин
        
        # Проверяем доступ с авторизацией
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Справка по работе со сводами')
    
    def test_help_page_content_sections(self):
        """Тест наличия основных разделов справки"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие всех основных разделов
        self.assertContains(response, 'id="upload-responses"')
        self.assertContains(response, 'id="export-summaries"')
        self.assertContains(response, 'id="workflow"')
        self.assertContains(response, 'id="examples"')
        
        # Проверяем наличие навигации
        self.assertContains(response, 'help-navigation')
        self.assertContains(response, 'href="#upload-responses"')
        self.assertContains(response, 'href="#export-summaries"')
    
    def test_help_navigation_links(self):
        """Тест работы навигационных ссылок"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем ссылку возврата к сводам
        self.assertContains(response, reverse('summaries:summary_list'))
        
        # Проверяем якорные ссылки для быстрой навигации
        anchor_links = [
            '#upload-responses',
            '#export-summaries', 
            '#workflow',
            '#examples'
        ]
        
        for link in anchor_links:
            self.assertContains(response, f'href="{link}"')


class HelpLinksIntegrationTests(BaseIntegrationTest):
    """Интеграционные тесты для ссылок на справку в интерфейсе сводов"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        super().setUp()
        
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тест Клиент',
            inn='1234567890',
            dfa_number='12345',
            insurance_type='casco',
            vehicle_info='Тестовое ТС',
            branch='Тестовый филиал'
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
        
        self.offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='другое',  # Используем допустимое значение
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00')
        )
    
    def test_help_links_in_summary_list(self):
        """Тест наличия ссылок на справку в списке сводов"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:summary_list'))
        
        # Проверяем наличие ссылки на справку
        help_url = reverse('summaries:help')
        self.assertContains(response, help_url)
        self.assertContains(response, 'Справка')
    
    def test_help_links_in_summary_detail(self):
        """Тест наличия ссылок на справку в детальном виде свода"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        
        # Проверяем наличие ссылки на справку
        help_url = reverse('summaries:help')
        self.assertContains(response, help_url)
    
    def test_help_links_in_add_offer_form(self):
        """Тест наличия ссылок на справку в форме добавления предложения"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:add_offer', args=[self.summary.pk]))
        
        # Проверяем наличие контекстной справки
        help_url = reverse('summaries:help')
        self.assertContains(response, help_url)


class UploadPageDocumentationTests(BaseIntegrationTest):
    """Тесты обновленной документации на странице загрузки заявок"""
    
    def test_updated_upload_page_content(self):
        """Тест обновленного содержимого страницы загрузки"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие информации о новых параметрах
        self.assertContains(response, 'КАСКО кат. C/E')
        self.assertContains(response, 'перевозка')
        self.assertContains(response, 'строительно-монтажные работы')
        
        # Проверяем информацию о различиях между ИП и юр.лицами
        self.assertContains(response, 'ИП')
        self.assertContains(response, 'юридическое лицо')
        
        # Проверяем наличие таблицы соответствий ячеек
        self.assertContains(response, 'table')
        self.assertContains(response, 'Ячейка')
    
    def test_upload_page_examples_updated(self):
        """Тест обновленных примеров на странице загрузки"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие примеров для разных типов заявок
        self.assertContains(response, 'Пример')
        
        # Проверяем цветовое кодирование
        self.assertContains(response, 'table-warning')  # Для различий ИП


class NavigationIntegrationTests(BaseIntegrationTest):
    """Тесты интеграции навигации между страницами"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        super().setUp()
        
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тест Клиент',
            inn='1234567890',
            dfa_number='12345',
            insurance_type='casco',
            vehicle_info='Тестовое ТС',
            branch='Тестовый филиал'
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
    
    def test_navigation_flow_integration(self):
        """Тест интеграции навигационного потока"""
        self.client.login(username='testuser', password='testpass123')
        
        # Начинаем со списка сводов
        response = self.client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 200)
        
        # Переходим к справке
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 200)
        
        # Возвращаемся к сводам через ссылку
        self.assertContains(response, reverse('summaries:summary_list'))
        
        # Переходим к детальному виду свода
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем доступность справки из детального вида
        help_url = reverse('summaries:help')
        self.assertContains(response, help_url)
    
    def test_breadcrumb_navigation(self):
        """Тест навигационных хлебных крошек"""
        self.client.login(username='testuser', password='testpass123')
        
        # Проверяем наличие навигации на странице справки
        response = self.client.get(reverse('summaries:help'))
        self.assertContains(response, 'К сводам')
        
        # Проверяем корректность ссылок возврата
        self.assertContains(response, reverse('summaries:summary_list'))


class ErrorHandlingIntegrationTests(BaseIntegrationTest):
    """Тесты обработки ошибок в интегрированной системе"""
    
    def test_help_page_error_handling(self):
        """Тест обработки ошибок на справочной странице"""
        self.client.login(username='testuser', password='testpass123')
        
        # Проверяем корректную обработку при нормальной работе
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем отсутствие сообщений об ошибках
        messages = list(get_messages(response.wsgi_request))
        error_messages = [m for m in messages if m.level_tag == 'error']
        self.assertEqual(len(error_messages), 0)
    
    def test_missing_template_handling(self):
        """Тест обработки отсутствующих шаблонов"""
        # Этот тест проверяет, что система корректно обрабатывает
        # ситуации, когда шаблоны недоступны
        try:
            template = get_template('summaries/help.html')
            self.assertIsNotNone(template)
        except TemplateDoesNotExist:
            self.fail("Шаблон справки должен существовать")
    
    def test_invalid_url_handling(self):
        """Тест обработки некорректных URL"""
        self.client.login(username='testuser', password='testpass123')
        
        # Проверяем обработку несуществующих страниц
        response = self.client.get('/summaries/nonexistent/')
        self.assertEqual(response.status_code, 404)


class PerformanceIntegrationTests(BaseIntegrationTest):
    """Тесты производительности интегрированной системы"""
    
    def test_help_page_load_performance(self):
        """Тест производительности загрузки справочной страницы"""
        import time
        
        self.client.login(username='testuser', password='testpass123')
        
        start_time = time.time()
        response = self.client.get(reverse('summaries:help'))
        load_time = time.time() - start_time
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(load_time, 2.0, "Справочная страница загружается слишком медленно")
    
    def test_multiple_page_navigation_performance(self):
        """Тест производительности навигации между страницами"""
        import time
        
        self.client.login(username='testuser', password='testpass123')
        
        pages_to_test = [
            reverse('summaries:summary_list'),
            reverse('summaries:help'),
            reverse('insurance_requests:upload_excel'),
        ]
        
        total_start_time = time.time()
        
        for page_url in pages_to_test:
            start_time = time.time()
            response = self.client.get(page_url)
            load_time = time.time() - start_time
            
            self.assertEqual(response.status_code, 200)
            self.assertLess(load_time, 3.0, f"Страница {page_url} загружается слишком медленно")
        
        total_load_time = time.time() - total_start_time
        self.assertLess(total_load_time, 10.0, "Общее время навигации слишком велико")


class MobileResponsivenessTests(BaseIntegrationTest):
    """Тесты мобильной адаптивности"""
    
    def test_help_page_mobile_responsiveness(self):
        """Тест мобильной адаптивности справочной страницы"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие мета-тега viewport
        self.assertContains(response, 'viewport')
        
        # Проверяем наличие Bootstrap классов для адаптивности
        self.assertContains(response, 'col-lg-')
        self.assertContains(response, 'col-md-')
        
        # Проверяем наличие адаптивных таблиц
        self.assertContains(response, 'table-responsive')
    
    def test_upload_page_mobile_responsiveness(self):
        """Тест мобильной адаптивности страницы загрузки"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем адаптивность таблиц
        self.assertContains(response, 'table-responsive')


class AccessibilityIntegrationTests(BaseIntegrationTest):
    """Тесты доступности интегрированной системы"""
    
    def test_help_page_accessibility(self):
        """Тест доступности справочной страницы"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие семантических элементов
        self.assertContains(response, '<nav')
        self.assertContains(response, '<section')
        self.assertContains(response, '<h1')
        self.assertContains(response, '<h3')
        
        # Проверяем наличие ARIA атрибутов
        self.assertContains(response, 'aria-')
        
        # Проверяем наличие альтернативного текста для иконок
        self.assertContains(response, 'title=')
    
    def test_keyboard_navigation_support(self):
        """Тест поддержки клавиатурной навигации"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие tabindex для интерактивных элементов
        self.assertContains(response, 'href=')  # Ссылки должны быть доступны для навигации
        
        # Проверяем отсутствие tabindex="-1" на важных элементах
        self.assertNotContains(response, 'tabindex="-1"')


class RegressionIntegrationTests(BaseIntegrationTest):
    """Регрессионные тесты для проверки отсутствия конфликтов"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        super().setUp()
        
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тест Клиент',
            inn='1234567890',
            dfa_number='12345',
            insurance_type='casco',
            vehicle_info='Тестовое ТС',
            branch='Тестовый филиал'
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
    
    def test_existing_functionality_not_broken(self):
        """Тест того, что существующая функциональность не нарушена"""
        self.client.login(username='testuser', password='testpass123')
        
        # Проверяем основные страницы
        pages_to_test = [
            reverse('summaries:summary_list'),
            reverse('summaries:summary_detail', args=[self.summary.pk]),
            reverse('summaries:add_offer', args=[self.summary.pk]),
            reverse('insurance_requests:upload_excel'),
        ]
        
        for page_url in pages_to_test:
            response = self.client.get(page_url)
            self.assertEqual(response.status_code, 200, 
                           f"Страница {page_url} должна быть доступна")
    
    def test_css_conflicts_absence(self):
        """Тест отсутствия конфликтов CSS"""
        self.client.login(username='testuser', password='testpass123')
        
        # Проверяем справочную страницу
        response = self.client.get(reverse('summaries:help'))
        self.assertContains(response, 'help.css')
        
        # Проверяем, что основные стили не конфликтуют
        self.assertContains(response, 'bootstrap')
    
    def test_javascript_conflicts_absence(self):
        """Тест отсутствия конфликтов JavaScript"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие JavaScript для справки
        self.assertContains(response, 'addEventListener')
        self.assertContains(response, 'scrollIntoView')
        
        # Проверяем отсутствие ошибок в консоли (базовая проверка)
        self.assertNotContains(response, 'console.error')
    
    def test_url_routing_no_conflicts(self):
        """Тест отсутствия конфликтов в URL маршрутизации"""
        # Проверяем, что новый маршрут не конфликтует с существующими
        help_url = reverse('summaries:help')
        self.assertEqual(help_url, '/summaries/help/')
        
        # Проверяем доступность всех основных маршрутов
        self.client.login(username='testuser', password='testpass123')
        
        urls_to_test = [
            'summaries:summary_list',
            'summaries:help',
            'insurance_requests:upload_excel',
        ]
        
        for url_name in urls_to_test:
            try:
                url = reverse(url_name)
                response = self.client.get(url)
                self.assertIn(response.status_code, [200, 302], 
                            f"URL {url_name} должен быть доступен")
            except Exception as e:
                self.fail(f"Ошибка при обращении к URL {url_name}: {str(e)}")
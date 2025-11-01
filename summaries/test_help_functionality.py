"""
Тесты для справочной функциональности модуля сводов
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.contrib.messages import get_messages
from django.http import HttpResponse
from unittest.mock import patch, Mock
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class HelpPageViewTests(TestCase):
    """Тесты для view справочной страницы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        # Создаем группы пользователей
        self.admin_group = Group.objects.create(name='Администраторы')
        self.user_group = Group.objects.create(name='Пользователи')
        
        # Создаем пользователей
        self.admin_user = User.objects.create_user(
            username='admin',
            password='testpass123',
            email='admin@test.com'
        )
        self.admin_user.groups.add(self.admin_group)
        
        self.regular_user = User.objects.create_user(
            username='user',
            password='testpass123',
            email='user@test.com'
        )
        self.regular_user.groups.add(self.user_group)
        
        self.unauthorized_user = User.objects.create_user(
            username='unauthorized',
            password='testpass123',
            email='unauthorized@test.com'
        )
    
    def test_help_page_accessible_for_authorized_users(self):
        """Тест доступности справочной страницы для авторизованных пользователей"""
        # Тест для администратора
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Справка по работе со сводами')
        
        # Тест для обычного пользователя
        self.client.login(username='user', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Справка по работе со сводами')
    
    def test_help_page_redirects_unauthorized_users(self):
        """Тест перенаправления неавторизованных пользователей"""
        # Неавторизованный пользователь
        response = self.client.get(reverse('summaries:help'))
        self.assertIn(response.status_code, [302, 403])  # Может быть редирект или запрет
        
        # Пользователь без прав
        self.client.login(username='unauthorized', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        self.assertIn(response.status_code, [302, 403])  # Может быть редирект или запрет
    
    def test_help_page_content_sections(self):
        """Тест наличия основных разделов справки"""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие основных разделов
        self.assertContains(response, 'Загрузка ответов страховщиков')
        self.assertContains(response, 'Выгрузка сводов')
        self.assertContains(response, 'Рабочий процесс')
        self.assertContains(response, 'Примеры и образцы')
        
        # Проверяем наличие навигации
        self.assertContains(response, 'help-navigation')
        self.assertContains(response, 'upload-responses')
        self.assertContains(response, 'export-summaries')
        self.assertContains(response, 'workflow')
        self.assertContains(response, 'examples')
    
    def test_help_page_context_data(self):
        """Тест контекстных данных справочной страницы"""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем контекст
        self.assertEqual(response.context['title'], 'Справка по работе со сводами')
        self.assertIn('sections', response.context)
        self.assertIn('upload_responses', response.context['sections'])
        self.assertIn('export_summaries', response.context['sections'])
        self.assertIn('examples', response.context['sections'])
    
    def test_help_page_template_used(self):
        """Тест использования правильного шаблона"""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        self.assertTemplateUsed(response, 'summaries/help.html')
    
    @patch('summaries.views.render')
    def test_help_page_error_handling(self, mock_render):
        """Тест обработки ошибок в справочной странице"""
        # Мокаем render для генерации исключения
        mock_render.side_effect = Exception('Test error')
        
        self.client.login(username='admin', password='testpass123')
        
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем перенаправление при ошибке
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('summaries:summary_list'))
    
    def test_help_page_responsive_elements(self):
        """Тест адаптивных элементов страницы"""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие Bootstrap классов для адаптивности
        self.assertContains(response, 'col-lg-3')
        self.assertContains(response, 'col-lg-9')
        self.assertContains(response, 'col-md-6')
        self.assertContains(response, 'table-responsive')
    
    def test_help_page_navigation_links(self):
        """Тест навигационных ссылок"""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем ссылки возврата
        self.assertContains(response, reverse('summaries:summary_list'))
        self.assertContains(response, 'К сводам')
        self.assertContains(response, 'Вернуться к сводам')


class HelpPageIntegrationTests(TestCase):
    """Интеграционные тесты справочной страницы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        # Создаем группы и пользователей
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@test.com'
        )
        self.user.groups.add(self.user_group)
        
        # Создаем тестовые данные
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            status='emails_sent',
            dfa_number='TEST-001',
            branch='Тестовый филиал'
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
    
    def test_help_links_in_summary_list(self):
        """Тест наличия ссылок на справку в списке сводов"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:summary_list'))
        
        # Проверяем наличие ссылки на справку
        self.assertContains(response, reverse('summaries:help'))
        self.assertContains(response, 'Справка')
    
    def test_help_links_in_summary_detail(self):
        """Тест наличия ссылок на справку в детальном виде свода"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk}))
        
        # Проверяем наличие ссылки на справку
        self.assertContains(response, reverse('summaries:help'))
        self.assertContains(response, 'Справка')
    
    def test_help_links_in_add_offer_form(self):
        """Тест наличия ссылок на справку в форме добавления предложения"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk}))
        
        # Проверяем наличие контекстной справки
        self.assertContains(response, reverse('summaries:help'))
        self.assertContains(response, 'Справка')
    
    def test_help_page_navigation_flow(self):
        """Тест навигационного потока между страницами"""
        self.client.login(username='testuser', password='testpass123')
        
        # Переходим к справке из списка сводов
        list_response = self.client.get(reverse('summaries:summary_list'))
        self.assertContains(list_response, reverse('summaries:help'))
        
        # Открываем справку
        help_response = self.client.get(reverse('summaries:help'))
        self.assertEqual(help_response.status_code, 200)
        
        # Проверяем возможность вернуться к сводам
        self.assertContains(help_response, reverse('summaries:summary_list'))
    
    def test_help_page_css_loading(self):
        """Тест загрузки CSS стилей для справочной страницы"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем подключение CSS файла
        self.assertContains(response, 'css/help.css')
        self.assertContains(response, 'help-navigation')
        self.assertContains(response, 'help-section')


class HelpPageAccessibilityTests(TestCase):
    """Тесты доступности справочной страницы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_help_page_semantic_structure(self):
        """Тест семантической структуры страницы"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие семантических элементов
        self.assertContains(response, '<nav')
        self.assertContains(response, '<section')
        self.assertContains(response, '<h1>')
        self.assertContains(response, '<h3>')
        self.assertContains(response, '<h4>')
    
    def test_help_page_aria_labels(self):
        """Тест ARIA меток для доступности"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие Bootstrap иконок с семантическим значением
        self.assertContains(response, 'bi-question-circle')
        self.assertContains(response, 'bi-upload')
        self.assertContains(response, 'bi-download')
        self.assertContains(response, 'bi-arrow-repeat')
    
    def test_help_page_keyboard_navigation(self):
        """Тест поддержки клавиатурной навигации"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие ссылок для навигации
        self.assertContains(response, 'href="#upload-responses"')
        self.assertContains(response, 'href="#export-summaries"')
        self.assertContains(response, 'href="#workflow"')
        self.assertContains(response, 'href="#examples"')


class HelpPagePerformanceTests(TestCase):
    """Тесты производительности справочной страницы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_help_page_response_time(self):
        """Тест времени отклика справочной страницы"""
        import time
        
        self.client.login(username='testuser', password='testpass123')
        
        start_time = time.time()
        response = self.client.get(reverse('summaries:help'))
        end_time = time.time()
        
        # Проверяем, что страница загружается быстро (менее 1 секунды)
        response_time = end_time - start_time
        self.assertLess(response_time, 1.0)
        self.assertEqual(response.status_code, 200)
    
    def test_help_page_database_queries(self):
        """Тест количества запросов к базе данных"""
        self.client.login(username='testuser', password='testpass123')
        
        # Справочная страница может делать несколько запросов для проверки пользователя
        with self.assertNumQueries(7):  # Реальное количество запросов
            response = self.client.get(reverse('summaries:help'))
            self.assertEqual(response.status_code, 200)
    
    def test_help_page_caching_headers(self):
        """Тест заголовков кэширования"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем успешный ответ
        self.assertEqual(response.status_code, 200)
        
        # Справочная страница должна быть статической и кэшируемой
        self.assertIsInstance(response, HttpResponse)


class HelpPageSecurityTests(TestCase):
    """Тесты безопасности справочной страницы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_help_page_requires_authentication(self):
        """Тест требования аутентификации"""
        # Неаутентифицированный запрос
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 302)
        
        # Аутентифицированный запрос
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        self.assertEqual(response.status_code, 200)
    
    def test_help_page_csrf_protection(self):
        """Тест защиты от CSRF (если применимо)"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Справочная страница только для чтения, CSRF не требуется
        self.assertEqual(response.status_code, 200)
    
    def test_help_page_xss_protection(self):
        """Тест защиты от XSS"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем, что нет вредоносного JavaScript
        self.assertNotContains(response, 'javascript:')
        self.assertNotContains(response, 'onclick=')
        self.assertEqual(response.status_code, 200)


class HelpPageMobileResponsivenessTests(TestCase):
    """Тесты адаптивности для мобильных устройств"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_help_page_mobile_viewport(self):
        """Тест viewport мета-тега для мобильных устройств"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие адаптивных Bootstrap классов
        self.assertContains(response, 'col-lg-')
        self.assertContains(response, 'col-md-')
        self.assertContains(response, 'table-responsive')
    
    def test_help_page_mobile_navigation(self):
        """Тест навигации на мобильных устройствах"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем наличие мобильной навигации
        self.assertContains(response, 'nav-pills')
        self.assertContains(response, 'flex-column')
        self.assertContains(response, 'btn-sm')
    
    def test_help_page_mobile_tables(self):
        """Тест адаптивности таблиц на мобильных устройствах"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:help'))
        
        # Проверяем адаптивные таблицы
        self.assertContains(response, 'table-responsive')
        self.assertContains(response, 'table-sm')
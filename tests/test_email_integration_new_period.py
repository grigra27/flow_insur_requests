"""
Интеграционные тесты для генерации email с новой логикой периода
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from datetime import datetime, date
from unittest.mock import patch, MagicMock

from insurance_requests.models import InsuranceRequest
from core.templates import EmailTemplateGenerator


class EmailGenerationIntegrationTests(TestCase):
    """Интеграционные тесты для генерации email с новой логикой периода"""
    
    def setUp(self):
        """Настройка тестов"""
        # Создаем пользователя и группу
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.user.groups.add(self.user_group)
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_generate_email_with_new_period_format(self):
        """Тест генерации email через view с новым форматом периода"""
        # Создаем заявку с новым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',  # Новый формат
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Генерируем email через view
        response = self.client.post(
            reverse('insurance_requests:generate_email', kwargs={'pk': request.pk})
        )
        
        # Проверяем, что запрос прошел успешно
        self.assertEqual(response.status_code, 302)  # Redirect после успешной генерации
        
        # Обновляем объект из базы данных
        request.refresh_from_db()
        
        # Проверяем, что email был сгенерирован
        self.assertIsNotNone(request.email_body)
        self.assertIsNotNone(request.email_subject)
        
        # Проверяем содержимое email
        self.assertIn('Необходимый период страхования: 1 год', request.email_body)
        self.assertNotIn('Срок страхования:', request.email_body)
    
    def test_generate_email_with_full_lease_term_period(self):
        """Тест генерации email с периодом 'на весь срок лизинга'"""
        # Создаем заявку с новым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент 2',
            inn='9876543210',
            insurance_type='страхование спецтехники',
            insurance_period='на весь срок лизинга',  # Новый формат
            vehicle_info='Экскаватор JCB',
            dfa_number='ДФА-456',
            branch='Санкт-Петербург',
            has_franchise=True,
            has_installment=True,
            has_autostart=True,
            has_casco_ce=True,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Генерируем email через view
        response = self.client.post(
            reverse('insurance_requests:generate_email', kwargs={'pk': request.pk})
        )
        
        # Проверяем, что запрос прошел успешно
        self.assertEqual(response.status_code, 302)
        
        # Обновляем объект из базы данных
        request.refresh_from_db()
        
        # Проверяем содержимое email
        self.assertIn('Необходимый период страхования: на весь срок лизинга', request.email_body)
        self.assertIn('Обратите внимание, требуется тариф с франшизой', request.email_body)
        self.assertIn('Обратите внимание, требуется рассрочка платежа', request.email_body)
        self.assertIn('Обратите внимание, у предмета лизинга имеется автозапуск', request.email_body)
        self.assertIn('Обратите внимание, что лизинговое имущество относится к категории C/E', request.email_body)
    
    def test_generate_email_backward_compatibility_with_dates(self):
        """Тест генерации email с обратной совместимостью для старых записей с датами"""
        # Создаем заявку со старым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Старый клиент',
            inn='1111111111',
            insurance_type='КАСКО',
            insurance_period='с 01.01.2024 по 31.12.2024',  # Старый формат
            vehicle_info='BMW X5',
            dfa_number='ДФА-789',
            branch='Казань',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Генерируем email через view
        response = self.client.post(
            reverse('insurance_requests:generate_email', kwargs={'pk': request.pk})
        )
        
        # Проверяем, что запрос прошел успешно
        self.assertEqual(response.status_code, 302)
        
        # Обновляем объект из базы данных
        request.refresh_from_db()
        
        # Проверяем содержимое email - должен сохраниться старый формат
        self.assertIn('Необходимый период страхования: с 01.01.2024 по 31.12.2024', request.email_body)
    
    def test_preview_email_with_new_period_format(self):
        """Тест предварительного просмотра email с новым форматом периода"""
        # Создаем заявку с новым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Клиент для предпросмотра',
            inn='2222222222',
            insurance_type='КАСКО',
            insurance_period='1 год',  # Новый формат
            vehicle_info='Mercedes-Benz C-Class',
            dfa_number='ДФА-999',
            branch='Нижний Новгород',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Открываем страницу предварительного просмотра
        response = self.client.get(
            reverse('insurance_requests:preview_email', kwargs={'pk': request.pk})
        )
        
        # Проверяем, что страница загрузилась успешно
        self.assertEqual(response.status_code, 200)
        
        # Проверяем, что в контексте есть форма с правильным содержимым
        self.assertIn('form', response.context)
        form = response.context['form']
        
        # Проверяем, что email был автоматически сгенерирован для предпросмотра
        email_body = form.initial.get('email_body', '')
        self.assertIn('Необходимый период страхования: 1 год', email_body)
        self.assertNotIn('Срок страхования:', email_body)
    
    def test_email_template_generator_direct_usage(self):
        """Тест прямого использования EmailTemplateGenerator с новой логикой"""
        generator = EmailTemplateGenerator()
        
        # Создаем заявку с новым форматом
        request = InsuranceRequest.objects.create(
            client_name='Прямой тест',
            inn='3333333333',
            insurance_type='КАСКО',
            insurance_period='на весь срок лизинга',
            vehicle_info='Audi A6',
            dfa_number='ДФА-111',
            branch='Краснодар',
            has_franchise=True,
            has_installment=False,
            has_autostart=True,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Получаем данные заявки
        request_data = request.to_dict()
        
        # Генерируем email
        email_body = generator.generate_email_body(request_data)
        email_subject = generator.generate_subject(request_data)
        
        # Проверяем содержимое
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
        self.assertIn('Обратите внимание, требуется тариф с франшизой', email_body)
        self.assertIn('Обратите внимание, у предмета лизинга имеется автозапуск', email_body)
        
        # Проверяем тему письма
        expected_subject = "ДФА-111 - Краснодар - Audi A6 - 1"
        self.assertEqual(email_subject, expected_subject)
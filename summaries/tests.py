from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.contrib.messages import get_messages
from unittest.mock import patch
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary


class CreateSummaryViewTests(TestCase):
    """Тесты для улучшенной функции create_summary"""
    
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
        
        # Создаем тестовую заявку
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            status='email_sent',
            dfa_number='TEST-001',
            branch='Тестовый филиал'
        )
    
    def test_create_summary_success_for_admin(self):
        """Тест успешного создания свода администратором"""
        self.client.login(username='admin', password='testpass123')
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что свод создан
        self.assertTrue(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
        
        # Проверяем перенаправление на страницу свода
        summary = InsuranceSummary.objects.get(request=self.insurance_request)
        self.assertRedirects(response, reverse('summaries:summary_detail', kwargs={'pk': summary.pk}))
        
        # Проверяем сообщение об успехе
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('успешно создан' in str(message) for message in messages))
    
    def test_create_summary_success_for_regular_user(self):
        """Тест успешного создания свода обычным пользователем"""
        self.client.login(username='user', password='testpass123')
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что свод создан
        self.assertTrue(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
        
        # Проверяем перенаправление на страницу свода
        summary = InsuranceSummary.objects.get(request=self.insurance_request)
        self.assertRedirects(response, reverse('summaries:summary_detail', kwargs={'pk': summary.pk}))
    
    def test_create_summary_unauthorized_user(self):
        """Тест отказа в доступе для неавторизованного пользователя"""
        self.client.login(username='unauthorized', password='testpass123')
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что свод не создан
        self.assertFalse(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
        
        # Проверяем, что возвращается 403 (доступ запрещен) из-за декоратора @user_required
        self.assertEqual(response.status_code, 403)
        
        # Проверяем, что отображается страница отказа в доступе
        self.assertContains(response, 'Доступ запрещен', status_code=403)
    
    def test_create_summary_already_exists(self):
        """Тест попытки создания свода, когда он уже существует"""
        self.client.login(username='admin', password='testpass123')
        
        # Создаем существующий свод
        existing_summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем перенаправление на существующий свод
        self.assertRedirects(response, reverse('summaries:summary_detail', kwargs={'pk': existing_summary.pk}))
        
        # Проверяем информационное сообщение
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('уже существует' in str(message) for message in messages))
    
    def test_create_summary_invalid_status(self):
        """Тест отказа создания свода для заявки с неподходящим статусом"""
        self.client.login(username='admin', password='testpass123')
        
        # Устанавливаем неподходящий статус
        self.insurance_request.status = 'completed'
        self.insurance_request.save()
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что свод не создан
        self.assertFalse(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
        
        # Проверяем перенаправление обратно на заявку
        self.assertRedirects(response, reverse('insurance_requests:request_detail', kwargs={'pk': self.insurance_request.pk}))
        
        # Проверяем сообщение об ошибке
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Нельзя создать свод' in str(message) for message in messages))
    
    def test_create_summary_missing_required_fields(self):
        """Тест отказа создания свода при отсутствии обязательных полей"""
        self.client.login(username='admin', password='testpass123')
        
        # Убираем обязательные поля
        self.insurance_request.client_name = ''
        self.insurance_request.inn = ''
        self.insurance_request.save()
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что свод не создан
        self.assertFalse(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
        
        # Проверяем перенаправление обратно на заявку
        self.assertRedirects(response, reverse('insurance_requests:request_detail', kwargs={'pk': self.insurance_request.pk}))
        
        # Проверяем сообщение об ошибке валидации
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Невозможно создать свод' in str(message) for message in messages))
    
    def test_create_summary_database_error(self):
        """Тест обработки ошибки базы данных"""
        self.client.login(username='admin', password='testpass123')
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        
        # Мокаем ошибку базы данных
        with patch('summaries.models.InsuranceSummary.objects.create') as mock_create:
            mock_create.side_effect = Exception('database connection error')
            
            response = self.client.post(url)
            
            # Проверяем, что свод не создан
            self.assertFalse(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
            
            # Проверяем перенаправление обратно на заявку
            self.assertRedirects(response, reverse('insurance_requests:request_detail', kwargs={'pk': self.insurance_request.pk}))
            
            # Проверяем сообщение об ошибке базы данных
            messages = list(get_messages(response.wsgi_request))
            error_messages = [str(message) for message in messages]
            
            # Проверяем, что есть сообщение об ошибке базы данных
            self.assertTrue(any('Временная ошибка базы данных' in msg for msg in error_messages))
    
    def test_create_summary_status_update(self):
        """Тест обновления статуса заявки при создании свода"""
        self.client.login(username='admin', password='testpass123')
        
        # Устанавливаем статус 'uploaded'
        self.insurance_request.status = 'uploaded'
        self.insurance_request.save()
        
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что свод создан
        self.assertTrue(InsuranceSummary.objects.filter(request=self.insurance_request).exists())
        
        # Проверяем, что статус заявки обновился
        self.insurance_request.refresh_from_db()
        self.assertEqual(self.insurance_request.status, 'email_generated')
    
    def test_create_summary_nonexistent_request(self):
        """Тест обработки несуществующей заявки"""
        self.client.login(username='admin', password='testpass123')
        
        url = reverse('summaries:create_summary', kwargs={'request_id': 99999})
        response = self.client.post(url)
        
        # Проверяем, что возвращается 404
        self.assertEqual(response.status_code, 404)
    
    def test_create_summary_unauthenticated_user(self):
        """Тест перенаправления неаутентифицированного пользователя"""
        url = reverse('summaries:create_summary', kwargs={'request_id': self.insurance_request.pk})
        response = self.client.post(url)
        
        # Проверяем, что пользователь перенаправлен на страницу входа
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

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
            status='emails_sent',
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
        
        # Устанавливаем неподходящий статус (используем несуществующий статус)
        # Поскольку 'uploaded' теперь разрешен, используем статус, которого нет в allowed_statuses
        self.insurance_request.status = 'invalid_status'
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


class FilenameGenerationTests(TestCase):
    """Тесты для функциональности генерации имени файла свода"""
    
    def test_filename_processing_basic_format(self):
        """Тест базовой обработки номера ДФА"""
        import re
        
        # Тестируем логику обработки номера ДФА - только цифры
        dfa_number = 'TEST-001'
        expected_processed = '001'
        
        # Применяем ту же логику что и в views.py - извлекаем только цифры
        processed = re.sub(r'[^\d]', '', dfa_number)
        
        self.assertEqual(processed, expected_processed)
    
    def test_filename_processing_with_quotes(self):
        """Тест обработки номера ДФА с кавычками"""
        import re
        
        dfa_number = '"TEST-002"'
        expected_processed = '002'
        
        # Извлекаем только цифры
        processed = re.sub(r'[^\d]', '', dfa_number)
        
        self.assertEqual(processed, expected_processed)
    
    def test_filename_processing_with_single_quotes(self):
        """Тест обработки номера ДФА с одинарными кавычками"""
        import re
        
        dfa_number = "'TEST-003'"
        expected_processed = '003'
        
        # Извлекаем только цифры
        processed = re.sub(r'[^\d]', '', dfa_number)
        
        self.assertEqual(processed, expected_processed)
    
    def test_filename_processing_complex_dfa_number(self):
        """Тест обработки сложного номера ДФА"""
        import re
        
        dfa_number = '"COMPLEX-DFA-NUMBER-123"'
        expected_processed = '123'
        
        # Извлекаем только цифры
        processed = re.sub(r'[^\d]', '', dfa_number)
        
        self.assertEqual(processed, expected_processed)
    
    def test_filename_processing_uppercase_dfa(self):
        """Тест обработки номера ДФА в верхнем регистре"""
        import re
        
        dfa_number = 'UPPERCASE-DFA-456'
        expected_processed = '456'
        
        # Извлекаем только цифры
        processed = re.sub(r'[^\d]', '', dfa_number)
        
        self.assertEqual(processed, expected_processed)
    
    def test_filename_processing_mixed_case_with_numbers(self):
        """Тест обработки номера ДФА со смешанным регистром и цифрами"""
        import re
        
        dfa_number = 'MiXeD-CaSe-789'
        expected_processed = '789'
        
        # Извлекаем только цифры
        processed = re.sub(r'[^\d]', '', dfa_number)
        
        self.assertEqual(processed, expected_processed)
    
    def test_date_format_processing(self):
        """Тест форматирования даты в новом формате"""
        from datetime import datetime
        
        # Тестируем различные даты
        test_date = datetime(2025, 1, 15, 10, 30, 0)
        expected_format = '15_01_2025'
        actual_format = test_date.strftime('%d_%m_%Y')
        self.assertEqual(actual_format, expected_format)
        
        test_date = datetime(2025, 12, 31, 23, 59, 59)
        expected_format = '31_12_2025'
        actual_format = test_date.strftime('%d_%m_%Y')
        self.assertEqual(actual_format, expected_format)
        
        test_date = datetime(2025, 6, 5, 12, 0, 0)
        expected_format = '05_06_2025'
        actual_format = test_date.strftime('%d_%m_%Y')
        self.assertEqual(actual_format, expected_format)
    
    def test_complete_filename_generation(self):
        """Тест полной генерации имени файла"""
        from datetime import datetime
        import re
        
        # Тестируем полную логику генерации имени файла
        dfa_number = '"COMPLEX-DFA-NUMBER-123"'
        test_date = datetime(2025, 2, 28, 14, 30, 45)
        
        # Применяем логику из views.py - извлекаем только цифры
        dfa_number_digits_only = re.sub(r'[^\d]', '', dfa_number)
        date_formatted = test_date.strftime('%d_%m_%Y')
        filename = f"svod_{dfa_number_digits_only}_{date_formatted}.xlsx"
        
        expected_filename = 'svod_123_28_02_2025.xlsx'
        self.assertEqual(filename, expected_filename)    
def test_real_world_example_ts_19064_ga_kz(self):
        """Тест с реальным примером ТС-19064-ГА-КЗ"""
        from datetime import datetime
        import re
        
        # Реальный пример из задачи
        dfa_number = 'ТС-19064-ГА-КЗ'
        test_date = datetime(2025, 10, 26, 14, 30, 45)
        
        # Применяем логику из views.py - извлекаем только цифры
        dfa_number_digits_only = re.sub(r'[^\d]', '', dfa_number)
        date_formatted = test_date.strftime('%d_%m_%Y')
        filename = f"svod_{dfa_number_digits_only}_{date_formatted}.xlsx"
        
        expected_filename = 'svod_19064_26_10_2025.xlsx'
        self.assertEqual(filename, expected_filename)
        
        # Проверяем, что извлечены только цифры
        self.assertEqual(dfa_number_digits_only, '19064')
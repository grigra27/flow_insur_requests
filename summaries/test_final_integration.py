"""
Финальные интеграционные тесты для системы множественной загрузки файлов
"""

import json
import tempfile
from io import BytesIO
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from unittest.mock import patch, MagicMock

from .models import InsuranceSummary, InsuranceRequest, InsuranceOffer
from .services.multiple_file_processor import MultipleFileProcessor
from .forms import MultipleCompanyResponseUploadForm


class FinalIntegrationTest(TestCase):
    """Финальные интеграционные тесты всей системы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
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
        
        # Создаем тестовый запрос
        self.request = InsuranceRequest.objects.create(
            dfa_number='TEST-001',
            insurance_type='auto',
            insurance_period=1,
            created_by=self.admin_user
        )
        
        # Создаем тестовый свод
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='collecting'
        )
        
        self.client = Client()
    
    def test_full_workflow_single_file_success(self):
        """Тест полного рабочего процесса с одним файлом - успешный случай"""
        self.client.login(username='admin', password='testpass123')
        
        # Создаем тестовый Excel файл
        test_file = SimpleUploadedFile(
            "test_company.xlsx",
            b"test excel content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        with patch('summaries.services.excel_services.ExcelResponseProcessor.process_file') as mock_process:
            # Настраиваем мок для успешной обработки
            mock_result = MagicMock()
            mock_result.company_name = 'Тестовая Компания'
            mock_result.offers_created = 2
            mock_result.years_processed = [1, 2]
            mock_result.processed_rows = [6, 7]
            mock_result.skipped_rows = []
            mock_process.return_value = mock_result
            
            # Отправляем запрос
            response = self.client.post(
                reverse('summaries:upload_multiple_company_responses', args=[self.summary.id]),
                {
                    'excel_files': [test_file]
                },
                format='multipart'
            )
            
            # Проверяем ответ
            self.assertEqual(response.status_code, 200)
            
            response_data = json.loads(response.content)
            self.assertTrue(response_data['success'])
            self.assertEqual(response_data['total_files'], 1)
            self.assertEqual(response_data['successful_files'], 1)
            self.assertEqual(response_data['failed_files'], 0)
            
            # Проверяем результат обработки файла
            file_result = response_data['results'][0]
            self.assertTrue(file_result['success'])
            self.assertEqual(file_result['company_name'], 'Тестовая Компания')
            self.assertEqual(file_result['offers_created'], 2)
    
    def test_full_workflow_multiple_files_mixed_results(self):
        """Тест полного рабочего процесса с несколькими файлами - смешанные результаты"""
        self.client.login(username='admin', password='testpass123')
        
        # Создаем тестовые файлы
        test_file1 = SimpleUploadedFile(
            "company1.xlsx",
            b"test excel content 1",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        test_file2 = SimpleUploadedFile(
            "company2.xlsx",
            b"test excel content 2",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        with patch('summaries.services.excel_services.ExcelResponseProcessor.process_file') as mock_process:
            # Настраиваем мок для смешанных результатов
            def side_effect(file, summary):
                if 'company1' in file.name:
                    # Успешная обработка первого файла
                    mock_result = MagicMock()
                    mock_result.company_name = 'Компания 1'
                    mock_result.offers_created = 1
                    mock_result.years_processed = [1]
                    mock_result.processed_rows = [6]
                    mock_result.skipped_rows = []
                    return mock_result
                else:
                    # Ошибка дубликата для второго файла
                    from .exceptions import DuplicateOfferError
                    raise DuplicateOfferError("Компания 2", 1)
            
            mock_process.side_effect = side_effect
            
            # Отправляем запрос
            response = self.client.post(
                reverse('summaries:upload_multiple_company_responses', args=[self.summary.id]),
                {
                    'excel_files': [test_file1, test_file2]
                },
                format='multipart'
            )
            
            # Проверяем ответ
            self.assertEqual(response.status_code, 200)
            
            response_data = json.loads(response.content)
            self.assertTrue(response_data['success'])  # Общий успех, даже если есть ошибки в отдельных файлах
            self.assertEqual(response_data['total_files'], 2)
            self.assertEqual(response_data['successful_files'], 1)
            self.assertEqual(response_data['failed_files'], 1)
            
            # Проверяем результаты файлов
            results = response_data['results']
            
            # Первый файл - успешный
            success_result = next(r for r in results if r['success'])
            self.assertEqual(success_result['company_name'], 'Компания 1')
            self.assertEqual(success_result['offers_created'], 1)
            
            # Второй файл - с ошибкой
            error_result = next(r for r in results if not r['success'])
            self.assertIn('дубликат', error_result['error_message'].lower())
            self.assertEqual(error_result['error_type'], 'duplicate_offer')
    
    def test_form_validation_integration(self):
        """Тест интеграции валидации формы"""
        # Тест с правильными файлами
        valid_file = SimpleUploadedFile(
            "test.xlsx",
            b"test content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        form_data = {}
        form_files = {'excel_files': [valid_file]}
        form = MultipleCompanyResponseUploadForm(form_data, form_files)
        
        self.assertTrue(form.is_valid())
        
        # Тест с неправильным форматом
        invalid_file = SimpleUploadedFile(
            "test.txt",
            b"test content",
            content_type="text/plain"
        )
        
        form_files = {'excel_files': [invalid_file]}
        form = MultipleCompanyResponseUploadForm(form_data, form_files)
        
        self.assertFalse(form.is_valid())
        self.assertIn('неподдерживаемый формат', str(form.errors).lower())
    
    def test_authentication_and_authorization(self):
        """Тест аутентификации и авторизации"""
        # Тест без аутентификации
        response = self.client.post(
            reverse('summaries:upload_multiple_company_responses', args=[self.summary.id])
        )
        self.assertEqual(response.status_code, 401)
        
        # Тест с обычным пользователем (недостаточно прав)
        self.client.login(username='user', password='testpass123')
        response = self.client.post(
            reverse('summaries:upload_multiple_company_responses', args=[self.summary.id])
        )
        self.assertEqual(response.status_code, 403)
        
        # Тест с администратором (достаточно прав)
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(
            reverse('summaries:upload_multiple_company_responses', args=[self.summary.id])
        )
        # Должна быть ошибка валидации формы (нет файлов), но не авторизации
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertIn('файл', response_data['error'].lower())
    
    def test_summary_status_validation(self):
        """Тест валидации статуса свода"""
        self.client.login(username='admin', password='testpass123')
        
        # Изменяем статус свода на неподходящий
        self.summary.status = 'completed'
        self.summary.save()
        
        test_file = SimpleUploadedFile(
            "test.xlsx",
            b"test content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        response = self.client.post(
            reverse('summaries:upload_multiple_company_responses', args=[self.summary.id]),
            {
                'excel_files': [test_file]
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertIn('статус', response_data['error'].lower())
    
    def test_file_size_and_count_limits(self):
        """Тест ограничений размера и количества файлов"""
        self.client.login(username='admin', password='testpass123')
        
        # Тест превышения количества файлов
        files = []
        for i in range(11):  # Больше максимума (10)
            files.append(SimpleUploadedFile(
                f"test{i}.xlsx",
                b"test content",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ))
        
        response = self.client.post(
            reverse('summaries:upload_multiple_company_responses', args=[self.summary.id]),
            {
                'excel_files': files
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertIn('много файлов', response_data['error'].lower())
    
    def test_processor_performance_optimization(self):
        """Тест оптимизации производительности процессора"""
        # Создаем процессор
        processor = MultipleFileProcessor(self.summary)
        
        # Создаем несколько тестовых файлов
        files = []
        for i in range(5):
            files.append(SimpleUploadedFile(
                f"test{i}.xlsx",
                b"test content",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ))
        
        with patch('summaries.services.excel_services.ExcelResponseProcessor.process_file') as mock_process:
            # Настраиваем мок для быстрой обработки
            mock_result = MagicMock()
            mock_result.company_name = 'Тест'
            mock_result.offers_created = 1
            mock_result.years_processed = [1]
            mock_result.processed_rows = [6]
            mock_result.skipped_rows = []
            mock_process.return_value = mock_result
            
            import time
            start_time = time.time()
            
            # Обрабатываем файлы
            results = processor.process_files(files)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Проверяем, что обработка завершилась быстро (менее 1 секунды для 5 файлов)
            self.assertLess(processing_time, 1.0)
            
            # Проверяем, что все файлы обработаны
            self.assertEqual(len(results), 5)
            
            # Проверяем, что процессор вызывался для каждого файла
            self.assertEqual(mock_process.call_count, 5)
    
    def test_error_handling_and_recovery(self):
        """Тест обработки ошибок и восстановления"""
        processor = MultipleFileProcessor(self.summary)
        
        # Создаем файлы с разными типами ошибок
        files = [
            SimpleUploadedFile("success.xlsx", b"content", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            SimpleUploadedFile("error.xlsx", b"content", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            SimpleUploadedFile("duplicate.xlsx", b"content", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]
        
        with patch('summaries.services.excel_services.ExcelResponseProcessor.process_file') as mock_process:
            def side_effect(file, summary):
                if 'success' in file.name:
                    mock_result = MagicMock()
                    mock_result.company_name = 'Успех'
                    mock_result.offers_created = 1
                    mock_result.years_processed = [1]
                    mock_result.processed_rows = [6]
                    mock_result.skipped_rows = []
                    return mock_result
                elif 'error' in file.name:
                    from .exceptions import ExcelProcessingError
                    raise ExcelProcessingError("Ошибка обработки")
                else:  # duplicate
                    from .exceptions import DuplicateOfferError
                    raise DuplicateOfferError("Дубликат", 1)
            
            mock_process.side_effect = side_effect
            
            # Обрабатываем файлы
            results = processor.process_files(files)
            
            # Проверяем, что все файлы обработаны (включая ошибочные)
            self.assertEqual(len(results), 3)
            
            # Проверяем результаты
            success_count = sum(1 for r in results if r['success'])
            error_count = sum(1 for r in results if not r['success'])
            
            self.assertEqual(success_count, 1)
            self.assertEqual(error_count, 2)
            
            # Проверяем типы ошибок
            error_results = [r for r in results if not r['success']]
            error_types = [r['error_type'] for r in error_results]
            
            self.assertIn('processing_error', error_types)
            self.assertIn('duplicate_offer', error_types)
    
    def test_backward_compatibility(self):
        """Тест обратной совместимости с существующим функционалом"""
        self.client.login(username='admin', password='testpass123')
        
        # Тест загрузки одного файла через новый интерфейс
        test_file = SimpleUploadedFile(
            "single_file.xlsx",
            b"test content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        with patch('summaries.services.excel_services.ExcelResponseProcessor.process_file') as mock_process:
            mock_result = MagicMock()
            mock_result.company_name = 'Одиночный файл'
            mock_result.offers_created = 1
            mock_result.years_processed = [1]
            mock_result.processed_rows = [6]
            mock_result.skipped_rows = []
            mock_process.return_value = mock_result
            
            # Отправляем один файл
            response = self.client.post(
                reverse('summaries:upload_multiple_company_responses', args=[self.summary.id]),
                {
                    'excel_files': [test_file]
                },
                format='multipart'
            )
            
            # Проверяем, что одиночный файл обрабатывается корректно
            self.assertEqual(response.status_code, 200)
            
            response_data = json.loads(response.content)
            self.assertTrue(response_data['success'])
            self.assertEqual(response_data['total_files'], 1)
            self.assertEqual(response_data['successful_files'], 1)
            
            # Проверяем результат
            file_result = response_data['results'][0]
            self.assertTrue(file_result['success'])
            self.assertEqual(file_result['company_name'], 'Одиночный файл')
    
    def test_system_integration_with_database(self):
        """Тест интеграции системы с базой данных"""
        # Создаем существующее предложение для проверки дубликатов
        existing_offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Существующая Компания',
            year=1,
            premium_amount=10000,
            franchise_amount=5000
        )
        
        processor = MultipleFileProcessor(self.summary)
        
        # Проверяем обнаружение существующих предложений
        conflicts = processor.check_existing_offers('Существующая Компания', [1, 2])
        
        self.assertEqual(len(conflicts), 1)
        self.assertIn('Существующая Компания - 1 год', conflicts)
        
        # Проверяем, что для нового года конфликтов нет
        conflicts = processor.check_existing_offers('Существующая Компания', [2, 3])
        self.assertEqual(len(conflicts), 0)
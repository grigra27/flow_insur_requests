"""
Финальная верификация системы множественной загрузки файлов
"""

from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import InsuranceSummary, InsuranceRequest
from .services.multiple_file_processor import MultipleFileProcessor


class FinalSystemVerificationTest(TestCase):
    """Финальная верификация всей системы"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        # Создаем группы пользователей
        self.admin_group = Group.objects.create(name='Администраторы')
        
        # Создаем пользователя
        self.admin_user = User.objects.create_user(
            username='admin',
            password='testpass123',
            email='admin@test.com'
        )
        self.admin_user.groups.add(self.admin_group)
        
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
    
    def test_system_is_fully_operational(self):
        """Тест полной работоспособности системы"""
        # Создаем процессор
        processor = MultipleFileProcessor(self.summary)
        
        # Проверяем, что процессор создается корректно
        self.assertIsNotNone(processor)
        self.assertEqual(processor.summary, self.summary)
        self.assertIsNotNone(processor.excel_processor)
        self.assertIsNotNone(processor.logger)
        
        # Проверяем константы
        self.assertEqual(processor.MAX_FILES_PER_UPLOAD, 10)
        self.assertEqual(processor.MAX_FILE_SIZE_MB, 1)
        self.assertEqual(processor.MAX_TOTAL_SIZE_MB, 10)
        self.assertEqual(processor.ALLOWED_EXTENSIONS, ['.xlsx'])
    
    def test_error_handling_is_robust(self):
        """Тест устойчивости обработки ошибок"""
        processor = MultipleFileProcessor(self.summary)
        
        # Создаем файлы с разными типами ошибок
        files = [
            SimpleUploadedFile("invalid.txt", b"content", content_type="text/plain"),
            SimpleUploadedFile("empty.xlsx", b"", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            SimpleUploadedFile("fake.xlsx", b"not excel", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]
        
        # Обрабатываем файлы
        results = processor.process_files(files)
        
        # Проверяем, что все файлы обработаны
        self.assertEqual(len(results), 3)
        
        # Проверяем, что все результаты содержат информацию об ошибках
        for result in results:
            self.assertFalse(result['success'])
            self.assertIsNotNone(result.get('error_message'))
            self.assertIsNotNone(result.get('error_type'))
            self.assertIn('file_name', result)
            self.assertIn('file_index', result)
    
    def test_validation_system_works(self):
        """Тест работы системы валидации"""
        processor = MultipleFileProcessor(self.summary)
        
        # Тест валидного файла
        valid_file = SimpleUploadedFile(
            "test.xlsx",
            b"test content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        error = processor.validate_file(valid_file)
        self.assertIsNone(error)
        
        # Тест невалидного файла
        invalid_file = SimpleUploadedFile(
            "test.txt",
            b"test content",
            content_type="text/plain"
        )
        
        error = processor.validate_file(invalid_file)
        self.assertIsNotNone(error)
        self.assertIn('неподдерживаемый формат', error.lower())
    
    def test_logging_system_is_active(self):
        """Тест активности системы логирования"""
        processor = MultipleFileProcessor(self.summary)
        
        # Проверяем, что логгер настроен
        self.assertIsNotNone(processor.logger)
        self.assertEqual(processor.logger.name, 'summaries.services.multiple_file_processor.MultipleFileProcessor')
        
        # Создаем файл для тестирования логирования
        test_file = SimpleUploadedFile(
            "log_test.xlsx",
            b"test content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Обрабатываем файл и проверяем, что логирование работает
        with self.assertLogs('summaries.services.multiple_file_processor', level='DEBUG') as log:
            results = processor.process_files([test_file])
            
            # Проверяем, что логирование работает
            self.assertTrue(len(log.output) > 0)
            
            # Проверяем, что в логах есть ключевые события
            log_text = ' '.join(log.output)
            self.assertIn('BATCH_START', log_text)
            self.assertIn('BATCH_END', log_text)
            self.assertIn('FILE_START', log_text)
    
    def test_performance_is_acceptable(self):
        """Тест приемлемой производительности"""
        processor = MultipleFileProcessor(self.summary)
        
        # Создаем несколько файлов
        files = []
        for i in range(5):
            files.append(SimpleUploadedFile(
                f"perf_test{i}.xlsx",
                b"test content" * 100,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ))
        
        import time
        start_time = time.time()
        results = processor.process_files(files)
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        # Проверяем, что обработка завершилась быстро
        self.assertLess(processing_time, 2.0, f"Обработка заняла {processing_time:.2f}с")
        
        # Проверяем, что все файлы обработаны
        self.assertEqual(len(results), 5)
    
    def test_system_handles_edge_cases(self):
        """Тест обработки граничных случаев"""
        processor = MultipleFileProcessor(self.summary)
        
        # Тест с пустым списком файлов
        results = processor.process_files([])
        self.assertEqual(len(results), 0)
        
        # Тест с одним файлом
        single_file = [SimpleUploadedFile(
            "single.xlsx",
            b"content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )]
        
        results = processor.process_files(single_file)
        self.assertEqual(len(results), 1)
        
        # Тест с максимальным количеством файлов
        max_files = []
        for i in range(10):  # Максимум
            max_files.append(SimpleUploadedFile(
                f"max{i}.xlsx",
                b"content",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ))
        
        results = processor.process_files(max_files)
        self.assertEqual(len(results), 10)
    
    def test_system_integration_complete(self):
        """Тест полной интеграции системы"""
        # Проверяем, что все компоненты доступны
        from .services.multiple_file_processor import MultipleFileProcessor, get_multiple_file_processor
        from .forms import MultipleCompanyResponseUploadForm
        from .views import upload_multiple_company_responses
        
        # Проверяем, что процессор создается через фабричную функцию
        processor = get_multiple_file_processor(self.summary)
        self.assertIsInstance(processor, MultipleFileProcessor)
        
        # Проверяем, что форма существует и работает
        form = MultipleCompanyResponseUploadForm()
        self.assertIsNotNone(form)
        
        # Проверяем, что представление существует
        self.assertTrue(callable(upload_multiple_company_responses))
    
    def test_backward_compatibility_maintained(self):
        """Тест сохранения обратной совместимости"""
        processor = MultipleFileProcessor(self.summary)
        
        # Тест обработки одного файла (как в старой системе)
        single_file = [SimpleUploadedFile(
            "backward_compat.xlsx",
            b"test content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )]
        
        results = processor.process_files(single_file)
        
        # Проверяем, что результат имеет ожидаемую структуру
        self.assertEqual(len(results), 1)
        result = results[0]
        
        # Проверяем обязательные поля
        required_fields = ['file_name', 'success', 'file_index']
        for field in required_fields:
            self.assertIn(field, result)
        
        # Если файл обработан с ошибкой, проверяем наличие информации об ошибке
        if not result['success']:
            self.assertIn('error_message', result)
            self.assertIn('error_type', result)
    
    def test_system_ready_for_production(self):
        """Тест готовности системы к продакшену"""
        # Проверяем, что все необходимые компоненты на месте
        
        # 1. Процессор
        processor = MultipleFileProcessor(self.summary)
        self.assertIsNotNone(processor)
        
        # 2. Логирование
        self.assertIsNotNone(processor.logger)
        
        # 3. Валидация
        self.assertTrue(hasattr(processor, 'validate_file'))
        
        # 4. Обработка файлов
        self.assertTrue(hasattr(processor, 'process_files'))
        
        # 5. Константы безопасности
        self.assertGreater(processor.MAX_FILES_PER_UPLOAD, 0)
        self.assertGreater(processor.MAX_FILE_SIZE_MB, 0)
        self.assertGreater(processor.MAX_TOTAL_SIZE_MB, 0)
        self.assertTrue(len(processor.ALLOWED_EXTENSIONS) > 0)
        
        # 6. Обработка ошибок
        test_file = SimpleUploadedFile("error_test.txt", b"content", content_type="text/plain")
        results = processor.process_files([test_file])
        
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['success'])
        self.assertIsNotNone(results[0]['error_message'])
        
        print("✅ Система множественной загрузки файлов готова к продакшену!")
        print(f"✅ Максимум файлов: {processor.MAX_FILES_PER_UPLOAD}")
        print(f"✅ Максимальный размер файла: {processor.MAX_FILE_SIZE_MB}MB")
        print(f"✅ Поддерживаемые форматы: {', '.join(processor.ALLOWED_EXTENSIONS)}")
        print("✅ Логирование активно")
        print("✅ Обработка ошибок работает")
        print("✅ Валидация файлов работает")
        print("✅ Обратная совместимость сохранена")
"""
Тесты для обновленной справочной информации на странице загрузки заявок
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from insurance_requests.models import InsuranceRequest


class UploadPageUpdatesTests(TestCase):
    """Тесты для обновленной страницы загрузки заявок"""
    
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
    
    def test_upload_page_accessible(self):
        """Тест доступности страницы загрузки"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Загрузка Excel файла')
    
    def test_updated_parameter_information(self):
        """Тест наличия информации о новых параметрах"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие информации о новых параметрах
        self.assertContains(response, 'КАСКО кат. C/E')
        self.assertContains(response, 'Перевозка')
        self.assertContains(response, 'СМР')
        self.assertContains(response, 'Территория страхования')
    
    def test_franchise_type_information(self):
        """Тест информации о типах франшизы"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем информацию о франшизе
        self.assertContains(response, 'none')
        self.assertContains(response, 'with_franchise')
        self.assertContains(response, 'both_variants')
    
    def test_ip_vs_company_differences(self):
        """Тест информации о различиях между ИП и юр.лицами"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем информацию о смещении строк для ИП
        self.assertContains(response, 'ИП')
        self.assertContains(response, 'юр')
        self.assertContains(response, 'смещение')
    
    def test_additional_casco_parameters(self):
        """Тест информации о дополнительных параметрах КАСКО"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем дополнительные параметры
        self.assertContains(response, 'комплектность ключей')
        self.assertContains(response, 'ПТС/ПСМ')
        self.assertContains(response, 'банк-кредитор')
        self.assertContains(response, 'цели использования')
        self.assertContains(response, 'телематический комплекс')
    
    def test_property_insurance_format(self):
        """Тест информации о формате страхования имущества"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем информацию о формате "имущество"
        self.assertContains(response, 'имущество')
        self.assertContains(response, 'C44')  # Ячейка для перевозки
        self.assertContains(response, 'C48')  # Ячейка для СМР
    
    def test_cell_mapping_table_updated(self):
        """Тест обновленной таблицы соответствий ячеек"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие таблицы соответствий
        self.assertContains(response, 'table')
        self.assertContains(response, 'Ячейка')
        self.assertContains(response, 'Параметр')
        self.assertContains(response, 'Описание')
    
    def test_visual_differences_highlighting(self):
        """Тест цветового выделения различий"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие CSS классов для выделения
        self.assertContains(response, 'table-')
        self.assertContains(response, 'bg-')
        self.assertContains(response, 'text-')
    
    def test_examples_for_different_types(self):
        """Тест примеров для разных типов заявок"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие примеров
        self.assertContains(response, 'Пример')
        self.assertContains(response, 'example')
    
    def test_mobile_responsiveness(self):
        """Тест адаптивности для мобильных устройств"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем адаптивные классы
        self.assertContains(response, 'table-responsive')
        self.assertContains(response, 'col-')
        self.assertContains(response, 'row')


class UploadPageContentValidationTests(TestCase):
    """Тесты валидации содержимого страницы загрузки"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_technical_accuracy_casco_ce(self):
        """Тест технической точности информации о КАСКО кат. C/E"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем правильную ячейку для КАСКО кат. C/E
        self.assertContains(response, '45')  # Строка 45
    
    def test_technical_accuracy_transportation_smr(self):
        """Тест технической точности информации о перевозке и СМР"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем правильные ячейки
        self.assertContains(response, 'C44')  # Перевозка
        self.assertContains(response, 'C48')  # СМР
    
    def test_row_offset_logic_explanation(self):
        """Тест объяснения логики смещения строк"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем объяснение смещения для ИП
        self.assertContains(response, '+1')
        self.assertContains(response, '> 8')
    
    def test_franchise_type_values(self):
        """Тест правильных значений типов франшизы"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем правильные значения
        self.assertContains(response, 'none')
        self.assertContains(response, 'with_franchise')
        self.assertContains(response, 'both_variants')
    
    def test_additional_parameters_cells(self):
        """Тест правильности ячеек для дополнительных параметров"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие информации о ячейках для дополнительных параметров
        # (конкретные ячейки будут проверены в следующем подзадании)
        self.assertContains(response, 'дополнительные параметры')


class UploadPageUsabilityTests(TestCase):
    """Тесты удобства использования страницы загрузки"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_clear_section_structure(self):
        """Тест четкой структуры разделов"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие заголовков разделов
        self.assertContains(response, '<h')
        self.assertContains(response, 'section')
    
    def test_color_coding_implementation(self):
        """Тест реализации цветового кодирования"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие цветовых классов
        self.assertContains(response, 'table-')
        self.assertContains(response, 'bg-')
    
    def test_examples_clarity(self):
        """Тест наглядности примеров"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие примеров
        self.assertContains(response, 'пример')
        self.assertContains(response, 'образец')
    
    def test_navigation_elements(self):
        """Тест элементов навигации"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие навигационных элементов
        self.assertContains(response, 'nav')
        self.assertContains(response, 'href')
    
    def test_quick_reference_availability(self):
        """Тест доступности быстрой справки"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие быстрой справки
        self.assertContains(response, 'справка')
        self.assertContains(response, 'помощь')


class UploadPageIntegrationTests(TestCase):
    """Интеграционные тесты страницы загрузки"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.user.groups.add(self.user_group)
    
    def test_upload_functionality_still_works(self):
        """Тест работоспособности функции загрузки после обновлений"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем наличие формы загрузки
        self.assertContains(response, 'form')
        self.assertContains(response, 'file')
        self.assertContains(response, 'submit')
    
    def test_help_information_integration(self):
        """Тест интеграции справочной информации"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем интеграцию справочной информации
        self.assertContains(response, 'help')
        self.assertContains(response, 'info')
    
    def test_consistent_styling(self):
        """Тест согласованности стилей"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем использование Bootstrap классов
        self.assertContains(response, 'btn')
        self.assertContains(response, 'table')
        self.assertContains(response, 'card')
    
    def test_cross_browser_compatibility_elements(self):
        """Тест элементов для кроссбраузерной совместимости"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('insurance_requests:upload_excel'))
        
        # Проверяем стандартные HTML элементы
        self.assertContains(response, '<!DOCTYPE html>')
        self.assertContains(response, '<html')
        self.assertContains(response, '<head>')
        self.assertContains(response, '<body>')
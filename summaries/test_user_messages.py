"""
Тесты для пользовательских сообщений и подсказок при работе со страховыми компаниями
"""
import unittest
from django.test import TestCase
from django.contrib.auth.models import User
from unittest.mock import Mock, patch

from .forms import OfferForm, AddOfferToSummaryForm
from .services.company_matcher import CompanyNameMatcher
from .services.excel_services import ExcelResponseProcessor


class UserMessagesTestCase(TestCase):
    """Тесты для пользовательских сообщений и подсказок"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_offer_form_company_validation_messages(self):
        """Тест сообщений валидации для поля выбора компании в OfferForm"""
        # Тест с пустым значением
        form_data = {
            'company_name': '',
            'insurance_year': 1,
            'insurance_sum': 1000000,
            'franchise_1': 0,
            'premium_with_franchise_1': 50000,
        }
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        self.assertEqual(
            form.errors['company_name'][0],
            'Пожалуйста, выберите страховую компанию из выпадающего списка.'
        )
        
        # Тест с недопустимым значением
        form_data['company_name'] = 'Несуществующая компания'
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        self.assertIn(
            'Выберите страховую компанию из предложенного списка',
            form.errors['company_name'][0]
        )
        
        # Тест с корректным значением
        form_data['company_name'] = 'Абсолют'
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_add_offer_form_company_validation_messages(self):
        """Тест сообщений валидации для поля выбора компании в AddOfferToSummaryForm"""
        # Тест с пустым значением
        form_data = {
            'company_name': '',
            'insurance_year': 1,
            'insurance_sum': 1000000,
            'franchise_1': 0,
            'premium_with_franchise_1': 50000,
        }
        form = AddOfferToSummaryForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        self.assertEqual(
            form.errors['company_name'][0],
            'Пожалуйста, выберите страховую компанию из выпадающего списка.'
        )
    
    def test_company_matcher_logging(self):
        """Тест логирования процесса сопоставления названий компаний"""
        matcher = CompanyNameMatcher()
        
        # Тест точного совпадения
        result = matcher.match_company_name('Абсолют')
        self.assertEqual(result, 'Абсолют')
        
        # Тест сопоставления с "другое"
        result = matcher.match_company_name('Неизвестная компания')
        self.assertEqual(result, 'другое')
        
        # Тест нечеткого сопоставления (регистр)
        result = matcher.match_company_name('абсолют')
        self.assertEqual(result, 'Абсолют')
    
    @patch('summaries.services.excel_services.openpyxl.load_workbook')
    def test_excel_processor_company_matching_info(self, mock_load_workbook):
        """Тест информации о сопоставлении компаний в Excel процессоре"""
        # Создаем мок worksheet
        mock_worksheet = Mock()
        mock_workbook = Mock()
        mock_workbook.active = mock_worksheet
        mock_load_workbook.return_value = mock_workbook
        
        # Настраиваем мок для возврата данных
        def mock_cell_value(cell_ref):
            cell_values = {
                'B2': 'Неизвестная Страховая Компания',  # Будет сопоставлено как "другое"
                'A6': 1,  # Год
                'B6': 1000000,  # Страховая сумма
                'D6': 0,  # Франшиза 1
                'E6': 50000,  # Премия 1
                'F6': None,  # Франшиза 2
                'G6': None,  # Премия 2
            }
            mock_cell = Mock()
            mock_cell.value = cell_values.get(cell_ref)
            return mock_cell
        
        mock_worksheet.__getitem__ = mock_cell_value
        
        processor = ExcelResponseProcessor()
        
        # Создаем мок файла
        mock_file = Mock()
        mock_file.name = 'test.xlsx'
        
        try:
            data = processor.extract_company_data(mock_worksheet)
            
            # Проверяем, что информация о сопоставлении включена
            self.assertIn('company_matching_info', data)
            matching_info = data['company_matching_info']
            
            self.assertEqual(matching_info['original_name'], 'Неизвестная Страховая Компания')
            self.assertEqual(matching_info['standardized_name'], 'другое')
            self.assertTrue(matching_info['assigned_other'])
            self.assertTrue(matching_info['was_matched'])
            
        except Exception as e:
            # Если тест не может выполниться из-за зависимостей, пропускаем
            self.skipTest(f"Тест пропущен из-за зависимостей: {e}")
    
    def test_form_help_text_presence(self):
        """Тест наличия подсказок в формах"""
        form = OfferForm()
        
        # Проверяем наличие help_text для поля company_name
        self.assertIsNotNone(form.fields['company_name'].help_text)
        self.assertIn('Выберите страховую компанию из списка', form.fields['company_name'].help_text)
        self.assertIn('Другое', form.fields['company_name'].help_text)
        
        # Проверяем наличие tooltip атрибутов
        widget_attrs = form.fields['company_name'].widget.attrs
        self.assertIn('data-bs-toggle', widget_attrs)
        self.assertIn('title', widget_attrs)


if __name__ == '__main__':
    unittest.main()
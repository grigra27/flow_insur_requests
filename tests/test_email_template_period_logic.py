"""
Тесты для стандартизированной логики периода страхования в email шаблонах
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from django.test import TestCase
from django.utils import timezone
import pytz

from core.templates import EmailTemplateGenerator


class TestEmailTemplatePeriodLogic(TestCase):
    """Тесты для стандартизированной логики определения периода страхования в email шаблонах"""
    
    def setUp(self):
        """Настройка тестов"""
        self.generator = EmailTemplateGenerator()
    
    def test_standardized_period_format_one_year(self):
        """Тест обработки стандартизированного формата периода '1 год'"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        email_body = self.generator.generate_email_body(data)
        
        # Проверяем, что используется стандартизированный формат
        self.assertIn('Необходимый период страхования: 1 год', email_body)
    
    def test_standardized_period_format_full_lease_term(self):
        """Тест обработки стандартизированного формата периода 'на весь срок лизинга'"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        email_body = self.generator.generate_email_body(data)
        
        # Проверяем, что используется стандартизированный формат
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
    
    def test_empty_period_fallback(self):
        """Тест fallback когда нет данных о периоде"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': '',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        email_body = self.generator.generate_email_body(data)
        
        # Проверяем, что используется fallback
        self.assertIn('Необходимый период страхования: не указан', email_body)
    
    def test_format_insurance_period_text_standardized_format(self):
        """Тест метода _format_insurance_period_text со стандартизированным форматом"""
        # Тест с "1 год"
        data = {'insurance_period': '1 год'}
        result = self.generator._format_insurance_period_text(data)
        self.assertEqual(result, '1 год')
        
        # Тест с "на весь срок лизинга"
        data = {'insurance_period': 'на весь срок лизинга'}
        result = self.generator._format_insurance_period_text(data)
        self.assertEqual(result, 'на весь срок лизинга')
        
        # Тест с пустыми данными
        data = {'insurance_period': ''}
        result = self.generator._format_insurance_period_text(data)
        self.assertEqual(result, 'не указан')
    
    def test_template_data_contains_period_field(self):
        """Тест что template_data содержит поле insurance_period_text"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
        }
        
        template_data = self.generator._prepare_template_data(data)
        
        # Проверяем, что поле присутствует
        self.assertIn('insurance_period_text', template_data)
        self.assertEqual(template_data['insurance_period_text'], '1 год')
    
    def test_email_generation_with_all_features(self):
        """Тест генерации email со стандартизированным периодом и всеми дополнительными параметрами"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
            'has_franchise': True,
            'has_installment': True,
            'has_autostart': True,
            'has_casco_ce': True,
        }
        
        email_body = self.generator.generate_email_body(data)
        
        # Проверяем основные элементы
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
        self.assertIn('Обратите внимание, требуется тариф с франшизой', email_body)
        self.assertIn('Обратите внимание, требуется рассрочка платежа', email_body)
        self.assertIn('Обратите внимание, у предмета лизинга имеется автозапуск', email_body)
        self.assertIn('Обратите внимание, что лизинговое имущество относится к категории C/E', email_body)
    
    def test_subject_generation_unchanged(self):
        """Тест что генерация темы письма не изменилась"""
        data = {
            'dfa_number': 'ДФА-123',
            'branch': 'Москва',
            'vehicle_info': 'Toyota Camry',
            'insurance_period': '1 год',
        }
        
        subject = self.generator.generate_subject(data)
        expected = "ДФА-123 - Москва - Toyota Camry - 1"
        
        self.assertEqual(subject, expected)
    
    def test_response_deadline_formatting_unchanged(self):
        """Тест что форматирование срока ответа не изменилось"""
        # Тест с строковым значением (уже отформатировано)
        data = {
            'response_deadline': '14:30 15.01.2024 г.',
            'insurance_period': '1 год',
        }
        
        result = self.generator._format_response_deadline_for_email(data)
        self.assertEqual(result, '14:30 15.01.2024 г.')
        
        # Тест с пустым значением
        data = {
            'response_deadline': None,
            'insurance_period': '1 год',
        }
        
        result = self.generator._format_response_deadline_for_email(data)
        self.assertEqual(result, '[дата не указана]')


if __name__ == '__main__':
    unittest.main()
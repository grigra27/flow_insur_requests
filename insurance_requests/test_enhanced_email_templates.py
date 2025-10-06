"""
Tests for enhanced email templates with insurance type descriptions and date formatting
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta
from django.utils import timezone
import pytz

from core.templates import EmailTemplateGenerator
from .models import InsuranceRequest
from django.contrib.auth.models import User


class InsuranceTypeDescriptionMappingTests(TestCase):
    """Tests for insurance type description mapping"""
    
    def setUp(self):
        """Set up test data"""
        self.template_generator = EmailTemplateGenerator()
    
    def test_insurance_type_descriptions_mapping_exists(self):
        """Test that INSURANCE_TYPE_DESCRIPTIONS mapping exists and contains all types"""
        descriptions = self.template_generator.INSURANCE_TYPE_DESCRIPTIONS
        
        # Check that all expected types are mapped
        expected_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
        for insurance_type in expected_types:
            self.assertIn(insurance_type, descriptions)
    
    def test_kasko_description_mapping(self):
        """Test КАСКО description mapping"""
        description = self.template_generator._get_insurance_type_description('КАСКО')
        self.assertEqual(description, 'страхование каско по условиям клиента')
    
    def test_special_equipment_description_mapping(self):
        """Test special equipment description mapping"""
        description = self.template_generator._get_insurance_type_description('страхование спецтехники')
        self.assertEqual(description, 'спецтезника под клиента')
    
    def test_property_insurance_description_mapping(self):
        """Test property insurance description mapping"""
        description = self.template_generator._get_insurance_type_description('страхование имущества')
        self.assertEqual(description, 'клиентское имузество')
    
    def test_other_insurance_description_mapping(self):
        """Test other insurance description mapping"""
        description = self.template_generator._get_insurance_type_description('другое')
        self.assertEqual(description, 'разная другая фигня')
    
    def test_unknown_insurance_type_fallback(self):
        """Test fallback for unknown insurance types"""
        unknown_type = 'неизвестный тип'
        description = self.template_generator._get_insurance_type_description(unknown_type)
        self.assertEqual(description, unknown_type)  # Should return original type as fallback
    
    def test_empty_insurance_type_fallback(self):
        """Test fallback for empty insurance type"""
        description = self.template_generator._get_insurance_type_description('')
        self.assertEqual(description, '')
    
    def test_none_insurance_type_fallback(self):
        """Test fallback for None insurance type"""
        description = self.template_generator._get_insurance_type_description(None)
        self.assertEqual(description, None)


class EmailGenerationWithEnhancedDescriptionsTests(TestCase):
    """Tests for email generation with enhanced insurance type descriptions"""
    
    def setUp(self):
        """Set up test data"""
        self.template_generator = EmailTemplateGenerator()
        self.base_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_period': '12 месяцев',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'response_deadline': 'до 15:00'
        }
    
    def test_email_generation_with_kasko_description(self):
        """Test email generation with КАСКО enhanced description"""
        data = self.base_data.copy()
        data['insurance_type'] = 'КАСКО'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain enhanced description, not simple type name
        self.assertIn('страхование каско по условиям клиента', email_body)
        self.assertNotIn('КАСКО', email_body)  # Simple type should not appear
    
    def test_email_generation_with_special_equipment_description(self):
        """Test email generation with special equipment enhanced description"""
        data = self.base_data.copy()
        data['insurance_type'] = 'страхование спецтехники'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain enhanced description
        self.assertIn('спецтезника под клиента', email_body)
        self.assertNotIn('страхование спецтехники', email_body)  # Simple type should not appear
    
    def test_email_generation_with_property_insurance_description(self):
        """Test email generation with property insurance enhanced description"""
        data = self.base_data.copy()
        data['insurance_type'] = 'страхование имущества'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain enhanced description
        self.assertIn('клиентское имузество', email_body)
        self.assertNotIn('страхование имущества', email_body)  # Simple type should not appear
    
    def test_email_generation_with_other_insurance_description(self):
        """Test email generation with other insurance enhanced description"""
        data = self.base_data.copy()
        data['insurance_type'] = 'другое'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain enhanced description
        self.assertIn('разная другая фигня', email_body)
        self.assertNotIn('другое', email_body)  # Simple type should not appear
    
    def test_email_generation_with_unknown_type_fallback(self):
        """Test email generation with unknown insurance type uses fallback"""
        data = self.base_data.copy()
        data['insurance_type'] = 'неизвестный тип'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain original type as fallback
        self.assertIn('неизвестный тип', email_body)
    
    def test_email_generation_without_insurance_type(self):
        """Test email generation without insurance type uses default"""
        data = self.base_data.copy()
        # Don't set insurance_type
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should use default КАСКО description
        self.assertIn('страхование каско по условиям клиента', email_body)
    
    def test_template_data_preparation_includes_enhanced_description(self):
        """Test that _prepare_template_data includes enhanced description"""
        data = self.base_data.copy()
        data['insurance_type'] = 'страхование имущества'
        
        template_data = self.template_generator._prepare_template_data(data)
        
        self.assertIn('ins_type', template_data)
        self.assertEqual(template_data['ins_type'], 'клиентское имузество')


class StandardizedPeriodEmailTemplatesTests(TestCase):
    """Tests for email templates with standardized insurance periods"""
    
    def setUp(self):
        """Set up test data"""
        self.template_generator = EmailTemplateGenerator()
        self.base_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'response_deadline': 'до 15:00'
        }
    
    def test_email_generation_with_one_year_period(self):
        """Test email generation with '1 год' period"""
        data = self.base_data.copy()
        data['insurance_period'] = '1 год'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain standardized period
        self.assertIn('1 год', email_body)
    
    def test_email_generation_with_full_lease_term_period(self):
        """Test email generation with 'на весь срок лизинга' period"""
        data = self.base_data.copy()
        data['insurance_period'] = 'на весь срок лизинга'
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain standardized period
        self.assertIn('на весь срок лизинга', email_body)
    
    def test_email_generation_with_empty_period(self):
        """Test email generation with empty period"""
        data = self.base_data.copy()
        data['insurance_period'] = ''
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should show period as not specified
        self.assertIn('не указан', email_body)
    
    def test_template_data_includes_standardized_period(self):
        """Test that template data includes standardized period"""
        data = self.base_data.copy()
        data['insurance_period'] = '1 год'
        
        template_data = self.template_generator._prepare_template_data(data)
        
        # Should include standardized period
        self.assertIn('insurance_period_text', template_data)
        self.assertEqual(template_data['insurance_period_text'], '1 год')
    
    def test_template_data_handles_empty_period(self):
        """Test that template data handles empty period properly"""
        data = self.base_data.copy()
        data['insurance_period'] = ''
        
        template_data = self.template_generator._prepare_template_data(data)
        
        # Should include fallback for empty period
        self.assertEqual(template_data['insurance_period_text'], 'не указан')


class ResponseDeadlineFormattingTests(TestCase):
    """Tests for response deadline formatting in email templates"""
    
    def setUp(self):
        """Set up test data"""
        self.template_generator = EmailTemplateGenerator()
        self.base_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
    
    def test_format_response_deadline_with_string(self):
        """Test response deadline formatting with string input"""
        data = self.base_data.copy()
        data['response_deadline'] = 'до 15:00'
        
        formatted = self.template_generator._format_response_deadline_for_email(data)
        self.assertEqual(formatted, 'до 15:00')
    
    def test_format_response_deadline_with_datetime(self):
        """Test response deadline formatting with datetime object"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        test_datetime = moscow_tz.localize(datetime(2024, 12, 25, 15, 30))
        
        data = self.base_data.copy()
        data['response_deadline'] = test_datetime
        
        formatted = self.template_generator._format_response_deadline_for_email(data)
        self.assertEqual(formatted, '25.12.2024 в 15:30')
    
    def test_format_response_deadline_with_none(self):
        """Test response deadline formatting with None"""
        data = self.base_data.copy()
        data['response_deadline'] = None
        
        formatted = self.template_generator._format_response_deadline_for_email(data)
        self.assertEqual(formatted, '[дата не указана]')
    
    def test_format_response_deadline_with_missing_field(self):
        """Test response deadline formatting when field is missing"""
        data = self.base_data.copy()
        # Don't set response_deadline
        
        formatted = self.template_generator._format_response_deadline_for_email(data)
        self.assertEqual(formatted, '[дата не указана]')
    
    @patch('core.templates.logger')
    def test_format_response_deadline_error_handling(self, mock_logger):
        """Test error handling in response deadline formatting"""
        # Create a mock object that will raise an exception
        mock_datetime = MagicMock()
        mock_datetime.astimezone.side_effect = Exception("Test error")
        
        data = self.base_data.copy()
        data['response_deadline'] = mock_datetime
        
        formatted = self.template_generator._format_response_deadline_for_email(data)
        
        # Should log warning and return string representation
        mock_logger.warning.assert_called_once()
        self.assertIsInstance(formatted, str)


class IntegrationEmailTemplateTests(TestCase):
    """Integration tests for complete email template functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.template_generator = EmailTemplateGenerator()
    
    def test_complete_email_generation_with_all_enhancements(self):
        """Test complete email generation with all enhancements"""
        # Create insurance request with all data
        request = InsuranceRequest.objects.create(
            client_name='Complete Test Client',
            inn='9876543210',
            insurance_type='страхование имущества',
            insurance_period='на весь срок лизинга',
            vehicle_info='Complete test property',
            dfa_number='COMPLETE-2024-001',
            branch='Москва',
            has_franchise=True,
            has_installment=True,
            has_autostart=True,
            created_by=self.user
        )
        
        # Generate email
        request_data = request.to_dict()
        email_body = self.template_generator.generate_email_body(request_data)
        
        # Check insurance type is present
        self.assertIn('страхование имущества', email_body)
        
        # Check standardized period formatting
        self.assertIn('на весь срок лизинга', email_body)
        
        # Check conditional texts
        self.assertIn('требуется тариф с франшизой', email_body)
        self.assertIn('требуется рассрочка платежа', email_body)
        self.assertIn('имеется автозапуск', email_body)
        
        # Check other data
        self.assertIn('9876543210', email_body)  # INN
    
    def test_email_generation_with_minimal_data(self):
        """Test email generation with minimal required data"""
        minimal_data = {
            'client_name': 'Minimal Client',
            'inn': '1111111111',
            'insurance_type': 'другое',
        }
        
        email_body = self.template_generator.generate_email_body(minimal_data)
        
        # Should handle missing data gracefully
        self.assertIn('разная другая фигня', email_body)  # Enhanced description
        self.assertIn('1111111111', email_body)  # INN
        self.assertIn('не указан', email_body)  # Missing dates
    
    def test_subject_generation_remains_unchanged(self):
        """Test that subject generation is not affected by enhancements"""
        data = {
            'dfa_number': 'TEST-2024-001',
            'branch': 'Test Branch',
            'vehicle_info': 'Test vehicle information',
        }
        
        subject = self.template_generator.generate_subject(data)
        expected = 'TEST-2024-001 - Test Branch - Test vehicle information - 1'
        self.assertEqual(subject, expected)
    
    def test_all_insurance_types_work_in_email_generation(self):
        """Test that all insurance types work correctly in email generation"""
        base_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_start_date': date(2024, 1, 1),
            'insurance_end_date': date(2024, 12, 31),
        }
        
        test_cases = [
            ('КАСКО', 'страхование каско по условиям клиента'),
            ('страхование спецтехники', 'спецтезника под клиента'),
            ('страхование имущества', 'клиентское имузество'),
            ('другое', 'разная другая фигня'),
        ]
        
        for insurance_type, expected_description in test_cases:
            with self.subTest(insurance_type=insurance_type):
                data = base_data.copy()
                data['insurance_type'] = insurance_type
                
                email_body = self.template_generator.generate_email_body(data)
                self.assertIn(expected_description, email_body)
                # Simple type name should not appear in email
                if insurance_type != expected_description:
                    self.assertNotIn(insurance_type, email_body)
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


class DateFormattingInEmailTemplatesTests(TestCase):
    """Tests for date formatting in email templates"""
    
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
    
    def test_format_date_with_date_object(self):
        """Test _format_date with date object"""
        test_date = date(2024, 12, 25)
        formatted = self.template_generator._format_date(test_date)
        self.assertEqual(formatted, '25.12.2024')
    
    def test_format_date_with_datetime_object(self):
        """Test _format_date with datetime object"""
        test_datetime = datetime(2024, 12, 25, 15, 30, 45)
        formatted = self.template_generator._format_date(test_datetime)
        self.assertEqual(formatted, '25.12.2024')
    
    def test_format_date_with_string(self):
        """Test _format_date with string"""
        test_string = '25.12.2024'
        formatted = self.template_generator._format_date(test_string)
        self.assertEqual(formatted, '25.12.2024')
    
    def test_format_date_with_none(self):
        """Test _format_date with None"""
        formatted = self.template_generator._format_date(None)
        self.assertEqual(formatted, 'не указано')
    
    def test_format_date_with_empty_string(self):
        """Test _format_date with empty string"""
        formatted = self.template_generator._format_date('')
        self.assertEqual(formatted, 'не указано')
    
    def test_format_insurance_period_with_both_dates(self):
        """Test _format_insurance_period with both start and end dates"""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 12, 31)
        
        formatted = self.template_generator._format_insurance_period(start_date, end_date)
        self.assertEqual(formatted, 'с 01.01.2024 по 31.12.2024')
    
    def test_format_insurance_period_with_start_date_only(self):
        """Test _format_insurance_period with start date only"""
        start_date = date(2024, 1, 1)
        end_date = None
        
        formatted = self.template_generator._format_insurance_period(start_date, end_date)
        self.assertEqual(formatted, 'с 01.01.2024 по не указано')
    
    def test_format_insurance_period_with_end_date_only(self):
        """Test _format_insurance_period with end date only"""
        start_date = None
        end_date = date(2024, 12, 31)
        
        formatted = self.template_generator._format_insurance_period(start_date, end_date)
        self.assertEqual(formatted, 'с не указано по 31.12.2024')
    
    def test_format_insurance_period_with_no_dates(self):
        """Test _format_insurance_period with no dates"""
        formatted = self.template_generator._format_insurance_period(None, None)
        self.assertEqual(formatted, 'не указан')
    
    def test_email_generation_with_separate_dates(self):
        """Test email generation uses separate insurance dates"""
        data = self.base_data.copy()
        data['insurance_start_date'] = date(2024, 6, 1)
        data['insurance_end_date'] = date(2025, 6, 1)
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should contain formatted period
        self.assertIn('с 01.06.2024 по 01.06.2025', email_body)
    
    def test_email_generation_with_missing_start_date(self):
        """Test email generation with missing start date"""
        data = self.base_data.copy()
        data['insurance_start_date'] = None
        data['insurance_end_date'] = date(2025, 6, 1)
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should handle missing start date
        self.assertIn('с не указано по 01.06.2025', email_body)
    
    def test_email_generation_with_missing_end_date(self):
        """Test email generation with missing end date"""
        data = self.base_data.copy()
        data['insurance_start_date'] = date(2024, 6, 1)
        data['insurance_end_date'] = None
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should handle missing end date
        self.assertIn('с 01.06.2024 по не указано', email_body)
    
    def test_email_generation_with_no_dates(self):
        """Test email generation with no insurance dates"""
        data = self.base_data.copy()
        data['insurance_start_date'] = None
        data['insurance_end_date'] = None
        
        email_body = self.template_generator.generate_email_body(data)
        
        # Should show period as not specified
        self.assertIn('не указан', email_body)
    
    def test_template_data_includes_separate_date_variables(self):
        """Test that template data includes separate date variables"""
        data = self.base_data.copy()
        data['insurance_start_date'] = date(2024, 3, 15)
        data['insurance_end_date'] = date(2025, 3, 15)
        
        template_data = self.template_generator._prepare_template_data(data)
        
        # Should include separate date variables
        self.assertIn('insurance_start_date', template_data)
        self.assertIn('insurance_end_date', template_data)
        self.assertIn('formatted_period', template_data)
        
        self.assertEqual(template_data['insurance_start_date'], '15.03.2024')
        self.assertEqual(template_data['insurance_end_date'], '15.03.2025')
        self.assertEqual(template_data['formatted_period'], 'с 15.03.2024 по 15.03.2025')
    
    def test_template_data_handles_missing_dates(self):
        """Test that template data handles missing dates properly"""
        data = self.base_data.copy()
        # Don't set insurance dates
        
        template_data = self.template_generator._prepare_template_data(data)
        
        # Should include placeholders for missing dates
        self.assertEqual(template_data['insurance_start_date'], 'не указано')
        self.assertEqual(template_data['insurance_end_date'], 'не указано')
        self.assertEqual(template_data['formatted_period'], 'не указан')


class EmailTemplateBackwardCompatibilityTests(TestCase):
    """Tests for backward compatibility with old insurance period format"""
    
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
    
    def test_format_insurance_period_for_email_with_new_dates(self):
        """Test that new date fields take priority over old insurance_period"""
        data = self.base_data.copy()
        data['insurance_start_date'] = date(2024, 1, 1)
        data['insurance_end_date'] = date(2024, 12, 31)
        data['insurance_period'] = 'старый период'  # Should be ignored
        
        formatted = self.template_generator._format_insurance_period_for_email(data)
        self.assertEqual(formatted, 'с 01.01.2024 по 31.12.2024')
    
    def test_format_insurance_period_for_email_fallback_to_old_field(self):
        """Test fallback to old insurance_period field when new dates are missing"""
        data = self.base_data.copy()
        data['insurance_period'] = 'с 01.01.2024 по 31.12.2024'
        # Don't set new date fields
        
        formatted = self.template_generator._format_insurance_period_for_email(data)
        self.assertEqual(formatted, 'с 01.01.2024 по 31.12.2024')
    
    def test_format_insurance_period_for_email_default_when_no_data(self):
        """Test default value when no date information is available"""
        data = self.base_data.copy()
        # Don't set any date fields
        
        formatted = self.template_generator._format_insurance_period_for_email(data)
        self.assertEqual(formatted, 'с 01.01.2024 по 01.01.2025')
    
    def test_template_data_includes_both_old_and_new_formats(self):
        """Test that template data includes both old and new date formats"""
        data = self.base_data.copy()
        data['insurance_start_date'] = date(2024, 6, 1)
        data['insurance_end_date'] = date(2025, 6, 1)
        
        template_data = self.template_generator._prepare_template_data(data)
        
        # Should include both formats
        self.assertIn('srok', template_data)  # Old format
        self.assertIn('formatted_period', template_data)  # New format
        
        # Both should have the same content when new dates are available
        self.assertEqual(template_data['srok'], 'с 01.06.2024 по 01.06.2025')
        self.assertEqual(template_data['formatted_period'], 'с 01.06.2024 по 01.06.2025')


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
            insurance_start_date=date(2024, 7, 1),
            insurance_end_date=date(2025, 7, 1),
            vehicle_info='Complete test property',
            dfa_number='COMPLETE-2024-001',
            branch='Complete Branch',
            has_franchise=True,
            has_installment=True,
            has_autostart=True,
            created_by=self.user
        )
        
        # Generate email
        request_data = request.to_dict()
        email_body = self.template_generator.generate_email_body(request_data)
        
        # Check enhanced insurance type description
        self.assertIn('клиентское имузество', email_body)
        self.assertNotIn('страхование имущества', email_body)
        
        # Check date formatting
        self.assertIn('с 01.07.2024 по 01.07.2025', email_body)
        
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
"""
Comprehensive tests for standardized insurance period functionality.
Tests model validation, form validation, Excel processing, email templates, and integration workflows.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.utils import timezone
import pytz

from insurance_requests.models import InsuranceRequest
from insurance_requests.forms import InsuranceRequestForm, ExcelUploadForm
from core.excel_utils import ExcelReader
from core.templates import EmailTemplateGenerator


class TestStandardizedPeriodModelValidation(TestCase):
    """Tests for model validation with choices constraint"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
    
    def test_model_accepts_valid_period_choices(self):
        """Test that model accepts only valid standardized period choices"""
        # Test "1 год"
        request1 = InsuranceRequest.objects.create(
            client_name='Test Client 1',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            created_by=self.user
        )
        self.assertEqual(request1.insurance_period, '1 год')
        
        # Test "на весь срок лизинга"
        request2 = InsuranceRequest.objects.create(
            client_name='Test Client 2',
            inn='0987654321',
            insurance_type='КАСКО',
            insurance_period='на весь срок лизинга',
            created_by=self.user
        )
        self.assertEqual(request2.insurance_period, 'на весь срок лизинга')
    
    def test_model_accepts_empty_period(self):
        """Test that model accepts empty insurance period"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',
            created_by=self.user
        )
        self.assertEqual(request.insurance_period, '')
    
    def test_model_to_dict_with_standardized_periods(self):
        """Test that to_dict method handles standardized periods correctly"""
        # Test with "1 год"
        request1 = InsuranceRequest.objects.create(
            client_name='Test Client 1',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            created_by=self.user
        )
        data1 = request1.to_dict()
        self.assertEqual(data1['insurance_period'], '1 год')
        
        # Test with "на весь срок лизинга"
        request2 = InsuranceRequest.objects.create(
            client_name='Test Client 2',
            inn='0987654321',
            insurance_type='КАСКО',
            insurance_period='на весь срок лизинга',
            created_by=self.user
        )
        data2 = request2.to_dict()
        self.assertEqual(data2['insurance_period'], 'на весь срок лизинга')
        
        # Test with empty period - should fallback to "не указан"
        request3 = InsuranceRequest.objects.create(
            client_name='Test Client 3',
            inn='1111111111',
            insurance_type='КАСКО',
            insurance_period='',
            created_by=self.user
        )
        data3 = request3.to_dict()
        self.assertEqual(data3['insurance_period'], 'не указан')
    
    def test_model_choices_constraint(self):
        """Test that model has proper choices constraint defined"""
        field = InsuranceRequest._meta.get_field('insurance_period')
        expected_choices = [
            ('1 год', '1 год'),
            ('на весь срок лизинга', 'на весь срок лизинга'),
        ]
        self.assertEqual(field.choices, expected_choices)


class TestStandardizedPeriodFormValidation(TestCase):
    """Tests for form validation with standardized dropdown"""
    
    def test_form_accepts_valid_period_choices(self):
        """Test that form accepts valid standardized period choices"""
        # Test "1 год"
        form_data1 = {
            'client_name': 'Test Client 1',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Москва'
        }
        form1 = InsuranceRequestForm(data=form_data1)
        self.assertTrue(form1.is_valid(), f"Form errors: {form1.errors}")
        self.assertEqual(form1.cleaned_data['insurance_period'], '1 год')
        
        # Test "на весь срок лизинга"
        form_data2 = {
            'client_name': 'Test Client 2',
            'inn': '0987654321',
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA456',
            'branch': 'Казань'
        }
        form2 = InsuranceRequestForm(data=form_data2)
        self.assertTrue(form2.is_valid(), f"Form errors: {form2.errors}")
        self.assertEqual(form2.cleaned_data['insurance_period'], 'на весь срок лизинга')
    
    def test_form_accepts_empty_period(self):
        """Test that form accepts empty insurance period"""
        form_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Москва'
        }
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        self.assertEqual(form.cleaned_data['insurance_period'], '')
    
    def test_form_rejects_invalid_period_choices(self):
        """Test that form rejects invalid period choices"""
        invalid_periods = [
            'с 01.01.2024 по 31.12.2024',
            '2 года',
            'invalid_period',
            '1 year',
            'на весь срок'
        ]
        
        for invalid_period in invalid_periods:
            form_data = {
                'client_name': 'Test Client',
                'inn': '1234567890',
                'insurance_type': 'КАСКО',
                'insurance_period': invalid_period,
                'vehicle_info': 'Test Vehicle',
                'dfa_number': 'DFA123',
                'branch': 'Москва'
            }
            form = InsuranceRequestForm(data=form_data)
            self.assertFalse(form.is_valid(), f"Form should reject invalid period: {invalid_period}")
            self.assertIn('insurance_period', form.errors)
    
    def test_form_choices_match_model_choices(self):
        """Test that form choices match model choices"""
        form = InsuranceRequestForm()
        form_choices = form.fields['insurance_period'].choices
        model_choices = InsuranceRequest.INSURANCE_PERIOD_CHOICES
        
        # Form has additional empty choice at the beginning
        expected_form_choices = [('', '-- Выберите период --')] + model_choices
        self.assertEqual(form_choices, expected_form_choices)
    
    def test_form_save_with_standardized_period(self):
        """Test that form saves standardized period correctly"""
        user = User.objects.create_user(username='testuser', password='testpass')
        
        form_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Москва'
        }
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save(commit=False)
        instance.created_by = user
        instance.save()
        
        self.assertEqual(instance.insurance_period, '1 год')


class TestStandardizedPeriodExcelProcessing(TestCase):
    """Tests for Excel processing returning only standardized options"""
    
    def setUp(self):
        """Set up test data"""
        self.excel_reader = ExcelReader("dummy_path.xlsx")
    
    def test_determine_insurance_period_openpyxl_returns_standardized_options(self):
        """Test that openpyxl period determination returns only standardized options"""
        mock_sheet = Mock()
        
        # Test N17 with value returns "1 год"
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_openpyxl') as mock_get_cell:
            def mock_get_cell_side_effect(sheet, col, row):
                if col == 'N' and row == 17:
                    return 'X'  # Has value
                elif col == 'N' and row == 18:
                    return None  # Empty
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "1 год")
        
        # Test N18 with value returns "на весь срок лизинга"
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_openpyxl') as mock_get_cell:
            def mock_get_cell_side_effect(sheet, col, row):
                if col == 'N' and row == 17:
                    return None  # Empty
                elif col == 'N' and row == 18:
                    return 'X'  # Has value
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "на весь срок лизинга")
        
        # Test both empty returns empty string
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_openpyxl') as mock_get_cell:
            def mock_get_cell_side_effect(sheet, col, row):
                if col == 'N' and row in [17, 18]:
                    return None  # Both empty
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "")
    
    def test_determine_insurance_period_pandas_returns_standardized_options(self):
        """Test that pandas period determination returns only standardized options"""
        mock_df = Mock()
        
        # Test N17 with value returns "1 год"
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_pandas') as mock_get_cell:
            def mock_get_cell_side_effect(df, row, col):
                if row == 17 and col == 13:  # N17
                    return 'X'  # Has value
                elif row == 18 and col == 13:  # N18
                    return None  # Empty
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_pandas(mock_df)
            self.assertEqual(result, "1 год")
        
        # Test N18 with value returns "на весь срок лизинга"
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_pandas') as mock_get_cell:
            def mock_get_cell_side_effect(df, row, col):
                if row == 17 and col == 13:  # N17
                    return None  # Empty
                elif row == 18 and col == 13:  # N18
                    return 'X'  # Has value
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_pandas(mock_df)
            self.assertEqual(result, "на весь срок лизинга")
        
        # Test both empty returns empty string
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_pandas') as mock_get_cell:
            def mock_get_cell_side_effect(df, row, col):
                if row in [17, 18] and col == 13:  # N17, N18
                    return None  # Both empty
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_pandas(mock_df)
            self.assertEqual(result, "")
    
    def test_excel_processing_handles_whitespace_values(self):
        """Test that Excel processing treats whitespace-only values as empty"""
        mock_sheet = Mock()
        
        # Test whitespace in N17, value in N18
        with patch.object(self.excel_reader, '_get_cell_with_adjustment_openpyxl') as mock_get_cell:
            def mock_get_cell_side_effect(sheet, col, row):
                if col == 'N' and row == 17:
                    return '   '  # Whitespace only
                elif col == 'N' and row == 18:
                    return 'X'  # Has value
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "на весь срок лизинга")  # Should use N18
    
    def test_extract_data_uses_standardized_period_logic(self):
        """Test that extract_data methods use standardized period logic"""
        mock_sheet = Mock()
        
        # Mock all required methods for _extract_data_openpyxl
        with patch.object(self.excel_reader, '_determine_insurance_type_openpyxl', return_value='КАСКО'), \
             patch.object(self.excel_reader, '_determine_insurance_period_openpyxl', return_value='1 год'), \
             patch.object(self.excel_reader, '_get_cell_with_adjustment_openpyxl', return_value=None), \
             patch.object(self.excel_reader, '_find_leasing_object_info_openpyxl', return_value='Test vehicle'), \
             patch.object(self.excel_reader, '_find_dfa_number_openpyxl', return_value='DFA123'), \
             patch.object(self.excel_reader, '_find_branch_openpyxl', return_value='Test branch'), \
             patch('django.utils.timezone.now') as mock_now:
            
            mock_now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            
            result = self.excel_reader._extract_data_openpyxl(mock_sheet)
            
            # Verify standardized period is used
            self.assertEqual(result['insurance_period'], '1 год')
            # Verify no date fields are set
            self.assertNotIn('insurance_start_date', result)
            self.assertNotIn('insurance_end_date', result)


class TestStandardizedPeriodEmailTemplates(TestCase):
    """Tests for email template generation with standardized periods"""
    
    def setUp(self):
        """Set up test data"""
        self.generator = EmailTemplateGenerator()
    
    def test_email_generation_with_one_year_period(self):
        """Test email generation with '1 год' period"""
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
        
        # Verify standardized period is used
        self.assertIn('Необходимый период страхования: 1 год', email_body)
        # Verify no date-based formatting in period context (not in general text)
        # The template contains "с занесением данных" which is unrelated to period formatting
        period_line = [line for line in email_body.split('\n') if 'Необходимый период страхования' in line][0]
        self.assertNotIn('с ', period_line)
        self.assertNotIn(' по ', period_line)
    
    def test_email_generation_with_full_lease_term_period(self):
        """Test email generation with 'на весь срок лизинга' period"""
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
        
        # Verify standardized period is used
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
    
    def test_email_generation_with_empty_period_fallback(self):
        """Test email generation with empty period falls back to 'не указан'"""
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
        
        # Verify fallback is used
        self.assertIn('Необходимый период страхования: не указан', email_body)
    
    def test_format_insurance_period_text_method(self):
        """Test _format_insurance_period_text method with standardized options"""
        # Test "1 год"
        data1 = {'insurance_period': '1 год'}
        result1 = self.generator._format_insurance_period_text(data1)
        self.assertEqual(result1, '1 год')
        
        # Test "на весь срок лизинга"
        data2 = {'insurance_period': 'на весь срок лизинга'}
        result2 = self.generator._format_insurance_period_text(data2)
        self.assertEqual(result2, 'на весь срок лизинга')
        
        # Test empty period
        data3 = {'insurance_period': ''}
        result3 = self.generator._format_insurance_period_text(data3)
        self.assertEqual(result3, 'не указан')
        
        # Test missing period key
        data4 = {}
        result4 = self.generator._format_insurance_period_text(data4)
        self.assertEqual(result4, 'не указан')
        
        # Test whitespace-only period
        data5 = {'insurance_period': '   '}
        result5 = self.generator._format_insurance_period_text(data5)
        self.assertEqual(result5, 'не указан')
    
    def test_template_data_preparation(self):
        """Test that template data preparation includes standardized period"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
        }
        
        template_data = self.generator._prepare_template_data(data)
        
        # Verify insurance_period_text is included and correct
        self.assertIn('insurance_period_text', template_data)
        self.assertEqual(template_data['insurance_period_text'], '1 год')
    
    def test_email_generation_with_all_features_and_standardized_period(self):
        """Test email generation with all features and standardized period"""
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
        
        # Verify all features are included along with standardized period
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
        self.assertIn('Обратите внимание, требуется тариф с франшизой', email_body)
        self.assertIn('Обратите внимание, требуется рассрочка платежа', email_body)
        self.assertIn('Обратите внимание, у предмета лизинга имеется автозапуск', email_body)
        self.assertIn('Обратите внимание, что лизинговое имущество относится к категории C/E', email_body)


class TestStandardizedPeriodIntegration(TestCase):
    """Integration tests using only standardized period options"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.generator = EmailTemplateGenerator()
    
    def test_end_to_end_workflow_with_one_year_period(self):
        """Test complete workflow from model creation to email generation with '1 год'"""
        # Create insurance request with standardized period
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            vehicle_info='Test Vehicle',
            dfa_number='DFA123',
            branch='Москва',
            has_franchise=True,
            has_installment=False,
            has_autostart=True,
            has_casco_ce=False,
            created_by=self.user
        )
        
        # Convert to dict (as used in email generation)
        data = request.to_dict()
        
        # Verify standardized period in data
        self.assertEqual(data['insurance_period'], '1 год')
        
        # Generate email
        email_body = self.generator.generate_email_body(data)
        
        # Verify email contains standardized period
        self.assertIn('Необходимый период страхования: 1 год', email_body)
        self.assertIn('Обратите внимание, требуется тариф с франшизой', email_body)
        self.assertIn('Обратите внимание, у предмета лизинга имеется автозапуск', email_body)
    
    def test_end_to_end_workflow_with_full_lease_term_period(self):
        """Test complete workflow with 'на весь срок лизинга'"""
        # Create insurance request with standardized period
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='0987654321',
            insurance_type='страхование спецтехники',
            insurance_period='на весь срок лизинга',
            vehicle_info='Special Equipment',
            dfa_number='DFA456',
            branch='Казань',
            has_franchise=False,
            has_installment=True,
            has_autostart=False,
            has_casco_ce=True,
            created_by=self.user
        )
        
        # Convert to dict
        data = request.to_dict()
        
        # Verify standardized period in data
        self.assertEqual(data['insurance_period'], 'на весь срок лизинга')
        
        # Generate email
        email_body = self.generator.generate_email_body(data)
        
        # Verify email contains standardized period and features
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
        self.assertIn('Обратите внимание, требуется рассрочка платежа', email_body)
        self.assertIn('Обратите внимание, что лизинговое имущество относится к категории C/E', email_body)
    
    def test_form_to_model_to_email_workflow(self):
        """Test workflow from form validation to model save to email generation"""
        # Test form with standardized period
        form_data = {
            'client_name': 'Form Test Client',
            'inn': '1111111111',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Form Test Vehicle',
            'dfa_number': 'FORM123',
            'branch': 'Санкт-Петербург',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False
        }
        
        # Validate form
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Save to model
        instance = form.save(commit=False)
        instance.created_by = self.user
        instance.save()
        
        # Verify model has standardized period
        self.assertEqual(instance.insurance_period, '1 год')
        
        # Convert to dict and generate email
        data = instance.to_dict()
        email_body = self.generator.generate_email_body(data)
        
        # Verify email generation works with standardized period
        self.assertIn('Необходимый период страхования: 1 год', email_body)
    
    def test_excel_to_model_to_email_workflow_simulation(self):
        """Test simulated workflow from Excel processing to model to email"""
        # Simulate Excel processing result with standardized period
        excel_data = {
            'client_name': 'Excel Test Client',
            'inn': '2222222222',
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',  # Standardized from Excel
            'vehicle_info': 'Excel Test Vehicle',
            'dfa_number': 'EXCEL123',
            'branch': 'Мурманск',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': timezone.now() + timedelta(hours=3)
        }
        
        # Create model instance from Excel data
        request = InsuranceRequest.objects.create(
            created_by=self.user,
            **excel_data
        )
        
        # Verify standardized period is saved
        self.assertEqual(request.insurance_period, 'на весь срок лизинга')
        
        # Generate email from model data
        data = request.to_dict()
        email_body = self.generator.generate_email_body(data)
        
        # Verify complete workflow
        self.assertIn('Необходимый период страхования: на весь срок лизинга', email_body)
        self.assertIn('Обратите внимание, требуется рассрочка платежа', email_body)


class TestStandardizedPeriodFallbackBehavior(TestCase):
    """Tests for fallback to 'не указан' for empty or invalid values"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.generator = EmailTemplateGenerator()
    
    def test_model_to_dict_fallback_for_empty_period(self):
        """Test that model to_dict falls back to 'не указан' for empty period"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',  # Empty
            created_by=self.user
        )
        
        data = request.to_dict()
        self.assertEqual(data['insurance_period'], 'не указан')
    
    def test_model_to_dict_fallback_for_none_period(self):
        """Test that model to_dict falls back to 'не указан' for None period"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',  # Create with empty string first
            created_by=self.user
        )
        # Test the to_dict method with None value directly
        request.insurance_period = None
        
        data = request.to_dict()
        self.assertEqual(data['insurance_period'], 'не указан')
    
    def test_email_template_fallback_for_empty_period(self):
        """Test that email template falls back to 'не указан' for empty period"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': '',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
        }
        
        result = self.generator._format_insurance_period_text(data)
        self.assertEqual(result, 'не указан')
        
        email_body = self.generator.generate_email_body(data)
        self.assertIn('Необходимый период страхования: не указан', email_body)
    
    def test_email_template_fallback_for_missing_period(self):
        """Test that email template falls back to 'не указан' for missing period key"""
        data = {
            'insurance_type': 'КАСКО',
            'inn': '1234567890',
            'response_deadline': datetime.now(),
            # insurance_period key is missing
        }
        
        result = self.generator._format_insurance_period_text(data)
        self.assertEqual(result, 'не указан')
        
        email_body = self.generator.generate_email_body(data)
        self.assertIn('Необходимый период страхования: не указан', email_body)
    
    def test_email_template_fallback_for_whitespace_period(self):
        """Test that email template falls back to 'не указан' for whitespace-only period"""
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': '   ',  # Whitespace only
            'inn': '1234567890',
            'response_deadline': datetime.now(),
        }
        
        result = self.generator._format_insurance_period_text(data)
        self.assertEqual(result, 'не указан')
        
        email_body = self.generator.generate_email_body(data)
        self.assertIn('Необходимый период страхования: не указан', email_body)
    
    def test_excel_processing_fallback_for_empty_cells(self):
        """Test that Excel processing returns empty string for empty cells (which becomes 'не указан' in email)"""
        excel_reader = ExcelReader("dummy_path.xlsx")
        mock_sheet = Mock()
        
        # Both N17 and N18 are empty
        with patch.object(excel_reader, '_get_cell_with_adjustment_openpyxl') as mock_get_cell:
            def mock_get_cell_side_effect(sheet, col, row):
                if col == 'N' and row in [17, 18]:
                    return None  # Both empty
                return None
            
            mock_get_cell.side_effect = mock_get_cell_side_effect
            result = excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "")  # Empty string from Excel processing
        
        # When this empty string goes through email generation, it becomes 'не указан'
        data = {
            'insurance_type': 'КАСКО',
            'insurance_period': result,  # Empty string from Excel
            'inn': '1234567890',
            'response_deadline': datetime.now(),
        }
        
        email_body = self.generator.generate_email_body(data)
        self.assertIn('Необходимый период страхования: не указан', email_body)


if __name__ == '__main__':
    unittest.main()
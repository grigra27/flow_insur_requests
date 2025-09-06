"""
Tests for new insurance type "страхование имущества"
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta
import tempfile
import os

from .models import InsuranceRequest
from .forms import InsuranceRequestForm
from core.excel_utils import ExcelReader


class NewInsuranceTypeModelTests(TestCase):
    """Tests for new insurance type in model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_insurance_type_choices_include_property_insurance(self):
        """Test that INSURANCE_TYPE_CHOICES includes 'страхование имущества'"""
        choices = dict(InsuranceRequest.INSURANCE_TYPE_CHOICES)
        
        # Check that all expected types are present
        expected_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
        for insurance_type in expected_types:
            self.assertIn(insurance_type, choices)
        
        # Specifically check the new type
        self.assertEqual(choices['страхование имущества'], 'страхование имущества')
    
    def test_create_request_with_property_insurance_type(self):
        """Test creating insurance request with property insurance type"""
        request = InsuranceRequest.objects.create(
            client_name='Test Property Client',
            inn='1234567890',
            insurance_type='страхование имущества',
            insurance_period='12 месяцев',
            vehicle_info='Property info',
            created_by=self.user
        )
        
        self.assertEqual(request.insurance_type, 'страхование имущества')
        self.assertEqual(request.get_insurance_type_display(), 'страхование имущества')
    
    def test_model_validation_accepts_property_insurance(self):
        """Test that model validation accepts property insurance type"""
        request = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='страхование имущества',
            insurance_period='12 месяцев',
            created_by=self.user
        )
        
        # Should not raise validation error
        request.full_clean()
        request.save()
        
        self.assertEqual(request.insurance_type, 'страхование имущества')
    
    def test_model_rejects_invalid_insurance_type(self):
        """Test that model rejects invalid insurance types"""
        from django.core.exceptions import ValidationError
        
        request = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='invalid_type',  # Invalid type
            insurance_period='12 месяцев',
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            request.full_clean()


class ExcelReaderInsuranceTypeTests(TestCase):
    """Tests for insurance type detection in Excel reader"""
    
    def setUp(self):
        """Set up test data"""
        self.excel_reader = ExcelReader('dummy_path.xlsx')
    
    def test_determine_insurance_type_property_insurance_openpyxl(self):
        """Test property insurance detection with openpyxl method"""
        # Mock sheet with D23 having value (property insurance)
        mock_sheet = MagicMock()
        
        # Mock cell values: D21=None, D22=None, D23='some value'
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'D21':
                return None
            elif cell_address == 'D22':
                return None
            elif cell_address == 'D23':
                return 'Property insurance value'
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            insurance_type = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
            self.assertEqual(insurance_type, 'страхование имущества')
    
    def test_determine_insurance_type_property_insurance_pandas(self):
        """Test property insurance detection with pandas method"""
        # Mock DataFrame
        mock_df = MagicMock()
        
        # Mock cell values: D21=None, D22=None, D23='some value'
        def mock_safe_get_cell(df, row, col):
            if row == 20 and col == 3:  # D21
                return None
            elif row == 21 and col == 3:  # D22
                return None
            elif row == 22 and col == 3:  # D23
                return 'Property insurance value'
            return None
        
        with patch.object(self.excel_reader, '_safe_get_cell', side_effect=mock_safe_get_cell):
            insurance_type = self.excel_reader._determine_insurance_type_pandas(mock_df)
            self.assertEqual(insurance_type, 'страхование имущества')
    
    def test_determine_insurance_type_kasko_priority_openpyxl(self):
        """Test that КАСКО has priority over property insurance"""
        mock_sheet = MagicMock()
        
        # Mock cell values: D21='КАСКО value', D22=None, D23='Property value'
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'D21':
                return 'КАСКО value'
            elif cell_address == 'D22':
                return None
            elif cell_address == 'D23':
                return 'Property value'
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            insurance_type = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
            self.assertEqual(insurance_type, 'КАСКО')  # Should be КАСКО, not property
    
    def test_determine_insurance_type_special_equipment_priority_pandas(self):
        """Test that special equipment has priority over property insurance"""
        mock_df = MagicMock()
        
        # Mock cell values: D21=None, D22='Special equipment', D23='Property value'
        def mock_safe_get_cell(df, row, col):
            if row == 20 and col == 3:  # D21
                return None
            elif row == 21 and col == 3:  # D22
                return 'Special equipment value'
            elif row == 22 and col == 3:  # D23
                return 'Property value'
            return None
        
        with patch.object(self.excel_reader, '_safe_get_cell', side_effect=mock_safe_get_cell):
            insurance_type = self.excel_reader._determine_insurance_type_pandas(mock_df)
            self.assertEqual(insurance_type, 'страхование спецтехники')  # Should be special equipment
    
    def test_determine_insurance_type_empty_cells_default(self):
        """Test that empty cells result in 'другое' type"""
        mock_sheet = MagicMock()
        
        # Mock all cells as empty
        def mock_get_cell_value(sheet, cell_address):
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            insurance_type = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
            self.assertEqual(insurance_type, 'другое')
    
    def test_determine_insurance_type_whitespace_handling(self):
        """Test that whitespace-only values are treated as empty"""
        mock_sheet = MagicMock()
        
        # Mock cell values with whitespace
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'D21':
                return '   '  # Only whitespace
            elif cell_address == 'D22':
                return ''     # Empty string
            elif cell_address == 'D23':
                return 'Property value'
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            insurance_type = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
            self.assertEqual(insurance_type, 'страхование имущества')  # Should detect property insurance
    
    def test_get_default_data_includes_valid_insurance_type(self):
        """Test that default data includes valid insurance type"""
        default_data = self.excel_reader._get_default_data()
        
        self.assertIn('insurance_type', default_data)
        self.assertIn(default_data['insurance_type'], ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое'])


class InsuranceRequestFormNewTypeTests(TestCase):
    """Tests for form validation with new insurance type"""
    
    def setUp(self):
        """Set up test data"""
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'страхование имущества',
            'insurance_start_date': date.today(),
            'insurance_end_date': date.today() + timedelta(days=365),
            'vehicle_info': 'Property information',
            'dfa_number': 'DFA123456',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_form_accepts_property_insurance_type(self):
        """Test that form accepts property insurance type"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        self.assertEqual(form.cleaned_data['insurance_type'], 'страхование имущества')
    
    def test_form_choices_include_property_insurance(self):
        """Test that form choices include property insurance"""
        form = InsuranceRequestForm()
        insurance_type_field = form.fields['insurance_type']
        
        # Get choices from the widget
        choices = dict(insurance_type_field.widget.choices)
        self.assertIn('страхование имущества', choices)
        self.assertEqual(choices['страхование имущества'], 'страхование имущества')
    
    def test_form_save_with_property_insurance(self):
        """Test form save functionality with property insurance"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_type, 'страхование имущества')
        self.assertEqual(instance.client_name, 'Test Client')
    
    def test_form_rejects_invalid_insurance_type(self):
        """Test that form rejects invalid insurance types"""
        invalid_data = self.valid_data.copy()
        invalid_data['insurance_type'] = 'invalid_type'
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_type', form.errors)
    
    def test_form_widget_attributes_for_insurance_type(self):
        """Test that insurance type field has correct widget attributes"""
        form = InsuranceRequestForm()
        insurance_type_widget = form.fields['insurance_type'].widget
        
        self.assertEqual(insurance_type_widget.attrs.get('class'), 'form-control')
        
        # Check that all choices are available
        choices = dict(insurance_type_widget.choices)
        expected_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
        for insurance_type in expected_types:
            self.assertIn(insurance_type, choices)


class TemplateRenderingNewTypeTests(TestCase):
    """Tests for template rendering with new insurance type"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create request with property insurance type
        self.property_request = InsuranceRequest.objects.create(
            client_name='Property Client',
            inn='1234567890',
            insurance_type='страхование имущества',
            insurance_period='12 месяцев',
            vehicle_info='Property information',
            branch='Moscow Branch',
            dfa_number='PROP-2024-001',
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_request_detail_displays_property_insurance_type(self):
        """Test request detail template displays property insurance type"""
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.property_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'страхование имущества')
        self.assertContains(response, 'Property Client')
    
    def test_request_list_displays_property_insurance_type(self):
        """Test request list template displays property insurance type"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'страхование имущества')
        self.assertContains(response, 'Property Client')
    
    def test_edit_form_displays_property_insurance_option(self):
        """Test edit form displays property insurance as an option"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.property_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        # Check that the option is present in the select
        self.assertContains(response, 'страхование имущества')
        # Check that it's selected
        self.assertContains(response, 'selected')
    
    def test_edit_form_can_change_to_property_insurance(self):
        """Test that edit form can change insurance type to property insurance"""
        # Create a request with different type
        other_request = InsuranceRequest.objects.create(
            client_name='Other Client',
            inn='0987654321',
            insurance_type='КАСКО',
            insurance_period='6 месяцев',
            created_by=self.user
        )
        
        # Submit form to change to property insurance
        form_data = {
            'client_name': 'Other Client',
            'inn': '0987654321',
            'insurance_type': 'страхование имущества',  # Change to property insurance
            'insurance_start_date': date.today(),
            'insurance_end_date': date.today() + timedelta(days=180),
            'vehicle_info': 'Updated property info',
            'dfa_number': '',
            'branch': '',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': other_request.pk}),
            data=form_data
        )
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Check that type was updated
        other_request.refresh_from_db()
        self.assertEqual(other_request.insurance_type, 'страхование имущества')
    
    def test_template_context_includes_all_insurance_types(self):
        """Test that templates have access to all insurance types"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.property_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that all types are available in the form
        content = response.content.decode()
        expected_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
        for insurance_type in expected_types:
            self.assertIn(insurance_type, content)


class IntegrationNewTypeTests(TestCase):
    """Integration tests for new insurance type functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_complete_workflow_with_property_insurance(self):
        """Test complete workflow from creation to display with property insurance"""
        # Create request with property insurance
        request = InsuranceRequest.objects.create(
            client_name='Workflow Test Client',
            inn='1111111111',
            insurance_type='страхование имущества',
            insurance_period='24 месяца',
            vehicle_info='Property for workflow test',
            branch='Test Branch',
            dfa_number='WORKFLOW-2024-001',
            created_by=self.user
        )
        
        # Test detail view
        detail_response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'страхование имущества')
        
        # Test list view
        list_response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'страхование имущества')
        
        # Test edit view
        edit_response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, 'страхование имущества')
        
        # Test edit submission
        form_data = {
            'client_name': 'Updated Workflow Client',
            'inn': '1111111111',
            'insurance_type': 'страхование имущества',  # Keep same type
            'insurance_start_date': date.today(),
            'insurance_end_date': date.today() + timedelta(days=730),
            'vehicle_info': 'Updated property info',
            'dfa_number': 'WORKFLOW-2024-001-UPDATED',
            'branch': 'Updated Branch',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
        }
        
        edit_post_response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=form_data
        )
        self.assertEqual(edit_post_response.status_code, 302)
        
        # Verify changes were saved
        request.refresh_from_db()
        self.assertEqual(request.insurance_type, 'страхование имущества')
        self.assertEqual(request.client_name, 'Updated Workflow Client')
        self.assertEqual(request.dfa_number, 'WORKFLOW-2024-001-UPDATED')
    
    def test_data_persistence_across_operations(self):
        """Test that property insurance type persists across various operations"""
        # Create request
        request = InsuranceRequest.objects.create(
            client_name='Persistence Test',
            inn='2222222222',
            insurance_type='страхование имущества',
            insurance_period='12 месяцев',
            created_by=self.user
        )
        
        original_id = request.id
        original_type = request.insurance_type
        
        # Refresh from database
        request.refresh_from_db()
        self.assertEqual(request.insurance_type, original_type)
        
        # Update other fields, keep insurance type
        request.client_name = 'Updated Persistence Test'
        request.save()
        
        # Verify type is still correct
        request.refresh_from_db()
        self.assertEqual(request.insurance_type, 'страхование имущества')
        self.assertEqual(request.client_name, 'Updated Persistence Test')
        
        # Query from database again
        request_from_db = InsuranceRequest.objects.get(id=original_id)
        self.assertEqual(request_from_db.insurance_type, 'страхование имущества')
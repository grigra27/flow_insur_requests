"""
Unit tests for form pre-population functionality
"""
from django.test import TestCase
from django.contrib.auth.models import User
from datetime import datetime
import pytz

from .models import InsuranceRequest
from .forms import InsuranceRequestForm


class FormPrePopulationTestCase(TestCase):
    """Test cases for form pre-population with existing values"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.moscow_tz = pytz.timezone('Europe/Moscow')
    
    def test_complete_data_prepopulation(self):
        """Test form pre-population with complete data"""
        # Create request with complete data
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='страхование спецтехники',
            branch='Санкт-Петербург',
            insurance_period='1 год',
            vehicle_info='Test vehicle information',
            dfa_number='DFA123',
            has_franchise=True,
            has_installment=True,
            has_autostart=False,
            has_casco_ce=True,
            response_deadline=self.moscow_tz.localize(datetime(2024, 12, 15, 10, 0)),
            created_by=self.user
        )
        
        # Initialize form with instance
        form = InsuranceRequestForm(instance=request)
        
        # Test all field values
        self.assertEqual(form['client_name'].value(), 'Test Client')
        self.assertEqual(form['inn'].value(), '1234567890')
        self.assertEqual(form['insurance_type'].value(), 'страхование спецтехники')
        self.assertEqual(form['branch'].value(), 'Санкт-Петербург')
        self.assertEqual(form['insurance_period'].value(), '1 год')
        self.assertEqual(form['vehicle_info'].value(), 'Test vehicle information')
        self.assertEqual(form['dfa_number'].value(), 'DFA123')
        self.assertEqual(form['has_franchise'].value(), True)
        self.assertEqual(form['has_installment'].value(), True)
        self.assertEqual(form['has_autostart'].value(), False)
        self.assertEqual(form['has_casco_ce'].value(), True)
        
        # Test datetime field formatting
        response_deadline_value = form['response_deadline'].value()
        self.assertIsInstance(response_deadline_value, datetime)
        formatted_datetime = response_deadline_value.strftime('%Y-%m-%dT%H:%M')
        self.assertEqual(formatted_datetime, '2024-12-15T10:00')
    
    def test_datetime_html_rendering(self):
        """Test that datetime field renders correctly for HTML5 datetime-local"""
        request = InsuranceRequest.objects.create(
            client_name='DateTime Test',
            inn='1111111111',
            insurance_type='КАСКО',
            response_deadline=self.moscow_tz.localize(datetime(2024, 12, 31, 15, 30)),
            created_by=self.user
        )
        
        form = InsuranceRequestForm(instance=request)
        datetime_html = str(form['response_deadline'])
        
        # Check that HTML contains correct attributes and value
        self.assertIn('type="datetime-local"', datetime_html)
        self.assertIn('2024-12-31T15:30', datetime_html)
        self.assertIn('class="form-control"', datetime_html)
    
    def test_branch_dropdown_selection(self):
        """Test that branch dropdown correctly selects existing value"""
        request = InsuranceRequest.objects.create(
            client_name='Branch Test',
            inn='2222222222',
            insurance_type='КАСКО',
            branch='Москва',
            created_by=self.user
        )
        
        form = InsuranceRequestForm(instance=request)
        branch_html = str(form['branch'])
        
        # Check that correct option is selected
        self.assertIn('value="Москва" selected', branch_html)
        self.assertEqual(form['branch'].value(), 'Москва')
    
    def test_invalid_branch_handling(self):
        """Test that invalid branch values are handled correctly"""
        request = InsuranceRequest.objects.create(
            client_name='Invalid Branch Test',
            inn='3333333333',
            insurance_type='КАСКО',
            branch='Несуществующий филиал',
            created_by=self.user
        )
        
        form = InsuranceRequestForm(instance=request)
        
        # Invalid branch should result in empty selection
        self.assertEqual(form['branch'].value(), '')
        
        # HTML should have empty option selected
        branch_html = str(form['branch'])
        self.assertIn('value="" selected', branch_html)
    
    def test_minimal_data_prepopulation(self):
        """Test form pre-population with minimal data"""
        request = InsuranceRequest.objects.create(
            client_name='Minimal Test',
            inn='4444444444',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        form = InsuranceRequestForm(instance=request)
        
        # Check that empty/default fields are handled correctly
        self.assertEqual(form['branch'].value(), '')
        self.assertEqual(form['vehicle_info'].value(), '')
        self.assertEqual(form['dfa_number'].value(), '')
        self.assertEqual(form['has_franchise'].value(), False)
        self.assertEqual(form['has_installment'].value(), False)
        self.assertEqual(form['has_autostart'].value(), False)
        self.assertEqual(form['has_casco_ce'].value(), False)
        self.assertEqual(form['insurance_period'].value(), '')
        # Note: response_deadline gets auto-set by the model's save method, so it won't be None
    
    def test_boolean_fields_prepopulation(self):
        """Test that boolean fields are correctly pre-populated"""
        # Test with all boolean fields True
        request_true = InsuranceRequest.objects.create(
            client_name='Boolean True Test',
            inn='5555555555',
            insurance_type='КАСКО',
            has_franchise=True,
            has_installment=True,
            has_autostart=True,
            has_casco_ce=True,
            created_by=self.user
        )
        
        form_true = InsuranceRequestForm(instance=request_true)
        self.assertEqual(form_true['has_franchise'].value(), True)
        self.assertEqual(form_true['has_installment'].value(), True)
        self.assertEqual(form_true['has_autostart'].value(), True)
        self.assertEqual(form_true['has_casco_ce'].value(), True)
        
        # Test with all boolean fields False
        request_false = InsuranceRequest.objects.create(
            client_name='Boolean False Test',
            inn='6666666666',
            insurance_type='КАСКО',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            created_by=self.user
        )
        
        form_false = InsuranceRequestForm(instance=request_false)
        self.assertEqual(form_false['has_franchise'].value(), False)
        self.assertEqual(form_false['has_installment'].value(), False)
        self.assertEqual(form_false['has_autostart'].value(), False)
        self.assertEqual(form_false['has_casco_ce'].value(), False)
    
    def test_insurance_period_prepopulation(self):
        """Test that insurance period field is correctly pre-populated"""
        request = InsuranceRequest.objects.create(
            client_name='Period Test',
            inn='7777777777',
            insurance_type='КАСКО',
            insurance_period='на весь срок лизинга',
            created_by=self.user
        )
        
        form = InsuranceRequestForm(instance=request)
        
        self.assertEqual(form['insurance_period'].value(), 'на весь срок лизинга')
        
        # Check HTML rendering
        period_html = str(form['insurance_period'])
        self.assertIn('на весь срок лизинга', period_html)
        self.assertIn('selected', period_html)
    
    def test_form_validation_with_prepopulated_data(self):
        """Test that form validation works correctly with pre-populated data"""
        request = InsuranceRequest.objects.create(
            client_name='Validation Test',
            inn='8888888888',
            insurance_type='КАСКО',
            branch='Казань',
            insurance_period='1 год',
            created_by=self.user
        )
        
        # Note: Unbound forms (without POST data) don't validate automatically
        # We need to test with actual form data
        
        # Test form submission with modified data
        form_data = {
            'client_name': 'Updated Client Name',
            'inn': '8888888888',
            'insurance_type': 'КАСКО',
            'branch': 'Москва',
            'insurance_period': 'на весь срок лизинга',
            'vehicle_info': '',
            'dfa_number': '',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        form_with_data = InsuranceRequestForm(form_data, instance=request)
        self.assertTrue(form_with_data.is_valid())
        
        # Save and verify changes
        updated_request = form_with_data.save()
        self.assertEqual(updated_request.client_name, 'Updated Client Name')
        self.assertEqual(updated_request.branch, 'Москва')
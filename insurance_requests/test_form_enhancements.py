"""
Tests for form enhancements with separate date fields and validation
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.exceptions import ValidationError
from datetime import datetime, date, timedelta
from django.utils import timezone
import pytz

from .models import InsuranceRequest
from .forms import InsuranceRequestForm


class DateFieldValidationTests(TestCase):
    """Tests for date field validation in forms"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': date.today(),
            'insurance_end_date': date.today() + timedelta(days=365),
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_form_accepts_valid_date_range(self):
        """Test that form accepts valid date range"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        self.assertEqual(form.cleaned_data['insurance_start_date'], self.valid_data['insurance_start_date'])
        self.assertEqual(form.cleaned_data['insurance_end_date'], self.valid_data['insurance_end_date'])
    
    def test_form_rejects_start_date_after_end_date(self):
        """Test that form rejects when start date is after end date"""
        invalid_data = self.valid_data.copy()
        invalid_data['insurance_start_date'] = date.today() + timedelta(days=365)
        invalid_data['insurance_end_date'] = date.today()
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_end_date', form.errors)
        self.assertIn('должна быть позже даты начала', str(form.errors['insurance_end_date']))
    
    def test_form_rejects_same_start_and_end_date(self):
        """Test that form rejects when start and end dates are the same"""
        invalid_data = self.valid_data.copy()
        same_date = date.today()
        invalid_data['insurance_start_date'] = same_date
        invalid_data['insurance_end_date'] = same_date
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_end_date', form.errors)
        self.assertIn('должна быть позже даты начала', str(form.errors['insurance_end_date']))
    
    def test_form_rejects_very_short_period(self):
        """Test that form rejects very short insurance periods"""
        invalid_data = self.valid_data.copy()
        invalid_data['insurance_start_date'] = date.today()
        invalid_data['insurance_end_date'] = date.today()  # Same day
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_end_date', form.errors)
    
    def test_form_accepts_empty_dates(self):
        """Test that form accepts empty date fields"""
        valid_data = self.valid_data.copy()
        valid_data['insurance_start_date'] = None
        valid_data['insurance_end_date'] = None
        
        form = InsuranceRequestForm(data=valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_accepts_only_start_date(self):
        """Test that form accepts only start date without end date"""
        valid_data = self.valid_data.copy()
        valid_data['insurance_end_date'] = None
        
        form = InsuranceRequestForm(data=valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_accepts_only_end_date(self):
        """Test that form accepts only end date without start date"""
        valid_data = self.valid_data.copy()
        valid_data['insurance_start_date'] = None
        
        form = InsuranceRequestForm(data=valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_start_date_validation_rejects_very_old_dates(self):
        """Test that start date validation rejects dates more than 5 years ago"""
        invalid_data = self.valid_data.copy()
        invalid_data['insurance_start_date'] = date.today() - timedelta(days=6*365)  # 6 years ago
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_start_date', form.errors)
        self.assertIn('не может быть более 5 лет назад', str(form.errors['insurance_start_date']))
    
    def test_start_date_validation_accepts_recent_dates(self):
        """Test that start date validation accepts dates within 5 years"""
        valid_data = self.valid_data.copy()
        valid_data['insurance_start_date'] = date.today() - timedelta(days=4*365)  # 4 years ago
        valid_data['insurance_end_date'] = date.today() + timedelta(days=365)
        
        form = InsuranceRequestForm(data=valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_end_date_validation_rejects_very_future_dates(self):
        """Test that end date validation rejects dates more than 10 years in future"""
        invalid_data = self.valid_data.copy()
        invalid_data['insurance_end_date'] = date.today() + timedelta(days=11*365)  # 11 years ahead
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_end_date', form.errors)
        self.assertIn('не может быть более 10 лет в будущем', str(form.errors['insurance_end_date']))
    
    def test_end_date_validation_accepts_reasonable_future_dates(self):
        """Test that end date validation accepts dates within 10 years"""
        valid_data = self.valid_data.copy()
        valid_data['insurance_end_date'] = date.today() + timedelta(days=9*365)  # 9 years ahead
        
        form = InsuranceRequestForm(data=valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")


class FormRenderingWithSeparateDateFieldsTests(TestCase):
    """Tests for form rendering with separate date fields"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_start_date=date(2024, 6, 1),
            insurance_end_date=date(2025, 6, 1),
            vehicle_info='Test vehicle',
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_form_includes_separate_date_fields(self):
        """Test that form includes separate date input fields"""
        form = InsuranceRequestForm()
        
        # Check that both date fields are present
        self.assertIn('insurance_start_date', form.fields)
        self.assertIn('insurance_end_date', form.fields)
        
        # Check field types
        from django.forms import DateField
        self.assertIsInstance(form.fields['insurance_start_date'], DateField)
        self.assertIsInstance(form.fields['insurance_end_date'], DateField)
    
    def test_date_field_widgets_have_correct_attributes(self):
        """Test that date field widgets have correct HTML attributes"""
        form = InsuranceRequestForm()
        
        # Check start date widget
        start_widget = form.fields['insurance_start_date'].widget
        self.assertEqual(start_widget.attrs.get('class'), 'form-control date-input')
        self.assertEqual(start_widget.attrs.get('type'), 'date')
        self.assertEqual(start_widget.attrs.get('placeholder'), 'дд.мм.гггг')
        
        # Check end date widget
        end_widget = form.fields['insurance_end_date'].widget
        self.assertEqual(end_widget.attrs.get('class'), 'form-control date-input')
        self.assertEqual(end_widget.attrs.get('type'), 'date')
        self.assertEqual(end_widget.attrs.get('placeholder'), 'дд.мм.гггг')
    
    def test_date_fields_have_help_text(self):
        """Test that date fields have appropriate help text"""
        form = InsuranceRequestForm()
        
        self.assertEqual(
            form.fields['insurance_start_date'].help_text,
            'Дата начала действия страхования'
        )
        self.assertEqual(
            form.fields['insurance_end_date'].help_text,
            'Дата окончания действия страхования'
        )
    
    def test_edit_form_template_displays_separate_date_fields(self):
        """Test that edit form template displays separate date fields"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that both date input fields are present
        self.assertContains(response, 'name="insurance_start_date"')
        self.assertContains(response, 'name="insurance_end_date"')
        
        # Check that they have the correct type
        self.assertContains(response, 'type="date"')
        
        # Check that current values are populated
        self.assertContains(response, '2024-06-01')  # Start date
        self.assertContains(response, '2025-06-01')  # End date
    
    def test_edit_form_template_shows_help_text(self):
        """Test that edit form template shows help text for date fields"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Дата начала действия страхования')
        self.assertContains(response, 'Дата окончания действия страхования')
    
    def test_form_with_empty_dates_renders_correctly(self):
        """Test that form with empty dates renders correctly"""
        empty_request = InsuranceRequest.objects.create(
            client_name='Empty Dates Client',
            inn='0987654321',
            insurance_type='другое',
            insurance_start_date=None,
            insurance_end_date=None,
            created_by=self.user
        )
        
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': empty_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Fields should be present but empty
        self.assertContains(response, 'name="insurance_start_date"')
        self.assertContains(response, 'name="insurance_end_date"')
    
    def test_form_fields_are_in_correct_order(self):
        """Test that form fields appear in the correct order"""
        form = InsuranceRequestForm()
        field_names = list(form.fields.keys())
        
        # Check that date fields are present and in reasonable order
        self.assertIn('insurance_start_date', field_names)
        self.assertIn('insurance_end_date', field_names)
        
        # Start date should come before end date
        start_index = field_names.index('insurance_start_date')
        end_index = field_names.index('insurance_end_date')
        self.assertLess(start_index, end_index)


class FormErrorHandlingTests(TestCase):
    """Tests for error handling with invalid date ranges"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_start_date=date(2024, 1, 1),
            insurance_end_date=date(2024, 12, 31),
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_form_displays_date_validation_errors(self):
        """Test that form displays date validation errors"""
        invalid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2024-12-31',  # After end date
            'insurance_end_date': '2024-01-01',    # Before start date
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk}),
            data=invalid_data
        )
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        
        # Should display validation error
        self.assertContains(response, 'должна быть позже даты начала')
    
    def test_form_displays_start_date_too_old_error(self):
        """Test that form displays error for start date too far in past"""
        invalid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2018-01-01',  # More than 5 years ago
            'insurance_end_date': '2024-12-31',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk}),
            data=invalid_data
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'не может быть более 5 лет назад')
    
    def test_form_displays_end_date_too_future_error(self):
        """Test that form displays error for end date too far in future"""
        invalid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2024-01-01',
            'insurance_end_date': '2036-01-01',  # More than 10 years ahead
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk}),
            data=invalid_data
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'не может быть более 10 лет в будущем')
    
    def test_form_preserves_valid_fields_when_dates_invalid(self):
        """Test that form preserves valid field values when date validation fails"""
        invalid_data = {
            'client_name': 'Updated Client Name',
            'inn': '9876543210',
            'insurance_type': 'страхование спецтехники',
            'insurance_start_date': '2024-12-31',  # Invalid: after end date
            'insurance_end_date': '2024-01-01',    # Invalid: before start date
            'vehicle_info': 'Updated vehicle info',
            'dfa_number': 'UPDATED-DFA',
            'branch': 'Updated Branch',
            'has_franchise': True,
            'has_installment': True,
            'has_autostart': True,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk}),
            data=invalid_data
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Valid fields should be preserved in the form
        self.assertContains(response, 'Updated Client Name')
        self.assertContains(response, '9876543210')
        self.assertContains(response, 'Updated vehicle info')
        self.assertContains(response, 'UPDATED-DFA')
        self.assertContains(response, 'Updated Branch')
    
    def test_form_does_not_save_when_date_validation_fails(self):
        """Test that form does not save data when date validation fails"""
        original_client_name = self.request.client_name
        
        invalid_data = {
            'client_name': 'Should Not Be Saved',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2024-12-31',  # Invalid
            'insurance_end_date': '2024-01-01',    # Invalid
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk}),
            data=invalid_data
        )
        
        # Form should not redirect (has errors)
        self.assertEqual(response.status_code, 200)
        
        # Data should not be saved
        self.request.refresh_from_db()
        self.assertEqual(self.request.client_name, original_client_name)
    
    def test_multiple_validation_errors_displayed(self):
        """Test that multiple validation errors are displayed correctly"""
        invalid_data = {
            'client_name': 'Test Client',
            'inn': 'invalid_inn',  # Invalid INN
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2018-01-01',  # Too old
            'insurance_end_date': '2036-01-01',    # Too future
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'A' * 101,  # Too long
            'branch': 'B' * 256,      # Too long
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk}),
            data=invalid_data
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Should display multiple errors
        self.assertContains(response, 'не может быть более 5 лет назад')  # Start date error
        self.assertContains(response, 'не может быть более 10 лет в будущем')  # End date error
        self.assertContains(response, 'должен содержать только цифры')  # INN error
        self.assertContains(response, 'не должен превышать 100 символов')  # DFA error
        self.assertContains(response, 'не должно превышать 255 символов')  # Branch error


class FormSaveWithDateFieldsTests(TestCase):
    """Tests for form save functionality with date fields"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': date(2024, 3, 15),
            'insurance_end_date': date(2025, 3, 15),
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_form_save_updates_insurance_period_from_dates(self):
        """Test that form save updates insurance_period field from separate dates"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        
        # Should update insurance_period based on separate dates
        expected_period = 'с 15.03.2024 по 15.03.2025'
        self.assertEqual(instance.insurance_period, expected_period)
    
    def test_form_save_with_only_start_date(self):
        """Test form save with only start date"""
        data = self.valid_data.copy()
        data['insurance_end_date'] = None
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        expected_period = 'с 15.03.2024 по не указано'
        self.assertEqual(instance.insurance_period, expected_period)
    
    def test_form_save_with_only_end_date(self):
        """Test form save with only end date"""
        data = self.valid_data.copy()
        data['insurance_start_date'] = None
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        expected_period = 'с не указано по 15.03.2025'
        self.assertEqual(instance.insurance_period, expected_period)
    
    def test_form_save_with_no_dates(self):
        """Test form save with no dates"""
        data = self.valid_data.copy()
        data['insurance_start_date'] = None
        data['insurance_end_date'] = None
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_period, 'Период не указан')
    
    def test_form_save_preserves_separate_date_fields(self):
        """Test that form save preserves separate date fields"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        
        self.assertEqual(instance.insurance_start_date, date(2024, 3, 15))
        self.assertEqual(instance.insurance_end_date, date(2025, 3, 15))
    
    def test_form_update_existing_instance_with_dates(self):
        """Test updating existing instance with new dates"""
        # Create existing instance
        existing_request = InsuranceRequest.objects.create(
            client_name='Original Client',
            inn='1111111111',
            insurance_type='другое',
            insurance_start_date=date(2024, 1, 1),
            insurance_end_date=date(2024, 12, 31),
            created_by=self.user
        )
        
        # Update with new dates
        update_data = {
            'client_name': 'Updated Client',
            'inn': '1111111111',
            'insurance_type': 'КАСКО',
            'insurance_start_date': date(2024, 6, 1),
            'insurance_end_date': date(2025, 6, 1),
            'vehicle_info': 'Updated vehicle',
            'dfa_number': 'UPDATED-DFA',
            'branch': 'Updated Branch',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
        }
        
        form = InsuranceRequestForm(data=update_data, instance=existing_request)
        self.assertTrue(form.is_valid())
        
        updated_instance = form.save()
        
        # Check that dates were updated
        self.assertEqual(updated_instance.insurance_start_date, date(2024, 6, 1))
        self.assertEqual(updated_instance.insurance_end_date, date(2025, 6, 1))
        
        # Check that insurance_period was updated
        expected_period = 'с 01.06.2024 по 01.06.2025'
        self.assertEqual(updated_instance.insurance_period, expected_period)
        
        # Check that other fields were updated
        self.assertEqual(updated_instance.client_name, 'Updated Client')
        self.assertEqual(updated_instance.insurance_type, 'КАСКО')


class ResponseDeadlineValidationTests(TestCase):
    """Tests for response deadline validation with Moscow timezone"""
    
    def setUp(self):
        """Set up test data"""
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': date.today(),
            'insurance_end_date': date.today() + timedelta(days=365),
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
        }
    
    def test_response_deadline_validation_with_future_datetime(self):
        """Test response deadline validation with future datetime"""
        data = self.valid_data.copy()
        data['response_deadline'] = datetime.now() + timedelta(hours=24)
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_response_deadline_validation_with_past_datetime(self):
        """Test response deadline validation with past datetime (should not block)"""
        data = self.valid_data.copy()
        data['response_deadline'] = datetime.now() - timedelta(hours=1)
        
        form = InsuranceRequestForm(data=data)
        # Should still be valid (past deadline doesn't block saving)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_response_deadline_validation_with_none(self):
        """Test response deadline validation with None value"""
        data = self.valid_data.copy()
        data['response_deadline'] = None
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_response_deadline_timezone_handling(self):
        """Test that response deadline handles timezone correctly"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        moscow_datetime = moscow_tz.localize(datetime(2024, 12, 25, 15, 30))
        
        data = self.valid_data.copy()
        data['response_deadline'] = moscow_datetime
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Check that timezone is preserved
        cleaned_deadline = form.cleaned_data['response_deadline']
        self.assertEqual(cleaned_deadline, moscow_datetime)


class IntegrationFormTests(TestCase):
    """Integration tests for complete form functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_complete_form_workflow_with_date_fields(self):
        """Test complete form workflow from creation to update with date fields"""
        # Create initial request
        request = InsuranceRequest.objects.create(
            client_name='Initial Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_start_date=date(2024, 1, 1),
            insurance_end_date=date(2024, 12, 31),
            created_by=self.user
        )
        
        # Test edit form GET
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="insurance_start_date"')
        self.assertContains(response, 'name="insurance_end_date"')
        
        # Test edit form POST with valid data
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'страхование имущества',
            'insurance_start_date': '2024-06-01',
            'insurance_end_date': '2025-06-01',
            'vehicle_info': 'Updated vehicle info',
            'dfa_number': 'UPDATED-DFA',
            'branch': 'Updated Branch',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=form_data
        )
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Verify changes were saved
        request.refresh_from_db()
        self.assertEqual(request.client_name, 'Updated Client')
        self.assertEqual(request.insurance_type, 'страхование имущества')
        self.assertEqual(request.insurance_start_date, date(2024, 6, 1))
        self.assertEqual(request.insurance_end_date, date(2025, 6, 1))
        self.assertEqual(request.insurance_period, 'с 01.06.2024 по 01.06.2025')
    
    def test_form_error_recovery_workflow(self):
        """Test form error recovery workflow"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        # Submit invalid data
        invalid_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2024-12-31',  # Invalid: after end date
            'insurance_end_date': '2024-01-01',    # Invalid: before start date
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=invalid_data
        )
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'должна быть позже даты начала')
        
        # Submit corrected data
        valid_data = invalid_data.copy()
        valid_data['insurance_start_date'] = '2024-01-01'
        valid_data['insurance_end_date'] = '2024-12-31'
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=valid_data
        )
        
        # Should redirect after successful correction
        self.assertEqual(response.status_code, 302)
        
        # Verify data was saved
        request.refresh_from_db()
        self.assertEqual(request.insurance_start_date, date(2024, 1, 1))
        self.assertEqual(request.insurance_end_date, date(2024, 12, 31))
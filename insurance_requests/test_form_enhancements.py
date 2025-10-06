"""
Tests for form enhancements with standardized insurance period functionality
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from django.utils import timezone
import pytz

from .models import InsuranceRequest
from .forms import InsuranceRequestForm


class StandardizedPeriodFormTests(TestCase):
    """Tests for form functionality with standardized insurance periods"""
    
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
            'insurance_period': '1 год',
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Казань',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_form_accepts_valid_standardized_period(self):
        """Test that form accepts valid standardized period"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        self.assertEqual(form.cleaned_data['insurance_period'], '1 год')
    
    def test_form_accepts_full_lease_term_period(self):
        """Test that form accepts 'на весь срок лизинга' period"""
        data = self.valid_data.copy()
        data['insurance_period'] = 'на весь срок лизинга'
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        self.assertEqual(form.cleaned_data['insurance_period'], 'на весь срок лизинга')
    
    def test_form_accepts_empty_period(self):
        """Test that form accepts empty period"""
        data = self.valid_data.copy()
        data['insurance_period'] = ''
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")


class FormRenderingWithStandardizedPeriodTests(TestCase):
    """Tests for form rendering with standardized period dropdown"""
    
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
            insurance_period='1 год',
            vehicle_info='Test vehicle',
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_form_includes_period_dropdown(self):
        """Test that form includes period dropdown field"""
        form = InsuranceRequestForm()
        
        # Check that period field is present
        self.assertIn('insurance_period', form.fields)
        
        # Check field choices
        expected_choices = [
            ('', '-- Выберите период --'),
            ('1 год', '1 год'),
            ('на весь срок лизинга', 'на весь срок лизинга'),
        ]
        self.assertEqual(form.fields['insurance_period'].choices, expected_choices)
    
    def test_edit_form_template_displays_period_dropdown(self):
        """Test that edit form template displays period dropdown"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that period dropdown is present
        self.assertContains(response, 'name="insurance_period"')
        self.assertContains(response, 'option value="1 год"')
        self.assertContains(response, 'option value="на весь срок лизинга"')
        
        # Check that current value is selected
        self.assertContains(response, 'selected>1 год</option>')
    
    def test_form_with_empty_period_renders_correctly(self):
        """Test that form with empty period renders correctly"""
        empty_request = InsuranceRequest.objects.create(
            client_name='Empty Period Client',
            inn='0987654321',
            insurance_type='другое',
            insurance_period='',
            created_by=self.user
        )
        
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': empty_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Field should be present with no selection
        self.assertContains(response, 'name="insurance_period"')
        self.assertContains(response, 'selected>-- Выберите период --</option>')


class FormSaveWithStandardizedPeriodTests(TestCase):
    """Tests for form save functionality with standardized periods"""
    
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
            'insurance_period': '1 год',
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Казань',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_form_save_preserves_standardized_period(self):
        """Test that form save preserves standardized period"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        
        # Should preserve the standardized period
        self.assertEqual(instance.insurance_period, '1 год')
    
    def test_form_save_with_full_lease_term(self):
        """Test form save with full lease term period"""
        data = self.valid_data.copy()
        data['insurance_period'] = 'на весь срок лизинга'
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_period, 'на весь срок лизинга')
    
    def test_form_save_with_empty_period(self):
        """Test form save with empty period"""
        data = self.valid_data.copy()
        data['insurance_period'] = ''
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_period, '')
    
    def test_form_update_existing_instance_with_period(self):
        """Test updating existing instance with new period"""
        # Create existing instance
        existing_request = InsuranceRequest.objects.create(
            client_name='Original Client',
            inn='1111111111',
            insurance_type='другое',
            insurance_period='1 год',
            created_by=self.user
        )
        
        # Update with new period
        update_data = {
            'client_name': 'Updated Client',
            'inn': '1111111111',
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',
            'vehicle_info': 'Updated vehicle',
            'dfa_number': 'UPDATED-DFA',
            'branch': 'Москва',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
        }
        
        form = InsuranceRequestForm(data=update_data, instance=existing_request)
        self.assertTrue(form.is_valid())
        
        updated_instance = form.save()
        
        # Check that period was updated
        self.assertEqual(updated_instance.insurance_period, 'на весь срок лизинга')
        
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
            'insurance_period': '1 год',
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Казань',
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
    
    def test_complete_form_workflow_with_standardized_periods(self):
        """Test complete form workflow from creation to update with standardized periods"""
        # Create initial request
        request = InsuranceRequest.objects.create(
            client_name='Initial Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            created_by=self.user
        )
        
        # Test edit form GET
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="insurance_period"')
        
        # Test edit form POST with valid data
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'страхование имущества',
            'insurance_period': 'на весь срок лизинга',
            'vehicle_info': 'Updated vehicle info',
            'dfa_number': 'UPDATED-DFA',
            'branch': 'Москва',
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
        self.assertEqual(request.insurance_period, 'на весь срок лизинга')
    
    def test_form_error_recovery_workflow(self):
        """Test form error recovery workflow"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        # Submit invalid data (missing required field)
        invalid_data = {
            'client_name': '',  # Missing required field
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Казань',
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
        
        # Submit corrected data
        valid_data = invalid_data.copy()
        valid_data['client_name'] = 'Updated Client'
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=valid_data
        )
        
        # Should redirect after successful correction
        self.assertEqual(response.status_code, 302)
        
        # Verify data was saved
        request.refresh_from_db()
        self.assertEqual(request.client_name, 'Updated Client')
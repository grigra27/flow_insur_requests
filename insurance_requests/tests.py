from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.template.loader import render_to_string
from django.forms import ValidationError
from datetime import datetime, timedelta
from unittest.mock import patch

from .models import InsuranceRequest, RequestAttachment
from .forms import InsuranceRequestForm, ExcelUploadForm, EmailPreviewForm


class InsuranceRequestFormTests(TestCase):
    """Tests for InsuranceRequestForm validation, especially branch and DFA fields"""
    
    def setUp(self):
        """Set up test data"""
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Казань',  # Valid branch choice
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'has_casco_ce': False,  # Add missing field
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_form_valid_with_branch_and_dfa(self):
        """Test form validation with valid branch and DFA number"""
        # Update to use valid branch from dropdown choices
        data = self.valid_data.copy()
        data['branch'] = 'Казань'  # Valid branch choice
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['branch'], 'Казань')
        self.assertEqual(form.cleaned_data['dfa_number'], 'DFA123456')
    
    def test_form_valid_with_empty_branch_and_dfa(self):
        """Test form validation with empty branch and DFA fields (should be valid)"""
        data = self.valid_data.copy()
        data['branch'] = ''
        data['dfa_number'] = ''
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['branch'], '')
        self.assertEqual(form.cleaned_data['dfa_number'], '')
    
    def test_dfa_number_max_length_validation(self):
        """Test DFA number field length validation (max 100 characters)"""
        data = self.valid_data.copy()
        data['dfa_number'] = 'A' * 101  # 101 characters, should fail
        
        form = InsuranceRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('dfa_number', form.errors)
        # Check for Django's default max_length validation message or custom message
        error_message = str(form.errors['dfa_number'])
        self.assertTrue(
            'не должен превышать 100 символов' in error_message or 
            'не более 100 символов' in error_message,
            f"Expected length validation error, got: {error_message}"
        )
    
    def test_dfa_number_exactly_max_length(self):
        """Test DFA number with exactly 100 characters (should be valid)"""
        data = self.valid_data.copy()
        data['dfa_number'] = 'A' * 100  # Exactly 100 characters
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data['dfa_number']), 100)
    
    def test_branch_invalid_choice_validation(self):
        """Test branch field validation with invalid choice"""
        data = self.valid_data.copy()
        data['branch'] = 'Invalid Branch Choice'  # Not in dropdown choices
        
        form = InsuranceRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('branch', form.errors)
        # Check for custom validation message
        error_message = str(form.errors['branch'])
        self.assertTrue(
            'Выберите корректный вариант' in error_message or
            'нет среди допустимых значений' in error_message,
            f"Expected choice validation error, got: {error_message}"
        )
    
    def test_branch_valid_choice(self):
        """Test branch with valid choice from dropdown"""
        data = self.valid_data.copy()
        data['branch'] = 'Москва'  # Valid choice from dropdown
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['branch'], 'Москва')
    
    def test_form_fields_include_branch_and_dfa(self):
        """Test that form includes branch and dfa_number fields"""
        form = InsuranceRequestForm()
        self.assertIn('branch', form.fields)
        self.assertIn('dfa_number', form.fields)
    
    def test_form_widgets_have_correct_attributes(self):
        """Test that branch and DFA fields have correct widget attributes"""
        form = InsuranceRequestForm()
        
        # Check DFA number widget
        dfa_widget = form.fields['dfa_number'].widget
        self.assertEqual(dfa_widget.attrs.get('class'), 'form-control')
        self.assertEqual(dfa_widget.attrs.get('maxlength'), '100')
        
        # Check branch widget (now a Select widget)
        branch_widget = form.fields['branch'].widget
        self.assertEqual(branch_widget.attrs.get('class'), 'form-control')
        # Select widgets don't have maxlength attribute
        from django.forms import Select
        self.assertIsInstance(branch_widget, Select)
    
    def test_form_save_with_branch_and_dfa(self):
        """Test form save functionality with branch and DFA data"""
        # Update to use valid branch choice
        data = self.valid_data.copy()
        data['branch'] = 'Санкт-Петербург'  # Valid branch choice
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.branch, 'Санкт-Петербург')
        self.assertEqual(instance.dfa_number, 'DFA123456')
        self.assertEqual(instance.client_name, 'Test Client')


class TemplateRenderingTests(TestCase):
    """Tests for template rendering with and without branch/DFA data"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to 'Пользователи' group for access
        users_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(users_group)
        
        # Create request with branch and DFA data
        self.request_with_data = InsuranceRequest.objects.create(
            client_name='Client With Data',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            vehicle_info='Test vehicle',
            branch='Москва',  # Valid branch choice
            dfa_number='DFA-2024-001',
            created_by=self.user
        )
        
        # Create request without branch and DFA data
        self.request_without_data = InsuranceRequest.objects.create(
            client_name='Client Without Data',
            inn='0987654321',
            insurance_type='другое',
            insurance_period='6 месяцев',
            vehicle_info='Another vehicle',
            branch='',
            dfa_number='',
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_request_detail_template_with_branch_and_dfa(self):
        """Test request detail template rendering with branch and DFA data"""
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request_with_data.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Москва')
        self.assertContains(response, 'DFA-2024-001')
        # Note: There might be other "Не указан" instances in the template for other fields
    
    def test_request_detail_template_without_branch_and_dfa(self):
        """Test request detail template rendering without branch and DFA data"""
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request_without_data.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        # Should show "Не указан" for empty fields - there might be more instances in other parts of template
        self.assertContains(response, 'Не указан')  # At least once for branch and DFA
    
    def test_request_list_template_with_branch_and_dfa(self):
        """Test request list template rendering with branch and DFA data"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Москва')
        self.assertContains(response, 'DFA-2024-001')
    
    def test_request_list_template_without_branch_and_dfa(self):
        """Test request list template rendering without branch and DFA data"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        # Should show "Не указан" for empty fields in list view
        self.assertContains(response, 'Не указан')
    
    def test_edit_request_template_includes_branch_and_dfa_fields(self):
        """Test edit request template includes branch and DFA form fields"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request_with_data.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        # Check that form fields are present
        self.assertContains(response, 'name="branch"')
        self.assertContains(response, 'name="dfa_number"')
        # Check that current values are populated
        self.assertContains(response, 'Москва')
        self.assertContains(response, 'DFA-2024-001')
    
    def test_edit_request_template_with_empty_branch_and_dfa(self):
        """Test edit request template with empty branch and DFA fields"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request_without_data.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        # Form fields should be present but empty
        self.assertContains(response, 'name="branch"')
        self.assertContains(response, 'name="dfa_number"')
    
    def test_template_context_includes_request_object(self):
        """Test that templates receive the correct request object in context"""
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request_with_data.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['request'], self.request_with_data)
    
    def test_template_handles_long_branch_names(self):
        """Test template handling of long branch names"""
        # Create request with long branch name
        long_branch_request = InsuranceRequest.objects.create(
            client_name='Client With Long Branch',
            inn='1111111111',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            branch='A' * 200,  # Very long branch name
            dfa_number='DFA-LONG-001',
            created_by=self.user
        )
        
        # Test list view (should truncate)
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        # Should contain truncated version - check for the beginning of the long string
        self.assertContains(response, 'A' * 20)  # At least first 20 characters should be there
        
        # Test detail view (should show full name)
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': long_branch_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A' * 200)  # Full branch name


class FormSubmissionAndPersistenceTests(TestCase):
    """Tests for form submission and data persistence of branch and DFA fields"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to 'Пользователи' group for access
        users_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(users_group)
        
        self.existing_request = InsuranceRequest.objects.create(
            client_name='Existing Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            branch='Казань',  # Valid branch choice
            dfa_number='OLD-DFA-001',
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_edit_form_submission_updates_branch_and_dfa(self):
        """Test that form submission correctly updates branch and DFA fields"""
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'страхование спецтехники',
            'insurance_period': '6',
            'vehicle_info': 'Updated vehicle info',
            'branch': 'Москва',  # Valid branch choice
            'dfa_number': 'NEW-DFA-2024-001',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.existing_request.pk}),
            data=form_data
        )
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Refresh from database and check updates
        self.existing_request.refresh_from_db()
        self.assertEqual(self.existing_request.branch, 'Москва')
        self.assertEqual(self.existing_request.dfa_number, 'NEW-DFA-2024-001')
        self.assertEqual(self.existing_request.client_name, 'Updated Client')
    
    def test_edit_form_submission_with_empty_branch_and_dfa(self):
        """Test form submission with empty branch and DFA fields"""
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'другое',
            'insurance_period': '6',
            'vehicle_info': 'Updated vehicle info',
            'branch': '',  # Empty branch
            'dfa_number': '',  # Empty DFA
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.existing_request.pk}),
            data=form_data
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Check that empty values are saved correctly
        self.existing_request.refresh_from_db()
        self.assertEqual(self.existing_request.branch, '')
        self.assertEqual(self.existing_request.dfa_number, '')
    
    def test_form_submission_with_invalid_data_shows_errors(self):
        """Test form submission with invalid branch/DFA data shows validation errors"""
        form_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'branch': 'Invalid Branch Choice',  # Invalid choice
            'dfa_number': 'D' * 101,  # Too long
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.existing_request.pk}),
            data=form_data
        )
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        
        # Check that validation errors are displayed
        self.assertContains(response, 'Выберите корректный вариант')  # Branch error
        self.assertContains(response, 'не более 100 символов')  # DFA error
        
        # Data should not be saved
        self.existing_request.refresh_from_db()
        self.assertEqual(self.existing_request.branch, 'Казань')  # Unchanged
        self.assertEqual(self.existing_request.dfa_number, 'OLD-DFA-001')  # Unchanged
    
    def test_data_persistence_after_multiple_edits(self):
        """Test data persistence after multiple form submissions"""
        # First edit
        form_data_1 = {
            'client_name': 'Client Edit 1',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'branch': 'Санкт-Петербург',  # Valid branch choice
            'dfa_number': 'DFA-EDIT-1',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.existing_request.pk}),
            data=form_data_1
        )
        
        self.existing_request.refresh_from_db()
        self.assertEqual(self.existing_request.branch, 'Санкт-Петербург')
        self.assertEqual(self.existing_request.dfa_number, 'DFA-EDIT-1')
        
        # Second edit
        form_data_2 = {
            'client_name': 'Client Edit 2',
            'inn': '1234567890',
            'insurance_type': 'страхование спецтехники',
            'insurance_period': '6',
            'branch': 'Челябинск',  # Valid branch choice
            'dfa_number': 'DFA-EDIT-2',
            'has_franchise': True,
            'has_installment': True,
            'has_autostart': True,
        }
        
        self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.existing_request.pk}),
            data=form_data_2
        )
        
        self.existing_request.refresh_from_db()
        self.assertEqual(self.existing_request.branch, 'Челябинск')
        self.assertEqual(self.existing_request.dfa_number, 'DFA-EDIT-2')
        self.assertEqual(self.existing_request.client_name, 'Client Edit 2')
    
    def test_form_preserves_other_fields_when_updating_branch_dfa(self):
        """Test that updating branch/DFA doesn't affect other fields"""
        original_created_at = self.existing_request.created_at
        original_status = self.existing_request.status
        
        form_data = {
            'client_name': self.existing_request.client_name,  # Keep same
            'inn': self.existing_request.inn,  # Keep same
            'insurance_type': self.existing_request.insurance_type,  # Keep same
            'insurance_period': self.existing_request.insurance_period,  # Keep same
            'vehicle_info': self.existing_request.vehicle_info,  # Keep same
            'branch': 'Мурманск',  # Change only this - valid choice
            'dfa_number': 'Updated DFA Only',  # Change only this
            'has_franchise': self.existing_request.has_franchise,  # Keep same
            'has_installment': self.existing_request.has_installment,  # Keep same
            'has_autostart': self.existing_request.has_autostart,  # Keep same
        }
        
        self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.existing_request.pk}),
            data=form_data
        )
        
        self.existing_request.refresh_from_db()
        
        # Check that branch and DFA were updated
        self.assertEqual(self.existing_request.branch, 'Мурманск')
        self.assertEqual(self.existing_request.dfa_number, 'Updated DFA Only')
        
        # Check that other fields remained unchanged
        self.assertEqual(self.existing_request.created_at, original_created_at)
        self.assertEqual(self.existing_request.status, original_status)
        self.assertEqual(self.existing_request.client_name, 'Existing Client')

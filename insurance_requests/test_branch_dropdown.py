"""
Tests for branch dropdown functionality in InsuranceRequestForm
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.forms import ValidationError
from datetime import datetime, timedelta

from .models import InsuranceRequest
from .forms import InsuranceRequestForm


class BranchDropdownTests(TestCase):
    """Tests for branch dropdown functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'vehicle_info': 'Test vehicle info',
            'dfa_number': 'DFA123456',
            'branch': 'Казань',  # Valid branch from dropdown
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_branch_choices_are_defined(self):
        """Test that BRANCH_CHOICES constant is properly defined"""
        form = InsuranceRequestForm()
        self.assertTrue(hasattr(form, 'BRANCH_CHOICES'))
        self.assertIsInstance(form.BRANCH_CHOICES, list)
        
        # Check that all expected branches are in the choices
        expected_branches = [
            'Казань', 'Нижний Новгород', 'Краснодар', 'Санкт-Петербург',
            'Мурманск', 'Псков', 'Челябинск', 'Москва', 
            'Великий Новгород', 'Архангельск'
        ]
        
        choice_values = [choice[0] for choice in form.BRANCH_CHOICES if choice[0]]  # Exclude empty choice
        for branch in expected_branches:
            self.assertIn(branch, choice_values)
    
    def test_branch_field_is_choice_field(self):
        """Test that branch field is a ChoiceField with correct widget"""
        form = InsuranceRequestForm()
        branch_field = form.fields['branch']
        
        # Check field type
        from django.forms import ChoiceField
        self.assertIsInstance(branch_field, ChoiceField)
        
        # Check widget type
        from django.forms import Select
        self.assertIsInstance(branch_field.widget, Select)
        
        # Check widget attributes
        self.assertEqual(branch_field.widget.attrs.get('class'), 'form-control')
    
    def test_form_valid_with_valid_branch_choice(self):
        """Test form validation with valid branch choice"""
        for branch_choice in ['Казань', 'Москва', 'Санкт-Петербург']:
            with self.subTest(branch=branch_choice):
                data = self.valid_data.copy()
                data['branch'] = branch_choice
                
                form = InsuranceRequestForm(data=data)
                self.assertTrue(form.is_valid(), f"Form should be valid with branch: {branch_choice}")
                self.assertEqual(form.cleaned_data['branch'], branch_choice)
    
    def test_form_valid_with_empty_branch(self):
        """Test form validation with empty branch (should be valid since field is not required)"""
        data = self.valid_data.copy()
        data['branch'] = ''
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['branch'], '')
    
    def test_form_invalid_with_invalid_branch_choice(self):
        """Test form validation with invalid branch choice"""
        invalid_branches = ['Invalid Branch', 'Random City', 'Test Branch']
        
        for invalid_branch in invalid_branches:
            with self.subTest(branch=invalid_branch):
                data = self.valid_data.copy()
                data['branch'] = invalid_branch
                
                form = InsuranceRequestForm(data=data)
                self.assertFalse(form.is_valid(), f"Form should be invalid with branch: {invalid_branch}")
                self.assertIn('branch', form.errors)
                # Django's ChoiceField uses its own validation message
                error_message = str(form.errors['branch'])
                self.assertTrue(
                    'Выберите корректный вариант' in error_message or
                    'нет среди допустимых значений' in error_message,
                    f"Expected choice validation error, got: {error_message}"
                )
    
    def test_branch_choices_include_empty_option(self):
        """Test that branch choices include empty option for 'no selection'"""
        form = InsuranceRequestForm()
        choice_values = [choice[0] for choice in form.BRANCH_CHOICES]
        choice_labels = [choice[1] for choice in form.BRANCH_CHOICES]
        
        # Check that empty choice is first
        self.assertEqual(choice_values[0], '')
        self.assertEqual(choice_labels[0], '-- Выберите филиал --')
    
    def test_branch_field_not_required(self):
        """Test that branch field is not required"""
        form = InsuranceRequestForm()
        self.assertFalse(form.fields['branch'].required)
    
    def test_all_predefined_branches_are_valid(self):
        """Test that all predefined branch choices are valid"""
        form = InsuranceRequestForm()
        valid_branches = [choice[0] for choice in form.BRANCH_CHOICES if choice[0]]  # Exclude empty choice
        
        for branch in valid_branches:
            with self.subTest(branch=branch):
                data = self.valid_data.copy()
                data['branch'] = branch
                
                form = InsuranceRequestForm(data=data)
                self.assertTrue(form.is_valid(), f"Predefined branch should be valid: {branch}")
    
    def test_branch_validation_case_sensitive(self):
        """Test that branch validation is case sensitive"""
        # Test with different cases
        test_cases = [
            ('казань', False),  # lowercase
            ('КАЗАНЬ', False),  # uppercase
            ('Казань', True),   # correct case
            ('КаЗаНь', False),  # mixed case
        ]
        
        for branch_value, should_be_valid in test_cases:
            with self.subTest(branch=branch_value, expected_valid=should_be_valid):
                data = self.valid_data.copy()
                data['branch'] = branch_value
                
                form = InsuranceRequestForm(data=data)
                if should_be_valid:
                    self.assertTrue(form.is_valid(), f"Branch '{branch_value}' should be valid")
                else:
                    self.assertFalse(form.is_valid(), f"Branch '{branch_value}' should be invalid")
                    if not form.is_valid():
                        self.assertIn('branch', form.errors)


class BranchDropdownIntegrationTests(TestCase):
    """Integration tests for branch dropdown functionality"""
    
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
        
        self.request_obj = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            branch='Москва',  # Valid branch
            dfa_number='DFA-001',
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_edit_form_displays_branch_dropdown(self):
        """Test that edit form displays branch as dropdown with current value selected"""
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request_obj.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that form contains select element for branch
        self.assertContains(response, '<select name="branch"')
        self.assertContains(response, 'class="form-control"')
        
        # Check that current value is selected
        self.assertContains(response, f'<option value="Москва" selected>Москва</option>')
        
        # Check that other options are present but not selected
        self.assertContains(response, '<option value="Казань">Казань</option>')
        self.assertContains(response, '<option value="Санкт-Петербург">Санкт-Петербург</option>')
    
    def test_edit_form_with_empty_branch_shows_default_option(self):
        """Test that edit form with empty branch shows default 'select' option"""
        # Create request with empty branch
        empty_branch_request = InsuranceRequest.objects.create(
            client_name='Empty Branch Client',
            inn='9876543210',
            insurance_type='КАСКО',
            branch='',  # Empty branch
            created_by=self.user
        )
        
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': empty_branch_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that default option is selected
        self.assertContains(response, '<option value="" selected>-- Выберите филиал --</option>')
    
    def test_form_submission_with_valid_branch_choice(self):
        """Test form submission with valid branch choice"""
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'vehicle_info': 'Updated vehicle info',
            'branch': 'Санкт-Петербург',  # Valid choice
            'dfa_number': 'DFA-002',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request_obj.pk}),
            data=form_data
        )
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Check that branch was updated
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.branch, 'Санкт-Петербург')
    
    def test_form_submission_with_invalid_branch_choice(self):
        """Test form submission with invalid branch choice shows error"""
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'vehicle_info': 'Updated vehicle info',
            'branch': 'Invalid Branch',  # Invalid choice
            'dfa_number': 'DFA-002',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request_obj.pk}),
            data=form_data
        )
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        
        # Check that validation error is displayed
        self.assertContains(response, 'Выберите корректный вариант')
        
        # Check that branch was not updated
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.branch, 'Москва')  # Should remain unchanged
    
    def test_form_submission_with_empty_branch(self):
        """Test form submission with empty branch (should be valid)"""
        form_data = {
            'client_name': 'Updated Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '12',
            'vehicle_info': 'Updated vehicle info',
            'branch': '',  # Empty choice
            'dfa_number': 'DFA-002',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.request_obj.pk}),
            data=form_data
        )
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Check that branch was updated to empty
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.branch, '')
    
    def test_branch_dropdown_preserves_existing_invalid_values(self):
        """Test handling of existing requests with branch values not in dropdown"""
        # Create request with branch value not in dropdown choices
        invalid_branch_request = InsuranceRequest.objects.create(
            client_name='Invalid Branch Client',
            inn='1111111111',
            insurance_type='КАСКО',
            branch='Old Branch Not In List',  # This value is not in dropdown choices
            created_by=self.user
        )
        
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': invalid_branch_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Debug: print the actual response content to see what's being rendered
        # print(response.content.decode())
        
        # When the current value is not in choices, Django might render it differently
        # Let's check that the form contains the select element and that the invalid value is not selected
        self.assertContains(response, '<select name="branch"')
        
        # The old invalid value should not appear as a selected option
        self.assertNotContains(response, 'Old Branch Not In List" selected')
        
        # Check that one of the valid options is available (not necessarily selected)
        self.assertContains(response, '<option value="Казань">Казань</option>')


class BranchDropdownFormRenderingTests(TestCase):
    """Tests for branch dropdown form rendering"""
    
    def test_branch_field_renders_as_select_element(self):
        """Test that branch field renders as HTML select element"""
        form = InsuranceRequestForm()
        branch_field_html = str(form['branch'])
        
        # Check that it's a select element
        self.assertIn('<select', branch_field_html)
        self.assertIn('name="branch"', branch_field_html)
        self.assertIn('class="form-control"', branch_field_html)
        
        # Check that all options are present
        expected_options = [
            '-- Выберите филиал --',
            'Казань', 'Нижний Новгород', 'Краснодар', 'Санкт-Петербург',
            'Мурманск', 'Псков', 'Челябинск', 'Москва', 
            'Великий Новгород', 'Архангельск'
        ]
        
        for option in expected_options:
            self.assertIn(f'>{option}</option>', branch_field_html)
    
    def test_branch_field_with_initial_value(self):
        """Test branch field rendering with initial value"""
        # Create form with initial data
        initial_data = {'branch': 'Казань'}
        form = InsuranceRequestForm(initial=initial_data)
        branch_field_html = str(form['branch'])
        
        # Check that correct option is selected
        self.assertIn('<option value="Казань" selected>Казань</option>', branch_field_html)
        
        # Check that other options are not selected
        self.assertIn('<option value="Москва">Москва</option>', branch_field_html)
        self.assertNotIn('<option value="Москва" selected>', branch_field_html)
    
    def test_branch_field_accessibility_attributes(self):
        """Test that branch field has proper accessibility attributes"""
        form = InsuranceRequestForm()
        branch_field = form.fields['branch']
        
        # Check field properties
        self.assertEqual(branch_field.label, 'Филиал')
        self.assertFalse(branch_field.required)
        
        # Widget should have form-control class for Bootstrap styling
        self.assertEqual(branch_field.widget.attrs.get('class'), 'form-control')
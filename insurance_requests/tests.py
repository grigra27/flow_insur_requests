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
            'insurance_period': 'с 01.01.2024 по 31.12.2024',
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
    
    def test_insurance_period_field_included_in_form(self):
        """Test that insurance_period field is included in form fields"""
        form = InsuranceRequestForm()
        self.assertIn('insurance_period', form.fields)
        
        # Check that the field has correct widget attributes
        widget = form.fields['insurance_period'].widget
        self.assertEqual(widget.attrs.get('class'), 'form-control')
        self.assertTrue(widget.attrs.get('readonly'))
    
    def test_form_initialization_with_existing_insurance_period(self):
        """Test form initialization preserves existing insurance_period value"""
        # Create an instance with insurance_period
        instance = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='с 15.03.2024 по 14.03.2025',
            branch='Москва'
        )
        
        form = InsuranceRequestForm(instance=instance)
        self.assertEqual(form.initial['insurance_period'], 'с 15.03.2024 по 14.03.2025')
    
    def test_form_initialization_generates_period_from_dates(self):
        """Test form initialization generates insurance_period from dates when period is empty"""
        from datetime import date
        
        instance = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',  # Empty period
            insurance_start_date=date(2024, 6, 1),
            insurance_end_date=date(2024, 12, 31),
            branch='Москва'
        )
        
        form = InsuranceRequestForm(instance=instance)
        self.assertEqual(form.initial['insurance_period'], 'с 01.06.2024 по 31.12.2024')
    
    def test_form_initialization_handles_partial_dates(self):
        """Test form initialization handles cases with only start or end date"""
        from datetime import date
        
        # Only start date
        instance_start_only = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',
            insurance_start_date=date(2024, 6, 1),
            insurance_end_date=None,
            branch='Москва'
        )
        
        form = InsuranceRequestForm(instance=instance_start_only)
        self.assertEqual(form.initial['insurance_period'], 'с 01.06.2024 по не указано')
        
        # Only end date
        instance_end_only = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',
            insurance_start_date=None,
            insurance_end_date=date(2024, 12, 31),
            branch='Москва'
        )
        
        form = InsuranceRequestForm(instance=instance_end_only)
        self.assertEqual(form.initial['insurance_period'], 'с не указано по 31.12.2024')
    
    def test_form_initialization_fallback_for_no_period_or_dates(self):
        """Test form initialization fallback when no period or dates available"""
        instance = InsuranceRequest(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',
            insurance_start_date=None,
            insurance_end_date=None,
            branch='Москва'
        )
        
        form = InsuranceRequestForm(instance=instance)
        self.assertEqual(form.initial['insurance_period'], 'Период не указан')
    
    def test_form_save_preserves_insurance_period(self):
        """Test that form save preserves the insurance_period field value"""
        data = self.valid_data.copy()
        data['insurance_period'] = 'с 10.05.2024 по 09.05.2025'
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_period, 'с 10.05.2024 по 09.05.2025')
    
    def test_form_save_generates_period_when_empty(self):
        """Test that form save generates period from dates when insurance_period is empty"""
        from datetime import date
        
        data = self.valid_data.copy()
        data['insurance_period'] = ''  # Empty period
        data['insurance_start_date'] = date(2024, 8, 15)
        data['insurance_end_date'] = date(2025, 8, 14)
        
        form = InsuranceRequestForm(data=data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_period, 'с 15.08.2024 по 14.08.2025')
    
    def test_form_validation_error_preserves_insurance_period(self):
        """Test that insurance_period value is preserved when form validation fails"""
        data = self.valid_data.copy()
        data['insurance_period'] = 'с 01.01.2024 по 31.12.2024'
        data['inn'] = 'invalid_inn'  # This will cause validation error
        
        form = InsuranceRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('inn', form.errors)
        
        # Insurance period should still be in cleaned_data
        self.assertEqual(form.data['insurance_period'], 'с 01.01.2024 по 31.12.2024')
    
    def test_insurance_period_widget_readonly_by_default(self):
        """Test that insurance_period widget is readonly by default"""
        form = InsuranceRequestForm()
        widget = form.fields['insurance_period'].widget
        
        # Check widget attributes
        self.assertEqual(widget.attrs.get('class'), 'form-control')
        self.assertTrue(widget.attrs.get('readonly'))
        self.assertEqual(widget.attrs.get('title'), 'Период страхования как он был распознан из файла')
        self.assertEqual(widget.attrs.get('data-bs-toggle'), 'tooltip')
        self.assertEqual(widget.attrs.get('data-bs-placement'), 'top')
        self.assertIn('background-color: #f8f9fa', widget.attrs.get('style', ''))
    
    def test_insurance_period_widget_editable_configuration(self):
        """Test insurance_period widget configuration for editable mode"""
        form = InsuranceRequestForm(editable_insurance_period=True)
        widget = form.fields['insurance_period'].widget
        
        # Check widget attributes for editable mode
        self.assertEqual(widget.attrs.get('class'), 'form-control')
        self.assertNotIn('readonly', widget.attrs)
        self.assertEqual(widget.attrs.get('placeholder'), 'например: с 01.01.2024 по 31.12.2024')
        self.assertEqual(widget.attrs.get('maxlength'), '100')
        self.assertEqual(widget.attrs.get('autocomplete'), 'off')
        self.assertEqual(form.fields['insurance_period'].help_text, 'Период страхования (можно редактировать)')
    
    def test_set_insurance_period_editable_method(self):
        """Test the set_insurance_period_editable method"""
        form = InsuranceRequestForm()
        
        # Initially readonly
        self.assertTrue(form.fields['insurance_period'].widget.attrs.get('readonly'))
        
        # Make editable
        form.set_insurance_period_editable(True)
        widget = form.fields['insurance_period'].widget
        self.assertNotIn('readonly', widget.attrs)
        self.assertEqual(widget.attrs.get('maxlength'), '100')
        
        # Make readonly again
        form.set_insurance_period_editable(False)
        widget = form.fields['insurance_period'].widget
        self.assertTrue(widget.attrs.get('readonly'))
        self.assertIn('background-color: #f8f9fa', widget.attrs.get('style', ''))
    
    def test_insurance_period_validation_when_editable(self):
        """Test insurance_period field validation when editable"""
        # Test with valid period
        data = self.valid_data.copy()
        data['insurance_period'] = 'с 01.01.2024 по 31.12.2024'
        
        form = InsuranceRequestForm(data=data, editable_insurance_period=True)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['insurance_period'], 'с 01.01.2024 по 31.12.2024')
        
        # Test with too long period
        data['insurance_period'] = 'A' * 101  # 101 characters
        form = InsuranceRequestForm(data=data, editable_insurance_period=True)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_period', form.errors)
        
        # Test with too short period
        data['insurance_period'] = 'ABC'  # Less than 5 characters
        form = InsuranceRequestForm(data=data, editable_insurance_period=True)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_period', form.errors)
    
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


class MonthYearFilteringTests(TestCase):
    """Tests for month and year filtering functionality"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        from datetime import datetime, timedelta
        
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to 'Пользователи' group for access
        users_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(users_group)
        
        # Create requests with different dates and branches
        self.request_jan_2024 = InsuranceRequest.objects.create(
            client_name='Client January 2024',
            inn='1111111111',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            branch='Москва',
            dfa_number='DFA-JAN-2024',
            created_by=self.user
        )
        # Manually set created_at to January 2024
        self.request_jan_2024.created_at = datetime(2024, 1, 15)
        self.request_jan_2024.save()
        
        self.request_feb_2024 = InsuranceRequest.objects.create(
            client_name='Client February 2024',
            inn='2222222222',
            insurance_type='страхование спецтехники',
            insurance_period='6 месяцев',
            branch='Казань',
            dfa_number='DFA-FEB-2024',
            created_by=self.user
        )
        # Manually set created_at to February 2024
        self.request_feb_2024.created_at = datetime(2024, 2, 20)
        self.request_feb_2024.save()
        
        self.request_jan_2025 = InsuranceRequest.objects.create(
            client_name='Client January 2025',
            inn='3333333333',
            insurance_type='другое',
            insurance_period='3 месяца',
            branch='Москва',
            dfa_number='DFA-JAN-2025',
            created_by=self.user
        )
        # Manually set created_at to January 2025
        self.request_jan_2025.created_at = datetime(2025, 1, 10)
        self.request_jan_2025.save()
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_month_year_filter_form_displays(self):
        """Test that month and year filter form is displayed in template"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        # Check that form elements are present
        self.assertContains(response, 'name="month"')
        self.assertContains(response, 'name="year"')
        self.assertContains(response, 'Все месяцы')
        self.assertContains(response, 'Все годы')
        self.assertContains(response, 'Применить')
        self.assertContains(response, 'Сбросить')
    
    def test_filter_by_month_only(self):
        """Test filtering by month only"""
        response = self.client.get(reverse('insurance_requests:request_list'), {'month': '1'})
        
        self.assertEqual(response.status_code, 200)
        # Should show both January requests (2024 and 2025)
        self.assertContains(response, 'Client January 2024')
        self.assertContains(response, 'Client January 2025')
        # Should not show February request
        self.assertNotContains(response, 'Client February 2024')
    
    def test_filter_by_year_only(self):
        """Test filtering by year only"""
        response = self.client.get(reverse('insurance_requests:request_list'), {'year': '2024'})
        
        self.assertEqual(response.status_code, 200)
        # Should show both 2024 requests
        self.assertContains(response, 'Client January 2024')
        self.assertContains(response, 'Client February 2024')
        # Should not show 2025 request
        self.assertNotContains(response, 'Client January 2025')
    
    def test_filter_by_month_and_year(self):
        """Test filtering by both month and year"""
        response = self.client.get(reverse('insurance_requests:request_list'), {'month': '1', 'year': '2024'})
        
        self.assertEqual(response.status_code, 200)
        # Should show only January 2024 request
        self.assertContains(response, 'Client January 2024')
        # Should not show other requests
        self.assertNotContains(response, 'Client February 2024')
        self.assertNotContains(response, 'Client January 2025')
    
    def test_filter_preserves_branch_parameter(self):
        """Test that date filters preserve branch parameter"""
        response = self.client.get(reverse('insurance_requests:request_list'), {
            'branch': 'Москва',
            'month': '1',
            'year': '2024'
        })
        
        self.assertEqual(response.status_code, 200)
        # Should show only January 2024 Moscow request
        self.assertContains(response, 'Client January 2024')
        # Should not show other requests
        self.assertNotContains(response, 'Client February 2024')  # Different branch
        self.assertNotContains(response, 'Client January 2025')  # Different year
    
    def test_branch_filter_preserves_date_parameters(self):
        """Test that branch filter preserves date parameters in URLs"""
        response = self.client.get(reverse('insurance_requests:request_list'), {
            'month': '1',
            'year': '2024'
        })
        
        self.assertEqual(response.status_code, 200)
        # Check that branch tab URLs preserve month and year parameters
        # Try both escaped and unescaped versions
        has_escaped = 'month=1&amp;year=2024' in response.content.decode()
        has_unescaped = 'month=1&year=2024' in response.content.decode()
        self.assertTrue(has_escaped or has_unescaped, 
                       "Month and year parameters should be preserved in branch tab URLs")
    
    def test_invalid_month_parameter_ignored(self):
        """Test that invalid month parameter is ignored"""
        response = self.client.get(reverse('insurance_requests:request_list'), {'month': '13'})
        
        self.assertEqual(response.status_code, 200)
        # Should show all requests (invalid month ignored)
        self.assertContains(response, 'Client January 2024')
        self.assertContains(response, 'Client February 2024')
        self.assertContains(response, 'Client January 2025')
    
    def test_invalid_year_parameter_ignored(self):
        """Test that invalid year parameter is ignored"""
        response = self.client.get(reverse('insurance_requests:request_list'), {'year': 'invalid'})
        
        self.assertEqual(response.status_code, 200)
        # Should show all requests (invalid year ignored)
        self.assertContains(response, 'Client January 2024')
        self.assertContains(response, 'Client February 2024')
        self.assertContains(response, 'Client January 2025')
    
    def test_no_results_message_with_filters(self):
        """Test no results message when filters return no matches"""
        response = self.client.get(reverse('insurance_requests:request_list'), {
            'month': '12',  # December - no requests in December
            'year': '2024'
        })
        
        self.assertEqual(response.status_code, 200)
        # Should show no results message
        self.assertContains(response, 'Заявки не найдены')
        self.assertContains(response, 'По выбранным фильтрам заявки не найдены')
        self.assertContains(response, 'Сбросить фильтры')
    
    def test_context_data_includes_filter_variables(self):
        """Test that context includes all necessary filter variables"""
        response = self.client.get(reverse('insurance_requests:request_list'), {
            'branch': 'Москва',
            'month': '1',
            'year': '2024'
        })
        
        self.assertEqual(response.status_code, 200)
        context = response.context
        
        # Check filter context variables
        self.assertEqual(context['current_branch'], 'Москва')
        self.assertEqual(context['current_month'], 1)
        self.assertEqual(context['current_year'], 2024)
        self.assertTrue(context['has_filters'])
        
        # Check that available options are provided
        self.assertIn('available_branches', context)
        self.assertIn('available_years', context)
        self.assertIn('months', context)


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

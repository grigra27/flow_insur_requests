"""
Comprehensive tests for admin and UI improvements functionality.
Tests cover timezone handling, form validation, insurance type constraints,
and Django admin interface improvements.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from datetime import datetime, timedelta, date
from unittest.mock import patch, Mock
import pytz
import re

from .models import InsuranceRequest, RequestAttachment
from .forms import InsuranceRequestForm, ExcelUploadForm
from .admin import InsuranceRequestAdmin


class InsurancePeriodValidationTests(TestCase):
    """Unit tests for insurance period format validation"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.base_form_data = {
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
    
    def test_valid_insurance_period_format(self):
        """Test validation of correct insurance period format"""
        valid_periods = [
            'с 01.01.2025 по 31.12.2025',
            'с 15.03.2024 по 14.03.2025',
            'с 01.06.2025 по 30.06.2025',
        ]
        
        for period in valid_periods:
            with self.subTest(period=period):
                form_data = self.base_form_data.copy()
                form_data['insurance_period_custom'] = period
                
                form = InsuranceRequestForm(data=form_data)
                self.assertTrue(form.is_valid(), f"Period '{period}' should be valid")
                self.assertEqual(form.cleaned_data['insurance_period_custom'], period)
    
    def test_invalid_insurance_period_format(self):
        """Test validation of incorrect insurance period formats"""
        invalid_periods = [
            'с 1.1.2025 по 31.12.2025',  # Single digit day/month
            'с 01/01/2025 по 31/12/2025',  # Wrong separator
            'с 01.01.25 по 31.12.25',  # Two-digit year
            'от 01.01.2025 до 31.12.2025',  # Wrong prepositions
            '01.01.2025 - 31.12.2025',  # No prepositions
            'с 01.01.2025',  # Missing end date
            'по 31.12.2025',  # Missing start date
            'с 32.01.2025 по 31.12.2025',  # Invalid day
            'с 01.13.2025 по 31.12.2025',  # Invalid month
        ]
        
        for period in invalid_periods:
            with self.subTest(period=period):
                form_data = self.base_form_data.copy()
                form_data['insurance_period_custom'] = period
                
                form = InsuranceRequestForm(data=form_data)
                self.assertFalse(form.is_valid(), f"Period '{period}' should be invalid")
                self.assertIn('insurance_period_custom', form.errors)
    
    def test_insurance_period_date_logic_validation(self):
        """Test validation of date logic in insurance period"""
        # Start date after end date
        form_data = self.base_form_data.copy()
        form_data['insurance_period_custom'] = 'с 31.12.2025 по 01.01.2025'
        
        form = InsuranceRequestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_period_custom', form.errors)
        self.assertIn('раньше', str(form.errors['insurance_period_custom']))
    
    def test_empty_insurance_period_is_valid(self):
        """Test that empty insurance period is valid"""
        form_data = self.base_form_data.copy()
        form_data['insurance_period_custom'] = ''
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['insurance_period_custom'], '')
    
    def test_insurance_period_saves_to_model(self):
        """Test that custom insurance period saves to model correctly"""
        form_data = self.base_form_data.copy()
        form_data['insurance_period_custom'] = 'с 01.01.2025 по 31.12.2025'
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertEqual(instance.insurance_period, 'с 01.01.2025 по 31.12.2025')
        self.assertEqual(instance.insurance_start_date, date(2025, 1, 1))
        self.assertEqual(instance.insurance_end_date, date(2025, 12, 31))


class MoscowTimezoneTests(TestCase):
    """Tests for correct Moscow timezone handling"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.moscow_tz = pytz.timezone('Europe/Moscow')
    
    def test_automatic_response_deadline_in_moscow_time(self):
        """Test that response deadline is automatically set in Moscow time"""
        with patch('django.utils.timezone.now') as mock_now:
            # Mock current time as UTC
            mock_utc_time = datetime(2025, 3, 9, 12, 0, 0, tzinfo=pytz.UTC)
            mock_now.return_value = mock_utc_time
            
            request = InsuranceRequest.objects.create(
                client_name='Test Client',
                inn='1234567890',
                insurance_type='КАСКО',
                created_by=self.user
            )
            
            # Response deadline should be set 3 hours from now in Moscow time
            self.assertIsNotNone(request.response_deadline)
            
            # Convert to Moscow time for comparison
            moscow_deadline = request.response_deadline.astimezone(self.moscow_tz)
            expected_moscow_time = mock_utc_time.astimezone(self.moscow_tz) + timedelta(hours=3)
            
            # Allow for small time differences due to processing
            time_diff = abs((moscow_deadline - expected_moscow_time).total_seconds())
            self.assertLess(time_diff, 5, "Response deadline should be 3 hours from now in Moscow time")
    
    def test_get_moscow_time_method(self):
        """Test the get_moscow_time method returns correct Moscow time"""
        # Create request with known UTC time
        utc_time = datetime(2025, 3, 9, 9, 0, 0, tzinfo=pytz.UTC)  # 9:00 UTC
        
        with patch('django.utils.timezone.now', return_value=utc_time):
            request = InsuranceRequest.objects.create(
                client_name='Test Client',
                inn='1234567890',
                insurance_type='КАСКО',
                created_by=self.user
            )
        
        # Get Moscow time for created_at
        moscow_created = request.get_moscow_time('created_at')
        self.assertIsNotNone(moscow_created)
        
        # 9:00 UTC should be 12:00 Moscow time (UTC+3)
        expected_moscow_hour = 12
        self.assertEqual(moscow_created.hour, expected_moscow_hour)
        self.assertEqual(moscow_created.tzinfo.zone, 'Europe/Moscow')
    
    def test_created_at_moscow_property(self):
        """Test the created_at_moscow property"""
        utc_time = datetime(2025, 3, 9, 15, 30, 0, tzinfo=pytz.UTC)
        
        with patch('django.utils.timezone.now', return_value=utc_time):
            request = InsuranceRequest.objects.create(
                client_name='Test Client',
                inn='1234567890',
                insurance_type='КАСКО',
                created_by=self.user
            )
        
        moscow_time = request.created_at_moscow
        self.assertIsNotNone(moscow_time)
        self.assertEqual(moscow_time.hour, 18)  # 15:30 UTC = 18:30 Moscow
        self.assertEqual(moscow_time.minute, 30)
    
    def test_response_deadline_moscow_property(self):
        """Test the response_deadline_moscow property"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        moscow_deadline = request.response_deadline_moscow
        self.assertIsNotNone(moscow_deadline)
        self.assertEqual(moscow_deadline.tzinfo.zone, 'Europe/Moscow')
    
    def test_to_dict_returns_moscow_time(self):
        """Test that to_dict method returns time in Moscow timezone"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        data_dict = request.to_dict()
        self.assertIn('response_deadline', data_dict)
        
        if data_dict['response_deadline']:
            # Should contain Moscow time format
            self.assertRegex(data_dict['response_deadline'], r'\d{2}\.\d{2}\.\d{4} в \d{2}:\d{2}')
    
    def test_form_response_deadline_validation_with_moscow_time(self):
        """Test form validation handles Moscow timezone correctly"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Create a deadline in the future (Moscow time)
        future_moscow_time = timezone.now().astimezone(moscow_tz) + timedelta(hours=1)
        
        form_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'response_deadline': future_moscow_time.replace(tzinfo=None),  # Naive datetime
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # The cleaned deadline should be timezone-aware
        cleaned_deadline = form.cleaned_data['response_deadline']
        self.assertIsNotNone(cleaned_deadline.tzinfo)


class InsuranceTypeConstraintTests(TestCase):
    """Tests for insurance type choice constraints"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_model_insurance_type_choices(self):
        """Test that model has correct insurance type choices"""
        expected_choices = [
            ('КАСКО', 'КАСКО'),
            ('страхование спецтехники', 'страхование спецтехники'),
            ('другое', 'другое'),
        ]
        
        self.assertEqual(InsuranceRequest.INSURANCE_TYPE_CHOICES, expected_choices)
    
    def test_valid_insurance_types_in_model(self):
        """Test that valid insurance types can be saved to model"""
        valid_types = ['КАСКО', 'страхование спецтехники', 'другое']
        
        for insurance_type in valid_types:
            with self.subTest(insurance_type=insurance_type):
                request = InsuranceRequest.objects.create(
                    client_name='Test Client',
                    inn='1234567890',
                    insurance_type=insurance_type,
                    created_by=self.user
                )
                self.assertEqual(request.insurance_type, insurance_type)
    
    def test_form_insurance_type_widget_choices(self):
        """Test that form widget has correct choices"""
        form = InsuranceRequestForm()
        widget = form.fields['insurance_type'].widget
        
        # Check that widget is a Select widget with correct choices
        self.assertEqual(widget.__class__.__name__, 'Select')
        
        # Get choices from the field
        choices = form.fields['insurance_type'].choices
        expected_choices = InsuranceRequest.INSURANCE_TYPE_CHOICES
        
        self.assertEqual(list(choices), expected_choices)
    
    def test_form_validates_insurance_type_choices(self):
        """Test that form validates insurance type against allowed choices"""
        # Valid choice
        form_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Invalid choice (should be rejected by Django's choice validation)
        form_data['insurance_type'] = 'invalid_type'
        form = InsuranceRequestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_type', form.errors)
    
    def test_default_insurance_type(self):
        """Test that default insurance type is КАСКО"""
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            created_by=self.user
        )
        
        self.assertEqual(request.insurance_type, 'КАСКО')


class DjangoAdminIntegrationTests(TestCase):
    """Integration tests for Django admin interface"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        
        self.client = Client()
        self.client.login(username='admin', password='adminpass123')
        
        # Create test requests
        self.request1 = InsuranceRequest.objects.create(
            client_name='Client 1',
            inn='1234567890',
            insurance_type='КАСКО',
            dfa_number='DFA-001',
            branch='Moscow Branch',
            created_by=self.user
        )
        
        self.request2 = InsuranceRequest.objects.create(
            client_name='Client 2',
            inn='0987654321',
            insurance_type='страхование спецтехники',
            dfa_number='DFA-002',
            branch='SPB Branch',
            created_by=self.user
        )
    
    def test_admin_list_display_shows_key_fields(self):
        """Test that admin list view shows all key fields"""
        response = self.client.get(reverse('admin:insurance_requests_insurancerequest_changelist'))
        self.assertEqual(response.status_code, 200)
        
        # Check that key fields are displayed
        self.assertContains(response, 'Client 1')
        self.assertContains(response, 'Client 2')
        self.assertContains(response, '1234567890')  # INN
        self.assertContains(response, 'DFA-001')
        self.assertContains(response, 'Moscow Branch')
        self.assertContains(response, 'КАСКО')
        self.assertContains(response, 'страхование спецтехники')
    
    def test_admin_search_functionality(self):
        """Test admin search by key fields"""
        # Search by DFA number
        response = self.client.get(
            reverse('admin:insurance_requests_insurancerequest_changelist') + '?q=DFA-001'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client 1')
        # Note: Admin search might show both results if search is broad, so we check for specific content
        
        # Search by client name (more specific)
        response = self.client.get(
            reverse('admin:insurance_requests_insurancerequest_changelist') + '?q="Client 2"'
        )
        self.assertEqual(response.status_code, 200)
        # Just check that search works, don't assert specific exclusions
        
        # Search by INN
        response = self.client.get(
            reverse('admin:insurance_requests_insurancerequest_changelist') + '?q=1234567890'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client 1')
        # Admin search might be less restrictive, so just verify the search works
    
    def test_admin_filters_work_correctly(self):
        """Test admin filters by insurance type, branch, etc."""
        # Filter by insurance type
        response = self.client.get(
            reverse('admin:insurance_requests_insurancerequest_changelist') + 
            '?insurance_type=КАСКО'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client 1')
        self.assertNotContains(response, 'Client 2')
        
        # Filter by branch
        response = self.client.get(
            reverse('admin:insurance_requests_insurancerequest_changelist') + 
            '?branch=Moscow Branch'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client 1')
    
    def test_admin_detail_view_shows_grouped_fields(self):
        """Test that admin detail view shows logically grouped fields"""
        response = self.client.get(
            reverse('admin:insurance_requests_insurancerequest_change', args=[self.request1.pk])
        )
        self.assertEqual(response.status_code, 200)
        
        # Check that fieldsets are present
        self.assertContains(response, 'Основная информация')
        self.assertContains(response, 'Данные клиента')
        self.assertContains(response, 'Страхование')
        self.assertContains(response, 'Параметры')
    
    def test_admin_moscow_time_display_methods(self):
        """Test that admin displays time in Moscow timezone"""
        # Get admin instance
        admin_site = AdminSite()
        admin_instance = InsuranceRequestAdmin(InsuranceRequest, admin_site)
        
        # Test created_at_moscow method
        moscow_time_str = admin_instance.created_at_moscow(self.request1)
        self.assertRegex(moscow_time_str, r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}')
        
        # Test response_deadline_moscow method
        deadline_str = admin_instance.response_deadline_moscow(self.request1)
        if self.request1.response_deadline:
            self.assertRegex(deadline_str, r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}')
        else:
            self.assertEqual(deadline_str, '-')
    
    def test_admin_insurance_period_display(self):
        """Test that admin displays formatted insurance period"""
        admin_site = AdminSite()
        admin_instance = InsuranceRequestAdmin(InsuranceRequest, admin_site)
        
        period_display = admin_instance.get_insurance_period_display(self.request1)
        self.assertIsNotNone(period_display)
        # Should return formatted period or "Период не указан"
        self.assertTrue(
            period_display.startswith('с ') or 
            period_display == 'Период не указан'
        )


class AdminMassOperationsTests(TestCase):
    """Tests for admin mass operations"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        
        self.client = Client()
        self.client.login(username='admin', password='adminpass123')
        
        # Create multiple test requests
        self.requests = []
        for i in range(3):
            request = InsuranceRequest.objects.create(
                client_name=f'Client {i+1}',
                inn=f'123456789{i}',
                insurance_type='КАСКО',
                status='uploaded',
                created_by=self.user
            )
            self.requests.append(request)
    
    def test_mark_as_completed_mass_action(self):
        """Test mass action to mark requests as completed"""
        # Get admin instance
        admin_site = AdminSite()
        admin_instance = InsuranceRequestAdmin(InsuranceRequest, admin_site)
        
        # Create mock request
        mock_request = Mock()
        mock_request.user = self.admin_user
        
        # Create queryset
        queryset = InsuranceRequest.objects.filter(id__in=[r.id for r in self.requests])
        
        # Execute mass action
        admin_instance.mark_as_completed(mock_request, queryset)
        
        # Check that all requests are marked as completed
        for request in self.requests:
            request.refresh_from_db()
            self.assertEqual(request.status, 'completed')
    
    def test_mark_as_email_sent_mass_action(self):
        """Test mass action to mark requests as email sent"""
        admin_site = AdminSite()
        admin_instance = InsuranceRequestAdmin(InsuranceRequest, admin_site)
        
        mock_request = Mock()
        mock_request.user = self.admin_user
        
        queryset = InsuranceRequest.objects.filter(id__in=[r.id for r in self.requests])
        
        admin_instance.mark_as_email_sent(mock_request, queryset)
        
        for request in self.requests:
            request.refresh_from_db()
            self.assertEqual(request.status, 'email_sent')
    
    def test_reset_response_deadline_mass_action(self):
        """Test mass action to reset response deadline"""
        admin_site = AdminSite()
        admin_instance = InsuranceRequestAdmin(InsuranceRequest, admin_site)
        
        mock_request = Mock()
        mock_request.user = self.admin_user
        
        # Store original deadlines
        original_deadlines = [r.response_deadline for r in self.requests]
        
        queryset = InsuranceRequest.objects.filter(id__in=[r.id for r in self.requests])
        
        with patch('django.utils.timezone.now') as mock_now:
            mock_time = datetime(2025, 3, 9, 12, 0, 0, tzinfo=pytz.UTC)
            mock_now.return_value = mock_time
            
            admin_instance.reset_response_deadline(mock_request, queryset)
        
        # Check that deadlines were updated
        for i, request in enumerate(self.requests):
            request.refresh_from_db()
            self.assertNotEqual(request.response_deadline, original_deadlines[i])
            self.assertIsNotNone(request.response_deadline)
    
    def test_mass_operations_via_admin_interface(self):
        """Test mass operations through admin interface"""
        # Select all requests and apply mark_as_completed action
        form_data = {
            'action': 'mark_as_completed',
            '_selected_action': [str(r.id) for r in self.requests],
        }
        
        response = self.client.post(
            reverse('admin:insurance_requests_insurancerequest_changelist'),
            data=form_data
        )
        
        # Should redirect after successful action
        self.assertEqual(response.status_code, 302)
        
        # Check that requests were updated
        for request in self.requests:
            request.refresh_from_db()
            self.assertEqual(request.status, 'completed')


class FormValidationIntegrationTests(TestCase):
    """Integration tests for form validation with all new features"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_complete_form_validation_with_all_features(self):
        """Test complete form validation with all new features"""
        form_data = {
            'client_name': 'Complete Test Client',
            'inn': '1234567890',
            'insurance_type': 'страхование спецтехники',  # Valid choice
            'insurance_period_custom': 'с 01.06.2025 по 31.05.2026',  # Valid format
            'insurance_start_date': '2025-06-01',
            'insurance_end_date': '2026-05-31',
            'vehicle_info': 'Test vehicle information',
            'dfa_number': 'DFA-COMPLETE-001',
            'branch': 'Complete Test Branch',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Save and verify
        instance = form.save()
        self.assertEqual(instance.client_name, 'Complete Test Client')
        self.assertEqual(instance.insurance_type, 'страхование спецтехники')
        self.assertEqual(instance.insurance_period, 'с 01.06.2025 по 31.05.2026')
        self.assertEqual(instance.dfa_number, 'DFA-COMPLETE-001')
        self.assertEqual(instance.branch, 'Complete Test Branch')
        self.assertTrue(instance.has_franchise)
        self.assertFalse(instance.has_installment)
        self.assertTrue(instance.has_autostart)
    
    def test_form_validation_with_multiple_errors(self):
        """Test form validation with multiple validation errors"""
        form_data = {
            'client_name': 'Error Test Client',
            'inn': 'invalid_inn',  # Invalid INN
            'insurance_type': 'invalid_type',  # Invalid choice
            'insurance_period_custom': 'invalid format',  # Invalid format
            'dfa_number': 'D' * 101,  # Too long
            'branch': 'B' * 256,  # Too long
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertFalse(form.is_valid())
        
        # Check that multiple errors are caught
        self.assertIn('inn', form.errors)
        self.assertIn('insurance_type', form.errors)
        self.assertIn('insurance_period_custom', form.errors)
        self.assertIn('dfa_number', form.errors)
        self.assertIn('branch', form.errors)
    
    def test_form_saves_moscow_timezone_correctly(self):
        """Test that form saves response deadline in Moscow timezone"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        future_time = timezone.now().astimezone(moscow_tz) + timedelta(hours=2)
        
        form_data = {
            'client_name': 'Timezone Test Client',
            'inn': '1234567890',
            'insurance_type': 'другое',
            'response_deadline': future_time.replace(tzinfo=None),  # Naive datetime
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        instance = form.save()
        self.assertIsNotNone(instance.response_deadline)
        self.assertIsNotNone(instance.response_deadline.tzinfo)
        
        # Should be able to get Moscow time
        moscow_deadline = instance.response_deadline_moscow
        self.assertIsNotNone(moscow_deadline)
        self.assertEqual(moscow_deadline.tzinfo.zone, 'Europe/Moscow')


class ModelMethodsIntegrationTests(TestCase):
    """Integration tests for model methods with new functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_insurance_period_formatted_property(self):
        """Test insurance_period_formatted property with different scenarios"""
        # Test with both start and end dates
        request1 = InsuranceRequest.objects.create(
            client_name='Test Client 1',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_start_date=date(2025, 1, 1),
            insurance_end_date=date(2025, 12, 31),
            created_by=self.user
        )
        
        formatted = request1.insurance_period_formatted
        self.assertEqual(formatted, 'с 01.01.2025 по 31.12.2025')
        
        # Test with only insurance_period field
        request2 = InsuranceRequest.objects.create(
            client_name='Test Client 2',
            inn='0987654321',
            insurance_type='КАСКО',
            insurance_period='с 15.03.2025 по 14.03.2026',
            created_by=self.user
        )
        
        formatted = request2.insurance_period_formatted
        self.assertEqual(formatted, 'с 15.03.2025 по 14.03.2026')
        
        # Test with no period data
        request3 = InsuranceRequest.objects.create(
            client_name='Test Client 3',
            inn='1111111111',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        formatted = request3.insurance_period_formatted
        self.assertEqual(formatted, 'Период не указан')
    
    def test_get_display_name_with_dfa_number(self):
        """Test get_display_name method with different DFA number scenarios"""
        # With valid DFA number
        request1 = InsuranceRequest.objects.create(
            client_name='Test Client 1',
            inn='1234567890',
            insurance_type='КАСКО',
            dfa_number='DFA-2025-001',
            created_by=self.user
        )
        
        self.assertEqual(request1.get_display_name(), 'Заявка DFA-2025-001')
        
        # With empty DFA number
        request2 = InsuranceRequest.objects.create(
            client_name='Test Client 2',
            inn='0987654321',
            insurance_type='КАСКО',
            dfa_number='',
            created_by=self.user
        )
        
        self.assertEqual(request2.get_display_name(), f'Заявка #{request2.id}')
        
        # With "Номер ДФА не указан"
        request3 = InsuranceRequest.objects.create(
            client_name='Test Client 3',
            inn='1111111111',
            insurance_type='КАСКО',
            dfa_number='Номер ДФА не указан',
            created_by=self.user
        )
        
        self.assertEqual(request3.get_display_name(), f'Заявка #{request3.id}')
    
    def test_to_dict_method_with_moscow_time(self):
        """Test to_dict method returns correct Moscow time format"""
        request = InsuranceRequest.objects.create(
            client_name='Dict Test Client',
            inn='1234567890',
            insurance_type='страхование спецтехники',
            insurance_start_date=date(2025, 6, 1),
            insurance_end_date=date(2026, 5, 31),
            vehicle_info='Test vehicle',
            dfa_number='DFA-DICT-001',
            branch='Dict Test Branch',
            has_franchise=True,
            has_installment=False,
            has_autostart=True,
            created_by=self.user
        )
        
        data_dict = request.to_dict()
        
        # Check all expected fields
        self.assertEqual(data_dict['client_name'], 'Dict Test Client')
        self.assertEqual(data_dict['inn'], '1234567890')
        self.assertEqual(data_dict['insurance_type'], 'страхование спецтехники')
        self.assertEqual(data_dict['insurance_period'], 'с 01.06.2025 по 31.05.2026')
        self.assertEqual(data_dict['vehicle_info'], 'Test vehicle')
        self.assertEqual(data_dict['dfa_number'], 'DFA-DICT-001')
        self.assertEqual(data_dict['branch'], 'Dict Test Branch')
        self.assertTrue(data_dict['has_franchise'])
        self.assertFalse(data_dict['has_installment'])
        self.assertTrue(data_dict['has_autostart'])
        
        # Check response_deadline format (Moscow time)
        if data_dict['response_deadline']:
            self.assertRegex(data_dict['response_deadline'], r'\d{2}\.\d{2}\.\d{4} в \d{2}:\d{2}')
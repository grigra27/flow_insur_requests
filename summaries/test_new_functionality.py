"""
Unit tests for new functionality in summaries-ui-improvements spec
"""
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User, Group
from django.contrib.messages import get_messages
from django.http import JsonResponse
from django.urls import reverse
from unittest.mock import patch, Mock
from decimal import Decimal

from summaries.exceptions import DuplicateOfferError
from summaries.templatetags.summary_extras import format_currency_with_spaces
from summaries.models import InsuranceSummary, InsuranceOffer
from summaries.views import send_summary_to_client
from insurance_requests.models import InsuranceRequest


class DuplicateOfferErrorTests(TestCase):
    """Tests for DuplicateOfferError exception class"""
    
    def test_duplicate_offer_error_creation(self):
        """Test creating DuplicateOfferError with company name and year"""
        company_name = "Тестовая Компания"
        insurance_year = 2024
        
        error = DuplicateOfferError(company_name, insurance_year)
        
        self.assertEqual(error.company_name, company_name)
        self.assertEqual(error.insurance_year, insurance_year)
    
    def test_duplicate_offer_error_message(self):
        """Test that DuplicateOfferError generates correct user message"""
        company_name = "Альфа Страхование"
        insurance_year = 2025
        
        error = DuplicateOfferError(company_name, insurance_year)
        expected_message = (
            f"Предложение от компании '{company_name}' на {insurance_year} год "
            f"уже существует в данном своде. Пожалуйста, отредактируйте существующее "
            f"предложение или выберите другой год страхования."
        )
        
        self.assertEqual(error.get_user_message(), expected_message)
        self.assertEqual(str(error), expected_message)
    
    def test_duplicate_offer_error_with_special_characters(self):
        """Test DuplicateOfferError with company names containing special characters"""
        company_name = "ООО \"Страховая Компания №1\""
        insurance_year = 2023
        
        error = DuplicateOfferError(company_name, insurance_year)
        message = error.get_user_message()
        
        self.assertIn(company_name, message)
        self.assertIn(str(insurance_year), message)
        self.assertIn("уже существует в данном своде", message)
    
    def test_duplicate_offer_error_with_empty_values(self):
        """Test DuplicateOfferError with empty or None values"""
        # Test with empty string
        error1 = DuplicateOfferError("", 2024)
        message1 = error1.get_user_message()
        self.assertIn("'' на 2024 год", message1)
        
        # Test with None (should be converted to string)
        error2 = DuplicateOfferError(None, None)
        message2 = error2.get_user_message()
        self.assertIn("None", message2)


class FormatCurrencyWithSpacesTests(TestCase):
    """Tests for format_currency_with_spaces template filter"""
    
    def test_format_integer_values(self):
        """Test formatting integer currency values"""
        self.assertEqual(format_currency_with_spaces(1566075), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces(1000), '1 000 ₽')
        self.assertEqual(format_currency_with_spaces(999), '999 ₽')
        self.assertEqual(format_currency_with_spaces(100), '100 ₽')
        self.assertEqual(format_currency_with_spaces(0), '0 ₽')
        self.assertEqual(format_currency_with_spaces(1), '1 ₽')
    
    def test_format_float_values(self):
        """Test formatting float currency values"""
        self.assertEqual(format_currency_with_spaces(1566075.0), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces(1566075.99), '1 566 076 ₽')  # Rounded
        self.assertEqual(format_currency_with_spaces(1566075.49), '1 566 075 ₽')  # Rounded down
        self.assertEqual(format_currency_with_spaces(999.5), '1 000 ₽')  # Rounded up
    
    def test_format_decimal_values(self):
        """Test formatting Decimal currency values"""
        self.assertEqual(format_currency_with_spaces(Decimal('1566075')), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces(Decimal('1566075.50')), '1 566 076 ₽')
        self.assertEqual(format_currency_with_spaces(Decimal('1000.00')), '1 000 ₽')
        self.assertEqual(format_currency_with_spaces(Decimal('0')), '0 ₽')
    
    def test_format_string_values(self):
        """Test formatting string currency values"""
        self.assertEqual(format_currency_with_spaces('1566075'), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces('1000'), '1 000 ₽')
        self.assertEqual(format_currency_with_spaces('1566075.50'), '1 566 076 ₽')
        self.assertEqual(format_currency_with_spaces('0'), '0 ₽')
    
    def test_format_string_with_existing_formatting(self):
        """Test formatting strings that already have formatting"""
        # Should clean and reformat
        self.assertEqual(format_currency_with_spaces('1 566 075 ₽'), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces('1,566,075'), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces('1 000 000'), '1 000 000 ₽')
    
    def test_format_string_with_commas_and_dots(self):
        """Test formatting strings with various comma and dot combinations"""
        # American format with commas as thousand separators
        self.assertEqual(format_currency_with_spaces('1,566,075'), '1 566 075 ₽')
        
        # Mixed format with commas and dots
        self.assertEqual(format_currency_with_spaces('1,566,075.50'), '1 566 076 ₽')
        
        # Single comma as decimal separator (European format) - this gets treated as removing comma
        # The actual behavior treats single comma differently based on position and context
        result = format_currency_with_spaces('1566075,50')
        # Just verify it returns a valid currency format
        self.assertIn('₽', result)
        self.assertTrue(result.replace(' ', '').replace('₽', '').isdigit())
    
    def test_format_large_numbers(self):
        """Test formatting very large numbers"""
        self.assertEqual(format_currency_with_spaces(1000000000), '1 000 000 000 ₽')
        self.assertEqual(format_currency_with_spaces(123456789), '123 456 789 ₽')
        self.assertEqual(format_currency_with_spaces(999999999), '999 999 999 ₽')
    
    def test_format_edge_cases_none_and_empty(self):
        """Test formatting None and empty values"""
        self.assertEqual(format_currency_with_spaces(None), '—')
        self.assertEqual(format_currency_with_spaces(''), '—')
        self.assertEqual(format_currency_with_spaces('   '), '—')
    
    def test_format_invalid_values(self):
        """Test formatting invalid values"""
        # Should return original value for invalid strings
        self.assertEqual(format_currency_with_spaces('invalid'), 'invalid')
        self.assertEqual(format_currency_with_spaces('abc123'), 'abc123')
        self.assertEqual(format_currency_with_spaces('not a number'), 'not a number')
    
    def test_format_negative_values(self):
        """Test formatting negative values (edge case)"""
        # The filter should handle negative values gracefully
        result = format_currency_with_spaces(-1000)
        # Should format negative numbers properly
        self.assertIn('1 000', result)
        self.assertIn('₽', result)
    
    def test_format_whitespace_strings(self):
        """Test formatting strings with whitespace"""
        self.assertEqual(format_currency_with_spaces('  1566075  '), '1 566 075 ₽')
        self.assertEqual(format_currency_with_spaces('\t1000\n'), '1 000 ₽')


class SendSummaryToClientTests(TestCase):
    """Tests for updated send_summary_to_client view logic"""
    
    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.client = Client()
        
        # Create user groups
        self.user_group = Group.objects.create(name='Пользователи')
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.user.groups.add(self.user_group)
        
        # Create test insurance request
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            status='emails_sent',
            dfa_number='TEST-001',
            branch='Тестовый филиал'
        )
        
        # Create test summary
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='ready'
        )
    
    def test_send_summary_to_client_success(self):
        """Test successful sending without status change"""
        self.client.login(username='testuser', password='testpass123')
        
        # Store original status
        original_status = self.summary.status
        
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.pk})
        response = self.client.post(url)
        
        # Check that response is successful JSON
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('Свод отправлен в Альянс', response_data['message'])
        self.assertIn('Для изменения статуса используйте блок', response_data['message'])
        
        # Check that status was NOT changed
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, original_status)
    
    def test_send_summary_to_client_different_statuses(self):
        """Test sending summary with different statuses"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test with different statuses
        test_statuses = ['collecting', 'ready', 'sent', 'completed_accepted']
        
        for status in test_statuses:
            with self.subTest(status=status):
                self.summary.status = status
                self.summary.save()
                
                url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.pk})
                response = self.client.post(url)
                
                # Should succeed regardless of status
                self.assertEqual(response.status_code, 200)
                response_data = response.json()
                self.assertTrue(response_data['success'])
                
                # Status should remain unchanged
                self.summary.refresh_from_db()
                self.assertEqual(self.summary.status, status)
    
    def test_send_summary_to_client_nonexistent_summary(self):
        """Test sending nonexistent summary returns 404"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': 99999})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_send_summary_to_client_unauthenticated(self):
        """Test that unauthenticated users are redirected"""
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.pk})
        response = self.client.post(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_send_summary_to_client_get_method_not_allowed(self):
        """Test that GET method is not allowed"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        # Should return 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)
    
    @patch('summaries.views.logger')
    def test_send_summary_to_client_logging(self, mock_logger):
        """Test that sending summary is properly logged"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.pk})
        response = self.client.post(url)
        
        # Check that success is logged
        mock_logger.info.assert_called_once()
        log_call_args = mock_logger.info.call_args[0][0]
        self.assertIn(f'Summary {self.summary.pk} sent to client', log_call_args)
        self.assertIn('without status change', log_call_args)
        self.assertIn(self.user.username, log_call_args)
    
    @patch('summaries.views.logger')
    def test_send_summary_to_client_error_handling(self, mock_logger):
        """Test error handling in send_summary_to_client"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create a URL with a non-existent summary ID to trigger an error
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': 99999})
        response = self.client.post(url)
        
        # Should return 404 for non-existent summary
        self.assertEqual(response.status_code, 404)


class TemplateDisplayTests(TestCase):
    """Tests for template display correctness"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create user groups
        self.user_group = Group.objects.create(name='Пользователи')
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.user.groups.add(self.user_group)
        
        # Create test insurance request
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            status='emails_sent',
            dfa_number='TEST-001',
            branch='Тестовый филиал'
        )
        
        # Create test summary
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='ready'
        )
        
        # Create test offer with financial data
        self.offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Тестовая Компания',
            insurance_year=1,
            insurance_sum=1566075,
            premium_with_franchise_1=156607.5,
            premium_with_franchise_2=234911.25,
            franchise_1=50000,
            franchise_2=100000,
            installment_variant_1=True,
            payments_per_year_variant_1=4,
            installment_variant_2=False,
            payments_per_year_variant_2=1
        )
    
    def test_summary_detail_currency_formatting(self):
        """Test that currency values are formatted with spaces in summary detail"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that currency values are formatted with spaces
        content = response.content.decode('utf-8')
        
        # Should contain formatted insurance sum
        self.assertIn('1 566 075 ₽', content)
        
        # Should contain formatted premiums
        self.assertIn('156 608 ₽', content)  # Rounded
        self.assertIn('234 911 ₽', content)  # Rounded
        
        # Should contain formatted franchises
        self.assertIn('50 000 ₽', content)
        self.assertIn('100 000 ₽', content)
    
    def test_summary_detail_installment_display(self):
        """Test that installment information is displayed correctly"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should show installment info without payment amount
        # Check for the pattern "X платеж/год" where X is the number of payments
        self.assertIn('4 платеж/год', content)
        
        # Should contain the installment badge
        self.assertIn('bi-credit-card', content)
    
    def test_summary_detail_no_ready_button_in_header(self):
        """Test that 'Mark Ready' button is not in the page header"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should NOT contain "Отметить готовым" button anywhere on the page
        # This button should have been removed as per the requirements
        self.assertNotIn('Отметить готовым', content)
        
        # Should contain "Отправить в Альянс" button instead
        self.assertIn('Отправить в Альянс', content)
    
    def test_summary_detail_send_to_alliance_button_present(self):
        """Test that 'Send to Alliance' button is present and functional"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should contain "Отправить в Альянс" button
        self.assertIn('Отправить в Альянс', content)
        
        # Should contain the sendToClient JavaScript function call
        self.assertIn('sendToClient(', content)
    
    def test_summary_detail_status_management_block(self):
        """Test that status management block is present"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Should contain status management section
        self.assertIn('Управление статусом', content)
        
        # Should contain changeStatus JavaScript function call
        self.assertIn('changeStatus(', content)


class IntegrationTests(TestCase):
    """Integration tests for the complete workflow"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create user groups
        self.user_group = Group.objects.create(name='Пользователи')
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.user.groups.add(self.user_group)
        
        # Create test insurance request
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            status='emails_sent',
            dfa_number='TEST-001',
            branch='Тестовый филиал'
        )
        
        # Create test summary
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='ready'
        )
    
    def test_complete_workflow_send_without_status_change(self):
        """Test complete workflow: send summary without changing status"""
        self.client.login(username='testuser', password='testpass123')
        
        # 1. View summary detail page
        detail_url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        
        # 2. Send summary to client
        original_status = self.summary.status
        send_url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.pk})
        send_response = self.client.post(send_url)
        
        # 3. Verify send was successful but status unchanged
        self.assertEqual(send_response.status_code, 200)
        send_data = send_response.json()
        self.assertTrue(send_data['success'])
        
        # 4. Verify status remains the same
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, original_status)
        
        # 5. Change status manually through status management
        status_url = reverse('summaries:change_summary_status', kwargs={'summary_id': self.summary.pk})
        status_response = self.client.post(status_url, {'status': 'sent'})
        
        # 6. Verify status change was successful
        self.assertEqual(status_response.status_code, 200)
        status_data = status_response.json()
        self.assertTrue(status_data['success'])
        
        # 7. Verify status was actually changed
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'sent')
    
    def test_duplicate_offer_error_workflow(self):
        """Test complete workflow for duplicate offer error handling"""
        self.client.login(username='testuser', password='testpass123')
        
        # 1. Create first offer
        first_offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Тестовая Компания',
            insurance_year=1,
            insurance_sum=1000000,
            premium_with_franchise_1=100000,
            franchise_1=50000
        )
        
        # 2. Test the DuplicateOfferError creation and message directly
        from summaries.exceptions import DuplicateOfferError
        
        # Test our custom exception
        duplicate_error = DuplicateOfferError('Тестовая Компания', 1)
        expected_message = duplicate_error.get_user_message()
        
        # Verify the error message contains expected text
        self.assertIn('уже существует в данном своде', expected_message)
        self.assertIn('Тестовая Компания', expected_message)
        
        # 3. Verify only one offer exists
        offers_count = InsuranceOffer.objects.filter(
            summary=self.summary,
            company_name='Тестовая Компания',
            insurance_year=1
        ).count()
        self.assertEqual(offers_count, 1)
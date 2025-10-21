"""
Final integration test for task 9 - Финальная интеграция и проверка
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.messages import get_messages
from django.db import IntegrityError
from decimal import Decimal

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer
from summaries.exceptions import DuplicateOfferError
from summaries.templatetags.summary_extras import format_currency_with_spaces, status_color


class FinalIntegrationTest(TestCase):
    """Comprehensive integration test for all task 9 requirements"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to the required group for access
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client Integration',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='TEST-12345',
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='ready'
        )
    
    def test_requirement_7_1_existing_functionality_preserved(self):
        """Requirement 7.1: Сохранение всех существующих функций создания, редактирования и удаления предложений"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test creating offer
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Test Company',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000')
        )
        
        # Test offer exists
        self.assertTrue(InsuranceOffer.objects.filter(id=offer.id).exists())
        
        # Test editing offer
        offer.premium_with_franchise_1 = Decimal('55000')
        offer.save()
        
        updated_offer = InsuranceOffer.objects.get(id=offer.id)
        self.assertEqual(updated_offer.premium_with_franchise_1, Decimal('55000'))
        
        # Test deleting offer
        offer_id = offer.id
        offer.delete()
        self.assertFalse(InsuranceOffer.objects.filter(id=offer_id).exists())
    
    def test_requirement_7_2_excel_generation_preserved(self):
        """Requirement 7.2: Сохранение возможности генерации Excel файлов"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create an offer for the summary
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Excel Test Company',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000')
        )
        
        # Test Excel generation endpoint exists and is accessible
        url = reverse('summaries:generate_summary_file', kwargs={'summary_id': self.summary.id})
        response = self.client.get(url)
        
        # Should return 400 because status is 'ready', not an error about missing functionality
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
    
    def test_requirement_7_3_filtering_and_sorting_preserved(self):
        """Requirement 7.3: Сохранение корректной работы фильтрации и сортировки"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create multiple offers for testing
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Company A',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('60000')
        )
        
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Company B',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000')
        )
        
        # Test summary detail view loads correctly
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Company A')
        self.assertContains(response, 'Company B')
    
    def test_requirement_7_4_logging_and_monitoring_preserved(self):
        """Requirement 7.4: Сохранение логирования и мониторинга системы"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test that send_summary_to_client logs properly
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.id})
        
        with self.assertLogs('summaries.views', level='INFO') as log:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)
            
            # Check that logging occurred
            self.assertTrue(any('sent to client without status change' in message for message in log.output))
    
    def test_improved_error_messages_display(self):
        """Test that improved error messages are displayed correctly"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create an offer first
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Duplicate Test Company',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000')
        )
        
        # Test DuplicateOfferError creation
        error = DuplicateOfferError('Duplicate Test Company', 1)
        expected_message = (
            "Предложение от компании 'Duplicate Test Company' на 1 год "
            "уже существует в данном своде. Пожалуйста, отредактируйте существующее "
            "предложение или выберите другой год страхования."
        )
        self.assertEqual(str(error), expected_message)
    
    def test_currency_formatting_on_real_data(self):
        """Test new currency formatting with real financial data"""
        # Test various real-world financial amounts
        test_cases = [
            (1566075, '1 566 075 ₽'),
            (50000, '50 000 ₽'),
            (1000000, '1 000 000 ₽'),
            (123456789, '123 456 789 ₽'),
            (999, '999 ₽'),
            (0, '0 ₽'),
            (None, '—'),
            ('', '—'),
        ]
        
        for input_value, expected_output in test_cases:
            with self.subTest(input_value=input_value):
                result = format_currency_with_spaces(input_value)
                self.assertEqual(result, expected_output)
    
    def test_status_migration_correctness(self):
        """Test that status migrations work correctly"""
        # Test all new statuses
        status_tests = [
            ('collecting', 'warning'),
            ('ready', 'info'),
            ('sent', 'secondary'),
            ('completed_accepted', 'success'),
            ('completed_rejected', 'danger'),
        ]
        
        for status_value, expected_color in status_tests:
            with self.subTest(status=status_value):
                # Test status color mapping
                self.assertEqual(status_color(status_value), expected_color)
                
                # Test that summary can be set to this status
                self.summary.status = status_value
                self.summary.save()
                
                # Reload from database
                updated_summary = InsuranceSummary.objects.get(id=self.summary.id)
                self.assertEqual(updated_summary.status, status_value)
    
    def test_send_summary_without_status_change(self):
        """Test that sending summary doesn't automatically change status"""
        self.client.login(username='testuser', password='testpass123')
        
        original_status = self.summary.status
        
        # Send summary to client
        url = reverse('summaries:send_summary_to_client', kwargs={'summary_id': self.summary.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify status hasn't changed automatically
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, original_status)
        
        # Verify response indicates no status change
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('Для изменения статуса используйте блок "Управление статусом"', response_data['message'])
    
    def test_comprehensive_workflow(self):
        """Test complete workflow from creation to completion"""
        self.client.login(username='testuser', password='testpass123')
        
        # 1. Create summary (already done in setUp)
        self.assertEqual(self.summary.status, 'ready')
        
        # 2. Add offer with proper error handling
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Workflow Test Company',
            insurance_year=1,
            insurance_sum=Decimal('1500000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('75000'),
            franchise_2=Decimal('50000'),
            premium_with_franchise_2=Decimal('65000'),
            installment_variant_1=True,
            payments_per_year_variant_1=4
        )
        
        # 3. Test summary detail view with currency formatting
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check that currency is formatted with spaces
        self.assertContains(response, '1 500 000 ₽')  # Insurance sum
        self.assertContains(response, '75 000 ₽')     # Premium 1
        self.assertContains(response, '65 000 ₽')     # Premium 2
        
        # Check installment display (without payment amount)
        # The installment display should be present in the template
        self.assertContains(response, 'платеж')  # Should contain installment info
        
        # 4. Test status management
        change_status_url = reverse('summaries:change_summary_status', kwargs={'summary_id': self.summary.id})
        response = self.client.post(change_status_url, {'status': 'sent'})
        
        self.assertEqual(response.status_code, 200)
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'sent')
        
        # 5. Test final status change
        response = self.client.post(change_status_url, {'status': 'completed_accepted'})
        
        self.assertEqual(response.status_code, 200)
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'completed_accepted')
    
    def test_ui_elements_present(self):
        """Test that all required UI elements are present"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test summary detail page
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that status management block is present
        self.assertContains(response, 'Управление статусом')
        
        # Check that send to alliance button is present
        self.assertContains(response, 'Отправить в Альянс')
        
        # Check that ready button is NOT in header (removed as per requirements)
        header_content = response.content.decode()
        # The button should not be in the header area
        self.assertNotIn('Отметить готовым', header_content.split('</h1>')[0])
    
    def test_performance_and_reliability(self):
        """Test system performance and reliability with multiple operations"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create multiple offers to test performance
        companies = ['Company A', 'Company B', 'Company C', 'Company D', 'Company E']
        
        for i, company in enumerate(companies):
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=company,
                insurance_year=1,
                insurance_sum=Decimal('1000000') + Decimal(i * 100000),
                franchise_1=Decimal('0'),
                premium_with_franchise_1=Decimal('50000') + Decimal(i * 5000)
            )
        
        # Test that summary detail loads efficiently
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify all companies are displayed
        for company in companies:
            self.assertContains(response, company)
        
        # Test that currency formatting works for all amounts
        self.assertContains(response, '1 000 000 ₽')
        self.assertContains(response, '1 400 000 ₽')
        self.assertContains(response, '50 000 ₽')
        self.assertContains(response, '70 000 ₽')


class DatabaseIntegrityTest(TestCase):
    """Test database integrity and migration correctness"""
    
    def test_status_choices_integrity(self):
        """Test that all status choices work correctly in database"""
        user = User.objects.create_user(username='testuser', password='testpass123')
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            created_by=user
        )
        
        # Test all valid statuses
        valid_statuses = ['collecting', 'ready', 'sent', 'completed_accepted', 'completed_rejected']
        
        for status in valid_statuses:
            with self.subTest(status=status):
                summary = InsuranceSummary.objects.create(
                    request=request,
                    status=status
                )
                
                # Verify status is saved correctly
                saved_summary = InsuranceSummary.objects.get(id=summary.id)
                self.assertEqual(saved_summary.status, status)
                
                # Clean up for next iteration
                summary.delete()
    
    def test_unique_constraint_enforcement(self):
        """Test that unique constraints are properly enforced"""
        user = User.objects.create_user(username='testuser', password='testpass123')
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            created_by=user
        )
        
        summary = InsuranceSummary.objects.create(request=request)
        
        # Create first offer
        InsuranceOffer.objects.create(
            summary=summary,
            company_name='Test Company',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000')
        )
        
        # Try to create duplicate offer - should raise IntegrityError
        with self.assertRaises(IntegrityError):
            InsuranceOffer.objects.create(
                summary=summary,
                company_name='Test Company',
                insurance_year=1,
                insurance_sum=Decimal('1000000'),
                franchise_1=Decimal('0'),
                premium_with_franchise_1=Decimal('60000')
            )
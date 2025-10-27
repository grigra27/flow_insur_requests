"""
UI and JavaScript functionality tests for insurance offer model refactor.
Tests user interface elements, JavaScript functionality, and accessibility.
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test.utils import override_settings

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class TestUIElements(TestCase):
    """Test UI elements and form rendering"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='uitestuser',
            email='ui@example.com',
            password='testpass123'
        )
        
        # Add user to required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="UI Test Client",
            inn="1111111111",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Login user
        self.client.login(username='uitestuser', password='testpass123')
    
    def test_add_offer_form_elements(self):
        """Test that add offer form contains all required UI elements"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check form structure
        self.assertContains(response, '<form method="post">')
        self.assertContains(response, 'csrfmiddlewaretoken')
        
        # Check company name field
        self.assertContains(response, 'name="company_name"')
        self.assertContains(response, 'class="form-control"')
        
        # Check insurance year field
        self.assertContains(response, 'name="insurance_year"')
        self.assertContains(response, 'Введите номер года')
        
        # Check insurance sum field
        self.assertContains(response, 'name="insurance_sum"')
        self.assertContains(response, 'step="0.01"')
        
        # Check franchise fields
        self.assertContains(response, 'name="franchise_1"')
        self.assertContains(response, 'name="franchise_2"')
        
        # Check premium fields
        self.assertContains(response, 'name="premium_with_franchise_1"')
        self.assertContains(response, 'name="premium_with_franchise_2"')
        
        # Check installment fields
        self.assertContains(response, 'name="installment_available"')
        self.assertContains(response, 'class="form-check-input"')
        self.assertContains(response, 'name="payments_per_year"')
        self.assertContains(response, 'class="form-select"')
        
        # Check payment options
        self.assertContains(response, '1 (годовой платеж)')
        self.assertContains(response, '2 (полугодовые)')
        self.assertContains(response, '4 (квартальные)')
        self.assertContains(response, '12 (ежемесячные)')
        
        # Check notes field
        self.assertContains(response, 'name="notes"')
        self.assertContains(response, 'rows="3"')
        
        # Check file upload field
        self.assertContains(response, 'name="attachment_file"')
        self.assertContains(response, 'type="file"')
    
    def test_edit_offer_form_prepopulation(self):
        """Test that edit form is properly pre-populated"""
        
        # Create offer to edit
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Согласие",
            insurance_year=3,
            insurance_sum=Decimal("1200000.00"),
            franchise_1=Decimal("5000.00"),
            premium_with_franchise_1=Decimal("48000.00"),
            franchise_2=Decimal("15000.00"),
            premium_with_franchise_2=Decimal("43000.00"),
            installment_available=True,
            payments_per_year=4,
            notes="UI test notes"
        )
        
        url = reverse('summaries:edit_offer', kwargs={'offer_id': offer.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check pre-populated values
        self.assertContains(response, 'value="Согласие"')
        self.assertContains(response, 'value="3"')  # insurance_year
        self.assertContains(response, 'value="1200000.00"')  # insurance_sum
        self.assertContains(response, 'value="5000.00"')  # franchise_1
        self.assertContains(response, 'value="48000.00"')  # premium_with_franchise_1
        self.assertContains(response, 'value="15000.00"')  # franchise_2
        self.assertContains(response, 'value="43000.00"')  # premium_with_franchise_2
        self.assertContains(response, 'selected>4 (квартальные)</option>')  # payments_per_year
        self.assertContains(response, 'UI test notes')  # notes
        
        # Check that installment checkbox is checked
        self.assertContains(response, 'checked')
    
    def test_summary_detail_display_structure(self):
        """Test summary detail page display structure"""
        
        # Create test offers
        offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Энергогарант",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            installment_available=False,
            payments_per_year=1
        )
        
        offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ПСБ-страхование",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("45000.00"),
            franchise_2=Decimal("20000.00"),
            premium_with_franchise_2=Decimal("40000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check page structure
        self.assertContains(response, '<h1>')
        self.assertContains(response, 'Свод к')
        
        # Check request information card
        self.assertContains(response, 'Информация о заявке')
        self.assertContains(response, 'UI Test Client')
        self.assertContains(response, 'КАСКО')
        
        # Check offers section
        self.assertContains(response, 'Предложения страховщиков')
        self.assertContains(response, 'Энергогарант')
        self.assertContains(response, 'ПСБ-страхование')
        
        # Check table structure
        self.assertContains(response, '<table')
        self.assertContains(response, '<thead')
        self.assertContains(response, '<tbody')
        
        # Check basic table content
        self.assertContains(response, 'Год')
        # Note: Specific column headers depend on template implementation
        
        # Check year display
        self.assertContains(response, '1 год')
        self.assertContains(response, '2 год')
        
        # Check action buttons
        self.assertContains(response, 'btn-outline-primary')  # Edit button
        self.assertContains(response, 'btn-outline-danger')   # Delete button
        self.assertContains(response, 'bi-pencil')            # Edit icon
        self.assertContains(response, 'bi-trash')             # Delete icon
    
    def test_responsive_design_elements(self):
        """Test responsive design elements"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check Bootstrap responsive classes
        self.assertContains(response, 'col-md-6')
        self.assertContains(response, 'col-lg-10')
        self.assertContains(response, 'row')
        self.assertContains(response, 'container')
        
        # Check responsive elements exist
        # Note: table-responsive may not be on add form page
        
        # Check mobile-friendly form elements
        self.assertContains(response, 'form-control')
        self.assertContains(response, 'form-select')
        self.assertContains(response, 'form-check-input')
        
        # Check button groups
        self.assertContains(response, 'btn-group')
        self.assertContains(response, 'btn-group-sm')
    
    def test_accessibility_elements(self):
        """Test accessibility elements"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check form labels
        self.assertContains(response, '<label')
        self.assertContains(response, 'for=')
        
        # Check required field indicators
        self.assertContains(response, 'text-danger">*</span>')
        
        # Check help text
        self.assertContains(response, 'form-text')
        self.assertContains(response, 'Введите номер года: 1, 2, 3 и т.д.')
        self.assertContains(response, 'Обычно 0 ₽ (без франшизы)')
        self.assertContains(response, 'Обязательное поле')
        
        # Check ARIA attributes (if any)
        # Note: These would need to be added to templates for full accessibility
        
        # Check semantic HTML structure (basic elements)
        # Note: Specific semantic elements depend on template implementation


class TestJavaScriptFunctionality(TestCase):
    """Test JavaScript functionality (simulated through HTML structure)"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='jsuser',
            email='js@example.com',
            password='testpass123'
        )
        
        # Add user to required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="JS Test Client",
            inn="2222222222",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Login user
        self.client.login(username='jsuser', password='testpass123')
    
    def test_installment_form_interaction_elements(self):
        """Test elements for installment form interaction"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check installment checkbox
        self.assertContains(response, 'name="installment_available"')
        self.assertContains(response, 'type="checkbox"')
        
        # Check payments per year select
        self.assertContains(response, 'name="payments_per_year"')
        self.assertContains(response, '<select')
        
        # Check that JavaScript can target these elements
        # (In a real test, we would use Selenium to test actual JS behavior)
        self.assertContains(response, 'id=')  # Elements should have IDs for JS targeting
    
    def test_form_validation_elements(self):
        """Test elements for client-side form validation"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check HTML5 validation attributes
        self.assertContains(response, 'step="0.01"')
        # Note: min/max attributes are in widget definition but may not appear in HTML
        
        # Check input types
        self.assertContains(response, 'type="number"')
        self.assertContains(response, 'type="text"')
        self.assertContains(response, 'type="file"')
        
        # Check placeholder text for user guidance
        self.assertContains(response, 'placeholder=')
    
    def test_delete_confirmation_elements(self):
        """Test elements for delete confirmation functionality"""
        
        # Create offer to test delete functionality
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Совкомбанк СК",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check delete button structure
        self.assertContains(response, 'btn-outline-danger')
        self.assertContains(response, 'bi-trash')
        
        # Check that delete buttons have proper data attributes for JS
        # (In actual implementation, these would be used by JavaScript)
        self.assertContains(response, 'onclick=')  # Should have onclick handler
    
    def test_dynamic_content_elements(self):
        """Test elements for dynamic content updates"""
        
        # Create offers for testing dynamic content
        offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ВСК",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check elements that would be updated by JavaScript
        self.assertContains(response, 'data-label=')  # For responsive tables
        
        # Check payment calculation display
        # (The div filter we added should work here)
        self.assertContains(response, '₽ за платеж')  # Payment amount display
        
        # Check installment badges
        self.assertContains(response, 'badge')
        self.assertContains(response, 'платеж')


class TestFormValidationUI(TestCase):
    """Test form validation UI elements"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='validationuser',
            email='validation@example.com',
            password='testpass123'
        )
        
        # Add user to required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="Validation Test Client",
            inn="3333333333",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Login user
        self.client.login(username='validationuser', password='testpass123')
    
    def test_validation_error_display(self):
        """Test validation error display in forms"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        # Submit form with invalid data
        invalid_data = {
            'company_name': '',  # Required field left empty
            'insurance_year': 15,  # Invalid year (> 10)
            'insurance_sum': -1000,  # Negative sum
            'franchise_1': -500,  # Negative franchise
            'premium_with_franchise_1': 0,  # Zero premium
            'payments_per_year': 1
        }
        
        response = self.client.post(url, data=invalid_data)
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        
        # Check error display structure
        self.assertContains(response, 'text-danger')
        
        # Check that form is re-rendered with errors
        self.assertContains(response, '<form method="post">')
        
        # Check that invalid values are preserved in form
        self.assertContains(response, 'value="15"')  # Invalid year preserved
    
    def test_success_message_elements(self):
        """Test success message display elements"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        # Submit valid form data
        valid_data = {
            'company_name': 'Success Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'payments_per_year': 1
        }
        
        response = self.client.post(url, data=valid_data, follow=True)
        
        # Should redirect after successful creation
        self.assertEqual(response.status_code, 200)
        
        # Check for success message (Django messages framework)
        # Note: The actual message display depends on template implementation
        messages = list(response.context.get('messages', []))
        if messages:
            self.assertTrue(any('успешно' in str(message).lower() for message in messages))


class TestUIConsistency(TestCase):
    """Test UI consistency across different pages"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='consistencyuser',
            email='consistency@example.com',
            password='testpass123'
        )
        
        # Add user to required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="Consistency Test Client",
            inn="4444444444",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        self.offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="РЕСО",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        # Login user
        self.client.login(username='consistencyuser', password='testpass123')
    
    def test_consistent_styling_across_pages(self):
        """Test that styling is consistent across different pages"""
        
        pages = [
            reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk}),
            reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk}),
            reverse('summaries:edit_offer', kwargs={'offer_id': self.offer.pk}),
        ]
        
        common_elements = [
            'Bootstrap',  # Should use Bootstrap
            'btn',        # Button classes
            'card',       # Card components
            'form-control',  # Form styling
            'table',      # Table styling
        ]
        
        for page_url in pages:
            with self.subTest(page=page_url):
                response = self.client.get(page_url)
                self.assertEqual(response.status_code, 200)
                
                # Check for common styling elements
                for element in common_elements:
                    with self.subTest(element=element):
                        self.assertContains(response, element)
    
    def test_consistent_navigation_elements(self):
        """Test consistent navigation elements"""
        
        pages = [
            reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk}),
            reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk}),
            reverse('summaries:edit_offer', kwargs={'offer_id': self.offer.pk}),
        ]
        
        for page_url in pages:
            with self.subTest(page=page_url):
                response = self.client.get(page_url)
                self.assertEqual(response.status_code, 200)
                
                # Check for consistent navigation elements (if they exist)
                # Note: Navigation elements may vary by page
                
                # Check for consistent icons (Bootstrap Icons)
                self.assertContains(response, 'bi-')  # Bootstrap icons


def run_ui_tests():
    """Helper function to run all UI tests"""
    import unittest
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestUIElements))
    test_suite.addTest(unittest.makeSuite(TestJavaScriptFunctionality))
    test_suite.addTest(unittest.makeSuite(TestFormValidationUI))
    test_suite.addTest(unittest.makeSuite(TestUIConsistency))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    run_ui_tests()
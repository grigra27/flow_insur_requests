"""
Simplified UI tests for insurance offer model refactor.
Tests core UI functionality and user interface elements.
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class TestCoreUIFunctionality(TestCase):
    """Test core UI functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='uiuser',
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
        self.client.login(username='uiuser', password='testpass123')
    
    def test_add_offer_page_loads(self):
        """Test that add offer page loads successfully"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Добавить предложение')
        self.assertContains(response, '<form')
        self.assertContains(response, 'method="post"')
    
    def test_add_offer_form_has_new_fields(self):
        """Test that add offer form contains new model fields"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check for new field names
        self.assertContains(response, 'name="company_name"')
        self.assertContains(response, 'name="insurance_year"')
        self.assertContains(response, 'name="insurance_sum"')
        self.assertContains(response, 'name="franchise_1"')
        self.assertContains(response, 'name="premium_with_franchise_1"')
        self.assertContains(response, 'name="payments_per_year"')
        
        # Check that old fields are NOT present
        self.assertNotContains(response, 'name="company_email"')
        self.assertNotContains(response, 'name="insurance_premium"')
        self.assertNotContains(response, 'name="franchise_amount"')
        self.assertNotContains(response, 'name="installment_months"')
        self.assertNotContains(response, 'name="valid_until"')
    
    def test_edit_offer_page_loads(self):
        """Test that edit offer page loads successfully"""
        
        # Create offer to edit
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Edit Test Company",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        url = reverse('summaries:edit_offer', kwargs={'offer_id': offer.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Редактировать предложение')
        self.assertContains(response, 'Edit Test Company')
        self.assertContains(response, '<form')
    
    def test_summary_detail_page_loads(self):
        """Test that summary detail page loads successfully"""
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Свод к')
        self.assertContains(response, 'UI Test Client')
        self.assertContains(response, 'КАСКО')
    
    def test_summary_detail_displays_offers_correctly(self):
        """Test that summary detail page displays offers with new structure"""
        
        # Create test offers
        offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Display Company A",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Display Company B",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("45000.00"),
            franchise_2=Decimal("20000.00"),
            premium_with_franchise_2=Decimal("40000.00")
        )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that offers are displayed
        self.assertContains(response, 'Display Company A')
        self.assertContains(response, 'Display Company B')
        
        # Check year display with new format
        self.assertContains(response, '1 год')
        self.assertContains(response, '2 год')
        
        # Check premium values
        self.assertContains(response, '50000')
        self.assertContains(response, '45000')
    
    def test_form_submission_works(self):
        """Test that form submission works with new model structure"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        form_data = {
            'company_name': 'Form Test Company',
            'insurance_year': 3,
            'insurance_sum': '1200000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '48000.00',
            'payments_per_year': 1
        }
        
        response = self.client.post(url, data=form_data)
        
        # Should redirect after successful creation
        self.assertEqual(response.status_code, 302)
        
        # Check that offer was created
        offer = InsuranceOffer.objects.get(company_name='Form Test Company')
        self.assertEqual(offer.insurance_year, 3)
        self.assertEqual(offer.franchise_1, Decimal('0.00'))
        self.assertEqual(offer.premium_with_franchise_1, Decimal('48000.00'))
        self.assertEqual(offer.payments_per_year, 1)
    
    def test_year_display_formatting(self):
        """Test that year display formatting works correctly"""
        
        # Create offers with different years
        for year in [1, 2, 3, 5]:
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=f"Year {year} Company",
                insurance_year=year,
                insurance_sum=Decimal("1000000.00"),
                franchise_1=Decimal("0.00"),
                premium_with_franchise_1=Decimal("50000.00")
            )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that years are displayed with "год" suffix
        for year in [1, 2, 3, 5]:
            self.assertContains(response, f'{year} год')
    
    def test_installment_display(self):
        """Test installment display functionality"""
        
        # Create offer with installments
        offer_with_installments = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Installment Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("60000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        # Create offer without installments
        offer_without_installments = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Single Payment Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("55000.00"),
            installment_available=False,
            payments_per_year=1
        )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that both companies are displayed
        self.assertContains(response, 'Installment Company')
        self.assertContains(response, 'Single Payment Company')
        
        # Check installment information is displayed
        # (Specific format depends on template implementation)
        self.assertContains(response, '60000')
        self.assertContains(response, '55000')
    
    def test_franchise_variants_display(self):
        """Test franchise variants display"""
        
        # Create offer with two franchise variants
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Franchise Variants Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            franchise_2=Decimal("25000.00"),
            premium_with_franchise_2=Decimal("45000.00")
        )
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that company is displayed
        self.assertContains(response, 'Franchise Variants Company')
        
        # Check that both premium values are displayed
        self.assertContains(response, '50000')
        self.assertContains(response, '45000')
    
    def test_form_validation_ui(self):
        """Test form validation UI"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        # Submit form with invalid data
        invalid_data = {
            'company_name': '',  # Required field empty
            'insurance_year': 15,  # Invalid year
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'payments_per_year': 1
        }
        
        response = self.client.post(url, data=invalid_data)
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        
        # Should display form again
        self.assertContains(response, '<form')
        
        # Should show error styling (check for any error indication)
        # The specific error display format depends on template implementation
        self.assertTrue(
            'error' in response.content.decode().lower() or 
            'invalid' in response.content.decode().lower() or
            'required' in response.content.decode().lower()
        )


class TestUIAccessibility(TestCase):
    """Test basic UI accessibility features"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='accessuser',
            email='access@example.com',
            password='testpass123'
        )
        
        # Add user to required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="Access Test Client",
            inn="2222222222",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Login user
        self.client.login(username='accessuser', password='testpass123')
    
    def test_form_labels_present(self):
        """Test that form fields have proper labels"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check for label elements
        self.assertContains(response, '<label')
        
        # Check for form-label class (Bootstrap)
        self.assertContains(response, 'form-label')
    
    def test_help_text_present(self):
        """Test that help text is provided for complex fields"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check for help text elements
        self.assertContains(response, 'form-text')
    
    def test_required_field_indicators(self):
        """Test that required fields are properly indicated"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check for required field indicators
        self.assertContains(response, 'text-danger')


def run_simple_ui_tests():
    """Helper function to run simplified UI tests"""
    import unittest
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestCoreUIFunctionality))
    test_suite.addTest(unittest.makeSuite(TestUIAccessibility))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    run_simple_ui_tests()
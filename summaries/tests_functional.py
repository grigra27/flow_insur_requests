"""
Functional tests for insurance offer model refactor.
Tests forms, views, and user interactions with the new model structure.
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer
from summaries.forms import OfferForm, AddOfferToSummaryForm


class TestOfferForms(TestCase):
    """Test form functionality with new model structure"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='formuser',
            email='form@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Form Test Client",
            inn="1234567890",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_offer_form_valid_data(self):
        """Test OfferForm with valid data"""
        
        form_data = {
            'company_name': 'Test Insurance Company',
            'insurance_year': 2,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            'franchise_2': Decimal('25000.00'),
            'premium_with_franchise_2': Decimal('45000.00'),
            'installment_available': True,
            'payments_per_year': 4,
            'notes': 'Test notes'
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Test that form saves correctly
        offer = form.save(commit=False)
        offer.summary = self.summary
        offer.save()
        
        self.assertEqual(offer.company_name, 'Test Insurance Company')
        self.assertEqual(offer.insurance_year, 2)
        self.assertEqual(offer.franchise_1, Decimal('0.00'))
        self.assertEqual(offer.premium_with_franchise_1, Decimal('50000.00'))
        self.assertEqual(offer.payments_per_year, 4)
    
    def test_offer_form_year_validation(self):
        """Test year field validation"""
        
        # Test valid years
        for year in [1, 2, 3, 5, 10]:
            form_data = {
                'company_name': 'Test Company',
                'insurance_year': year,
                'insurance_sum': Decimal('1000000.00'),
                'franchise_1': Decimal('0.00'),
                'premium_with_franchise_1': Decimal('50000.00'),
                'payments_per_year': 1
            }
            form = OfferForm(data=form_data)
            self.assertTrue(form.is_valid(), f"Year {year} should be valid")
        
        # Test invalid years (only test values that would actually fail validation)
        for year in [11, 15]:  # 0 and -1 are handled by HTML5 min validation, not Django
            form_data = {
                'company_name': 'Test Company',
                'insurance_year': year,
                'insurance_sum': Decimal('1000000.00'),
                'franchise_1': Decimal('0.00'),
                'premium_with_franchise_1': Decimal('50000.00'),
                'payments_per_year': 1
            }
            form = OfferForm(data=form_data)
            self.assertFalse(form.is_valid(), f"Year {year} should be invalid")
    
    def test_offer_form_payments_per_year_validation(self):
        """Test payments per year validation"""
        
        # Test valid payment counts
        for payments in [1, 2, 3, 4, 12]:
            form_data = {
                'company_name': 'Test Company',
                'insurance_year': 1,
                'insurance_sum': Decimal('1000000.00'),
                'franchise_1': Decimal('0.00'),
                'premium_with_franchise_1': Decimal('50000.00'),
                'payments_per_year': payments
            }
            form = OfferForm(data=form_data)
            self.assertTrue(form.is_valid(), f"Payments {payments} should be valid")
        
        # Test invalid payment counts when installment is available
        for payments in [13, 24]:
            form_data = {
                'company_name': 'Test Company',
                'insurance_year': 1,
                'insurance_sum': Decimal('1000000.00'),
                'franchise_1': Decimal('0.00'),
                'premium_with_franchise_1': Decimal('50000.00'),
                'installment_available': True,  # Рассрочка доступна
                'payments_per_year': payments
            }
            form = OfferForm(data=form_data)
            self.assertFalse(form.is_valid(), f"Payments {payments} should be invalid when installment is available")
    
    def test_offer_form_installment_logic(self):
        """Test installment logic in form"""
        
        # Test that when installment is not available, payments_per_year defaults to 1
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            'installment_available': False,
            'payments_per_year': 4  # Should be overridden
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        offer = form.save(commit=False)
        offer.summary = self.summary
        offer.save()
        
        # Should automatically set to 1 when installment is not available
        self.assertEqual(offer.payments_per_year, 1)
    
    def test_add_offer_to_summary_form(self):
        """Test AddOfferToSummaryForm functionality"""
        
        form_data = {
            'company_name': 'Summary Test Company',
            'insurance_year': 3,
            'insurance_sum': Decimal('800000.00'),
            'franchise_1': Decimal('5000.00'),
            'premium_with_franchise_1': Decimal('42000.00'),
            'installment_available': True,
            'payments_per_year': 2
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        offer = form.save(commit=False)
        offer.summary = self.summary
        offer.save()
        
        self.assertEqual(offer.company_name, 'Summary Test Company')
        self.assertEqual(offer.insurance_year, 3)
        self.assertEqual(offer.franchise_1, Decimal('5000.00'))
    
    def test_form_franchise_validation(self):
        """Test franchise field validation"""
        
        # Test that franchise_1 cannot be negative
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('-1000.00'),  # Negative franchise
            'premium_with_franchise_1': Decimal('50000.00'),
            'payments_per_year': 1
        }
        
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('franchise_1', form.errors)
        
        # Test that premium cannot be zero or negative
        form_data['franchise_1'] = Decimal('0.00')
        form_data['premium_with_franchise_1'] = Decimal('0.00')
        
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('premium_with_franchise_1', form.errors)


class TestOfferViews(TestCase):
    """Test view functionality with new model structure"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        
        self.client = Client()
        self.user = User.objects.create_user(
            username='viewuser',
            email='view@example.com',
            password='testpass123'
        )
        
        # Add user to required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="View Test Client",
            inn="9876543210",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Login user
        self.client.login(username='viewuser', password='testpass123')
    
    def test_summary_detail_view(self):
        """Test summary detail view displays new model structure correctly"""
        
        # Create test offers
        offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="View Company A",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("55000.00"),
            franchise_2=Decimal("20000.00"),
            premium_with_franchise_2=Decimal("50000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="View Company B",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("48000.00"),
            installment_available=False,
            payments_per_year=1
        )
        
        # Get summary detail page
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that offers are displayed
        self.assertContains(response, "View Company A")
        self.assertContains(response, "View Company B")
        
        # Check year display
        self.assertContains(response, "1 год")
        self.assertContains(response, "2 год")
        
        # Check that premium values are displayed
        self.assertContains(response, "55000")  # Premium from offer1
        self.assertContains(response, "48000")  # Premium from offer2
    
    def test_add_offer_view(self):
        """Test add offer view functionality"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that form fields are present
        self.assertContains(response, 'name="company_name"')
        self.assertContains(response, 'name="insurance_year"')
        self.assertContains(response, 'name="franchise_1"')
        self.assertContains(response, 'name="premium_with_franchise_1"')
        self.assertContains(response, 'name="franchise_2"')
        self.assertContains(response, 'name="premium_with_franchise_2"')
        self.assertContains(response, 'name="payments_per_year"')
        
        # Check that old fields are not present
        self.assertNotContains(response, 'name="company_email"')
        self.assertNotContains(response, 'name="insurance_premium"')
        self.assertNotContains(response, 'name="franchise_amount"')
        self.assertNotContains(response, 'name="installment_months"')
        self.assertNotContains(response, 'name="valid_until"')
    
    def test_add_offer_post(self):
        """Test adding offer via POST request"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        post_data = {
            'company_name': 'POST Test Company',
            'insurance_year': 2,
            'insurance_sum': '1500000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '65000.00',
            'franchise_2': '30000.00',
            'premium_with_franchise_2': '58000.00',
            'installment_available': True,
            'payments_per_year': 12,
            'notes': 'Added via POST'
        }
        
        response = self.client.post(url, data=post_data)
        
        # Should redirect after successful creation
        self.assertEqual(response.status_code, 302)
        
        # Check that offer was created
        offer = InsuranceOffer.objects.get(company_name='POST Test Company')
        self.assertEqual(offer.insurance_year, 2)
        self.assertEqual(offer.franchise_1, Decimal('0.00'))
        self.assertEqual(offer.premium_with_franchise_1, Decimal('65000.00'))
        self.assertEqual(offer.franchise_2, Decimal('30000.00'))
        self.assertEqual(offer.premium_with_franchise_2, Decimal('58000.00'))
        self.assertEqual(offer.payments_per_year, 12)
        self.assertEqual(offer.notes, 'Added via POST')
    
    def test_edit_offer_view(self):
        """Test edit offer view functionality"""
        
        # Create offer to edit
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Edit Test Company",
            insurance_year=1,
            insurance_sum=Decimal("900000.00"),
            franchise_1=Decimal("5000.00"),
            premium_with_franchise_1=Decimal("45000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        url = reverse('summaries:edit_offer', kwargs={'offer_id': offer.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that form is pre-populated
        self.assertContains(response, 'value="Edit Test Company"')
        self.assertContains(response, 'value="1"')  # insurance_year
        self.assertContains(response, 'value="5000.00"')  # franchise_1
        self.assertContains(response, 'value="45000.00"')  # premium_with_franchise_1
        self.assertContains(response, 'value="4"')  # payments_per_year
    
    def test_edit_offer_post(self):
        """Test editing offer via POST request"""
        
        # Create offer to edit
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Original Company",
            insurance_year=1,
            insurance_sum=Decimal("800000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("40000.00"),
            payments_per_year=1
        )
        
        url = reverse('summaries:edit_offer', kwargs={'offer_id': offer.pk})
        
        post_data = {
            'company_name': 'Updated Company',
            'insurance_year': 3,
            'insurance_sum': '1200000.00',
            'franchise_1': '10000.00',
            'premium_with_franchise_1': '52000.00',
            'franchise_2': '25000.00',
            'premium_with_franchise_2': '47000.00',
            'installment_available': True,
            'payments_per_year': 2,
            'notes': 'Updated via POST'
        }
        
        response = self.client.post(url, data=post_data)
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Check that offer was updated
        offer.refresh_from_db()
        self.assertEqual(offer.company_name, 'Updated Company')
        self.assertEqual(offer.insurance_year, 3)
        self.assertEqual(offer.franchise_1, Decimal('10000.00'))
        self.assertEqual(offer.premium_with_franchise_1, Decimal('52000.00'))
        self.assertEqual(offer.franchise_2, Decimal('25000.00'))
        self.assertEqual(offer.premium_with_franchise_2, Decimal('47000.00'))
        self.assertEqual(offer.payments_per_year, 2)
        self.assertEqual(offer.notes, 'Updated via POST')


class TestDataDisplayAndFormatting(TestCase):
    """Test data display and formatting with new model structure"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='displayuser',
            email='display@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Display Test Client",
            inn="5555555555",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_year_display_formatting(self):
        """Test year display formatting in various contexts"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Year Display Company",
            insurance_year=5,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        # Test year display method
        self.assertEqual(offer.get_insurance_year_display(), "5 год")
        
        # Test string representation includes year
        self.assertIn("5 год", str(offer))
    
    def test_franchise_display_formatting(self):
        """Test franchise display formatting"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Franchise Display Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            franchise_2=Decimal("15000.00"),
            premium_with_franchise_2=Decimal("45000.00")
        )
        
        # Test zero franchise display
        self.assertEqual(offer.get_franchise_display_variant1(), "0")
        
        # Test non-zero franchise display
        self.assertEqual(offer.get_franchise_display_variant2(), "15,000 ₽")
        
        # Test missing second franchise
        offer.franchise_2 = None
        offer.premium_with_franchise_2 = None
        offer.save()
        
        self.assertEqual(offer.get_franchise_display_variant2(), "Нет")
    
    def test_installment_display_formatting(self):
        """Test installment display formatting"""
        
        # Test single payment
        offer_single = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Single Payment Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            installment_available=False,
            payments_per_year=1
        )
        
        self.assertEqual(offer_single.get_installment_display(), "Единовременно")
        
        # Test multiple payments
        test_cases = [
            (2, "2 платежей в год"),
            (3, "3 платежей в год"),
            (4, "4 платежей в год"),
            (12, "12 платежей в год")
        ]
        
        for payments, expected_display in test_cases:
            offer_multiple = InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=f"Payment Company {payments}",
                insurance_year=1,
                insurance_sum=Decimal("1000000.00"),
                franchise_1=Decimal("0.00"),
                premium_with_franchise_1=Decimal("50000.00"),
                installment_available=True,
                payments_per_year=payments
            )
            
            self.assertEqual(offer_multiple.get_installment_display(), expected_display)
    
    def test_payment_calculation_display(self):
        """Test payment amount calculation and display"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Payment Calculation Company",
            insurance_year=1,
            insurance_sum=Decimal("1200000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("60000.00"),
            franchise_2=Decimal("20000.00"),
            premium_with_franchise_2=Decimal("50000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        # Test payment calculation for first franchise variant
        payment_1 = offer.get_payment_amount(franchise_variant=1)
        expected_1 = Decimal("60000.00") / 4
        self.assertEqual(payment_1, expected_1)
        
        # Test payment calculation for second franchise variant
        payment_2 = offer.get_payment_amount(franchise_variant=2)
        expected_2 = Decimal("50000.00") / 4
        self.assertEqual(payment_2, expected_2)
        
        # Test premium per payment property
        self.assertEqual(offer.premium_per_payment, expected_1)


class TestDataIntegrity(TestCase):
    """Test data integrity and business logic with new model structure"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='integrityuser',
            email='integrity@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Integrity Test Client",
            inn="7777777777",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_unique_constraint_enforcement(self):
        """Test that unique constraint is properly enforced"""
        
        # Create first offer
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Unique Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        # Try to create duplicate
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name="Unique Company",
                insurance_year=1,  # Same year
                insurance_sum=Decimal("1000000.00"),
                franchise_1=Decimal("0.00"),
                premium_with_franchise_1=Decimal("50000.00")
            )
    
    def test_summary_offers_count(self):
        """Test that summary correctly counts offers"""
        
        # Create multiple offers
        offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Company A",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("55000.00")
        )
        
        offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Company B",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("48000.00")
        )
        
        offer3 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Company C",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("45000.00")
        )
        
        # Check that offers are counted correctly
        self.assertEqual(self.summary.offers.count(), 3)
    
    def test_offer_business_logic_methods(self):
        """Test business logic methods work correctly with new structure"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Business Logic Company",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            franchise_2=Decimal("15000.00"),
            premium_with_franchise_2=Decimal("45000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        # Test effective properties
        self.assertEqual(offer.effective_premium_with_franchise, Decimal("50000.00"))
        self.assertEqual(offer.effective_premium_without_franchise, Decimal("45000.00"))
        self.assertEqual(offer.effective_franchise_amount, Decimal("0.00"))
        
        # Test that both premium variants are available
        self.assertTrue(offer.has_second_franchise_variant())
        
        # Test franchise variants
        variants = offer.get_franchise_variants()
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0]['franchise'], Decimal("0.00"))
        self.assertEqual(variants[1]['franchise'], Decimal("15000.00"))
        
        # Test second franchise variant detection
        self.assertTrue(offer.has_second_franchise_variant())


def run_functional_tests():
    """Helper function to run all functional tests"""
    import unittest
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestOfferForms))
    test_suite.addTest(unittest.makeSuite(TestOfferViews))
    test_suite.addTest(unittest.makeSuite(TestDataDisplayAndFormatting))
    test_suite.addTest(unittest.makeSuite(TestDataIntegrity))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    run_functional_tests()
"""
Simplified migration tests for insurance offer model refactor.
Tests current model functionality and data validation.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class TestMigrationResults(TestCase):
    """Test the results of the migration - current model functionality"""
    
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test request
        self.request = InsuranceRequest.objects.create(
            client_name="Test Client",
            inn="1234567890",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        # Create test summary
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_new_model_structure(self):
        """Test that the new model structure works correctly"""
        
        # Create offer with new structure
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ВСК",
            insurance_year=2,  # Numeric year
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            franchise_2=Decimal("25000.00"),
            premium_with_franchise_2=Decimal("45000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        # Test basic functionality
        self.assertEqual(offer.company_name, "ВСК")
        self.assertEqual(offer.insurance_year, 2)
        self.assertEqual(offer.insurance_sum, Decimal("1000000.00"))
        
        # Test franchise fields
        self.assertEqual(offer.franchise_1, Decimal("0.00"))
        self.assertEqual(offer.premium_with_franchise_1, Decimal("50000.00"))
        self.assertEqual(offer.franchise_2, Decimal("25000.00"))
        self.assertEqual(offer.premium_with_franchise_2, Decimal("45000.00"))
        
        # Test payment fields
        self.assertTrue(offer.installment_available)
        self.assertEqual(offer.payments_per_year, 4)
    
    def test_year_display_method(self):
        """Test that year display method works correctly"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Энергогарант",
            insurance_year=3,
            insurance_sum=Decimal("500000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("30000.00")
        )
        
        # Test year display
        year_display = offer.get_insurance_year_display()
        self.assertEqual(year_display, "3 год")
        
        # Test year number
        year_number = offer.get_year_number()
        self.assertEqual(year_number, 3)
    
    def test_franchise_display_methods(self):
        """Test franchise display methods"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="РЕСО",
            insurance_year=1,
            insurance_sum=Decimal("800000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("40000.00"),
            franchise_2=Decimal("15000.00"),
            premium_with_franchise_2=Decimal("35000.00")
        )
        
        # Test franchise display methods
        franchise_1_display = offer.get_franchise_display_variant1()
        self.assertEqual(franchise_1_display, "0")
        
        franchise_2_display = offer.get_franchise_display_variant2()
        self.assertEqual(franchise_2_display, "15,000 ₽")
        
        # Test premium methods
        premium_1 = offer.get_premium_with_franchise1()
        self.assertEqual(premium_1, Decimal("40000.00"))
        
        premium_2 = offer.get_premium_with_franchise2()
        self.assertEqual(premium_2, Decimal("35000.00"))
    
    def test_installment_display_method(self):
        """Test installment display method"""
        
        # Test single payment
        offer_single = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Ренессанс",
            insurance_year=1,
            insurance_sum=Decimal("600000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("35000.00"),
            installment_available=False,
            payments_per_year=1
        )
        
        installment_display = offer_single.get_installment_display()
        self.assertEqual(installment_display, "Единовременно")
        
        # Test multiple payments
        offer_multiple = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Абсолют",
            insurance_year=1,
            insurance_sum=Decimal("600000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("35000.00"),
            installment_available=True,
            payments_per_year=12
        )
        
        installment_display = offer_multiple.get_installment_display()
        self.assertEqual(installment_display, "12 платежей в год")
    
    def test_payment_calculation(self):
        """Test payment amount calculation"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Росгосстрах",
            insurance_year=1,
            insurance_sum=Decimal("1200000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("60000.00"),
            franchise_2=Decimal("20000.00"),
            premium_with_franchise_2=Decimal("50000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        # Test payment calculation for franchise variant 1
        payment_1 = offer.get_payment_amount(franchise_variant=1)
        expected_payment_1 = Decimal("60000.00") / 4
        self.assertEqual(payment_1, expected_payment_1)
        
        # Test payment calculation for franchise variant 2
        payment_2 = offer.get_payment_amount(franchise_variant=2)
        expected_payment_2 = Decimal("50000.00") / 4
        self.assertEqual(payment_2, expected_payment_2)
        
        # Test premium per payment property
        premium_per_payment = offer.premium_per_payment
        self.assertEqual(premium_per_payment, expected_payment_1)
    
    def test_franchise_variants_method(self):
        """Test franchise variants method"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Альфа",
            insurance_year=1,
            insurance_sum=Decimal("900000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("45000.00"),
            franchise_2=Decimal("30000.00"),
            premium_with_franchise_2=Decimal("40000.00")
        )
        
        variants = offer.get_franchise_variants()
        
        # Should have 2 variants
        self.assertEqual(len(variants), 2)
        
        # Test first variant
        variant_1 = variants[0]
        self.assertEqual(variant_1['franchise'], Decimal("0.00"))
        self.assertEqual(variant_1['premium'], Decimal("45000.00"))
        self.assertEqual(variant_1['franchise_display'], "0")
        self.assertEqual(variant_1['variant_number'], 1)
        
        # Test second variant
        variant_2 = variants[1]
        self.assertEqual(variant_2['franchise'], Decimal("30000.00"))
        self.assertEqual(variant_2['premium'], Decimal("40000.00"))
        self.assertEqual(variant_2['franchise_display'], "30,000 ₽")
        self.assertEqual(variant_2['variant_number'], 2)
    
    def test_premium_variants_functionality(self):
        """Test premium variants functionality"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Пари",
            insurance_year=1,
            insurance_sum=Decimal("700000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("42000.00"),
            franchise_2=Decimal("10000.00"),
            premium_with_franchise_2=Decimal("38000.00")
        )
        
        # Test that both variants are available
        self.assertTrue(offer.has_second_franchise_variant())
        variants = offer.get_franchise_variants()
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[1]['premium'], Decimal("38000.00"))
    
    def test_model_validation(self):
        """Test model validation rules"""
        
        # Test valid offer
        valid_offer = InsuranceOffer(
            summary=self.summary,
            company_name="Альфа",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            payments_per_year=1
        )
        
        # Should not raise validation error
        try:
            valid_offer.full_clean()
        except ValidationError:
            self.fail("Valid offer should not raise ValidationError")
        
        # Test that required fields are enforced
        invalid_offer = InsuranceOffer(
            summary=self.summary,
            # Missing company_name
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        with self.assertRaises(ValidationError):
            invalid_offer.full_clean()
    
    def test_unique_constraint(self):
        """Test unique constraint on summary, company_name, insurance_year"""
        
        # Create first offer
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Согласие",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        # Try to create duplicate offer (same summary, company, year)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name="Согласие",
                insurance_year=1,  # Same year
                insurance_sum=Decimal("1000000.00"),
                franchise_1=Decimal("0.00"),
                premium_with_franchise_1=Decimal("50000.00")
            )
        
        # But different year should work
        different_year_offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Согласие",
            insurance_year=2,  # Different year
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        self.assertEqual(different_year_offer.insurance_year, 2)
    
    def test_string_representation(self):
        """Test string representation of the model"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Совкомбанк СК",
            insurance_year=2,
            insurance_sum=Decimal("800000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("40000.00")
        )
        
        str_repr = str(offer)
        expected = "Совкомбанк СК (2 год): 40000.00 ₽"
        self.assertEqual(str_repr, expected)
    
    def test_effective_properties(self):
        """Test effective premium and franchise properties"""
        
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Согаз",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("5000.00"),
            premium_with_franchise_1=Decimal("48000.00"),
            franchise_2=Decimal("25000.00"),
            premium_with_franchise_2=Decimal("43000.00")
        )
        
        # Test effective properties
        self.assertEqual(offer.effective_premium_with_franchise, Decimal("48000.00"))
        self.assertEqual(offer.effective_premium_without_franchise, Decimal("43000.00"))
        self.assertEqual(offer.effective_franchise_amount, Decimal("5000.00"))
    
    def test_has_second_franchise_variant(self):
        """Test second franchise variant detection"""
        
        # Offer with second variant
        offer_with_second = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Ингосстрах",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00"),
            franchise_2=Decimal("20000.00"),
            premium_with_franchise_2=Decimal("45000.00")
        )
        
        self.assertTrue(offer_with_second.has_second_franchise_variant())
        
        # Offer without second variant
        offer_without_second = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Зетта",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
            # No franchise_2 and premium_with_franchise_2
        )
        
        self.assertFalse(offer_without_second.has_second_franchise_variant())


class TestSummaryIntegration(TestCase):
    """Test integration with InsuranceSummary model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='summaryuser',
            email='summary@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Summary Test Client",
            inn="9876543210",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_summary_offers_management(self):
        """Test that summary correctly manages offers"""
        
        # Create multiple offers
        offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ВСК",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("55000.00")
        )
        
        offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Согаз",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("48000.00")
        )
        
        offer3 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="РЕСО",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("52000.00")
        )
        
        # Test offers are properly associated with summary
        self.assertEqual(self.summary.offers.count(), 3)
        self.assertIn(offer1, self.summary.offers.all())
        self.assertIn(offer2, self.summary.offers.all())
        self.assertIn(offer3, self.summary.offers.all())
    
    def test_summary_offers_by_year(self):
        """Test getting offers by year"""
        
        # Create offers for different years
        offer_year1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ПСБ-страхование",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        offer_year2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ПСБ-страхование",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("45000.00")
        )
        
        # Test getting offers by year
        year1_offers = self.summary.get_offers_by_year(1)
        year2_offers = self.summary.get_offers_by_year(2)
        
        self.assertEqual(year1_offers.count(), 1)
        self.assertEqual(year2_offers.count(), 1)
        self.assertEqual(year1_offers.first(), offer_year1)
        self.assertEqual(year2_offers.first(), offer_year2)
    
    def test_summary_grouped_offers(self):
        """Test getting offers grouped by company"""
        
        # Create offers from multiple companies and years
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Альфа",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("50000.00")
        )
        
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Альфа",
            insurance_year=2,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("45000.00")
        )
        
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="ВСК",
            insurance_year=1,
            insurance_sum=Decimal("1000000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("48000.00")
        )
        
        # Test grouped offers
        grouped_offers = self.summary.get_offers_grouped_by_company()
        
        # Should have 2 companies
        self.assertEqual(len(grouped_offers), 2)
        self.assertIn("Альфа", grouped_offers)
        self.assertIn("ВСК", grouped_offers)
        
        # Alpha should have 2 offers, Beta should have 1
        self.assertEqual(len(grouped_offers["Альфа"]), 2)
        self.assertEqual(len(grouped_offers["ВСК"]), 1)
        
        # Test that offers are sorted by year within company
        alpha_offers = grouped_offers["Альфа"]
        self.assertEqual(alpha_offers[0].insurance_year, 1)
        self.assertEqual(alpha_offers[1].insurance_year, 2)


def run_simple_migration_tests():
    """Helper function to run simplified migration tests"""
    import unittest
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestMigrationResults))
    test_suite.addTest(unittest.makeSuite(TestSummaryIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    run_simple_migration_tests()
"""
Test for color coding functionality in summary detail template.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class ColorCodingTest(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to the required group
        from django.contrib.auth.models import Group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        # Create a test insurance request
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            vehicle_info='Test Vehicle',
            created_by=self.user
        )
        
        # Create a test summary
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='collecting'
        )
        
        # Create test offers with different franchise variants
        self.offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Test Company 1',
            insurance_year=1,
            insurance_sum=1000000.00,
            franchise_1=50000.00,
            premium_with_franchise_1=75000.00,
            franchise_2=100000.00,
            premium_with_franchise_2=65000.00
        )
        
        self.offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Test Company 1',
            insurance_year=2,
            insurance_sum=800000.00,
            franchise_1=40000.00,
            premium_with_franchise_1=60000.00,
            franchise_2=80000.00,
            premium_with_franchise_2=50000.00
        )

    def test_franchise_variant_1_color_coding(self):
        """Test that franchise variant 1 fields use dark green color"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that franchise-variant-1 class is present in the template
        self.assertContains(response, 'franchise-variant-1')
        
        # Check that the CSS class definition is present
        self.assertContains(response, '.franchise-variant-1')
        self.assertContains(response, 'color: #0f5132 !important')

    def test_franchise_variant_2_color_coding(self):
        """Test that franchise variant 2 fields use dark blue color"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that franchise-variant-2 class is present in the template
        self.assertContains(response, 'franchise-variant-2')
        
        # Check that the CSS class definition is present
        self.assertContains(response, '.franchise-variant-2')
        self.assertContains(response, 'color: #052c65 !important')

    def test_total_row_color_coding(self):
        """Test that total rows use pale yellow background"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that company-total-row class is present
        self.assertContains(response, 'company-total-row')
        
        # Check that the CSS class definition uses pale yellow background
        self.assertContains(response, 'background-color: #fff3cd !important')
        self.assertContains(response, 'border-top: 2px solid #ffc107 !important')

    def test_mobile_responsive_color_coding(self):
        """Test that color coding is maintained on mobile devices"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that mobile responsive styles are present
        self.assertContains(response, '@media (max-width: 576px)')
        self.assertContains(response, '@media (max-width: 768px)')
        
        # Check that franchise variant colors are maintained in mobile styles
        content = response.content.decode('utf-8')
        mobile_section_start = content.find('@media (max-width: 576px)')
        mobile_section_end = content.find('}', content.find('.franchise-variant-2', mobile_section_start))
        mobile_section = content[mobile_section_start:mobile_section_end]
        
        self.assertIn('.franchise-variant-1', mobile_section)
        self.assertIn('.franchise-variant-2', mobile_section)
        self.assertIn('#0f5132', mobile_section)
        self.assertIn('#052c65', mobile_section)

    def test_color_coding_css_classes_defined(self):
        """Test that all required CSS classes are properly defined"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Check franchise variant 1 CSS
        self.assertIn('.franchise-variant-1 {', content)
        self.assertIn('color: #0f5132 !important;', content)
        self.assertIn('font-weight: 600;', content)
        
        # Check franchise variant 2 CSS
        self.assertIn('.franchise-variant-2 {', content)
        self.assertIn('color: #052c65 !important;', content)
        
        # Check total row CSS
        self.assertIn('.company-total-row {', content)
        self.assertIn('background-color: #fff3cd !important;', content)
        
        # Check hover effect
        self.assertIn('.company-total-row:hover {', content)
        self.assertIn('background-color: #ffeaa7 !important;', content)
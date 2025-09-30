from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from .models import InsuranceRequest


class CascoCEListDisplayTests(TestCase):
    """Tests for КАСКО C/E display in request list template"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to 'Пользователи' group for access
        users_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(users_group)
        
        # Create request with КАСКО C/E enabled
        self.request_with_casco_ce = InsuranceRequest.objects.create(
            client_name='Client With КАСКО C/E',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            vehicle_info='Test vehicle',
            branch='Москва',
            dfa_number='DFA-2024-001',
            has_casco_ce=True,
            has_franchise=True,  # Also add franchise to test multiple features
            created_by=self.user
        )
        
        # Create request without КАСКО C/E
        self.request_without_casco_ce = InsuranceRequest.objects.create(
            client_name='Client Without КАСКО C/E',
            inn='0987654321',
            insurance_type='КАСКО',
            insurance_period='6 месяцев',
            vehicle_info='Another vehicle',
            branch='Казань',
            dfa_number='DFA-2024-002',
            has_casco_ce=False,
            has_installment=True,  # Add installment to test other features
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_casco_ce_displayed_in_features_section(self):
        """Test that КАСКО C/E is displayed in the features section when enabled"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that КАСКО C/E badge is displayed for the request that has it
        self.assertContains(response, 'КАСКО кат. C/E')
        
        # Check that the badge has correct styling and attributes
        self.assertContains(response, 'badge bg-primary')
        self.assertContains(response, 'title="КАСКО кат. C/E"')
        
        # Check responsive display - full text on large screens
        self.assertContains(response, '<span class="d-none d-xl-inline">КАСКО кат. C/E</span>')
        
        # Check responsive display - abbreviated text on small screens
        self.assertContains(response, '<span class="d-xl-none">C/E</span>')
    
    def test_casco_ce_not_displayed_when_disabled(self):
        """Test that КАСКО C/E is not displayed when disabled"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        
        # The response should contain the КАСКО C/E badge only once (for the enabled request)
        content = response.content.decode()
        casco_ce_count = content.count('КАСКО кат. C/E')
        
        # Should appear twice: once in full text span, once in title attribute
        self.assertEqual(casco_ce_count, 2)
    
    def test_multiple_features_displayed_correctly(self):
        """Test that multiple features are displayed correctly with proper separation"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that both franchise and КАСКО C/E are displayed for the first request
        content = response.content.decode()
        
        # Find the features section for the request with both features
        self.assertContains(response, 'Франшиза')
        self.assertContains(response, 'КАСКО кат. C/E')
        
        # Check that installment is displayed for the second request
        self.assertContains(response, 'Рассрочка')
    
    def test_features_section_structure(self):
        """Test that the features section has correct HTML structure"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check that features are wrapped in the correct div structure
        self.assertIn('<div class="d-flex flex-wrap gap-1">', content)
        
        # Check that КАСКО C/E badge has correct structure (rendered HTML, not template syntax)
        self.assertIn('<span class="badge bg-primary" title="КАСКО кат. C/E">', content)
    
    def test_casco_ce_badge_styling_consistency(self):
        """Test that КАСКО C/E badge styling is consistent with other feature badges"""
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check that all badges follow the same pattern with responsive text
        # Franchise badge pattern
        self.assertIn('<span class="d-none d-xl-inline">Франшиза</span>', content)
        self.assertIn('<span class="d-xl-none">Ф</span>', content)
        
        # Installment badge pattern
        self.assertIn('<span class="d-none d-xl-inline">Рассрочка</span>', content)
        self.assertIn('<span class="d-xl-none">Р</span>', content)
        
        # КАСКО C/E badge pattern (should follow same structure)
        self.assertIn('<span class="d-none d-xl-inline">КАСКО кат. C/E</span>', content)
        self.assertIn('<span class="d-xl-none">C/E</span>', content)
    
    def test_empty_features_section_when_no_features(self):
        """Test features section when no features are enabled"""
        # Create a request with no features enabled
        request_no_features = InsuranceRequest.objects.create(
            client_name='Client No Features',
            inn='5555555555',
            insurance_type='КАСКО',
            insurance_period='12 месяцев',
            vehicle_info='Test vehicle',
            branch='Москва',
            dfa_number='DFA-2024-003',
            has_casco_ce=False,
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            created_by=self.user
        )
        
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        self.assertEqual(response.status_code, 200)
        
        # The features div should still exist but be empty for this request
        # We can't easily test this without parsing HTML, but we can verify
        # that the template structure is maintained
        self.assertContains(response, '<div class="d-flex flex-wrap gap-1">')
"""
Integration test for status display functionality
"""
from django.test import TestCase
from django.contrib.auth.models import User
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary
from summaries.templatetags.summary_extras import status_color, status_display_name


class StatusIntegrationTest(TestCase):
    """Test integration between model status display and templatetags"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='sent'
        )
    
    def test_model_status_display(self):
        """Test that model returns correct status display"""
        self.assertEqual(self.summary.get_status_display(), 'Отправлен в Альянс')
    
    def test_templatetag_status_color(self):
        """Test that templatetag returns correct color for sent status"""
        self.assertEqual(status_color('sent'), 'secondary')  # Updated to match status_colors.py
    
    def test_templatetag_status_display_name(self):
        """Test that templatetag returns correct status name"""
        self.assertEqual(status_display_name('sent'), 'Отправлен в Альянс')
    
    def test_all_status_values(self):
        """Test all status values work correctly"""
        status_tests = [
            ('collecting', 'Сбор предложений', 'warning'),
            ('ready', 'Готов к отправке', 'info'),
            ('sent', 'Отправлен в Альянс', 'secondary'),  # Updated to match status_colors.py
            ('completed_accepted', 'Завершен: акцепт/распоряжение', 'success'),  # New status
            ('completed_rejected', 'Завершен: не будет', 'danger'),  # New status
        ]
        
        for status_value, expected_display, expected_color in status_tests:
            self.summary.status = status_value
            self.summary.save()
            
            # Test model method
            self.assertEqual(self.summary.get_status_display(), expected_display)
            
            # Test templatetag filters
            self.assertEqual(status_color(status_value), expected_color)
            self.assertEqual(status_display_name(status_value), expected_display)
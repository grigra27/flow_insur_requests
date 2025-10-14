"""
Tests for insurance_requests app
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import InsuranceRequest


class RequestDetailViewTest(TestCase):
    """Test the request detail view with summary creation button"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to the required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.client.login(username='testuser', password='testpass123')
        
        # Create a test request
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            status='uploaded',
            created_by=self.user
        )
    
    def test_create_summary_button_shown_for_uploaded_status(self):
        """Test that create summary button is shown for uploaded status"""
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertContains(response, 'Можно создать свод и добавить предложения вручную')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_create_summary_button_shown_for_email_generated_status(self):
        """Test that create summary button is shown for email_generated status"""
        self.request.status = 'email_generated'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertContains(response, 'Рекомендуется сначала отправить письма страховщикам')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_create_summary_button_shown_for_email_sent_status(self):
        """Test that create summary button is shown for email_sent status"""
        self.request.status = 'email_sent'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_create_summary_button_shown_for_response_received_status(self):
        """Test that create summary button is shown for response_received status"""
        self.request.status = 'response_received'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_summary_unavailable_for_other_statuses(self):
        """Test that summary is unavailable for other statuses"""
        self.request.status = 'completed'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Создать свод')
        # Should show the status from get_summary_status method
        self.assertContains(response, 'Свод недоступен')
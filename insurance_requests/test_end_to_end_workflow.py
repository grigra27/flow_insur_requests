"""
End-to-end workflow tests for complete user workflows from login to request processing
Tests admin and regular user access patterns and email generation with all new features
"""
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.core.management import call_command
from django.core import mail
from django.test.utils import override_settings
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
import tempfile
import os
import io

from .models import InsuranceRequest, RequestAttachment, InsuranceResponse
from .forms import InsuranceRequestForm
from core.templates import EmailTemplateGenerator
from core.excel_utils import ExcelReader


class CompleteUserWorkflowTests(TransactionTestCase):
    """Tests for complete user workflow from login to request processing"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Set up groups and users using management command
        call_command('setup_user_groups')
        
        # Get created users
        self.admin_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='user')
        
        # Create test insurance request data
        self.test_request_data = {
            'client_name': 'ООО "Тестовая Компания"',
            'inn': '1234567890',
            'insurance_type': 'страхование имущества',
            'insurance_start_date': date(2024, 6, 1),
            'insurance_end_date': date(2025, 6, 1),
            'vehicle_info': 'Офисное здание, г. Москва',
            'dfa_number': 'DFA-2024-001',
            'branch': 'Московский филиал',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
            'response_deadline': datetime.now() + timedelta(days=7)
        }
    
    def test_complete_admin_workflow_from_login_to_email_generation(self):
        """Test complete admin workflow from login to email generation"""
        # Step 1: Login as admin
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 2: Access main page
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Список страховых заявок')
        
        # Step 3: Create new insurance request
        request = InsuranceRequest.objects.create(
            client_name=self.test_request_data['client_name'],
            inn=self.test_request_data['inn'],
            insurance_type=self.test_request_data['insurance_type'],
            insurance_start_date=self.test_request_data['insurance_start_date'],
            insurance_end_date=self.test_request_data['insurance_end_date'],
            vehicle_info=self.test_request_data['vehicle_info'],
            dfa_number=self.test_request_data['dfa_number'],
            branch=self.test_request_data['branch'],
            has_franchise=self.test_request_data['has_franchise'],
            has_installment=self.test_request_data['has_installment'],
            has_autostart=self.test_request_data['has_autostart'],
            response_deadline=self.test_request_data['response_deadline'],
            created_by=self.admin_user
        )
        
        # Step 4: View request detail
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.test_request_data['client_name'])
        self.assertContains(response, 'страхование имущества')
        
        # Step 5: Edit request
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="insurance_start_date"')
        self.assertContains(response, 'name="insurance_end_date"')
        
        # Step 6: Update request with new data
        updated_data = {
            'client_name': 'ООО "Обновленная Компания"',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_start_date': '2024-07-01',
            'insurance_end_date': '2025-07-01',
            'vehicle_info': 'Обновленная информация о транспорте',
            'dfa_number': 'DFA-2024-002',
            'branch': 'Санкт-Петербургский филиал',
            'has_franchise': False,
            'has_installment': True,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=updated_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Step 7: Verify changes were saved
        request.refresh_from_db()
        self.assertEqual(request.client_name, 'ООО "Обновленная Компания"')
        self.assertEqual(request.insurance_type, 'КАСКО')
        self.assertEqual(request.insurance_start_date, date(2024, 7, 1))
        self.assertEqual(request.insurance_end_date, date(2025, 7, 1))
        
        # Step 8: Test email generation with enhanced features
        with patch('core.mail_utils.send_email') as mock_send_email:
            mock_send_email.return_value = True
            
            # Generate email template
            template_generator = EmailTemplateGenerator()
            request_data = {
                'insurance_type': request.insurance_type,
                'insurance_start_date': request.insurance_start_date,
                'insurance_end_date': request.insurance_end_date,
                'inn': request.inn,
                'has_franchise': request.has_franchise,
                'has_installment': request.has_installment,
                'has_autostart': request.has_autostart,
                'response_deadline': request.response_deadline,
            }
            email_body = template_generator.generate_email_body(request_data)
            
            # Verify enhanced insurance type description
            self.assertIn('страхование каско по условиям клиента', email_body)
            
            # Verify separate date formatting
            self.assertIn('с 01.07.2024 по 01.07.2025', email_body)
            
            # Verify other enhanced features
            self.assertIn('1234567890', email_body)  # INN instead of company name
        
        # Step 9: Test preview email functionality
        response = self.client.get(
            reverse('insurance_requests:preview_email', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'страхование каско по условиям клиента')
        self.assertContains(response, 'с 01.07.2024 по 01.07.2025')
        
        # Step 10: Logout
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        
        # Step 11: Verify logout worked
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)  # Should redirect to login
    
    def test_complete_regular_user_workflow(self):
        """Test complete regular user workflow"""
        # Step 1: Login as regular user
        response = self.client.post(reverse('login'), {
            'username': 'user',
            'password': 'user123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 2: Access main page
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Step 3: Create insurance request
        request = InsuranceRequest.objects.create(
            client_name='ООО "Пользовательская Компания"',
            inn='9876543210',
            insurance_type='страхование спецтехники',
            insurance_start_date=date(2024, 8, 1),
            insurance_end_date=date(2025, 8, 1),
            vehicle_info='Экскаватор JCB',
            dfa_number='DFA-USER-001',
            branch='Региональный филиал',
            created_by=self.regular_user
        )
        
        # Step 4: View request detail
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ООО "Пользовательская Компания"')
        
        # Step 5: Edit request (regular users should have access)
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Step 6: Update request
        updated_data = {
            'client_name': 'ООО "Пользовательская Компания"',
            'inn': '9876543210',
            'insurance_type': 'другое',
            'insurance_start_date': '2024-09-01',
            'insurance_end_date': '2025-09-01',
            'vehicle_info': 'Обновленная спецтехника',
            'dfa_number': 'DFA-USER-002',
            'branch': 'Региональный филиал',
            'has_franchise': True,
            'has_installment': True,
            'has_autostart': False,
        }
        
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data=updated_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Step 7: Verify changes
        request.refresh_from_db()
        self.assertEqual(request.insurance_type, 'другое')
        self.assertEqual(request.insurance_start_date, date(2024, 9, 1))
        
        # Step 8: Test email generation for regular user
        template_generator = EmailTemplateGenerator()
        request_data = {
            'insurance_type': request.insurance_type,
            'insurance_start_date': request.insurance_start_date,
            'insurance_end_date': request.insurance_end_date,
            'inn': request.inn,
            'has_franchise': request.has_franchise,
            'has_installment': request.has_installment,
            'has_autostart': request.has_autostart,
            'response_deadline': request.response_deadline,
        }
        email_body = template_generator.generate_email_body(request_data)
        
        # Verify enhanced description for "другое" type
        self.assertIn('разная другая фигня', email_body)
        self.assertIn('с 01.09.2024 по 01.09.2025', email_body)
    
    def test_excel_upload_workflow_with_new_insurance_type(self):
        """Test Excel upload workflow with new insurance type detection"""
        # Login as admin
        self.client.login(username='admin', password='admin123')
        
        # Create test Excel file with property insurance
        test_excel_content = self._create_test_excel_with_property_insurance()
        
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            temp_file.write(test_excel_content)
            temp_file_path = temp_file.name
        
        try:
            # Upload Excel file
            with open(temp_file_path, 'rb') as excel_file:
                response = self.client.post(
                    reverse('insurance_requests:upload_excel'),
                    {'excel_file': excel_file},
                    follow=True
                )
            
            self.assertEqual(response.status_code, 200)
            
            # Verify that property insurance type was detected
            requests = InsuranceRequest.objects.filter(
                insurance_type='страхование имущества'
            )
            self.assertGreater(requests.count(), 0)
            
            # Test email generation for property insurance
            if requests.exists():
                request = requests.first()
                template_generator = EmailTemplateGenerator()
                request_data = {
                    'insurance_type': request.insurance_type,
                    'insurance_start_date': request.insurance_start_date,
                    'insurance_end_date': request.insurance_end_date,
                    'inn': request.inn,
                    'has_franchise': request.has_franchise,
                    'has_installment': request.has_installment,
                    'has_autostart': request.has_autostart,
                    'response_deadline': request.response_deadline,
                }
                email_body = template_generator.generate_email_body(request_data)
                
                # Verify enhanced description for property insurance
                self.assertIn('клиентское имузество', email_body)
        
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
    def test_access_control_workflow(self):
        """Test access control workflow for different user types"""
        # Create user without groups
        no_group_user = User.objects.create_user(
            username='no_group',
            password='testpass123'
        )
        
        # Test 1: User without groups should be denied access
        self.client.login(username='no_group', password='testpass123')
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Доступ запрещен')
        
        # Test 2: Regular user should have limited access
        self.client.login(username='user', password='user123')
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Test 3: Admin should have full access
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_session_persistence_across_workflow(self):
        """Test that user session persists across complete workflow"""
        # Login
        self.client.login(username='admin', password='admin123')
        
        # Perform multiple operations
        operations = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
        ]
        
        for url in operations:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            # Verify user remains authenticated
            self.assertTrue(response.wsgi_request.user.is_authenticated)
            self.assertEqual(response.wsgi_request.user.username, 'admin')
    
    def _create_test_excel_with_property_insurance(self):
        """Create test Excel content with property insurance type"""
        # This would create actual Excel content in a real implementation
        # For testing purposes, we'll return mock content
        return b'Mock Excel content with property insurance'


class AdminAndRegularUserAccessPatternsTests(TestCase):
    """Tests for admin and regular user access patterns"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Set up users and groups
        call_command('setup_user_groups')
        self.admin_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='user')
        
        # Create test request
        self.test_request = InsuranceRequest.objects.create(
            client_name='Test Access Client',
            inn='1111111111',
            insurance_type='КАСКО',
            created_by=self.admin_user
        )
    
    def test_admin_access_patterns(self):
        """Test admin user access patterns"""
        self.client.login(username='admin', password='admin123')
        
        # Admin should have access to all views
        admin_accessible_urls = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
            reverse('insurance_requests:request_detail', kwargs={'pk': self.test_request.pk}),
            reverse('insurance_requests:edit_request', kwargs={'pk': self.test_request.pk}),
            reverse('insurance_requests:preview_email', kwargs={'pk': self.test_request.pk}),
        ]
        
        for url in admin_accessible_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, [200, 302])  # 200 for GET, 302 for redirects
    
    def test_regular_user_access_patterns(self):
        """Test regular user access patterns"""
        self.client.login(username='user', password='user123')
        
        # Regular user should have access to basic functionality
        user_accessible_urls = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
            reverse('insurance_requests:request_detail', kwargs={'pk': self.test_request.pk}),
            reverse('insurance_requests:edit_request', kwargs={'pk': self.test_request.pk}),
            reverse('insurance_requests:preview_email', kwargs={'pk': self.test_request.pk}),
        ]
        
        for url in user_accessible_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, [200, 302])
    
    def test_unauthenticated_user_access_patterns(self):
        """Test unauthenticated user access patterns"""
        # Unauthenticated users should be redirected to login
        protected_urls = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
            reverse('insurance_requests:request_detail', kwargs={'pk': self.test_request.pk}),
            reverse('insurance_requests:edit_request', kwargs={'pk': self.test_request.pk}),
        ]
        
        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login/', response.url)
    
    def test_user_without_groups_access_patterns(self):
        """Test user without groups access patterns"""
        # Create user without any groups
        no_group_user = User.objects.create_user(
            username='no_group',
            password='testpass123'
        )
        
        self.client.login(username='no_group', password='testpass123')
        
        # Should get access denied
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 403)
    
    def test_role_based_functionality_differences(self):
        """Test differences in functionality between admin and regular users"""
        # Create requests by both users
        admin_request = InsuranceRequest.objects.create(
            client_name='Admin Request',
            inn='2222222222',
            insurance_type='КАСКО',
            created_by=self.admin_user
        )
        
        user_request = InsuranceRequest.objects.create(
            client_name='User Request',
            inn='3333333333',
            insurance_type='другое',
            created_by=self.regular_user
        )
        
        # Test admin can access all requests
        self.client.login(username='admin', password='admin123')
        
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': admin_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': user_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Test regular user can access requests
        self.client.login(username='user', password='user123')
        
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': admin_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': user_request.pk})
        )
        self.assertEqual(response.status_code, 200)


class EmailGenerationWithAllNewFeaturesTests(TestCase):
    """Tests for email generation with all new features"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create test requests for each insurance type
        self.kasko_request = InsuranceRequest.objects.create(
            client_name='КАСКО Клиент',
            inn='1111111111',
            insurance_type='КАСКО',
            insurance_start_date=date(2024, 6, 1),
            insurance_end_date=date(2025, 6, 1),
            vehicle_info='BMW X5',
            dfa_number='KASKO-001',
            branch='Московский филиал',
            has_franchise=True,
            has_installment=False,
            has_autostart=True,
            created_by=self.user
        )
        
        self.special_tech_request = InsuranceRequest.objects.create(
            client_name='Спецтехника Клиент',
            inn='2222222222',
            insurance_type='страхование спецтехники',
            insurance_start_date=date(2024, 7, 15),
            insurance_end_date=date(2025, 7, 15),
            vehicle_info='Экскаватор Caterpillar',
            dfa_number='TECH-002',
            branch='Санкт-Петербургский филиал',
            created_by=self.user
        )
        
        self.property_request = InsuranceRequest.objects.create(
            client_name='Имущество Клиент',
            inn='3333333333',
            insurance_type='страхование имущества',
            insurance_start_date=date(2024, 8, 1),
            insurance_end_date=date(2025, 8, 1),
            vehicle_info='Офисное здание',
            dfa_number='PROP-003',
            branch='Новосибирский филиал',
            created_by=self.user
        )
        
        self.other_request = InsuranceRequest.objects.create(
            client_name='Другое Клиент',
            inn='4444444444',
            insurance_type='другое',
            insurance_start_date=date(2024, 9, 1),
            insurance_end_date=date(2025, 9, 1),
            vehicle_info='Специальное оборудование',
            dfa_number='OTHER-004',
            branch='Екатеринбургский филиал',
            created_by=self.user
        )
    
    def test_email_generation_with_enhanced_kasko_description(self):
        """Test email generation with enhanced КАСКО description"""
        template_generator = EmailTemplateGenerator()
        request_data = {
            'insurance_type': self.kasko_request.insurance_type,
            'insurance_start_date': self.kasko_request.insurance_start_date,
            'insurance_end_date': self.kasko_request.insurance_end_date,
            'inn': self.kasko_request.inn,
            'has_franchise': self.kasko_request.has_franchise,
            'has_installment': self.kasko_request.has_installment,
            'has_autostart': self.kasko_request.has_autostart,
            'response_deadline': self.kasko_request.response_deadline,
        }
        email_body = template_generator.generate_email_body(request_data)
        
        # Verify enhanced description
        self.assertIn('страхование каско по условиям клиента', email_body)
        
        # Verify separate date formatting
        self.assertIn('с 01.06.2024 по 01.06.2025', email_body)
        
        # Verify other data
        self.assertIn('1111111111', email_body)  # INN
    
    def test_email_generation_with_enhanced_special_tech_description(self):
        """Test email generation with enhanced special tech description"""
        template_generator = EmailTemplateGenerator()
        request_data = {
            'insurance_type': self.special_tech_request.insurance_type,
            'insurance_start_date': self.special_tech_request.insurance_start_date,
            'insurance_end_date': self.special_tech_request.insurance_end_date,
            'inn': self.special_tech_request.inn,
            'has_franchise': self.special_tech_request.has_franchise,
            'has_installment': self.special_tech_request.has_installment,
            'has_autostart': self.special_tech_request.has_autostart,
            'response_deadline': self.special_tech_request.response_deadline,
        }
        email_body = template_generator.generate_email_body(request_data)
        
        # Verify enhanced description
        self.assertIn('спецтезника под клиента', email_body)
        
        # Verify separate date formatting
        self.assertIn('с 15.07.2024 по 15.07.2025', email_body)
        
        # Verify other data
        self.assertIn('2222222222', email_body)  # INN
    
    def test_email_generation_with_enhanced_property_description(self):
        """Test email generation with enhanced property insurance description"""
        template_generator = EmailTemplateGenerator()
        email_data = template_generator.generate_email_template(self.property_request)
        
        # Verify enhanced description for new insurance type
        self.assertIn('клиентское имузество', email_data['body'])
        
        # Verify separate date formatting
        self.assertIn('с 01.08.2024 по 01.08.2025', email_data['body'])
        
        # Verify other data
        self.assertIn('Имущество Клиент', email_data['body'])
        self.assertIn('PROP-003', email_data['body'])
    
    def test_email_generation_with_enhanced_other_description(self):
        """Test email generation with enhanced 'другое' description"""
        template_generator = EmailTemplateGenerator()
        email_data = template_generator.generate_email_template(self.other_request)
        
        # Verify enhanced description
        self.assertIn('разная другая фигня', email_data['body'])
        
        # Verify separate date formatting
        self.assertIn('с 01.09.2024 по 01.09.2025', email_data['body'])
        
        # Verify other data
        self.assertIn('Другое Клиент', email_data['body'])
        self.assertIn('OTHER-004', email_data['body'])
    
    def test_email_generation_with_partial_dates(self):
        """Test email generation with partial date information"""
        # Request with only start date
        start_only_request = InsuranceRequest.objects.create(
            client_name='Только Начало',
            inn='5555555555',
            insurance_type='КАСКО',
            insurance_start_date=date(2024, 10, 1),
            insurance_end_date=None,
            created_by=self.user
        )
        
        template_generator = EmailTemplateGenerator()
        email_data = template_generator.generate_email_template(start_only_request)
        
        # Should show start date with "не указано" for end date
        self.assertIn('с 01.10.2024 по не указано', email_data['body'])
        
        # Request with only end date
        end_only_request = InsuranceRequest.objects.create(
            client_name='Только Конец',
            inn='6666666666',
            insurance_type='КАСКО',
            insurance_start_date=None,
            insurance_end_date=date(2024, 11, 1),
            created_by=self.user
        )
        
        email_data = template_generator.generate_email_template(end_only_request)
        
        # Should show "не указано" for start date with end date
        self.assertIn('с не указано по 01.11.2024', email_data['body'])
        
        # Request with no dates
        no_dates_request = InsuranceRequest.objects.create(
            client_name='Без Дат',
            inn='7777777777',
            insurance_type='КАСКО',
            insurance_start_date=None,
            insurance_end_date=None,
            created_by=self.user
        )
        
        email_data = template_generator.generate_email_template(no_dates_request)
        
        # Should show "не указан" for period
        self.assertIn('Срок страхования: не указан', email_data['body'])
    
    def test_email_generation_with_all_boolean_flags(self):
        """Test email generation with all boolean flags combinations"""
        # Request with all flags True
        all_true_request = InsuranceRequest.objects.create(
            client_name='Все Опции',
            inn='8888888888',
            insurance_type='КАСКО',
            has_franchise=True,
            has_installment=True,
            has_autostart=True,
            created_by=self.user
        )
        
        template_generator = EmailTemplateGenerator()
        email_data = template_generator.generate_email_template(all_true_request)
        
        # Verify all flags are reflected in email
        self.assertIn('с франшизой', email_data['body'])
        self.assertIn('в рассрочку', email_data['body'])
        self.assertIn('с автозапуском', email_data['body'])
        
        # Request with all flags False
        all_false_request = InsuranceRequest.objects.create(
            client_name='Без Опций',
            inn='9999999999',
            insurance_type='КАСКО',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            created_by=self.user
        )
        
        email_data = template_generator.generate_email_template(all_false_request)
        
        # Verify flags are not mentioned when False
        self.assertNotIn('с франшизой', email_data['body'])
        self.assertNotIn('в рассрочку', email_data['body'])
        self.assertNotIn('с автозапуском', email_data['body'])
    
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_sending_integration(self):
        """Test complete email sending integration"""
        template_generator = EmailTemplateGenerator()
        
        # Generate and send email
        email_data = template_generator.generate_email_template(self.kasko_request)
        
        # Simulate sending email
        from django.core.mail import send_mail
        
        send_mail(
            subject=email_data['subject'],
            message=email_data['body'],
            from_email='test@example.com',
            recipient_list=['recipient@example.com'],
            fail_silently=False,
        )
        
        # Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        
        # Verify email content includes enhanced features
        self.assertIn('страхование каско по условиям клиента', sent_email.message().as_string())
        self.assertIn('с 01.06.2024 по 01.06.2025', sent_email.message().as_string())
    
    def test_email_template_fallback_for_unknown_insurance_type(self):
        """Test email template fallback for unknown insurance type"""
        # Create request with unknown insurance type
        unknown_request = InsuranceRequest.objects.create(
            client_name='Неизвестный Тип',
            inn='0000000000',
            insurance_type='неизвестный тип',
            created_by=self.user
        )
        
        template_generator = EmailTemplateGenerator()
        email_data = template_generator.generate_email_template(unknown_request)
        
        # Should fallback to original insurance type name
        self.assertIn('неизвестный тип', email_data['body'])
        
        # Should not contain any of the enhanced descriptions
        enhanced_descriptions = [
            'страхование каско по условиям клиента',
            'спецтезника под клиента',
            'клиентское имузество',
            'разная другая фигня'
        ]
        
        for description in enhanced_descriptions:
            self.assertNotIn(description, email_data['body'])


class WorkflowPerformanceTests(TestCase):
    """Tests for workflow performance and optimization"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        call_command('setup_user_groups')
        self.admin_user = User.objects.get(username='admin')
    
    def test_login_workflow_performance(self):
        """Test login workflow performance"""
        import time
        
        start_time = time.time()
        
        # Login
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        
        # Access main page
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        end_time = time.time()
        
        # Should complete within reasonable time (2 seconds for testing)
        total_time = end_time - start_time
        self.assertLess(total_time, 2.0)
        self.assertEqual(response.status_code, 200)
    
    def test_request_creation_workflow_performance(self):
        """Test request creation workflow performance"""
        self.client.login(username='admin', password='admin123')
        
        import time
        start_time = time.time()
        
        # Create multiple requests
        for i in range(10):
            InsuranceRequest.objects.create(
                client_name=f'Performance Test Client {i}',
                inn=f'{1000000000 + i}',
                insurance_type='КАСКО',
                created_by=self.admin_user
            )
        
        end_time = time.time()
        
        # Should create 10 requests within reasonable time
        total_time = end_time - start_time
        self.assertLess(total_time, 1.0)
        
        # Verify all requests were created
        self.assertEqual(
            InsuranceRequest.objects.filter(
                client_name__startswith='Performance Test Client'
            ).count(),
            10
        )
    
    def test_email_generation_performance(self):
        """Test email generation performance"""
        # Create test request
        request = InsuranceRequest.objects.create(
            client_name='Performance Email Test',
            inn='1234567890',
            insurance_type='страхование имущества',
            insurance_start_date=date(2024, 6, 1),
            insurance_end_date=date(2025, 6, 1),
            created_by=self.admin_user
        )
        
        template_generator = EmailTemplateGenerator()
        
        import time
        start_time = time.time()
        
        # Generate multiple emails
        for _ in range(50):
            email_data = template_generator.generate_email_template(request)
            self.assertIsNotNone(email_data)
        
        end_time = time.time()
        
        # Should generate 50 emails within reasonable time
        total_time = end_time - start_time
        self.assertLess(total_time, 2.0)
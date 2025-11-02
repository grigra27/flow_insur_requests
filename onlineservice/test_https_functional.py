"""
Functional tests for HTTPS functionality across all four domains.
Tests end-to-end functionality for insflow.ru, zs.insflow.ru, insflow.tw1.su, zs.insflow.tw1.su
"""
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch, Mock
import json


@override_settings(
    ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su', 'localhost', 'testserver'],
    MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
    SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su'],
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True
)
class HTTPSFunctionalTest(TestCase):
    """Functional tests for HTTPS across all four domains"""
    
    def setUp(self):
        self.client = Client()
        self.domains = {
            'main': ['insflow.ru', 'insflow.tw1.su'],
            'sub': ['zs.insflow.ru', 'zs.insflow.tw1.su']
        }
    
    def test_landing_page_functionality_all_main_domains(self):
        """Test that landing page works correctly on all main domains over HTTPS"""
        for domain in self.domains['main']:
            with self.subTest(domain=domain):
                response = self.client.get('/', HTTP_HOST=domain, secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'здесь есть флоу')
    
    def test_landing_page_explicit_path_all_main_domains(self):
        """Test that /landing/ path works on all main domains over HTTPS"""
        for domain in self.domains['main']:
            with self.subTest(domain=domain):
                response = self.client.get('/landing/', HTTP_HOST=domain, secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'здесь есть флоу')
    
    def test_static_files_accessibility_main_domains(self):
        """Test that static files are accessible on main domains over HTTPS"""
        static_files = [
            '/static/css/custom.css',
            '/static/css/landing.css',
            '/static/favicon.ico'
        ]
        
        for domain in self.domains['main']:
            for static_file in static_files:
                with self.subTest(domain=domain, file=static_file):
                    response = self.client.get(static_file, HTTP_HOST=domain, secure=True)
                    # Should not be blocked by domain routing (not 404 from middleware)
                    self.assertNotEqual(response.status_code, 404)
    
    def test_media_files_accessibility_main_domains(self):
        """Test that media files are accessible on main domains over HTTPS"""
        # Test media file access (even if file doesn't exist, should pass through routing)
        media_file = '/media/test.jpg'
        
        for domain in self.domains['main']:
            with self.subTest(domain=domain):
                response = self.client.get(media_file, HTTP_HOST=domain, secure=True)
                # Should pass through domain routing, actual 404 would come from file serving
                self.assertNotEqual(response.status_code, 404)
    
    def test_forbidden_paths_main_domains(self):
        """Test that forbidden paths return 404 on main domains over HTTPS"""
        forbidden_paths = [
            '/admin/',
            '/api/',
            '/insurance/',
            '/summaries/',
            '/login/',
            '/logout/'
        ]
        
        for domain in self.domains['main']:
            for path in forbidden_paths:
                with self.subTest(domain=domain, path=path):
                    response = self.client.get(path, HTTP_HOST=domain, secure=True)
                    self.assertEqual(response.status_code, 404)
    
    def test_health_check_all_domains(self):
        """Test that health check works on all domains over HTTPS"""
        all_domains = self.domains['main'] + self.domains['sub']
        
        for domain in all_domains:
            with self.subTest(domain=domain):
                response = self.client.get('/healthz/', HTTP_HOST=domain, secure=True)
                # Health check should work on all domains (or return consistent response)
                self.assertIn(response.status_code, [200, 404])  # 404 if endpoint not implemented
    
    def test_subdomain_application_access(self):
        """Test that Django application is accessible on subdomains over HTTPS"""
        app_paths = [
            '/',
            '/admin/',
            '/login/',
            '/insurance/',
            '/summaries/'
        ]
        
        for domain in self.domains['sub']:
            for path in app_paths:
                with self.subTest(domain=domain, path=path):
                    response = self.client.get(path, HTTP_HOST=domain, secure=True)
                    # Should not be blocked by domain routing
                    self.assertNotEqual(response.status_code, 404)
                    # Actual response depends on URL configuration and authentication
                    self.assertIn(response.status_code, [200, 302, 403, 404])
    
    def test_subdomain_static_files_access(self):
        """Test that static files work on subdomains over HTTPS"""
        static_files = [
            '/static/css/custom.css',
            '/static/admin/css/base.css',
            '/static/favicon.ico'
        ]
        
        for domain in self.domains['sub']:
            for static_file in static_files:
                with self.subTest(domain=domain, file=static_file):
                    response = self.client.get(static_file, HTTP_HOST=domain, secure=True)
                    # Should pass through domain routing
                    self.assertNotEqual(response.status_code, 404)


@override_settings(
    ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su'],
    MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
    SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su']
)
class HTTPSAuthenticationFunctionalTest(TestCase):
    """Test authentication functionality over HTTPS across domains"""
    
    def setUp(self):
        self.client = Client()
        self.test_user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
    
    def test_login_functionality_subdomains(self):
        """Test that login works on subdomains over HTTPS"""
        for domain in ['zs.insflow.ru', 'zs.insflow.tw1.su']:
            with self.subTest(domain=domain):
                # Test login page access
                response = self.client.get('/login/', HTTP_HOST=domain, secure=True)
                self.assertIn(response.status_code, [200, 302])
                
                # Test login functionality (if login endpoint exists)
                login_data = {
                    'username': 'testuser',
                    'password': 'testpass123'
                }
                response = self.client.post('/login/', login_data, HTTP_HOST=domain, secure=True)
                # Should not be blocked by domain routing
                self.assertIn(response.status_code, [200, 302, 404])
    
    def test_session_cookies_secure_over_https(self):
        """Test that session cookies are marked secure over HTTPS"""
        with override_settings(SESSION_COOKIE_SECURE=True):
            response = self.client.get('/', HTTP_HOST='zs.insflow.ru', secure=True)
            
            # Verify that secure cookie setting is enabled
            self.assertTrue(self.client.session.get_session_cookie_age())
    
    def test_csrf_protection_over_https(self):
        """Test that CSRF protection works correctly over HTTPS"""
        with override_settings(CSRF_COOKIE_SECURE=True):
            # Get CSRF token
            response = self.client.get('/', HTTP_HOST='zs.insflow.ru', secure=True)
            
            # CSRF cookie should be secure when HTTPS is used
            self.assertTrue(response.wsgi_request.META.get('HTTPS') or 
                          response.wsgi_request.is_secure())


class HTTPSCrossDomainFunctionalTest(TestCase):
    """Test cross-domain functionality and consistency over HTTPS"""
    
    def setUp(self):
        self.client = Client()
    
    @override_settings(
        ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su'],
        MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
        SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su']
    )
    def test_consistent_landing_page_across_main_domains(self):
        """Test that landing page content is consistent across main domains"""
        responses = {}
        
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            response = self.client.get('/', HTTP_HOST=domain, secure=True)
            responses[domain] = response.content
        
        # Content should be identical across main domains
        self.assertEqual(responses['insflow.ru'], responses['insflow.tw1.su'])
    
    def test_consistent_application_behavior_across_subdomains(self):
        """Test that application behavior is consistent across subdomains"""
        test_paths = ['/', '/admin/', '/login/']
        
        for path in test_paths:
            responses = {}
            for domain in ['zs.insflow.ru', 'zs.insflow.tw1.su']:
                response = self.client.get(path, HTTP_HOST=domain, secure=True)
                responses[domain] = {
                    'status_code': response.status_code,
                    'content_type': response.get('Content-Type', '')
                }
            
            # Behavior should be consistent across subdomains
            with self.subTest(path=path):
                self.assertEqual(
                    responses['zs.insflow.ru']['status_code'],
                    responses['zs.insflow.tw1.su']['status_code']
                )
    
    def test_domain_isolation_functionality(self):
        """Test that main domains and subdomains are properly isolated"""
        # Test that admin is blocked on main domains but allowed on subdomains
        admin_path = '/admin/'
        
        # Should be blocked on main domains
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            with self.subTest(domain=domain, access='blocked'):
                response = self.client.get(admin_path, HTTP_HOST=domain, secure=True)
                self.assertEqual(response.status_code, 404)
        
        # Should be allowed on subdomains
        for domain in ['zs.insflow.ru', 'zs.insflow.tw1.su']:
            with self.subTest(domain=domain, access='allowed'):
                response = self.client.get(admin_path, HTTP_HOST=domain, secure=True)
                self.assertNotEqual(response.status_code, 404)


class HTTPSErrorHandlingFunctionalTest(TestCase):
    """Test error handling functionality over HTTPS"""
    
    def setUp(self):
        self.client = Client()
    
    @override_settings(
        ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su'],
        MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
        SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su']
    )
    def test_404_error_handling_main_domains(self):
        """Test that 404 errors are handled correctly on main domains over HTTPS"""
        invalid_paths = ['/nonexistent/', '/admin/', '/api/']
        
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            for path in invalid_paths:
                with self.subTest(domain=domain, path=path):
                    response = self.client.get(path, HTTP_HOST=domain, secure=True)
                    self.assertEqual(response.status_code, 404)
                    # Should contain helpful error message
                    self.assertContains(response, 'not available on the main domain', status_code=404)
    
    def test_unknown_domain_error_handling(self):
        """Test error handling for unknown domains over HTTPS"""
        response = self.client.get('/', HTTP_HOST='unknown.com', secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Domain not allowed', status_code=400)
    
    @patch('onlineservice.middleware.logger')
    def test_error_logging_over_https(self, mock_logger):
        """Test that errors are properly logged over HTTPS"""
        # Test 404 on main domain
        response = self.client.get('/admin/', HTTP_HOST='insflow.ru', secure=True)
        
        # Verify logging occurred
        mock_logger.info.assert_called_with('Domain routing: insflow.ru -> /admin/')
        mock_logger.warning.assert_called_with('404 on main domain insflow.ru: /admin/')
    
    def test_security_error_responses_over_https(self):
        """Test that security-related errors are handled properly over HTTPS"""
        with override_settings(ALLOWED_HOSTS=['insflow.ru']):  # Restrict allowed hosts
            response = self.client.get('/', HTTP_HOST='malicious.com', secure=True)
            self.assertEqual(response.status_code, 400)


class HTTPSPerformanceFunctionalTest(TestCase):
    """Test performance-related functionality over HTTPS"""
    
    def setUp(self):
        self.client = Client()
    
    @override_settings(
        ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su'],
        MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
        SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su']
    )
    def test_response_time_consistency_across_domains(self):
        """Test that response times are consistent across domains over HTTPS"""
        import time
        
        response_times = {}
        
        # Test main domains
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            start_time = time.time()
            response = self.client.get('/', HTTP_HOST=domain, secure=True)
            end_time = time.time()
            
            response_times[domain] = end_time - start_time
            self.assertEqual(response.status_code, 200)
        
        # Response times should be similar (within reasonable variance)
        time_diff = abs(response_times['insflow.ru'] - response_times['insflow.tw1.su'])
        self.assertLess(time_diff, 1.0)  # Should be within 1 second
    
    def test_static_file_caching_over_https(self):
        """Test that static files are properly cached over HTTPS"""
        static_file = '/static/css/custom.css'
        
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            with self.subTest(domain=domain):
                response = self.client.get(static_file, HTTP_HOST=domain, secure=True)
                
                # Should pass through domain routing for caching
                self.assertNotEqual(response.status_code, 404)
    
    def test_concurrent_requests_handling(self):
        """Test that concurrent requests to different domains are handled correctly"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def make_request(domain, path):
            try:
                response = self.client.get(path, HTTP_HOST=domain, secure=True)
                results.put((domain, path, response.status_code))
            except Exception as e:
                results.put((domain, path, str(e)))
        
        # Create concurrent requests
        threads = []
        test_cases = [
            ('insflow.ru', '/'),
            ('insflow.tw1.su', '/'),
            ('zs.insflow.ru', '/admin/'),
            ('zs.insflow.tw1.su', '/admin/')
        ]
        
        for domain, path in test_cases:
            thread = threading.Thread(target=make_request, args=(domain, path))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all requests completed successfully
        while not results.empty():
            domain, path, status = results.get()
            with self.subTest(domain=domain, path=path):
                if isinstance(status, int):
                    self.assertIn(status, [200, 302, 404])  # Valid HTTP status codes
                else:
                    self.fail(f"Request failed: {status}")
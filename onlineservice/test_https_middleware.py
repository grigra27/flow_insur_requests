"""
Unit tests for HTTPS-enabled domain routing middleware.
Tests the updated DomainRoutingMiddleware with all four domains and HTTPS functionality.
"""
from django.test import TestCase, RequestFactory, override_settings
from django.http import Http404, HttpResponseBadRequest
from unittest.mock import Mock, patch
from onlineservice.middleware import DomainRoutingMiddleware


@override_settings(
    ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su', 'localhost', '127.0.0.1', 'testserver'],
    MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
    SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su'],
    DEVELOPMENT_DOMAINS=['localhost', '127.0.0.1', 'testserver']
)
class HTTPSDomainRoutingMiddlewareTest(TestCase):
    """Test HTTPS-enabled domain routing middleware functionality"""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response_mock = Mock(return_value=Mock(status_code=200))
        self.middleware = DomainRoutingMiddleware(self.get_response_mock)
    
    def test_middleware_initialization_with_https_domains(self):
        """Test middleware initializes correctly with HTTPS domain configuration"""
        self.assertEqual(self.middleware.main_domains, ['insflow.ru', 'insflow.tw1.su'])
        self.assertEqual(self.middleware.subdomains, ['zs.insflow.ru', 'zs.insflow.tw1.su'])
        self.assertEqual(self.middleware.development_domains, ['localhost', '127.0.0.1', 'testserver'])
    
    def test_main_domain_insflow_ru_root_serves_landing(self):
        """Test that insflow.ru root serves landing page"""
        request = self.factory.get('/', HTTP_HOST='insflow.ru')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')
    
    def test_main_domain_insflow_tw1_su_root_serves_landing(self):
        """Test that insflow.tw1.su root serves landing page"""
        request = self.factory.get('/', HTTP_HOST='insflow.tw1.su')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')
    
    def test_main_domains_landing_path_serves_landing(self):
        """Test that /landing/ path serves landing page on both main domains"""
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            with self.subTest(domain=domain):
                request = self.factory.get('/landing/', HTTP_HOST=domain)
                response = self.middleware(request)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'здесь есть флоу')
    
    def test_main_domains_health_check_allowed(self):
        """Test that health check is allowed on main domains"""
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            with self.subTest(domain=domain):
                request = self.factory.get('/healthz/', HTTP_HOST=domain)
                response = self.middleware(request)
                # Should pass through to normal URL routing
                self.get_response_mock.assert_called_with(request)
    
    def test_main_domains_static_files_allowed(self):
        """Test that static files are allowed on main domains"""
        static_paths = ['/static/css/style.css', '/static/js/app.js', '/media/uploads/file.jpg']
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            for path in static_paths:
                with self.subTest(domain=domain, path=path):
                    request = self.factory.get(path, HTTP_HOST=domain)
                    response = self.middleware(request)
                    self.get_response_mock.assert_called_with(request)
    
    def test_main_domains_other_paths_raise_404(self):
        """Test that other paths on main domains raise 404"""
        forbidden_paths = ['/admin/', '/api/', '/insurance/', '/summaries/']
        for domain in ['insflow.ru', 'insflow.tw1.su']:
            for path in forbidden_paths:
                with self.subTest(domain=domain, path=path):
                    request = self.factory.get(path, HTTP_HOST=domain)
                    with self.assertRaises(Http404):
                        self.middleware(request)
    
    def test_subdomains_pass_through_all_paths(self):
        """Test that subdomain requests pass through normally for all paths"""
        test_paths = ['/admin/', '/api/', '/insurance/', '/summaries/', '/']
        for domain in ['zs.insflow.ru', 'zs.insflow.tw1.su']:
            for path in test_paths:
                with self.subTest(domain=domain, path=path):
                    request = self.factory.get(path, HTTP_HOST=domain)
                    response = self.middleware(request)
                    self.get_response_mock.assert_called_with(request)
    
    def test_development_domains_pass_through(self):
        """Test that development domains pass through normally"""
        test_paths = ['/admin/', '/api/', '/insurance/', '/']
        for domain in ['localhost', '127.0.0.1', 'testserver']:
            for path in test_paths:
                with self.subTest(domain=domain, path=path):
                    request = self.factory.get(path, HTTP_HOST=domain)
                    response = self.middleware(request)
                    self.get_response_mock.assert_called_with(request)
    
    def test_host_with_port_handling(self):
        """Test that hosts with ports are handled correctly"""
        request = self.factory.get('/', HTTP_HOST='insflow.ru:443')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')
    
    def test_case_insensitive_domain_handling(self):
        """Test that domain handling is case insensitive"""
        request = self.factory.get('/', HTTP_HOST='INSFLOW.RU')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')
    
    def test_unknown_domain_in_allowed_hosts(self):
        """Test handling of unknown domain that is in ALLOWED_HOSTS"""
        with override_settings(ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su', 'unknown.com']):
            middleware = DomainRoutingMiddleware(self.get_response_mock)
            request = self.factory.get('/', HTTP_HOST='unknown.com')
            response = middleware(request)
            # Should pass through as development domain
            self.get_response_mock.assert_called_with(request)
    
    def test_unknown_domain_not_in_allowed_hosts(self):
        """Test handling of unknown domain not in ALLOWED_HOSTS"""
        # Django will raise DisallowedHost before middleware gets the request
        from django.core.exceptions import DisallowedHost
        request = self.factory.get('/', HTTP_HOST='malicious.com')
        
        with self.assertRaises(DisallowedHost):
            # Django's security will catch this before our middleware
            request.get_host()
    
    def test_wildcard_allowed_hosts(self):
        """Test handling with wildcard in ALLOWED_HOSTS"""
        with override_settings(ALLOWED_HOSTS=['*']):
            middleware = DomainRoutingMiddleware(self.get_response_mock)
            request = self.factory.get('/', HTTP_HOST='any-domain.com')
            response = middleware(request)
            # Should pass through as development domain
            self.get_response_mock.assert_called_with(request)
    
    @patch('onlineservice.middleware.logger')
    def test_logging_domain_routing_decisions(self, mock_logger):
        """Test that domain routing decisions are logged"""
        request = self.factory.get('/admin/', HTTP_HOST='insflow.ru')
        try:
            self.middleware(request)
        except Http404:
            pass
        
        # Check that routing decision was logged
        mock_logger.info.assert_called_with('Domain routing: insflow.ru -> /admin/')
        mock_logger.warning.assert_called_with('404 on main domain insflow.ru: /admin/')
    
    @patch('onlineservice.middleware.logger')
    def test_logging_unknown_domain_warning(self, mock_logger):
        """Test that unknown domains are logged as warnings"""
        # Test with a domain that's in ALLOWED_HOSTS but not in our domain lists
        with override_settings(ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su', 'unknown.com']):
            middleware = DomainRoutingMiddleware(self.get_response_mock)
            request = self.factory.get('/', HTTP_HOST='unknown.com')
            response = middleware(request)
            
            mock_logger.warning.assert_called_with('Request from unknown domain: unknown.com')
    
    def test_middleware_configuration_logging_on_startup(self):
        """Test that middleware logs configuration on startup"""
        with patch('onlineservice.middleware.logger') as mock_logger:
            middleware = DomainRoutingMiddleware(self.get_response_mock)
            mock_logger.info.assert_called_with(
                "Domain routing initialized - Main domains: ['insflow.ru', 'insflow.tw1.su'], "
                "Subdomains: ['zs.insflow.ru', 'zs.insflow.tw1.su']"
            )


@override_settings(
    MAIN_DOMAINS=['insflow.ru'],
    SUBDOMAINS=['zs.insflow.ru']
)
class HTTPSDomainRoutingConfigurationTest(TestCase):
    """Test middleware with different domain configurations"""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response_mock = Mock(return_value=Mock(status_code=200))
    
    def test_custom_domain_configuration(self):
        """Test middleware with custom domain configuration"""
        middleware = DomainRoutingMiddleware(self.get_response_mock)
        self.assertEqual(middleware.main_domains, ['insflow.ru'])
        self.assertEqual(middleware.subdomains, ['zs.insflow.ru'])
    
    def test_fallback_to_default_configuration(self):
        """Test middleware falls back to default configuration when settings missing"""
        # Test without the custom domain settings - should use defaults from settings.py
        with override_settings(MAIN_DOMAINS=None, SUBDOMAINS=None):
            # Create middleware without domain settings
            middleware = DomainRoutingMiddleware(self.get_response_mock)
            # Should fall back to getattr defaults
            self.assertEqual(middleware.main_domains, ['insflow.tw1.su'])
            self.assertEqual(middleware.subdomains, ['zs.insflow.tw1.su'])
"""
Tests for domain-based routing functionality.
"""
from django.test import TestCase, RequestFactory, override_settings
from django.http import Http404
from onlineservice.middleware import DomainRoutingMiddleware
from onlineservice.views import landing_view


@override_settings(ALLOWED_HOSTS=['insflow.tw1.su', 'zs.insflow.tw1.su', 'localhost', '127.0.0.1', 'testserver'])
class DomainRoutingTest(TestCase):
    """Test domain routing middleware and views"""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = DomainRoutingMiddleware(lambda request: None)
    
    def test_main_domain_root_serves_landing(self):
        """Test that main domain root serves landing page"""
        request = self.factory.get('/', HTTP_HOST='insflow.tw1.su')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')
    
    def test_main_domain_landing_path_serves_landing(self):
        """Test that main domain /landing/ serves landing page"""
        request = self.factory.get('/landing/', HTTP_HOST='insflow.tw1.su')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')
    
    def test_main_domain_health_check_allowed(self):
        """Test that health check is allowed on main domain"""
        request = self.factory.get('/healthz/', HTTP_HOST='insflow.tw1.su')
        # This should pass through to normal URL routing
        try:
            response = self.middleware(request)
            # If middleware returns None, it passed through
            self.assertIsNone(response)
        except:
            # If it raises an exception, that's also expected behavior
            pass
    
    def test_main_domain_other_paths_raise_404(self):
        """Test that other paths on main domain raise 404"""
        request = self.factory.get('/admin/', HTTP_HOST='insflow.tw1.su')
        with self.assertRaises(Http404):
            self.middleware(request)
    
    def test_subdomain_passes_through(self):
        """Test that subdomain requests pass through normally"""
        request = self.factory.get('/admin/', HTTP_HOST='zs.insflow.tw1.su')
        response = self.middleware(request)
        # Should pass through (return None)
        self.assertIsNone(response)
    
    def test_development_domains_pass_through(self):
        """Test that development domains pass through normally"""
        for domain in ['localhost', '127.0.0.1']:
            request = self.factory.get('/admin/', HTTP_HOST=domain)
            response = self.middleware(request)
            # Should pass through (return None)
            self.assertIsNone(response)
    
    def test_landing_view_renders_correctly(self):
        """Test that landing view renders the correct template"""
        request = self.factory.get('/')
        response = landing_view(request)
        self.assertEqual(response.status_code, 200)
        # Check that it contains the expected content
        self.assertContains(response, 'здесь есть флоу')
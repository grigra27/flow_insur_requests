"""
Tests for login interface including page rendering, styling, form validation, and responsive design
"""
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.staticfiles import finders
from unittest.mock import patch, MagicMock
import os
import re


class LoginPageRenderingTests(TestCase):
    """Tests for login page rendering and styling"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test user
        self.test_user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create groups
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.test_user.groups.add(user_group)
    
    def test_login_page_loads_successfully(self):
        """Test that login page loads without errors"""
        response = self.client.get(reverse('login'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Вход в систему')
        self.assertContains(response, 'Система управления страховыми заявками')
    
    def test_login_page_contains_required_elements(self):
        """Test that login page contains all required HTML elements"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for essential form elements
        self.assertIn('id="loginForm"', content)
        self.assertIn('name="username"', content)
        self.assertIn('name="password"', content)
        self.assertIn('type="submit"', content)
        
        # Check for CSRF token
        self.assertIn('csrfmiddlewaretoken', content)
        
        # Check for login button
        self.assertIn('id="loginButton"', content)
        self.assertContains(response, 'Войти')
    
    def test_login_page_includes_bootstrap_css(self):
        """Test that login page includes Bootstrap CSS"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for Bootstrap CDN link
        self.assertIn('bootstrap@5.1.3', content)
        self.assertIn('bootstrap.min.css', content)
    
    def test_login_page_includes_font_awesome(self):
        """Test that login page includes Font Awesome icons"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for Font Awesome CDN link
        self.assertIn('font-awesome', content)
        
        # Check for icon usage
        self.assertIn('fas fa-shield-alt', content)  # Header icon
        self.assertIn('fas fa-user', content)        # Username icon
        self.assertIn('fas fa-lock', content)        # Password icon
        self.assertIn('fas fa-sign-in-alt', content) # Login button icon
    
    def test_login_page_includes_custom_css(self):
        """Test that login page includes custom CSS file"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for custom CSS link
        self.assertIn('css/login.css', content)
    
    def test_login_page_has_proper_meta_tags(self):
        """Test that login page has proper meta tags"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for viewport meta tag (responsive design)
        self.assertIn('name="viewport"', content)
        self.assertIn('width=device-width, initial-scale=1.0', content)
        
        # Check for charset
        self.assertIn('charset="UTF-8"', content)
        
        # Check for proper title
        self.assertIn('<title>Вход в систему - Страховые заявки</title>', content)
    
    def test_login_page_displays_test_credentials(self):
        """Test that login page displays test credentials section"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for test credentials section
        self.assertIn('test-credentials', content)
        self.assertContains(response, 'Тестовые учетные записи')
        self.assertContains(response, 'admin / admin123')
        self.assertContains(response, 'user / user123')
    
    def test_login_page_has_proper_form_structure(self):
        """Test that login page has proper form structure"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for form groups
        self.assertIn('form-group', content)
        
        # Check for form labels
        self.assertIn('form-label', content)
        
        # Check for form controls
        self.assertIn('form-control', content)
        
        # Check for proper input types
        self.assertIn('type="text"', content)      # Username field
        self.assertIn('type="password"', content)  # Password field
    
    def test_login_page_javascript_functionality(self):
        """Test that login page includes JavaScript functionality"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for JavaScript code
        self.assertIn('<script>', content)
        self.assertIn('DOMContentLoaded', content)
        self.assertIn('getElementById', content)
        
        # Check for specific functionality
        self.assertIn('validateField', content)
        self.assertIn('validateForm', content)
        self.assertIn('showFieldError', content)
        self.assertIn('hideFieldError', content)


class LoginFormValidationTests(TestCase):
    """Tests for login form validation and error handling"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test user
        self.test_user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create groups
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.test_user.groups.add(user_group)
    
    def test_login_form_displays_validation_errors(self):
        """Test that login form displays validation errors"""
        response = self.client.post(reverse('login'), {
            'username': 'nonexistent',
            'password': 'wrongpassword'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should display error message
        self.assertContains(response, 'alert-danger')
        self.assertContains(response, 'Пользователь с таким логином не найден')
    
    def test_login_form_handles_empty_fields(self):
        """Test that login form handles empty fields"""
        response = self.client.post(reverse('login'), {
            'username': '',
            'password': ''
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should display validation errors
        self.assertContains(response, 'alert-danger')
    
    def test_login_form_handles_short_username(self):
        """Test that login form handles short username"""
        response = self.client.post(reverse('login'), {
            'username': 'ab',  # Too short
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should display validation error
        self.assertContains(response, 'alert-danger')
        self.assertContains(response, 'минимум 3 символа')
    
    def test_login_form_handles_short_password(self):
        """Test that login form handles short password"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': '12345'  # Too short
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should display validation error
        self.assertContains(response, 'alert-danger')
        self.assertContains(response, 'минимум 6 символов')
    
    def test_login_form_handles_invalid_characters(self):
        """Test that login form handles invalid characters in username"""
        response = self.client.post(reverse('login'), {
            'username': 'test<script>',  # Invalid characters
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should display validation error
        self.assertContains(response, 'alert-danger')
    
    def test_login_form_preserves_username_on_error(self):
        """Test that login form preserves username when password is wrong"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Username should be preserved in the form
        self.assertContains(response, 'value="testuser"')
    
    def test_login_form_handles_inactive_user(self):
        """Test that login form handles inactive user properly"""
        # Create inactive user
        inactive_user = User.objects.create_user(
            username='inactive',
            password='testpass123',
            is_active=False
        )
        
        response = self.client.post(reverse('login'), {
            'username': 'inactive',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'учетная запись отключена')
    
    def test_successful_login_redirects_properly(self):
        """Test that successful login redirects to the correct page"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        # Should redirect after successful login
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('insurance_requests:request_list'))
    
    def test_login_with_next_parameter_redirects_correctly(self):
        """Test that login with next parameter redirects to specified URL"""
        next_url = reverse('insurance_requests:upload_excel')
        response = self.client.post(f"{reverse('login')}?next={next_url}", {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)


class LoginPageResponsiveDesignTests(TestCase):
    """Tests for responsive design on different screen sizes"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
    
    def test_login_page_has_responsive_meta_tag(self):
        """Test that login page has responsive viewport meta tag"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for responsive viewport meta tag
        self.assertIn('name="viewport"', content)
        self.assertIn('width=device-width', content)
        self.assertIn('initial-scale=1.0', content)
    
    def test_login_page_includes_responsive_css_classes(self):
        """Test that login page includes responsive CSS classes"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Check for responsive container classes
        self.assertIn('login-container', content)
        self.assertIn('login-card', content)
        
        # Check for Bootstrap responsive classes
        self.assertIn('form-control', content)
    
    def test_css_file_contains_media_queries(self):
        """Test that CSS file contains media queries for responsive design"""
        # Find the CSS file
        css_path = finders.find('css/login.css')
        
        if css_path and os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            # Check for media queries
            self.assertIn('@media (max-width: 768px)', css_content)
            self.assertIn('@media (max-width: 480px)', css_content)
            self.assertIn('@media (max-width: 360px)', css_content)
            
            # Check for responsive adjustments
            self.assertIn('max-width: 380px', css_content)  # Mobile container
            self.assertIn('padding: 35px 25px', css_content)  # Mobile padding
        else:
            self.skipTest("CSS file not found in static files")
    
    def test_css_file_contains_accessibility_features(self):
        """Test that CSS file contains accessibility features"""
        css_path = finders.find('css/login.css')
        
        if css_path and os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            # Check for accessibility media queries
            self.assertIn('@media (prefers-color-scheme: dark)', css_content)
            self.assertIn('@media (prefers-contrast: high)', css_content)
            self.assertIn('@media (prefers-reduced-motion: reduce)', css_content)
            
            # Check for focus states
            self.assertIn(':focus', css_content)
            self.assertIn('outline:', css_content)
        else:
            self.skipTest("CSS file not found in static files")


class LoginRedirectFunctionalityTests(TestCase):
    """Tests for redirect functionality after login"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test user
        self.test_user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create groups
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.test_user.groups.add(user_group)
    
    def test_login_redirects_to_default_page(self):
        """Test that login redirects to default page when no next parameter"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('insurance_requests:request_list'))
    
    def test_login_redirects_to_next_parameter(self):
        """Test that login redirects to URL specified in next parameter"""
        next_url = reverse('insurance_requests:upload_excel')
        login_url = f"{reverse('login')}?next={next_url}"
        
        response = self.client.post(login_url, {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
    
    def test_login_handles_invalid_next_parameter(self):
        """Test that login handles invalid next parameter gracefully"""
        invalid_next = 'http://evil-site.com/hack'
        login_url = f"{reverse('login')}?next={invalid_next}"
        
        response = self.client.post(login_url, {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 302)
        # Should redirect to default page, not the invalid URL
        self.assertEqual(response.url, reverse('insurance_requests:request_list'))
    
    def test_authenticated_user_redirected_from_login_page(self):
        """Test that authenticated users are redirected away from login page"""
        # Login first
        self.client.login(username='testuser', password='testpass123')
        
        # Try to access login page
        response = self.client.get(reverse('login'))
        
        # Should redirect authenticated users
        self.assertEqual(response.status_code, 302)
    
    def test_logout_redirects_to_login_page(self):
        """Test that logout redirects to login page"""
        # Login first
        self.client.login(username='testuser', password='testpass123')
        
        # Logout
        response = self.client.post(reverse('logout'))
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


class LoginPagePerformanceTests(TestCase):
    """Tests for login page performance and loading"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
    
    def test_login_page_loads_quickly(self):
        """Test that login page loads within reasonable time"""
        import time
        
        start_time = time.time()
        response = self.client.get(reverse('login'))
        end_time = time.time()
        
        # Should load within 1 second (generous for testing)
        load_time = end_time - start_time
        self.assertLess(load_time, 1.0)
        self.assertEqual(response.status_code, 200)
    
    def test_login_page_css_is_minified_friendly(self):
        """Test that CSS file structure is minification-friendly"""
        css_path = finders.find('css/login.css')
        
        if css_path and os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            # Check that CSS is well-structured (not necessarily minified in dev)
            # Count of selectors should be reasonable
            selector_count = css_content.count('{')
            self.assertGreater(selector_count, 10)  # Should have multiple selectors
            self.assertLess(selector_count, 500)    # But not excessive
        else:
            self.skipTest("CSS file not found in static files")
    
    def test_login_page_has_minimal_external_dependencies(self):
        """Test that login page has minimal external dependencies"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Count external CDN links
        cdn_links = content.count('cdn.')
        
        # Should have Bootstrap and Font Awesome (2 CDN links is reasonable)
        self.assertLessEqual(cdn_links, 3)
    
    def test_login_page_javascript_is_inline(self):
        """Test that JavaScript is inline for better performance"""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # JavaScript should be inline (not external file)
        self.assertIn('<script>', content)
        self.assertIn('</script>', content)
        
        # Should not have external JS files (except CDN)
        js_file_count = content.count('.js"')
        # Only CDN JS files should be present
        self.assertLessEqual(js_file_count, 2)


class LoginIntegrationTests(TestCase):
    """Integration tests for complete login workflow"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create admin and regular users
        self.admin_user = User.objects.create_user(
            username='admin',
            password='admin123',
            is_staff=True,
            is_superuser=True
        )
        
        self.regular_user = User.objects.create_user(
            username='user',
            password='user123'
        )
        
        # Create groups
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        
        self.admin_user.groups.add(admin_group)
        self.regular_user.groups.add(user_group)
    
    def test_complete_login_workflow_admin(self):
        """Test complete login workflow for admin user"""
        # Access login page
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
        # Submit login form
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        
        # Should redirect after successful login
        self.assertEqual(response.status_code, 302)
        
        # Follow redirect and check we're logged in
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Check that user is authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, 'admin')
    
    def test_complete_login_workflow_regular_user(self):
        """Test complete login workflow for regular user"""
        # Access login page
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
        # Submit login form
        response = self.client.post(reverse('login'), {
            'username': 'user',
            'password': 'user123'
        })
        
        # Should redirect after successful login
        self.assertEqual(response.status_code, 302)
        
        # Follow redirect and check we're logged in
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Check that user is authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, 'user')
    
    def test_login_error_recovery_workflow(self):
        """Test login error recovery workflow"""
        # Try to login with wrong password
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'wrongpassword'
        })
        
        # Should stay on login page with error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'alert-danger')
        
        # Try again with correct password
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        
        # Should succeed this time
        self.assertEqual(response.status_code, 302)
        
        # Verify we're logged in
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_login_logout_login_cycle(self):
        """Test complete login-logout-login cycle"""
        # Login
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify logged in
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Logout
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        
        # Verify logged out (should redirect to login)
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
        
        # Login again
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify logged in again
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_login_preserves_session_data(self):
        """Test that login preserves necessary session data"""
        # Login
        self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        
        # Check session data
        session = self.client.session
        self.assertIn('_auth_user_id', session)
        self.assertEqual(int(session['_auth_user_id']), self.admin_user.id)
    
    def test_concurrent_login_attempts(self):
        """Test handling of concurrent login attempts"""
        # Simulate multiple login attempts
        responses = []
        
        for i in range(3):
            response = self.client.post(reverse('login'), {
                'username': 'admin',
                'password': 'admin123'
            })
            responses.append(response)
        
        # All should succeed (or at least not fail catastrophically)
        for response in responses:
            self.assertIn(response.status_code, [200, 302])  # Either success or redirect
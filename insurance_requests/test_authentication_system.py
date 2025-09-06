"""
Tests for authentication system including user groups, permissions, middleware, and decorators
"""
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.http import HttpResponse
from django.core.management import call_command
from unittest.mock import patch, MagicMock
import io

from .models import InsuranceRequest, RequestAttachment, InsuranceResponse, ResponseAttachment
from .middleware import AuthenticationMiddleware
from .decorators import admin_required, user_required, get_user_role, has_admin_access, has_user_access
from .management.commands.setup_user_groups import Command


class UserGroupCreationTests(TestCase):
    """Tests for user group creation and permissions setup"""
    
    def setUp(self):
        """Set up test data"""
        # Clear existing groups to test creation
        Group.objects.filter(name__in=['Администраторы', 'Пользователи']).delete()
    
    def test_setup_user_groups_command_creates_groups(self):
        """Test that setup_user_groups command creates required groups"""
        # Capture command output
        out = io.StringIO()
        call_command('setup_user_groups', stdout=out)
        
        # Check that groups were created
        admin_group = Group.objects.get(name='Администраторы')
        user_group = Group.objects.get(name='Пользователи')
        
        self.assertIsNotNone(admin_group)
        self.assertIsNotNone(user_group)
        
        # Check command output
        output = out.getvalue()
        self.assertIn('Создана группа "Администраторы"', output)
        self.assertIn('Создана группа "Пользователи"', output)
    
    def test_setup_user_groups_command_assigns_admin_permissions(self):
        """Test that admin group gets all permissions"""
        call_command('setup_user_groups')
        
        admin_group = Group.objects.get(name='Администраторы')
        all_permissions = Permission.objects.all()
        admin_permissions = admin_group.permissions.all()
        
        # Admin should have all permissions
        self.assertEqual(admin_permissions.count(), all_permissions.count())
    
    def test_setup_user_groups_command_assigns_user_permissions(self):
        """Test that user group gets appropriate permissions"""
        call_command('setup_user_groups')
        
        user_group = Group.objects.get(name='Пользователи')
        user_permissions = user_group.permissions.all()
        
        # Check that user has specific permissions
        permission_codenames = [perm.codename for perm in user_permissions]
        
        expected_permissions = [
            'view_insurancerequest',
            'add_insurancerequest',
            'change_insurancerequest',
            'view_requestattachment',
            'add_requestattachment',
            'change_requestattachment',
            'view_insuranceresponse',
            'add_insuranceresponse',
            'view_responseattachment',
            'add_responseattachment',
        ]
        
        for expected_perm in expected_permissions:
            self.assertIn(expected_perm, permission_codenames)
        
        # User should NOT have delete permissions
        delete_permissions = [perm for perm in permission_codenames if 'delete' in perm]
        self.assertEqual(len(delete_permissions), 0)
    
    def test_setup_user_groups_command_creates_default_users(self):
        """Test that command creates default admin and test users"""
        call_command('setup_user_groups')
        
        # Check admin user
        admin_user = User.objects.get(username='admin')
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.groups.filter(name='Администраторы').exists())
        
        # Check test user
        test_user = User.objects.get(username='user')
        self.assertFalse(test_user.is_staff)
        self.assertFalse(test_user.is_superuser)
        self.assertTrue(test_user.groups.filter(name='Пользователи').exists())
    
    def test_setup_user_groups_command_idempotent(self):
        """Test that running command multiple times doesn't cause errors"""
        # Run command twice
        call_command('setup_user_groups')
        call_command('setup_user_groups')
        
        # Should still have exactly one of each group
        admin_groups = Group.objects.filter(name='Администраторы')
        user_groups = Group.objects.filter(name='Пользователи')
        
        self.assertEqual(admin_groups.count(), 1)
        self.assertEqual(user_groups.count(), 1)
        
        # Should still have exactly one of each default user
        admin_users = User.objects.filter(username='admin')
        test_users = User.objects.filter(username='user')
        
        self.assertEqual(admin_users.count(), 1)
        self.assertEqual(test_users.count(), 1)
    
    def test_command_class_directly(self):
        """Test Command class directly"""
        command = Command()
        
        # Capture output
        out = io.StringIO()
        command.stdout = out
        command.style = MagicMock()
        command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
        
        # Run command
        command.handle()
        
        # Check that groups exist
        self.assertTrue(Group.objects.filter(name='Администраторы').exists())
        self.assertTrue(Group.objects.filter(name='Пользователи').exists())


class AuthenticationMiddlewareTests(TestCase):
    """Tests for authentication middleware functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.middleware = AuthenticationMiddleware(lambda request: HttpResponse())
        
        # Create test users
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='testpass123'
        )
        self.regular_user = User.objects.create_user(
            username='user_test',
            password='testpass123'
        )
        
        # Create groups
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        
        self.admin_user.groups.add(admin_group)
        self.regular_user.groups.add(user_group)
    
    def test_middleware_allows_authenticated_user(self):
        """Test that middleware allows authenticated users"""
        request = self.factory.get('/some-protected-url/')
        request.user = self.regular_user
        
        response = self.middleware(request)
        
        # Should not redirect (returns normal response)
        self.assertEqual(response.status_code, 200)
    
    def test_middleware_redirects_unauthenticated_user(self):
        """Test that middleware redirects unauthenticated users"""
        request = self.factory.get('/some-protected-url/')
        request.user = MagicMock()
        request.user.is_authenticated = False
        
        response = self.middleware(request)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_middleware_allows_public_urls(self):
        """Test that middleware allows access to public URLs"""
        public_urls = [
            '/admin/login/',
            '/admin/logout/',
            '/login/',
            '/logout/',
            '/static/css/style.css',
            '/media/uploads/file.jpg',
        ]
        
        for url in public_urls:
            with self.subTest(url=url):
                request = self.factory.get(url)
                request.user = MagicMock()
                request.user.is_authenticated = False
                
                response = self.middleware(request)
                
                # Should not redirect for public URLs
                self.assertEqual(response.status_code, 200)
    
    def test_middleware_preserves_next_parameter(self):
        """Test that middleware preserves next parameter for redirect after login"""
        request = self.factory.get('/protected-page/')
        request.user = MagicMock()
        request.user.is_authenticated = False
        
        response = self.middleware(request)
        
        # Should redirect with next parameter
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=/protected-page/', response.url)
    
    def test_is_public_url_method(self):
        """Test _is_public_url method"""
        test_cases = [
            ('/admin/login/', True),
            ('/login/', True),
            ('/static/css/style.css', True),
            ('/media/file.jpg', True),
            ('/protected-page/', False),
            ('/insurance-requests/', False),
            ('/', False),
        ]
        
        for url, expected in test_cases:
            with self.subTest(url=url):
                result = self.middleware._is_public_url(url)
                self.assertEqual(result, expected)


class RoleBasedAccessDecoratorsTests(TestCase):
    """Tests for role-based access control decorators"""
    
    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        
        # Create users
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='testpass123'
        )
        self.regular_user = User.objects.create_user(
            username='user_test',
            password='testpass123'
        )
        self.no_group_user = User.objects.create_user(
            username='no_group_test',
            password='testpass123'
        )
        
        # Create groups
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        
        self.admin_user.groups.add(admin_group)
        self.regular_user.groups.add(user_group)
        # no_group_user is not in any group
        
        # Create test view functions
        @admin_required
        def admin_view(request):
            return HttpResponse('Admin content')
        
        @user_required
        def user_view(request):
            return HttpResponse('User content')
        
        self.admin_view = admin_view
        self.user_view = user_view
    
    def test_admin_required_allows_admin_user(self):
        """Test that admin_required allows admin users"""
        request = self.factory.get('/admin-only/')
        request.user = self.admin_user
        
        response = self.admin_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'Admin content')
    
    def test_admin_required_denies_regular_user(self):
        """Test that admin_required denies regular users"""
        request = self.factory.get('/admin-only/')
        request.user = self.regular_user
        
        response = self.admin_view(request)
        
        self.assertEqual(response.status_code, 403)
        self.assertIn('access_denied.html', response.template_name)
    
    def test_admin_required_denies_no_group_user(self):
        """Test that admin_required denies users with no group"""
        request = self.factory.get('/admin-only/')
        request.user = self.no_group_user
        
        response = self.admin_view(request)
        
        self.assertEqual(response.status_code, 403)
    
    def test_user_required_allows_admin_user(self):
        """Test that user_required allows admin users"""
        request = self.factory.get('/user-area/')
        request.user = self.admin_user
        
        response = self.user_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'User content')
    
    def test_user_required_allows_regular_user(self):
        """Test that user_required allows regular users"""
        request = self.factory.get('/user-area/')
        request.user = self.regular_user
        
        response = self.user_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'User content')
    
    def test_user_required_denies_no_group_user(self):
        """Test that user_required denies users with no group"""
        request = self.factory.get('/user-area/')
        request.user = self.no_group_user
        
        response = self.user_view(request)
        
        self.assertEqual(response.status_code, 403)
    
    def test_get_user_role_function(self):
        """Test get_user_role helper function"""
        self.assertEqual(get_user_role(self.admin_user), 'Администратор')
        self.assertEqual(get_user_role(self.regular_user), 'Пользователь')
        self.assertEqual(get_user_role(self.no_group_user), 'Неопределенная роль')
    
    def test_has_admin_access_function(self):
        """Test has_admin_access helper function"""
        self.assertTrue(has_admin_access(self.admin_user))
        self.assertFalse(has_admin_access(self.regular_user))
        self.assertFalse(has_admin_access(self.no_group_user))
        
        # Test with unauthenticated user
        unauthenticated_user = MagicMock()
        unauthenticated_user.is_authenticated = False
        self.assertFalse(has_admin_access(unauthenticated_user))
    
    def test_has_user_access_function(self):
        """Test has_user_access helper function"""
        self.assertTrue(has_user_access(self.admin_user))
        self.assertTrue(has_user_access(self.regular_user))
        self.assertFalse(has_user_access(self.no_group_user))
        
        # Test with unauthenticated user
        unauthenticated_user = MagicMock()
        unauthenticated_user.is_authenticated = False
        self.assertFalse(has_user_access(unauthenticated_user))


class LoginLogoutFunctionalityTests(TestCase):
    """Tests for login/logout functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test users
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='testpass123'
        )
        self.regular_user = User.objects.create_user(
            username='user_test',
            password='testpass123'
        )
        
        # Create groups
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        
        self.admin_user.groups.add(admin_group)
        self.regular_user.groups.add(user_group)
    
    def test_login_page_accessible(self):
        """Test that login page is accessible without authentication"""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Вход в систему')
    
    def test_successful_login_redirects_to_home(self):
        """Test that successful login redirects to home page"""
        response = self.client.post(reverse('login'), {
            'username': 'admin_test',
            'password': 'testpass123'
        })
        
        # Should redirect after successful login
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('insurance_requests:request_list'))
    
    def test_successful_login_with_next_parameter(self):
        """Test that successful login redirects to next parameter"""
        next_url = reverse('insurance_requests:request_list')
        response = self.client.post(f"{reverse('login')}?next={next_url}", {
            'username': 'admin_test',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
    
    def test_failed_login_shows_error(self):
        """Test that failed login shows error message"""
        response = self.client.post(reverse('login'), {
            'username': 'admin_test',
            'password': 'wrongpassword'
        })
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Неверный пароль')
    
    def test_login_with_nonexistent_user(self):
        """Test login with nonexistent username"""
        response = self.client.post(reverse('login'), {
            'username': 'nonexistent',
            'password': 'somepassword'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Пользователь с таким логином не найден')
    
    def test_login_with_inactive_user(self):
        """Test login with inactive user"""
        inactive_user = User.objects.create_user(
            username='inactive_test',
            password='testpass123',
            is_active=False
        )
        
        response = self.client.post(reverse('login'), {
            'username': 'inactive_test',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'учетная запись отключена')
    
    def test_logout_functionality(self):
        """Test logout functionality"""
        # First login
        self.client.login(username='admin_test', password='testpass123')
        
        # Verify user is logged in
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Logout
        response = self.client.post(reverse('logout'))
        
        # Should redirect after logout
        self.assertEqual(response.status_code, 302)
        
        # Verify user is logged out (should redirect to login)
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_authenticated_user_cannot_access_login_page(self):
        """Test that authenticated users are redirected from login page"""
        self.client.login(username='admin_test', password='testpass123')
        
        response = self.client.get(reverse('login'))
        
        # Should redirect authenticated users away from login page
        self.assertEqual(response.status_code, 302)


class IntegrationAuthenticationTests(TestCase):
    """Integration tests for complete authentication workflow"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Set up groups and users using the management command
        call_command('setup_user_groups')
        
        # Get the created users
        self.admin_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='user')
    
    def test_complete_admin_workflow(self):
        """Test complete workflow for admin user"""
        # Login as admin
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Access main page
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Create insurance request
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.admin_user
        )
        
        # Access request detail
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Edit request
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Logout
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        
        # Verify logout worked
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 302)  # Should redirect to login
    
    def test_complete_regular_user_workflow(self):
        """Test complete workflow for regular user"""
        # Login as regular user
        response = self.client.post(reverse('login'), {
            'username': 'user',
            'password': 'user123'
        })
        self.assertEqual(response.status_code, 302)
        
        # Access main page
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        
        # Create insurance request
        request = InsuranceRequest.objects.create(
            client_name='User Test Client',
            inn='0987654321',
            insurance_type='другое',
            created_by=self.regular_user
        )
        
        # Access request detail
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Edit request (should work for regular users)
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test that unauthenticated users are redirected to login"""
        protected_urls = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
        ]
        
        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login/', response.url)
    
    def test_user_without_group_access_denied(self):
        """Test that users without proper groups get access denied"""
        # Create user without any groups
        no_group_user = User.objects.create_user(
            username='no_group',
            password='testpass123'
        )
        
        # Login
        self.client.login(username='no_group', password='testpass123')
        
        # Try to access protected page
        response = self.client.get(reverse('insurance_requests:request_list'))
        
        # Should get access denied
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Доступ запрещен')
    
    def test_session_persistence_across_requests(self):
        """Test that user session persists across multiple requests"""
        # Login
        self.client.login(username='admin', password='admin123')
        
        # Make multiple requests
        urls = [
            reverse('insurance_requests:request_list'),
            reverse('insurance_requests:upload_excel'),
        ]
        
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                # User should remain authenticated
    
    def test_permission_enforcement_in_views(self):
        """Test that permissions are properly enforced in views"""
        # Create test request
        request = InsuranceRequest.objects.create(
            client_name='Permission Test',
            inn='1111111111',
            insurance_type='КАСКО',
            created_by=self.admin_user
        )
        
        # Test with regular user
        self.client.login(username='user', password='user123')
        
        # Regular user should be able to view and edit
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Test with admin user
        self.client.login(username='admin', password='admin123')
        
        # Admin should have full access
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        self.assertEqual(response.status_code, 200)
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from io import StringIO


class InitialDataFixturesTest(TestCase):
    """Тесты для фикстур и команд управления начальными данными"""

    def setUp(self):
        """Очищаем данные перед каждым тестом"""
        User.objects.all().delete()
        Group.objects.all().delete()

    def test_setup_user_groups_command(self):
        """Тест команды setup_user_groups"""
        out = StringIO()
        call_command('setup_user_groups', stdout=out)
        
        # Проверяем, что группы созданы
        self.assertTrue(Group.objects.filter(name='Администраторы').exists())
        self.assertTrue(Group.objects.filter(name='Пользователи').exists())
        
        # Проверяем разрешения
        admin_group = Group.objects.get(name='Администраторы')
        user_group = Group.objects.get(name='Пользователи')
        
        self.assertGreater(admin_group.permissions.count(), 0)
        self.assertGreater(user_group.permissions.count(), 0)
        
        # Проверяем, что создались пользователи по умолчанию
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertTrue(User.objects.filter(username='user').exists())

    def test_create_default_users_command(self):
        """Тест команды create_default_users"""
        # Сначала создаем группы
        call_command('setup_user_groups', verbosity=0)
        
        # Удаляем пользователей, созданных setup_user_groups
        User.objects.all().delete()
        
        out = StringIO()
        call_command('create_default_users', 
                    '--create-test-user',
                    '--admin-username', 'testadmin',
                    '--admin-password', 'testpass123',
                    '--test-username', 'testuser',
                    '--test-password', 'testpass456',
                    stdout=out)
        
        # Проверяем, что пользователи созданы
        admin_user = User.objects.get(username='testadmin')
        test_user = User.objects.get(username='testuser')
        
        # Проверяем свойства администратора
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.groups.filter(name='Администраторы').exists())
        
        # Проверяем свойства обычного пользователя
        self.assertFalse(test_user.is_staff)
        self.assertFalse(test_user.is_superuser)
        self.assertTrue(test_user.groups.filter(name='Пользователи').exists())

    def test_load_initial_fixtures_command(self):
        """Тест команды load_initial_fixtures"""
        out = StringIO()
        call_command('load_initial_fixtures',
                    '--admin-password', 'custompass123',
                    '--user-password', 'userpass456',
                    stdout=out)
        
        # Проверяем, что группы созданы
        self.assertTrue(Group.objects.filter(name='Администраторы').exists())
        self.assertTrue(Group.objects.filter(name='Пользователи').exists())
        
        # Проверяем, что пользователи созданы
        admin_user = User.objects.get(username='admin')
        test_user = User.objects.get(username='user')
        
        # Проверяем принадлежность к группам
        self.assertTrue(admin_user.groups.filter(name='Администраторы').exists())
        self.assertTrue(test_user.groups.filter(name='Пользователи').exists())

    def test_setup_initial_data_command_standard(self):
        """Тест команды setup_initial_data в стандартном режиме"""
        out = StringIO()
        call_command('setup_initial_data',
                    '--admin-username', 'customadmin',
                    '--admin-password', 'custompass123',
                    stdout=out)
        
        # Проверяем, что система настроена
        self.assertTrue(Group.objects.filter(name='Администраторы').exists())
        self.assertTrue(Group.objects.filter(name='Пользователи').exists())
        
        # Проверяем пользователей
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertTrue(User.objects.filter(username='user').exists())
        self.assertTrue(User.objects.filter(username='customadmin').exists())

    def test_setup_initial_data_command_with_fixtures(self):
        """Тест команды setup_initial_data с использованием фикстур"""
        out = StringIO()
        call_command('setup_initial_data',
                    '--use-fixtures',
                    '--admin-password', 'fixturepass123',
                    stdout=out)
        
        # Проверяем, что система настроена через фикстуры
        self.assertTrue(Group.objects.filter(name='Администраторы').exists())
        self.assertTrue(Group.objects.filter(name='Пользователи').exists())
        
        # Проверяем пользователей
        admin_user = User.objects.get(username='admin')
        test_user = User.objects.get(username='user')
        
        self.assertTrue(admin_user.groups.filter(name='Администраторы').exists())
        self.assertTrue(test_user.groups.filter(name='Пользователи').exists())

    def test_user_permissions(self):
        """Тест разрешений пользователей"""
        call_command('setup_user_groups', verbosity=0)
        
        admin_group = Group.objects.get(name='Администраторы')
        user_group = Group.objects.get(name='Пользователи')
        
        # Проверяем, что у администраторов больше разрешений
        self.assertGreater(admin_group.permissions.count(), user_group.permissions.count())
        
        # Проверяем, что у пользователей есть базовые разрешения для работы с заявками
        user_permissions = user_group.permissions.all()
        permission_codenames = [p.codename for p in user_permissions]
        
        self.assertIn('view_insurancerequest', permission_codenames)
        self.assertIn('add_insurancerequest', permission_codenames)
        self.assertIn('change_insurancerequest', permission_codenames)

    def test_groups_exist_after_setup(self):
        """Тест существования групп после настройки"""
        call_command('setup_user_groups', verbosity=0)
        
        # Проверяем, что группы существуют
        admin_group = Group.objects.get(name='Администраторы')
        user_group = Group.objects.get(name='Пользователи')
        
        self.assertIsNotNone(admin_group)
        self.assertIsNotNone(user_group)
        
        # Проверяем, что у групп есть разрешения
        self.assertGreater(admin_group.permissions.count(), 0)
        self.assertGreater(user_group.permissions.count(), 0)
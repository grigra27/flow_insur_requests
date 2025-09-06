from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.db import transaction


class Command(BaseCommand):
    help = 'Загружает начальные фикстуры для системы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно пересоздать данные (удалит существующих пользователей)'
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            default='admin123',
            help='Пароль для администратора по умолчанию'
        )
        parser.add_argument(
            '--user-password', 
            type=str,
            default='user123',
            help='Пароль для тестового пользователя'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Загрузка начальных фикстур ==='))
        
        force = options['force']
        admin_password = options['admin_password']
        user_password = options['user_password']
        
        try:
            with transaction.atomic():
                # Если force=True, удаляем существующих пользователей
                if force:
                    self.stdout.write('Удаление существующих пользователей...')
                    User.objects.filter(username__in=['admin', 'user']).delete()
                    self.stdout.write(self.style.WARNING('Существующие пользователи удалены'))
                
                # Создаем группы пользователей
                self.stdout.write('Создание групп пользователей...')
                call_command('setup_user_groups', verbosity=0)
                
                # Создаем администратора
                self._create_admin_user(admin_password, force)
                
                # Создаем тестового пользователя
                self._create_test_user(user_password, force)
                
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('=== Фикстуры успешно загружены ==='))
                self._display_user_info(admin_password, user_password)
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при загрузке фикстур: {str(e)}')
            )
            raise

    def _create_admin_user(self, password, force):
        """Создает администратора по умолчанию"""
        if User.objects.filter(username='admin').exists() and not force:
            self.stdout.write('Администратор уже существует')
            return
        
        admin_group = Group.objects.get(name='Администраторы')
        
        admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password=password,
            first_name='Администратор',
            last_name='Системы',
            is_staff=True,
            is_superuser=True
        )
        admin_user.groups.add(admin_group)
        
        self.stdout.write(self.style.SUCCESS('Создан администратор: admin'))

    def _create_test_user(self, password, force):
        """Создает тестового пользователя"""
        if User.objects.filter(username='user').exists() and not force:
            self.stdout.write('Тестовый пользователь уже существует')
            return
        
        user_group = Group.objects.get(name='Пользователи')
        
        test_user = User.objects.create_user(
            username='user',
            email='user@example.com', 
            password=password,
            first_name='Тестовый',
            last_name='Пользователь'
        )
        test_user.groups.add(user_group)
        
        self.stdout.write(self.style.SUCCESS('Создан тестовый пользователь: user'))

    def _display_user_info(self, admin_password, user_password):
        """Отображает информацию о созданных пользователях"""
        self.stdout.write('')
        self.stdout.write('Доступные учетные записи:')
        self.stdout.write(f'  Администратор: admin / {admin_password}')
        self.stdout.write(f'  Пользователь: user / {user_password}')
        self.stdout.write('')
        self.stdout.write('Группы пользователей:')
        
        admin_group = Group.objects.get(name='Администраторы')
        user_group = Group.objects.get(name='Пользователи')
        
        self.stdout.write(f'  Администраторы: {admin_group.permissions.count()} разрешений')
        self.stdout.write(f'  Пользователи: {user_group.permissions.count()} разрешений')
        self.stdout.write('')
        self.stdout.write('Для входа в систему: http://localhost:8000/login/')
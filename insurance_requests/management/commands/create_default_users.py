from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.db import transaction


class Command(BaseCommand):
    help = 'Создает пользователей по умолчанию для системы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-username',
            type=str,
            default='admin',
            help='Имя пользователя администратора'
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            default='admin123',
            help='Пароль администратора'
        )
        parser.add_argument(
            '--admin-email',
            type=str,
            default='admin@example.com',
            help='Email администратора'
        )
        parser.add_argument(
            '--create-test-user',
            action='store_true',
            help='Создать тестового пользователя'
        )
        parser.add_argument(
            '--test-username',
            type=str,
            default='user',
            help='Имя тестового пользователя'
        )
        parser.add_argument(
            '--test-password',
            type=str,
            default='user123',
            help='Пароль тестового пользователя'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Создание пользователей по умолчанию ==='))
        
        try:
            with transaction.atomic():
                # Убеждаемся, что группы существуют
                self._ensure_groups_exist()
                
                # Создаем администратора
                admin_created = self._create_admin(
                    options['admin_username'],
                    options['admin_password'], 
                    options['admin_email']
                )
                
                # Создаем тестового пользователя если нужно
                test_created = False
                if options['create_test_user']:
                    test_created = self._create_test_user(
                        options['test_username'],
                        options['test_password']
                    )
                
                # Выводим результат
                self._display_results(
                    admin_created, test_created,
                    options['admin_username'], options['admin_password'],
                    options['test_username'], options['test_password']
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при создании пользователей: {str(e)}')
            )
            raise

    def _ensure_groups_exist(self):
        """Убеждается, что группы пользователей существуют"""
        if not Group.objects.filter(name='Администраторы').exists():
            self.stdout.write('Создание групп пользователей...')
            call_command('setup_user_groups', verbosity=0)

    def _create_admin(self, username, password, email):
        """Создает администратора"""
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Администратор {username} уже существует')
            return False
        
        admin_group = Group.objects.get(name='Администраторы')
        
        admin_user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name='Администратор',
            last_name='Системы',
            is_staff=True,
            is_superuser=True
        )
        admin_user.groups.add(admin_group)
        
        self.stdout.write(self.style.SUCCESS(f'Создан администратор: {username}'))
        return True

    def _create_test_user(self, username, password):
        """Создает тестового пользователя"""
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Пользователь {username} уже существует')
            return False
        
        user_group = Group.objects.get(name='Пользователи')
        
        test_user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password=password,
            first_name='Тестовый',
            last_name='Пользователь'
        )
        test_user.groups.add(user_group)
        
        self.stdout.write(self.style.SUCCESS(f'Создан пользователь: {username}'))
        return True

    def _display_results(self, admin_created, test_created, 
                        admin_username, admin_password,
                        test_username, test_password):
        """Отображает результаты создания пользователей"""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Создание завершено ==='))
        self.stdout.write('')
        
        if admin_created or test_created:
            self.stdout.write('Созданные учетные записи:')
            if admin_created:
                self.stdout.write(f'  Администратор: {admin_username} / {admin_password}')
            if test_created:
                self.stdout.write(f'  Пользователь: {test_username} / {test_password}')
        else:
            self.stdout.write('Новые пользователи не были созданы')
        
        self.stdout.write('')
        self.stdout.write('Для входа в систему: http://localhost:8000/login/')
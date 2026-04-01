from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Настраивает начальные данные для системы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-username',
            type=str,
            default='admin',
            help='Имя пользователя для администратора (по умолчанию: admin)'
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            default='admin123',
            help='Пароль для администратора (по умолчанию: admin123)'
        )
        parser.add_argument(
            '--admin-email',
            type=str,
            default='admin@example.com',
            help='Email для администратора (по умолчанию: admin@example.com)'
        )
        parser.add_argument(
            '--skip-test-user',
            action='store_true',
            help='Пропустить создание тестового пользователя'
        )
        parser.add_argument(
            '--create-default-users',
            action='store_true',
            help='Явно создать пользователей (admin/user или кастомные из параметров)'
        )
        parser.add_argument(
            '--use-fixtures',
            action='store_true',
            help='Использовать фикстуры для создания пользователей'
        )
        parser.add_argument(
            '--force-fixtures',
            action='store_true',
            help='Принудительно пересоздать пользователей из фикстур'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Настройка начальных данных ==='))
        
        # Выполняем миграции
        self.stdout.write('Применение миграций...')
        call_command('migrate', verbosity=0)
        self.stdout.write(self.style.SUCCESS('Миграции применены'))
        
        # Получаем параметры пользователя
        admin_username = options['admin_username']
        admin_password = options['admin_password']
        admin_email = options['admin_email']
        
        # Выбираем способ создания пользователей
        if options['use_fixtures']:
            self.stdout.write('Загрузка пользователей из фикстур...')
            call_command('load_initial_fixtures', 
                        force=options['force_fixtures'],
                        admin_password=admin_password,
                        verbosity=1)
        else:
            # Настраиваем группы пользователей стандартным способом
            self.stdout.write('Настройка групп пользователей...')
            call_command('setup_user_groups', verbosity=1)

            custom_admin_requested = (
                admin_username != 'admin'
                or admin_password != 'admin123'
                or admin_email != 'admin@example.com'
            )

            if options['create_default_users'] or custom_admin_requested:
                self.stdout.write('Создание пользователей через create_default_users...')
                create_users_kwargs = {
                    'admin_username': admin_username,
                    'admin_password': admin_password,
                    'admin_email': admin_email,
                    'create_test_user': not options['skip_test_user'],
                }
                call_command('create_default_users', **create_users_kwargs)
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'Пользователи не создавались автоматически. '
                        'Используйте --create-default-users или команду create_default_users.'
                    )
                )
        
        # Собираем статические файлы
        self.stdout.write('Сбор статических файлов...')
        call_command('collectstatic', '--noinput', verbosity=0)
        self.stdout.write(self.style.SUCCESS('Статические файлы собраны'))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Настройка завершена ==='))
        self.stdout.write('')
        self.stdout.write('Система готова к использованию!')
        self.stdout.write('')
        self.stdout.write('Администраторы в системе:')

        from django.contrib.auth.models import Group
        admin_group = Group.objects.get(name='Администраторы')
        admin_users = User.objects.filter(groups=admin_group).order_by('username')

        if admin_users.exists():
            for user in admin_users:
                self.stdout.write(f'  - {user.username}')
        else:
            self.stdout.write('  - не найдены')
        
        self.stdout.write('')
        self.stdout.write('Для входа в систему перейдите по адресу: http://localhost:8000/login/')

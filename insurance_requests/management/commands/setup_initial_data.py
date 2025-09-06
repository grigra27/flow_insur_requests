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
        
        # Создаем кастомного администратора если не используем фикстуры
        if not options['use_fixtures']:
            if admin_username != 'admin' or admin_password != 'admin123':
                self.stdout.write(f'Создание кастомного администратора: {admin_username}')
                
                if User.objects.filter(username=admin_username).exists():
                    self.stdout.write(f'Пользователь {admin_username} уже существует')
                else:
                    from django.contrib.auth.models import Group
                    
                    admin_user = User.objects.create_user(
                        username=admin_username,
                        email=admin_email,
                        password=admin_password,
                        is_staff=True,
                        is_superuser=True
                    )
                    
                    # Добавляем в группу администраторов
                    admin_group = Group.objects.get(name='Администраторы')
                    admin_user.groups.add(admin_group)
                    
                    self.stdout.write(self.style.SUCCESS(f'Создан администратор: {admin_username}'))
        
        # Собираем статические файлы
        self.stdout.write('Сбор статических файлов...')
        call_command('collectstatic', '--noinput', verbosity=0)
        self.stdout.write(self.style.SUCCESS('Статические файлы собраны'))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Настройка завершена ==='))
        self.stdout.write('')
        self.stdout.write('Система готова к использованию!')
        self.stdout.write('')
        self.stdout.write('Доступные учетные записи:')
        
        # Показываем всех администраторов
        from django.contrib.auth.models import Group
        admin_group = Group.objects.get(name='Администраторы')
        admin_users = User.objects.filter(groups=admin_group)
        
        for user in admin_users:
            if user.username == 'admin':
                self.stdout.write(f'  Администратор: {user.username} / admin123')
            else:
                self.stdout.write(f'  Администратор: {user.username} / [установленный пароль]')
        
        if not options['skip_test_user']:
            self.stdout.write('  Тестовый пользователь: user / user123')
        
        self.stdout.write('')
        self.stdout.write('Для входа в систему перейдите по адресу: http://localhost:8000/login/')
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from insurance_requests.models import InsuranceRequest, RequestAttachment


class Command(BaseCommand):
    help = 'Создает группы пользователей и настраивает разрешения'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-default-users',
            action='store_true',
            help='Создать дефолтных пользователей admin/user'
        )

    def handle(self, *args, **options):
        self.stdout.write('Создание групп пользователей...')
        
        # Создание групп
        admin_group, admin_created = Group.objects.get_or_create(name='Администраторы')
        user_group, user_created = Group.objects.get_or_create(name='Пользователи')
        
        if admin_created:
            self.stdout.write(self.style.SUCCESS('Создана группа "Администраторы"'))
        else:
            self.stdout.write('Группа "Администраторы" уже существует')
            
        if user_created:
            self.stdout.write(self.style.SUCCESS('Создана группа "Пользователи"'))
        else:
            self.stdout.write('Группа "Пользователи" уже существует')
        
        # Настройка разрешений для администраторов (все разрешения)
        self.stdout.write('Настройка разрешений для администраторов...')
        admin_permissions = Permission.objects.all()
        admin_group.permissions.set(admin_permissions)
        self.stdout.write(self.style.SUCCESS(f'Администраторам назначено {admin_permissions.count()} разрешений'))
        
        # Настройка разрешений для обычных пользователей
        self.stdout.write('Настройка разрешений для пользователей...')
        
        # Получаем content types для наших моделей
        insurance_request_ct = ContentType.objects.get_for_model(InsuranceRequest)
        request_attachment_ct = ContentType.objects.get_for_model(RequestAttachment)
        
        # Разрешения для обычных пользователей
        user_permissions = Permission.objects.filter(
            content_type__in=[
                insurance_request_ct,
                request_attachment_ct,
            ],
            codename__in=[
                # InsuranceRequest permissions
                'view_insurancerequest',
                'add_insurancerequest',
                'change_insurancerequest',
                
                # RequestAttachment permissions
                'view_requestattachment',
                'add_requestattachment',
                'change_requestattachment',
            ]
        )
        
        user_group.permissions.set(user_permissions)
        self.stdout.write(self.style.SUCCESS(f'Пользователям назначено {user_permissions.count()} разрешений'))
        
        create_default_users = options.get('create_default_users', False)
        if create_default_users:
            self.stdout.write('Создание дефолтных пользователей по явному флагу...')
            self._create_default_users(admin_group, user_group)
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Создание дефолтных пользователей пропущено. '
                    'Используйте --create-default-users или отдельную команду create_default_users.'
                )
            )

        self.stdout.write(self.style.SUCCESS('Настройка групп и разрешений завершена!'))

    def _create_default_users(self, admin_group, user_group):
        """Создает/актуализирует дефолтных пользователей admin/user."""
        self.stdout.write('Проверка администратора по умолчанию...')

        if not User.objects.filter(username='admin').exists():
            admin_user = User.objects.create_user(
                username='admin',
                email='admin@example.com',
                password='admin123',
                is_staff=True,
                is_superuser=True
            )
            admin_user.groups.add(admin_group)
            self.stdout.write(self.style.SUCCESS('Создан администратор по умолчанию (admin/admin123)'))
        else:
            admin_user = User.objects.get(username='admin')
            admin_user.groups.add(admin_group)
            self.stdout.write('Администратор по умолчанию уже существует')

        if not User.objects.filter(username='user').exists():
            test_user = User.objects.create_user(
                username='user',
                email='user@example.com',
                password='user123'
            )
            test_user.groups.add(user_group)
            self.stdout.write(self.style.SUCCESS('Создан тестовый пользователь (user/user123)'))
        else:
            test_user = User.objects.get(username='user')
            test_user.groups.add(user_group)
            self.stdout.write('Тестовый пользователь уже существует')

#!/usr/bin/env python
"""
Enhanced database migration script for insurance system enhancements
Handles comprehensive migration with detailed logging and error recovery
"""

import os
import sys
import django
from datetime import datetime, date
import re
import json
import traceback
from pathlib import Path

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onlineservice.settings')
django.setup()

from django.db import transaction, connection
from django.contrib.auth.models import User, Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from insurance_requests.models import InsuranceRequest


class EnhancedDatabaseMigrator:
    """Enhanced database migrator with comprehensive error handling and validation"""
    
    def __init__(self):
        self.migration_log = []
        self.errors = []
        self.warnings = []
        self.stats = {
            'migrations_applied': 0,
            'groups_created': 0,
            'users_created': 0,
            'periods_migrated': 0,
            'types_updated': 0,
            'validation_errors': 0
        }
        self.backup_file = None
        self.start_time = datetime.now()
    
    def log(self, message, level='INFO'):
        """Log migration message with level"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {level}: {message}"
        print(log_message)
        self.migration_log.append(log_message)
    
    def error(self, message, exception=None):
        """Log error message with optional exception details"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        error_message = f"[{timestamp}] ERROR: {message}"
        
        if exception:
            error_message += f"\nException: {str(exception)}"
            error_message += f"\nTraceback: {traceback.format_exc()}"
        
        print(error_message)
        self.errors.append(error_message)
    
    def warning(self, message):
        """Log warning message"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        warning_message = f"[{timestamp}] WARNING: {message}"
        print(warning_message)
        self.warnings.append(warning_message)
    
    def check_prerequisites(self):
        """Check system prerequisites before migration"""
        self.log("Проверка предварительных требований...")
        
        try:
            # Check Django version
            import django
            self.log(f"Django версия: {django.get_version()}")
            
            # Check database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                self.log("Подключение к базе данных: OK")
            
            # Check if insurance_requests app is installed
            from django.apps import apps
            if not apps.is_installed('insurance_requests'):
                raise Exception("Приложение insurance_requests не установлено")
            
            # Check available disk space
            import shutil
            total, used, free = shutil.disk_usage('.')
            free_gb = free // (1024**3)
            if free_gb < 1:
                self.warning(f"Мало свободного места на диске: {free_gb} GB")
            else:
                self.log(f"Свободное место на диске: {free_gb} GB")
            
            self.log("Предварительные требования выполнены")
            return True
            
        except Exception as e:
            self.error("Ошибка при проверке предварительных требований", e)
            return False
    
    def create_backup(self):
        """Create comprehensive backup before migration"""
        self.log("Создание резервной копии...")
        
        try:
            # Create backup directory
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.backup_file = backup_dir / f"migration_backup_{timestamp}.json"
            
            # Create database dump
            with open(self.backup_file, 'w', encoding='utf-8') as backup_file:
                call_command('dumpdata', 'insurance_requests', 'auth', stdout=backup_file)
            
            # Create metadata file
            metadata_file = backup_dir / f"migration_metadata_{timestamp}.json"
            metadata = {
                'timestamp': timestamp,
                'django_version': django.get_version(),
                'python_version': sys.version,
                'backup_file': str(self.backup_file),
                'pre_migration_stats': self._get_current_stats()
            }
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str)
            
            self.log(f"Резервная копия создана: {self.backup_file}")
            self.log(f"Метаданные сохранены: {metadata_file}")
            return True
            
        except Exception as e:
            self.error("Ошибка при создании резервной копии", e)
            return False
    
    def _get_current_stats(self):
        """Get current database statistics"""
        try:
            stats = {
                'total_requests': InsuranceRequest.objects.count(),
                'requests_with_period': InsuranceRequest.objects.exclude(
                    insurance_period__isnull=True
                ).exclude(insurance_period='').count(),
                'requests_with_dates': InsuranceRequest.objects.filter(
                    insurance_start_date__isnull=False,
                    insurance_end_date__isnull=False
                ).count(),
                'total_users': User.objects.count(),
                'total_groups': Group.objects.count(),
                'insurance_types': list(
                    InsuranceRequest.objects.values_list('insurance_type', flat=True)
                    .distinct()
                )
            }
            return stats
        except Exception as e:
            self.warning(f"Не удалось получить статистику: {str(e)}")
            return {}
    
    def run_django_migrations(self):
        """Run Django database migrations with error handling"""
        self.log("Запуск миграций Django...")
        
        try:
            # Check for pending migrations
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            
            if plan:
                self.log(f"Найдено {len(plan)} миграций для применения")
                
                # Make migrations first
                try:
                    call_command('makemigrations', 'insurance_requests', verbosity=1)
                    self.log("Миграции созданы успешно")
                except CommandError as e:
                    if "No changes detected" in str(e):
                        self.log("Новые миграции не требуются")
                    else:
                        raise e
                
                # Apply migrations
                call_command('migrate', verbosity=1)
                self.stats['migrations_applied'] = len(plan)
                self.log(f"Применено {len(plan)} миграций")
            else:
                self.log("Все миграции уже применены")
            
            return True
            
        except Exception as e:
            self.error("Ошибка при применении миграций Django", e)
            return False
    
    def setup_user_groups(self):
        """Setup user groups and permissions with detailed logging"""
        self.log("Настройка групп пользователей...")
        
        try:
            with transaction.atomic():
                # Create admin group
                admin_group, created = Group.objects.get_or_create(name='Администраторы')
                if created:
                    self.log("Создана группа 'Администраторы'")
                    self.stats['groups_created'] += 1
                else:
                    self.log("Группа 'Администраторы' уже существует")
                
                # Create user group
                user_group, created = Group.objects.get_or_create(name='Пользователи')
                if created:
                    self.log("Создана группа 'Пользователи'")
                    self.stats['groups_created'] += 1
                else:
                    self.log("Группа 'Пользователи' уже существует")
                
                # Setup permissions for admin group (all permissions)
                admin_permissions = Permission.objects.all()
                admin_group.permissions.set(admin_permissions)
                self.log(f"Назначено {admin_permissions.count()} разрешений группе 'Администраторы'")
                
                # Setup permissions for user group (limited permissions)
                user_permissions = Permission.objects.filter(
                    content_type__app_label='insurance_requests',
                    codename__in=[
                        'view_insurancerequest',
                        'add_insurancerequest',
                        'change_insurancerequest'
                    ]
                )
                user_group.permissions.set(user_permissions)
                self.log(f"Назначено {user_permissions.count()} разрешений группе 'Пользователи'")
                
                # Create default admin user
                admin_user, created = User.objects.get_or_create(
                    username='admin',
                    defaults={
                        'email': 'admin@example.com',
                        'is_staff': True,
                        'is_superuser': True
                    }
                )
                
                if created:
                    admin_user.set_password('admin123')
                    admin_user.save()
                    self.log("Создан пользователь 'admin'")
                    self.stats['users_created'] += 1
                else:
                    self.log("Пользователь 'admin' уже существует")
                
                admin_user.groups.add(admin_group)
                
                # Create default regular user
                regular_user, created = User.objects.get_or_create(
                    username='user',
                    defaults={
                        'email': 'user@example.com',
                        'is_staff': False,
                        'is_superuser': False
                    }
                )
                
                if created:
                    regular_user.set_password('user123')
                    regular_user.save()
                    self.log("Создан пользователь 'user'")
                    self.stats['users_created'] += 1
                else:
                    self.log("Пользователь 'user' уже существует")
                
                regular_user.groups.add(user_group)
                
            self.log("Настройка групп пользователей завершена успешно")
            return True
            
        except Exception as e:
            self.error("Ошибка при настройке групп пользователей", e)
            return False
    
    def migrate_insurance_periods(self):
        """Migrate existing insurance_period data to separate date fields"""
        self.log("Миграция данных периодов страхования...")
        
        migrated_count = 0
        error_count = 0
        skipped_count = 0
        
        # Get all requests with insurance_period but without separate dates
        requests_to_migrate = InsuranceRequest.objects.filter(
            insurance_period__isnull=False,
            insurance_start_date__isnull=True,
            insurance_end_date__isnull=True
        ).exclude(insurance_period='')
        
        total_requests = requests_to_migrate.count()
        self.log(f"Найдено {total_requests} заявок для миграции дат")
        
        if total_requests == 0:
            self.log("Нет заявок для миграции дат")
            return True
        
        # Process requests in batches
        batch_size = 100
        for i in range(0, total_requests, batch_size):
            batch = requests_to_migrate[i:i + batch_size]
            self.log(f"Обработка пакета {i//batch_size + 1}: заявки {i+1}-{min(i+batch_size, total_requests)}")
            
            for request in batch:
                try:
                    with transaction.atomic():
                        start_date, end_date = self._parse_insurance_period(request.insurance_period)
                        
                        if start_date or end_date:
                            request.insurance_start_date = start_date
                            request.insurance_end_date = end_date
                            request.save()
                            migrated_count += 1
                            
                            if migrated_count % 50 == 0:
                                self.log(f"Мигрировано {migrated_count} заявок...")
                        else:
                            skipped_count += 1
                            self.warning(f"Не удалось распарсить период для заявки ID {request.id}: '{request.insurance_period}'")
                            
                except Exception as e:
                    error_count += 1
                    self.error(f"Ошибка при миграции заявки ID {request.id}: {str(e)}")
        
        self.stats['periods_migrated'] = migrated_count
        self.log(f"Миграция дат завершена: {migrated_count} успешно, {skipped_count} пропущено, {error_count} ошибок")
        
        # Return True if no critical errors (some parsing failures are acceptable)
        return error_count < total_requests * 0.1  # Allow up to 10% failures
    
    def _parse_insurance_period(self, period_text):
        """Enhanced parsing of insurance period text"""
        if not period_text or not isinstance(period_text, str):
            return None, None
        
        # Clean the text
        period_text = period_text.strip()
        
        # Common patterns for date parsing (ordered by specificity)
        patterns = [
            # "с 01.06.2024 по 01.06.2025"
            r'с\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+по\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "01.06.2024 - 01.06.2025"
            r'(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–—]\s*(\d{1,2}\.\d{1,2}\.\d{4})',
            # "01.06.2024 по 01.06.2025"
            r'(\d{1,2}\.\d{1,2}\.\d{4})\s+по\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "от 01.06.2024 до 01.06.2025"
            r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+до\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "с 01.06.2024"
            r'с\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "до 01.06.2025"
            r'до\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "от 01.06.2024"
            r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # Just a date "01.06.2024"
            r'^(\d{1,2}\.\d{1,2}\.\d{4})$',
            # Two dates separated by space
            r'(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}\.\d{1,2}\.\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, period_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) == 2:
                    # Two dates found
                    start_date = self._parse_date(groups[0])
                    end_date = self._parse_date(groups[1])
                    
                    # Validate date order
                    if start_date and end_date and start_date > end_date:
                        # Swap dates if they're in wrong order
                        start_date, end_date = end_date, start_date
                    
                    return start_date, end_date
                    
                elif len(groups) == 1:
                    # One date found
                    parsed_date = self._parse_date(groups[0])
                    
                    if 'с' in period_text.lower() or 'от' in period_text.lower():
                        # Start date
                        return parsed_date, None
                    elif 'до' in period_text.lower():
                        # End date
                        return None, parsed_date
                    else:
                        # Assume it's start date for single date
                        return parsed_date, None
        
        return None, None
    
    def _parse_date(self, date_str):
        """Enhanced date parsing with multiple format support"""
        if not date_str:
            return None
        
        # Remove extra whitespace
        date_str = date_str.strip()
        
        # Try different date formats
        formats = [
            '%d.%m.%Y',
            '%d.%m.%y',
            '%d/%m/%Y',
            '%d/%m/%y',
            '%Y-%m-%d',
            '%d-%m-%Y'
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                
                # Handle 2-digit years
                if parsed_date.year < 1950:
                    parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                
                # Validate reasonable date range
                current_year = datetime.now().year
                if parsed_date.year < 2000 or parsed_date.year > current_year + 10:
                    continue
                
                return parsed_date
                
            except ValueError:
                continue
        
        return None
    
    def update_insurance_types(self):
        """Update insurance types to include new property insurance type"""
        self.log("Обновление типов страхования...")
        
        # Map old types to new types
        type_mapping = {
            'имущество': 'страхование имущества',
            'property': 'страхование имущества',
            'недвижимость': 'страхование имущества',
            'имущественное': 'страхование имущества',
            'имущественное страхование': 'страхование имущества',
        }
        
        updated_count = 0
        
        try:
            with transaction.atomic():
                for old_type, new_type in type_mapping.items():
                    requests = InsuranceRequest.objects.filter(
                        insurance_type__icontains=old_type
                    ).exclude(insurance_type=new_type)
                    
                    count = requests.count()
                    if count > 0:
                        requests.update(insurance_type=new_type)
                        updated_count += count
                        self.log(f"Обновлено {count} заявок с типа содержащего '{old_type}' на '{new_type}'")
                
                # Also check for exact matches with variations
                exact_mappings = {
                    'имущество': 'страхование имущества',
                    'Имущество': 'страхование имущества',
                    'ИМУЩЕСТВО': 'страхование имущества',
                }
                
                for old_type, new_type in exact_mappings.items():
                    count = InsuranceRequest.objects.filter(
                        insurance_type=old_type
                    ).update(insurance_type=new_type)
                    
                    if count > 0:
                        updated_count += count
                        self.log(f"Обновлено {count} заявок с точного типа '{old_type}' на '{new_type}'")
            
            self.stats['types_updated'] = updated_count
            self.log(f"Обновление типов страхования завершено: {updated_count} заявок обновлено")
            return True
            
        except Exception as e:
            self.error("Ошибка при обновлении типов страхования", e)
            return False
    
    def validate_migration(self):
        """Comprehensive validation of migration results"""
        self.log("Валидация результатов миграции...")
        
        validation_errors = []
        validation_warnings = []
        
        try:
            # Check user groups
            try:
                admin_group = Group.objects.get(name='Администраторы')
                user_group = Group.objects.get(name='Пользователи')
                self.log("✓ Группы пользователей созданы корректно")
                
                # Check permissions
                admin_perms = admin_group.permissions.count()
                user_perms = user_group.permissions.count()
                self.log(f"✓ Разрешения: Администраторы ({admin_perms}), Пользователи ({user_perms})")
                
            except Group.DoesNotExist as e:
                validation_errors.append(f"Группа пользователей не найдена: {str(e)}")
            
            # Check default users
            try:
                admin_user = User.objects.get(username='admin')
                regular_user = User.objects.get(username='user')
                
                # Check group membership
                if not admin_user.groups.filter(name='Администраторы').exists():
                    validation_errors.append("Пользователь admin не в группе Администраторы")
                
                if not regular_user.groups.filter(name='Пользователи').exists():
                    validation_errors.append("Пользователь user не в группе Пользователи")
                
                self.log("✓ Пользователи по умолчанию созданы корректно")
                
            except User.DoesNotExist as e:
                validation_errors.append(f"Пользователь по умолчанию не найден: {str(e)}")
            
            # Check insurance requests data
            total_requests = InsuranceRequest.objects.count()
            requests_with_dates = InsuranceRequest.objects.filter(
                insurance_start_date__isnull=False,
                insurance_end_date__isnull=False
            ).count()
            
            requests_with_start_only = InsuranceRequest.objects.filter(
                insurance_start_date__isnull=False,
                insurance_end_date__isnull=True
            ).count()
            
            requests_with_end_only = InsuranceRequest.objects.filter(
                insurance_start_date__isnull=True,
                insurance_end_date__isnull=False
            ).count()
            
            self.log(f"✓ Заявок всего: {total_requests}")
            self.log(f"✓ С обеими датами: {requests_with_dates}")
            self.log(f"✓ Только с датой начала: {requests_with_start_only}")
            self.log(f"✓ Только с датой окончания: {requests_with_end_only}")
            
            # Check insurance types
            property_requests = InsuranceRequest.objects.filter(
                insurance_type='страхование имущества'
            ).count()
            
            all_types = InsuranceRequest.objects.values_list(
                'insurance_type', flat=True
            ).distinct()
            
            self.log(f"✓ Заявок с типом 'страхование имущества': {property_requests}")
            self.log(f"✓ Всего уникальных типов страхования: {len(all_types)}")
            
            # Check for invalid dates
            from django.db import models
            invalid_dates = InsuranceRequest.objects.filter(
                insurance_start_date__isnull=False,
                insurance_end_date__isnull=False,
                insurance_start_date__gt=models.F('insurance_end_date')
            ).count()
            
            if invalid_dates > 0:
                validation_warnings.append(f"Найдено {invalid_dates} заявок с некорректным порядком дат")
            
            # Database integrity check
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA integrity_check" if 'sqlite' in connection.vendor else "SELECT 1")
                self.log("✓ Проверка целостности базы данных пройдена")
            
        except Exception as e:
            validation_errors.append(f"Ошибка при валидации: {str(e)}")
        
        # Record validation results
        self.stats['validation_errors'] = len(validation_errors)
        
        # Log results
        if validation_errors:
            for error in validation_errors:
                self.error(error)
        
        if validation_warnings:
            for warning in validation_warnings:
                self.warning(warning)
        
        if not validation_errors:
            self.log("✓ Валидация прошла успешно")
            return True
        else:
            self.log(f"✗ Валидация завершена с {len(validation_errors)} ошибками")
            return False
    
    def cleanup_old_data(self):
        """Clean up old or redundant data after migration"""
        self.log("Очистка устаревших данных...")
        
        try:
            # Clean up empty insurance periods after successful migration
            empty_periods = InsuranceRequest.objects.filter(
                insurance_period__in=['', None],
                insurance_start_date__isnull=False,
                insurance_end_date__isnull=False
            ).count()
            
            if empty_periods > 0:
                self.log(f"Найдено {empty_periods} заявок с пустыми периодами после миграции")
            
            # Clean up old sessions
            call_command('clearsessions')
            self.log("Очищены старые сессии")
            
            return True
            
        except Exception as e:
            self.warning(f"Ошибка при очистке данных: {str(e)}")
            return False
    
    def generate_migration_report(self):
        """Generate comprehensive migration report"""
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        report = {
            'migration_info': {
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration.total_seconds(),
                'backup_file': str(self.backup_file) if self.backup_file else None
            },
            'statistics': self.stats,
            'summary': {
                'total_log_entries': len(self.migration_log),
                'total_errors': len(self.errors),
                'total_warnings': len(self.warnings),
                'success': len(self.errors) == 0
            },
            'post_migration_stats': self._get_current_stats()
        }
        
        # Save report to file
        report_file = Path("backups") / f"migration_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.log(f"Отчет о миграции сохранен: {report_file}")
        return report
    
    def run_full_migration(self):
        """Run complete migration process with comprehensive error handling"""
        self.log("=== НАЧАЛО РАСШИРЕННОЙ МИГРАЦИИ БАЗЫ ДАННЫХ ===")
        
        success = True
        
        try:
            # Step 1: Check prerequisites
            if not self.check_prerequisites():
                return False
            
            # Step 2: Create backup
            if not self.create_backup():
                return False
            
            # Step 3: Run Django migrations
            if not self.run_django_migrations():
                success = False
            
            # Step 4: Setup user groups
            if not self.setup_user_groups():
                success = False
            
            # Step 5: Migrate insurance periods
            if not self.migrate_insurance_periods():
                self.warning("Некоторые периоды страхования не удалось мигрировать")
                # Don't fail completely for this step
            
            # Step 6: Update insurance types
            if not self.update_insurance_types():
                success = False
            
            # Step 7: Validate migration
            if not self.validate_migration():
                success = False
            
            # Step 8: Cleanup (optional, don't fail on errors)
            self.cleanup_old_data()
            
            if success:
                self.log("=== МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО ===")
            else:
                self.log("=== МИГРАЦИЯ ЗАВЕРШЕНА С ОШИБКАМИ ===")
            
            return success
            
        except Exception as e:
            self.error(f"Критическая ошибка во время миграции: {str(e)}", e)
            self.log(f"Для восстановления используйте: python manage.py loaddata {self.backup_file}")
            return False
        
        finally:
            # Always generate report
            self.generate_migration_report()
    
    def print_summary(self):
        """Print comprehensive migration summary"""
        duration = datetime.now() - self.start_time
        
        print("\n" + "="*80)
        print("СВОДКА РАСШИРЕННОЙ МИГРАЦИИ")
        print("="*80)
        
        print(f"Время выполнения: {duration}")
        print(f"Всего сообщений: {len(self.migration_log)}")
        print(f"Ошибок: {len(self.errors)}")
        print(f"Предупреждений: {len(self.warnings)}")
        
        print("\nСТАТИСТИКА:")
        for key, value in self.stats.items():
            print(f"  {key}: {value}")
        
        if self.errors:
            print("\nОШИБКИ:")
            for error in self.errors[-5:]:  # Show last 5 errors
                print(f"  {error}")
            if len(self.errors) > 5:
                print(f"  ... и еще {len(self.errors) - 5} ошибок")
        
        if self.warnings:
            print("\nПРЕДУПРЕЖДЕНИЯ:")
            for warning in self.warnings[-5:]:  # Show last 5 warnings
                print(f"  {warning}")
            if len(self.warnings) > 5:
                print(f"  ... и еще {len(self.warnings) - 5} предупреждений")
        
        print("\nРЕКОМЕНДАЦИИ:")
        if len(self.errors) == 0:
            print("  ✅ Миграция прошла успешно")
            print("  ✅ Можно продолжать с развертыванием")
        else:
            print("  ❌ Обнаружены критические ошибки")
            print("  ❌ Рекомендуется исправить ошибки перед продолжением")
            print(f"  ❌ Для отката используйте: python manage.py loaddata {self.backup_file}")
        
        if len(self.warnings) > 0:
            print("  ⚠️  Обратите внимание на предупреждения")
        
        print("="*80)


def main():
    """Main migration function with enhanced error handling"""
    migrator = EnhancedDatabaseMigrator()
    
    print("Расширенная система миграции базы данных для улучшений страховой системы")
    print("="*80)
    print("Эта миграция включает:")
    print("  • Применение Django миграций")
    print("  • Создание групп пользователей и разрешений")
    print("  • Миграцию данных периодов страхования")
    print("  • Обновление типов страхования")
    print("  • Комплексную валидацию результатов")
    print("  • Создание детального отчета")
    print("="*80)
    
    # Ask for confirmation
    response = input("Продолжить расширенную миграцию? (y/N): ")
    if response.lower() not in ['y', 'yes', 'да']:
        print("Миграция отменена пользователем")
        return
    
    # Run migration
    success = migrator.run_full_migration()
    
    # Print summary
    migrator.print_summary()
    
    if success:
        print("\n✅ Расширенная миграция завершена успешно!")
        print("\nСледующие шаги:")
        print("1. Запустите тесты: python manage.py test insurance_requests")
        print("2. Соберите статические файлы: python manage.py collectstatic")
        print("3. Перезапустите веб-сервер")
        print("4. Проверьте работу новых функций")
    else:
        print("\n❌ Миграция завершена с ошибками!")
        print("Проверьте логи выше и исправьте проблемы перед продолжением")
        print(f"Для отката используйте: python manage.py loaddata {migrator.backup_file}")
        sys.exit(1)


if __name__ == '__main__':
    main()
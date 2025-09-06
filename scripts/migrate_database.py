#!/usr/bin/env python
"""
Database migration script for insurance system enhancements
Handles migration of existing data to new schema with enhanced features
"""

import os
import sys
import django
from datetime import datetime, date
import re

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onlineservice.settings')
django.setup()

from django.db import transaction
from django.contrib.auth.models import User, Group, Permission
from django.core.management import call_command
from insurance_requests.models import InsuranceRequest


class DatabaseMigrator:
    """Handles database migration for insurance system enhancements"""
    
    def __init__(self):
        self.migration_log = []
        self.errors = []
    
    def log(self, message):
        """Log migration message"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        self.migration_log.append(log_message)
    
    def error(self, message):
        """Log error message"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        error_message = f"[{timestamp}] ERROR: {message}"
        print(error_message)
        self.errors.append(error_message)
    
    def run_django_migrations(self):
        """Run Django database migrations"""
        self.log("Запуск миграций Django...")
        
        try:
            # Make migrations
            call_command('makemigrations', 'insurance_requests', verbosity=1)
            self.log("Миграции созданы успешно")
            
            # Apply migrations
            call_command('migrate', verbosity=1)
            self.log("Миграции применены успешно")
            
            return True
        except Exception as e:
            self.error(f"Ошибка при применении миграций: {str(e)}")
            return False
    
    def setup_user_groups(self):
        """Setup user groups and permissions"""
        self.log("Настройка групп пользователей...")
        
        try:
            call_command('setup_user_groups')
            self.log("Группы пользователей настроены успешно")
            return True
        except Exception as e:
            self.error(f"Ошибка при настройке групп: {str(e)}")
            return False
    
    def migrate_insurance_periods(self):
        """Migrate existing insurance_period data to separate date fields"""
        self.log("Миграция данных периодов страхования...")
        
        migrated_count = 0
        error_count = 0
        
        # Get all requests with insurance_period but without separate dates
        requests_to_migrate = InsuranceRequest.objects.filter(
            insurance_period__isnull=False,
            insurance_start_date__isnull=True,
            insurance_end_date__isnull=True
        ).exclude(insurance_period='')
        
        self.log(f"Найдено {requests_to_migrate.count()} заявок для миграции дат")
        
        for request in requests_to_migrate:
            try:
                with transaction.atomic():
                    start_date, end_date = self._parse_insurance_period(request.insurance_period)
                    
                    if start_date or end_date:
                        request.insurance_start_date = start_date
                        request.insurance_end_date = end_date
                        request.save()
                        migrated_count += 1
                        
                        self.log(f"Мигрирована заявка ID {request.id}: {start_date} - {end_date}")
                    else:
                        self.log(f"Не удалось распарсить период для заявки ID {request.id}: '{request.insurance_period}'")
                        
            except Exception as e:
                error_count += 1
                self.error(f"Ошибка при миграции заявки ID {request.id}: {str(e)}")
        
        self.log(f"Миграция дат завершена: {migrated_count} успешно, {error_count} ошибок")
        return error_count == 0
    
    def _parse_insurance_period(self, period_text):
        """Parse insurance period text to extract start and end dates"""
        if not period_text:
            return None, None
        
        # Common patterns for date parsing
        patterns = [
            # "с 01.06.2024 по 01.06.2025"
            r'с\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+по\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "01.06.2024 - 01.06.2025"
            r'(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})',
            # "01.06.2024 по 01.06.2025"
            r'(\d{1,2}\.\d{1,2}\.\d{4})\s+по\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "с 01.06.2024"
            r'с\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # "до 01.06.2025"
            r'до\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            # Just a date "01.06.2024"
            r'^(\d{1,2}\.\d{1,2}\.\d{4})$',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, period_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) == 2:
                    # Two dates found
                    start_date = self._parse_date(groups[0])
                    end_date = self._parse_date(groups[1])
                    return start_date, end_date
                elif len(groups) == 1:
                    # One date found
                    parsed_date = self._parse_date(groups[0])
                    if 'с' in period_text.lower() or period_text.strip() == groups[0]:
                        # Start date
                        return parsed_date, None
                    elif 'до' in period_text.lower():
                        # End date
                        return None, parsed_date
                    else:
                        # Assume it's start date
                        return parsed_date, None
        
        return None, None
    
    def _parse_date(self, date_str):
        """Parse date string in DD.MM.YYYY format"""
        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except ValueError:
            try:
                return datetime.strptime(date_str, '%d.%m.%y').date()
            except ValueError:
                return None
    
    def update_insurance_types(self):
        """Update insurance types to include new property insurance type"""
        self.log("Обновление типов страхования...")
        
        # Map old types to new types if needed
        type_mapping = {
            'имущество': 'страхование имущества',
            'property': 'страхование имущества',
            'недвижимость': 'страхование имущества',
        }
        
        updated_count = 0
        
        for old_type, new_type in type_mapping.items():
            requests = InsuranceRequest.objects.filter(
                insurance_type__icontains=old_type
            ).exclude(insurance_type=new_type)
            
            count = requests.count()
            if count > 0:
                requests.update(insurance_type=new_type)
                updated_count += count
                self.log(f"Обновлено {count} заявок с типа '{old_type}' на '{new_type}'")
        
        self.log(f"Обновление типов страхования завершено: {updated_count} заявок обновлено")
        return True
    
    def validate_migration(self):
        """Validate migration results"""
        self.log("Валидация результатов миграции...")
        
        validation_errors = []
        
        # Check user groups
        try:
            admin_group = Group.objects.get(name='Администраторы')
            user_group = Group.objects.get(name='Пользователи')
            self.log("Группы пользователей созданы корректно")
        except Group.DoesNotExist as e:
            validation_errors.append(f"Группа пользователей не найдена: {str(e)}")
        
        # Check default users
        try:
            admin_user = User.objects.get(username='admin')
            regular_user = User.objects.get(username='user')
            self.log("Пользователи по умолчанию созданы корректно")
        except User.DoesNotExist as e:
            validation_errors.append(f"Пользователь по умолчанию не найден: {str(e)}")
        
        # Check insurance requests with dates
        requests_with_dates = InsuranceRequest.objects.filter(
            insurance_start_date__isnull=False,
            insurance_end_date__isnull=False
        ).count()
        
        total_requests = InsuranceRequest.objects.count()
        self.log(f"Заявок с датами: {requests_with_dates} из {total_requests}")
        
        # Check insurance types
        property_requests = InsuranceRequest.objects.filter(
            insurance_type='страхование имущества'
        ).count()
        self.log(f"Заявок с типом 'страхование имущества': {property_requests}")
        
        if validation_errors:
            for error in validation_errors:
                self.error(error)
            return False
        
        self.log("Валидация прошла успешно")
        return True
    
    def create_backup(self):
        """Create database backup before migration"""
        self.log("Создание резервной копии базы данных...")
        
        try:
            backup_filename = f"backup_before_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            with open(backup_filename, 'w', encoding='utf-8') as backup_file:
                call_command('dumpdata', 'insurance_requests', stdout=backup_file)
            
            self.log(f"Резервная копия создана: {backup_filename}")
            return backup_filename
        except Exception as e:
            self.error(f"Ошибка при создании резервной копии: {str(e)}")
            return None
    
    def run_full_migration(self):
        """Run complete migration process"""
        self.log("=== НАЧАЛО МИГРАЦИИ БАЗЫ ДАННЫХ ===")
        
        # Create backup
        backup_file = self.create_backup()
        if not backup_file:
            self.error("Не удалось создать резервную копию. Миграция прервана.")
            return False
        
        try:
            # Step 1: Run Django migrations
            if not self.run_django_migrations():
                return False
            
            # Step 2: Setup user groups
            if not self.setup_user_groups():
                return False
            
            # Step 3: Migrate insurance periods
            if not self.migrate_insurance_periods():
                self.log("Предупреждение: Некоторые периоды страхования не удалось мигрировать")
            
            # Step 4: Update insurance types
            if not self.update_insurance_types():
                return False
            
            # Step 5: Validate migration
            if not self.validate_migration():
                return False
            
            self.log("=== МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО ===")
            return True
            
        except Exception as e:
            self.error(f"Критическая ошибка во время миграции: {str(e)}")
            self.log(f"Для восстановления используйте: python manage.py loaddata {backup_file}")
            return False
    
    def print_summary(self):
        """Print migration summary"""
        print("\n" + "="*60)
        print("СВОДКА МИГРАЦИИ")
        print("="*60)
        
        print(f"Всего сообщений: {len(self.migration_log)}")
        print(f"Ошибок: {len(self.errors)}")
        
        if self.errors:
            print("\nОШИБКИ:")
            for error in self.errors:
                print(f"  {error}")
        
        print("\nПОЛНЫЙ ЛОГ:")
        for log_entry in self.migration_log:
            print(f"  {log_entry}")
        
        print("="*60)


def main():
    """Main migration function"""
    migrator = DatabaseMigrator()
    
    print("Система миграции базы данных для улучшений страховой системы")
    print("="*60)
    
    # Ask for confirmation
    response = input("Продолжить миграцию? (y/N): ")
    if response.lower() not in ['y', 'yes', 'да']:
        print("Миграция отменена пользователем")
        return
    
    # Run migration
    success = migrator.run_full_migration()
    
    # Print summary
    migrator.print_summary()
    
    if success:
        print("\n✅ Миграция завершена успешно!")
        print("\nСледующие шаги:")
        print("1. Запустите тесты: python manage.py test insurance_requests")
        print("2. Соберите статические файлы: python manage.py collectstatic")
        print("3. Перезапустите веб-сервер")
    else:
        print("\n❌ Миграция завершена с ошибками!")
        print("Проверьте логи выше и исправьте проблемы перед продолжением")
        sys.exit(1)


if __name__ == '__main__':
    main()
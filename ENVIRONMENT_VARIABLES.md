# Переменные окружения

Подробное описание всех переменных окружения, используемых в системе управления страховыми заявками.

## Содержание

1. [Обзор](#обзор)
2. [Основные настройки Django](#основные-настройки-django)
3. [Настройки базы данных](#настройки-базы-данных)
4. [Настройки безопасности](#настройки-безопасности)
5. [Настройки email](#настройки-email)
6. [Настройки Celery](#настройки-celery)
7. [Настройки логирования](#настройки-логирования)
8. [Примеры конфигураций](#примеры-конфигураций)
9. [Валидация настроек](#валидация-настроек)

## Обзор

Система использует файл `.env` для хранения переменных окружения. Создайте файл на основе `.env.example`:

```bash
cp .env.example .env
```

### Приоритет настроек

1. Переменные окружения системы
2. Файл `.env`
3. Значения по умолчанию в `settings.py`

### Безопасность

⚠️ **Важно**: Никогда не коммитьте файл `.env` в систему контроля версий. Он должен быть добавлен в `.gitignore`.

## Основные настройки Django

### SECRET_KEY

**Описание**: Секретный ключ Django для криптографических операций.

**Тип**: Строка  
**Обязательный**: Да  
**По умолчанию**: Нет  

```env
SECRET_KEY=your-very-secure-secret-key-here-change-this-in-production
```

**Генерация нового ключа**:
```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

**Требования**:
- Минимум 50 символов
- Должен быть уникальным для каждой установки
- Содержать специальные символы

### DEBUG

**Описание**: Режим отладки Django.

**Тип**: Булево  
**Обязательный**: Да  
**По умолчанию**: False  

```env
DEBUG=True   # Для разработки
DEBUG=False  # Для продакшена
```

**Влияние**:
- `True`: Подробные сообщения об ошибках, отладочная панель
- `False`: Краткие сообщения об ошибках, оптимизация производительности

### ALLOWED_HOSTS

**Описание**: Список разрешенных хостов для Django.

**Тип**: Строка (разделенная запятыми)  
**Обязательный**: Да (если DEBUG=False)  
**По умолчанию**: [] (пустой список)  

```env
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com,www.your-domain.com
```

**Примеры**:
- Разработка: `localhost,127.0.0.1`
- Продакшен: `your-domain.com,www.your-domain.com`
- Все хосты (не рекомендуется): `*`

### LANGUAGE_CODE

**Описание**: Код языка по умолчанию.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: ru-ru  

```env
LANGUAGE_CODE=ru-ru
```

### TIME_ZONE

**Описание**: Временная зона.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: Europe/Moscow  

```env
TIME_ZONE=Europe/Moscow
```

## Настройки базы данных

### DB_ENGINE

**Описание**: Движок базы данных Django.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: django.db.backends.sqlite3  

```env
# SQLite (для разработки)
DB_ENGINE=django.db.backends.sqlite3

# PostgreSQL (для продакшена)
DB_ENGINE=django.db.backends.postgresql

# MySQL
DB_ENGINE=django.db.backends.mysql
```

### DB_NAME

**Описание**: Имя базы данных.

**Тип**: Строка  
**Обязательный**: Да  
**По умолчанию**: db.sqlite3  

```env
# SQLite
DB_NAME=db.sqlite3

# PostgreSQL/MySQL
DB_NAME=insurance_db
```

### DB_USER

**Описание**: Пользователь базы данных.

**Тип**: Строка  
**Обязательный**: Для PostgreSQL/MySQL  
**По умолчанию**: Нет  

```env
DB_USER=insurance_user
```

### DB_PASSWORD

**Описание**: Пароль пользователя базы данных.

**Тип**: Строка  
**Обязательный**: Для PostgreSQL/MySQL  
**По умолчанию**: Нет  

```env
DB_PASSWORD=secure_password_here
```

### DB_HOST

**Описание**: Хост базы данных.

**Тип**: Строка  
**Обязательный**: Для удаленной БД  
**По умолчанию**: localhost  

```env
DB_HOST=localhost
# или
DB_HOST=db.example.com
```

### DB_PORT

**Описание**: Порт базы данных.

**Тип**: Число  
**Обязательный**: Нет  
**По умолчанию**: Стандартный порт для движка  

```env
# PostgreSQL
DB_PORT=5432

# MySQL
DB_PORT=3306
```

### DATABASE_URL

**Описание**: URL подключения к базе данных (альтернатива отдельным параметрам).

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: Нет  

```env
# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# SQLite
DATABASE_URL=sqlite:///db.sqlite3

# MySQL
DATABASE_URL=mysql://user:password@localhost:3306/dbname
```

## Настройки безопасности

### SESSION_COOKIE_SECURE

**Описание**: Передача session cookie только по HTTPS.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
SESSION_COOKIE_SECURE=True   # Для продакшена с HTTPS
SESSION_COOKIE_SECURE=False  # Для разработки
```

### CSRF_COOKIE_SECURE

**Описание**: Передача CSRF cookie только по HTTPS.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
CSRF_COOKIE_SECURE=True   # Для продакшена с HTTPS
CSRF_COOKIE_SECURE=False  # Для разработки
```

### SECURE_HSTS_SECONDS

**Описание**: Время действия HSTS заголовка в секундах.

**Тип**: Число  
**Обязательный**: Нет  
**По умолчанию**: 0  

```env
SECURE_HSTS_SECONDS=31536000  # 1 год для продакшена
SECURE_HSTS_SECONDS=0         # Отключено для разработки
```

### SECURE_HSTS_INCLUDE_SUBDOMAINS

**Описание**: Применение HSTS к поддоменам.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
SECURE_HSTS_INCLUDE_SUBDOMAINS=True   # Для продакшена
SECURE_HSTS_INCLUDE_SUBDOMAINS=False  # Для разработки
```

### SECURE_HSTS_PRELOAD

**Описание**: Включение в HSTS preload список.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
SECURE_HSTS_PRELOAD=True   # Для продакшена
SECURE_HSTS_PRELOAD=False  # Для разработки
```

### SECURE_SSL_REDIRECT

**Описание**: Автоматическое перенаправление HTTP на HTTPS.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
SECURE_SSL_REDIRECT=True   # Для продакшена с HTTPS
SECURE_SSL_REDIRECT=False  # Для разработки
```

## Настройки Email

### EMAIL_BACKEND

**Описание**: Backend для отправки email.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: django.core.mail.backends.console.EmailBackend  

```env
# Консольный вывод (для разработки)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# SMTP (для продакшена)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend

# Файловый backend (для тестирования)
EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend

# В памяти (для тестов)
EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend

# Dummy backend (отключение email)
EMAIL_BACKEND=django.core.mail.backends.dummy.EmailBackend
```

### EMAIL_HOST

**Описание**: SMTP сервер для отправки email.

**Тип**: Строка  
**Обязательный**: Для SMTP backend  
**По умолчанию**: localhost  

```env
# Gmail
EMAIL_HOST=smtp.gmail.com

# Yandex
EMAIL_HOST=smtp.yandex.ru

# Mail.ru
EMAIL_HOST=smtp.mail.ru

# Собственный сервер
EMAIL_HOST=mail.your-domain.com
```

### EMAIL_PORT

**Описание**: Порт SMTP сервера.

**Тип**: Число  
**Обязательный**: Нет  
**По умолчанию**: 25  

```env
EMAIL_PORT=587   # TLS
EMAIL_PORT=465   # SSL
EMAIL_PORT=25    # Без шифрования
```

### EMAIL_USE_TLS

**Описание**: Использование TLS для SMTP.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
EMAIL_USE_TLS=True   # Для порта 587
EMAIL_USE_TLS=False  # Для порта 465 (используйте EMAIL_USE_SSL)
```

### EMAIL_USE_SSL

**Описание**: Использование SSL для SMTP.

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
EMAIL_USE_SSL=True   # Для порта 465
EMAIL_USE_SSL=False  # Для порта 587 (используйте EMAIL_USE_TLS)
```

### EMAIL_HOST_USER

**Описание**: Пользователь для аутентификации SMTP.

**Тип**: Строка  
**Обязательный**: Для аутентификации  
**По умолчанию**: Нет  

```env
EMAIL_HOST_USER=your-email@gmail.com
```

### EMAIL_HOST_PASSWORD

**Описание**: Пароль для аутентификации SMTP.

**Тип**: Строка  
**Обязательный**: Для аутентификации  
**По умолчанию**: Нет  

```env
EMAIL_HOST_PASSWORD=your-app-password
```

**Примечание**: Для Gmail используйте App Password, а не обычный пароль.

### DEFAULT_FROM_EMAIL

**Описание**: Email отправителя по умолчанию.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: webmaster@localhost  

```env
DEFAULT_FROM_EMAIL=noreply@your-domain.com
```

## Настройки Celery

### CELERY_BROKER_URL

**Описание**: URL брокера сообщений для Celery.

**Тип**: Строка  
**Обязательный**: Для Celery  
**По умолчанию**: Нет  

```env
# Redis
CELERY_BROKER_URL=redis://localhost:6379/0

# RabbitMQ
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//

# Amazon SQS
CELERY_BROKER_URL=sqs://AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY@sqs.us-east-1.amazonaws.com/123456789012/celery
```

### CELERY_RESULT_BACKEND

**Описание**: Backend для хранения результатов Celery.

**Тип**: Строка  
**Обязательный**: Для Celery  
**По умолчанию**: Нет  

```env
# Redis
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# База данных
CELERY_RESULT_BACKEND=db+postgresql://user:password@localhost/celery

# Memcached
CELERY_RESULT_BACKEND=cache+memcached://127.0.0.1:11211/
```

### CELERY_TASK_ALWAYS_EAGER

**Описание**: Выполнение задач Celery синхронно (для тестирования).

**Тип**: Булево  
**Обязательный**: Нет  
**По умолчанию**: False  

```env
CELERY_TASK_ALWAYS_EAGER=True   # Для тестов
CELERY_TASK_ALWAYS_EAGER=False  # Для продакшена
```

## Настройки логирования

### LOG_LEVEL

**Описание**: Уровень логирования.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: INFO  

```env
LOG_LEVEL=DEBUG    # Подробное логирование
LOG_LEVEL=INFO     # Информационные сообщения
LOG_LEVEL=WARNING  # Предупреждения и ошибки
LOG_LEVEL=ERROR    # Только ошибки
LOG_LEVEL=CRITICAL # Критические ошибки
```

### LOG_FILE

**Описание**: Путь к файлу логов.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: Нет (логи в консоль)  

```env
LOG_FILE=/var/log/django/insurance_system.log
```

### DJANGO_LOG_LEVEL

**Описание**: Уровень логирования Django.

**Тип**: Строка  
**Обязательный**: Нет  
**По умолчанию**: INFO  

```env
DJANGO_LOG_LEVEL=INFO
```

## Примеры конфигураций

### Разработка (Development)

```env
# Django основные настройки
SECRET_KEY=dev-secret-key-not-for-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# База данных SQLite
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# Email консольный вывод
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Безопасность отключена
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0

# Логирование
LOG_LEVEL=DEBUG
```

### Тестирование (Testing)

```env
# Django основные настройки
SECRET_KEY=test-secret-key-not-for-production
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,testserver

# База данных в памяти
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=:memory:

# Email в памяти
EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend

# Celery синхронно
CELERY_TASK_ALWAYS_EAGER=True

# Логирование минимальное
LOG_LEVEL=WARNING
```

### Продакшен (Production)

```env
# Django основные настройки
SECRET_KEY=your-very-secure-secret-key-here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# PostgreSQL база данных
DB_ENGINE=django.db.backends.postgresql
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure_password_here
DB_HOST=localhost
DB_PORT=5432

# SMTP email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.your-provider.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@your-domain.com

# Безопасность включена
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SECURE_SSL_REDIRECT=True

# Celery с Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Логирование
LOG_LEVEL=INFO
LOG_FILE=/var/log/django/insurance_system.log
```

## Валидация настроек

### Проверка конфигурации

```bash
# Проверка настроек Django
python manage.py check

# Проверка настроек для продакшена
python manage.py check --deploy

# Проверка подключения к базе данных
python manage.py dbshell -c "SELECT 1;"

# Проверка отправки email
python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test', 'Test message', 'from@example.com', ['to@example.com'])
"
```

### Скрипт валидации

Создайте файл `validate_env.py`:

```python
#!/usr/bin/env python3
"""
Скрипт для валидации переменных окружения
"""

import os
import sys
from pathlib import Path

def validate_env():
    """Валидация переменных окружения"""
    errors = []
    warnings = []
    
    # Загрузка .env файла
    env_file = Path('.env')
    if not env_file.exists():
        errors.append("Файл .env не найден")
        return errors, warnings
    
    # Чтение переменных
    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    
    # Проверка обязательных переменных
    required_vars = ['SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS']
    for var in required_vars:
        if var not in env_vars:
            errors.append(f"Отсутствует обязательная переменная: {var}")
    
    # Проверка SECRET_KEY
    if 'SECRET_KEY' in env_vars:
        secret_key = env_vars['SECRET_KEY']
        if len(secret_key) < 50:
            warnings.append("SECRET_KEY слишком короткий (рекомендуется минимум 50 символов)")
        if secret_key in ['your-secret-key-here', 'dev-secret-key-not-for-production']:
            errors.append("SECRET_KEY использует значение по умолчанию")
    
    # Проверка DEBUG
    if 'DEBUG' in env_vars:
        debug = env_vars['DEBUG'].lower()
        if debug not in ['true', 'false']:
            errors.append("DEBUG должен быть True или False")
        elif debug == 'true' and 'ALLOWED_HOSTS' in env_vars:
            allowed_hosts = env_vars['ALLOWED_HOSTS']
            if not allowed_hosts or allowed_hosts == '*':
                warnings.append("DEBUG=True с пустым или '*' ALLOWED_HOSTS может быть небезопасно")
    
    # Проверка базы данных
    if 'DB_ENGINE' in env_vars:
        engine = env_vars['DB_ENGINE']
        if 'postgresql' in engine:
            required_db_vars = ['DB_NAME', 'DB_USER', 'DB_PASSWORD']
            for var in required_db_vars:
                if var not in env_vars:
                    errors.append(f"Для PostgreSQL требуется переменная: {var}")
    
    # Проверка email
    if 'EMAIL_BACKEND' in env_vars:
        backend = env_vars['EMAIL_BACKEND']
        if 'smtp' in backend:
            required_email_vars = ['EMAIL_HOST', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD']
            for var in required_email_vars:
                if var not in env_vars:
                    warnings.append(f"Для SMTP рекомендуется переменная: {var}")
    
    # Проверка безопасности для продакшена
    if env_vars.get('DEBUG', '').lower() == 'false':
        security_vars = [
            'SESSION_COOKIE_SECURE',
            'CSRF_COOKIE_SECURE',
            'SECURE_HSTS_SECONDS'
        ]
        for var in security_vars:
            if var not in env_vars:
                warnings.append(f"Для продакшена рекомендуется переменная: {var}")
    
    return errors, warnings

if __name__ == '__main__':
    errors, warnings = validate_env()
    
    if errors:
        print("❌ ОШИБКИ:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    if warnings:
        print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    if not errors and not warnings:
        print("✅ Конфигурация корректна")
    
    sys.exit(1 if errors else 0)
```

Запуск валидации:
```bash
python validate_env.py
```

### Генерация .env файла

Создайте скрипт `generate_env.py`:

```python
#!/usr/bin/env python3
"""
Скрипт для генерации .env файла
"""

from django.core.management.utils import get_random_secret_key
import secrets
import string

def generate_password(length=16):
    """Генерация случайного пароля"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_env_file(environment='development'):
    """Генерация .env файла для указанной среды"""
    
    secret_key = get_random_secret_key()
    db_password = generate_password()
    
    if environment == 'development':
        content = f"""# Django основные настройки
SECRET_KEY={secret_key}
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# База данных SQLite
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# Email консольный вывод
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Безопасность отключена
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0

# Логирование
LOG_LEVEL=DEBUG
"""
    
    elif environment == 'production':
        content = f"""# Django основные настройки
SECRET_KEY={secret_key}
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# PostgreSQL база данных
DB_ENGINE=django.db.backends.postgresql
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD={db_password}
DB_HOST=localhost
DB_PORT=5432

# SMTP email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.your-provider.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@your-domain.com

# Безопасность включена
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SECURE_SSL_REDIRECT=True

# Celery с Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Логирование
LOG_LEVEL=INFO
LOG_FILE=/var/log/django/insurance_system.log
"""
    
    with open(f'.env.{environment}', 'w') as f:
        f.write(content)
    
    print(f"✅ Создан файл .env.{environment}")
    if environment == 'production':
        print(f"🔑 Сгенерированный пароль БД: {db_password}")
        print("⚠️  Не забудьте обновить настройки email и домена!")

if __name__ == '__main__':
    import sys
    
    env = sys.argv[1] if len(sys.argv) > 1 else 'development'
    
    if env not in ['development', 'production']:
        print("Использование: python generate_env.py [development|production]")
        sys.exit(1)
    
    generate_env_file(env)
```

Использование:
```bash
# Генерация для разработки
python generate_env.py development

# Генерация для продакшена
python generate_env.py production
```

---

**Примечание**: Всегда проверяйте и адаптируйте сгенерированные конфигурации под ваши конкретные требования.
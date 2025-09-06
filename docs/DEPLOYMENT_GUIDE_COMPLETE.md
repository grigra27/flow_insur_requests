# Полное руководство по развертыванию системы управления страховыми заявками

## Обзор

Данное руководство содержит исчерпывающие инструкции по развертыванию системы управления страховыми заявками с новыми функциями, включая систему аутентификации, улучшенные формы и шаблоны писем.

## Содержание

1. [Предварительные требования](#предварительные-требования)
2. [Подготовка к развертыванию](#подготовка-к-развертыванию)
3. [Автоматическое развертывание](#автоматическое-развертывание)
4. [Ручное развертывание](#ручное-развертывание)
5. [Настройка для продакшена](#настройка-для-продакшена)
6. [Тестирование системы](#тестирование-системы)
7. [Мониторинг и обслуживание](#мониторинг-и-обслуживание)
8. [Устранение неполадок](#устранение-неполадок)
9. [Откат изменений](#откат-изменений)

## Предварительные требования

### Системные требования

#### Минимальные требования
- **ОС**: Ubuntu 18.04+ / CentOS 7+ / macOS 10.14+
- **Python**: 3.8+
- **RAM**: 2 GB
- **Диск**: 10 GB свободного места
- **CPU**: 2 ядра

#### Рекомендуемые требования для продакшена
- **ОС**: Ubuntu 20.04 LTS / CentOS 8
- **Python**: 3.9+
- **RAM**: 8 GB
- **Диск**: 50 GB SSD
- **CPU**: 4 ядра
- **База данных**: PostgreSQL 12+

### Программное обеспечение

#### Обязательные компоненты
```bash
# Python и pip
python3 --version  # >= 3.8
pip3 --version

# Git
git --version

# Виртуальное окружение
python3 -m venv --help
```

#### Дополнительные компоненты для продакшена
```bash
# PostgreSQL
psql --version  # >= 12

# Nginx
nginx -v

# Supervisor или systemd
supervisorctl version
# или
systemctl --version

# Redis (опционально)
redis-server --version
```

### Проверка готовности системы

Запустите скрипт проверки:
```bash
#!/bin/bash
echo "=== Проверка готовности системы ==="

# Проверка Python
if command -v python3 &> /dev/null; then
    echo "✅ Python3: $(python3 --version)"
else
    echo "❌ Python3 не найден"
fi

# Проверка pip
if command -v pip3 &> /dev/null; then
    echo "✅ pip3: $(pip3 --version)"
else
    echo "❌ pip3 не найден"
fi

# Проверка Git
if command -v git &> /dev/null; then
    echo "✅ Git: $(git --version)"
else
    echo "❌ Git не найден"
fi

# Проверка свободного места
available_space=$(df -h . | awk 'NR==2{print $4}')
echo "💾 Свободное место: $available_space"

echo "=== Проверка завершена ==="
```

## Подготовка к развертыванию

### 1. Клонирование репозитория

```bash
# Клонируйте репозиторий
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# Проверьте текущую ветку
git branch -a
git checkout main  # или master
```

### 2. Создание виртуального окружения

```bash
# Создайте виртуальное окружение
python3 -m venv venv

# Активируйте окружение
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# Обновите pip
pip install --upgrade pip
```

### 3. Настройка переменных окружения

Создайте файл `.env`:
```bash
cp .env.example .env
```

Отредактируйте `.env`:
```env
# Основные настройки
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# База данных (для разработки)
DATABASE_URL=sqlite:///db.sqlite3

# База данных (для продакшена)
# DATABASE_URL=postgresql://user:password@localhost:5432/insurance_db

# Email настройки
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_HOST_USER=your-email@gmail.com
# EMAIL_HOST_PASSWORD=your-app-password

# Безопасность (только для продакшена)
# SECURE_SSL_REDIRECT=True
# SESSION_COOKIE_SECURE=True
# CSRF_COOKIE_SECURE=True

# Логирование
LOG_LEVEL=INFO
LOG_FILE=/var/log/django/insurance_system.log

# Celery (опционально)
# CELERY_BROKER_URL=redis://localhost:6379/0
# CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 4. Создание директорий

```bash
# Создайте необходимые директории
mkdir -p logs
mkdir -p media/attachments
mkdir -p static
mkdir -p backups

# Установите права доступа
chmod 755 logs media static backups
```

## Автоматическое развертывание

### Использование скрипта развертывания

```bash
# Сделайте скрипт исполняемым
chmod +x scripts/deploy.sh

# Отредактируйте пути в скрипте
nano scripts/deploy.sh

# Обновите следующие переменные:
PROJECT_DIR="/path/to/your/project"
VENV_DIR="/path/to/your/venv"
BACKUP_DIR="/backups/insurance_system"

# Запустите развертывание
./scripts/deploy.sh
```

### Что делает скрипт автоматического развертывания

1. **Проверка предварительных требований**
   - Проверяет наличие Python, pip, git
   - Проверяет виртуальное окружение
   - Проверяет свободное место на диске

2. **Создание резервной копии**
   - Создает дамп базы данных
   - Сохраняет текущие настройки

3. **Обновление кода**
   - Получает последние изменения из Git
   - Сохраняет локальные изменения в stash

4. **Установка зависимостей**
   - Обновляет pip
   - Устанавливает пакеты из requirements.txt

5. **Миграция базы данных**
   - Запускает кастомный скрипт миграции
   - Создает группы пользователей
   - Мигрирует данные периодов страхования

6. **Сбор статических файлов**
   - Собирает CSS, JS, изображения
   - Настраивает права доступа

7. **Запуск тестов**
   - Тестирует новые функции
   - Проверяет целостность системы

8. **Перезапуск сервисов**
   - Перезапускает веб-сервер
   - Обновляет конфигурацию

## Ручное развертывание

### Шаг 1: Установка зависимостей

```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Проверьте установку
pip list | grep -E "(Django|openpyxl|pandas)"
```

### Шаг 2: Настройка базы данных

#### Для разработки (SQLite)
```bash
# Создайте миграции
python manage.py makemigrations insurance_requests
python manage.py makemigrations summaries

# Примените миграции
python manage.py migrate

# Создайте суперпользователя
python manage.py createsuperuser
```

#### Для продакшена (PostgreSQL)
```bash
# Создайте базу данных
sudo -u postgres psql
CREATE DATABASE insurance_db;
CREATE USER insurance_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE insurance_db TO insurance_user;
\q

# Обновите DATABASE_URL в .env
DATABASE_URL=postgresql://insurance_user:secure_password@localhost:5432/insurance_db

# Примените миграции
python manage.py migrate
```

### Шаг 3: Настройка групп пользователей

```bash
# Создайте группы и пользователей
python manage.py setup_user_groups

# Проверьте создание
python manage.py shell -c "
from django.contrib.auth.models import User, Group
print('Группы:', [g.name for g in Group.objects.all()])
print('Пользователи:', [u.username for u in User.objects.all()])
"
```

### Шаг 4: Миграция данных

```bash
# Запустите кастомный скрипт миграции
python scripts/migrate_database.py

# Проверьте результаты
python manage.py shell -c "
from insurance_requests.models import InsuranceRequest
total = InsuranceRequest.objects.count()
with_dates = InsuranceRequest.objects.filter(
    insurance_start_date__isnull=False,
    insurance_end_date__isnull=False
).count()
print(f'Всего заявок: {total}')
print(f'С датами: {with_dates}')
"
```

### Шаг 5: Сбор статических файлов

```bash
# Соберите статические файлы
python manage.py collectstatic --noinput

# Проверьте создание файлов
ls -la staticfiles/css/
ls -la staticfiles/admin/
```

### Шаг 6: Загрузка начальных данных

```bash
# Загрузите фикстуры (если есть)
python manage.py loaddata insurance_requests/fixtures/initial_data.json

# Или создайте тестовые данные
python manage.py create_test_data
```

## Настройка для продакшена

### 1. Настройка Django

Создайте `settings_production.py`:
```python
from .settings import *

# Безопасность
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

# База данных
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'insurance_db',
        'USER': 'insurance_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
        'OPTIONS': {
            'MAX_CONNS': 20,
        }
    }
}

# Кэширование
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Сессии
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Безопасность
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Логирование
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/insurance_system.log',
            'maxBytes': 1024*1024*10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'auth_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/auth.log',
            'maxBytes': 1024*1024*5,  # 5 MB
            'backupCount': 3,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'insurance_requests.middleware': {
            'handlers': ['auth_file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.your-provider.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@domain.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
```

### 2. Настройка Gunicorn

Создайте `gunicorn.conf.py`:
```python
# Gunicorn configuration file
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"

# Process naming
proc_name = "insurance_system"

# Server mechanics
daemon = False
pidfile = "/var/run/gunicorn/insurance_system.pid"
user = "www-data"
group = "www-data"
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None
```

### 3. Настройка Nginx

Создайте `/etc/nginx/sites-available/insurance_system`:
```nginx
# HTTP redirect to HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL configuration
    ssl_certificate /path/to/your/certificate.crt;
    ssl_certificate_key /path/to/your/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;

    # Client max body size
    client_max_body_size 50M;

    # Proxy to Django
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files
    location /static/ {
        alias /path/to/your/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Gzip static files
        gzip_static on;
    }

    # Media files
    location /media/ {
        alias /path/to/your/media/;
        expires 1y;
        add_header Cache-Control "public";
    }

    # Favicon
    location = /favicon.ico {
        alias /path/to/your/staticfiles/favicon.ico;
        expires 1y;
        add_header Cache-Control "public";
    }

    # Robots.txt
    location = /robots.txt {
        alias /path/to/your/staticfiles/robots.txt;
        expires 1y;
        add_header Cache-Control "public";
    }
}
```

### 4. Настройка systemd

Создайте `/etc/systemd/system/insurance_system.service`:
```ini
[Unit]
Description=Insurance System Gunicorn daemon
Requires=insurance_system.socket
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
RuntimeDirectory=gunicorn
WorkingDirectory=/path/to/your/project
ExecStart=/path/to/your/venv/bin/gunicorn --config gunicorn.conf.py onlineservice.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Создайте `/etc/systemd/system/insurance_system.socket`:
```ini
[Unit]
Description=Insurance System gunicorn socket

[Socket]
ListenStream=/run/gunicorn/insurance_system.sock
SocketUser=www-data
SocketGroup=www-data
SocketMode=0600

[Install]
WantedBy=sockets.target
```

### 5. Запуск сервисов

```bash
# Создайте директории для логов
sudo mkdir -p /var/log/django /var/log/gunicorn /var/run/gunicorn
sudo chown www-data:www-data /var/log/django /var/log/gunicorn /var/run/gunicorn

# Включите и запустите сервисы
sudo systemctl daemon-reload
sudo systemctl enable insurance_system.socket
sudo systemctl start insurance_system.socket
sudo systemctl enable insurance_system.service
sudo systemctl start insurance_system.service

# Включите Nginx
sudo ln -s /etc/nginx/sites-available/insurance_system /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Проверьте статус
sudo systemctl status insurance_system
sudo systemctl status nginx
```

## Тестирование системы

### 1. Автоматические тесты

```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Запустите все тесты
python manage.py test insurance_requests --verbosity=2

# Запустите конкретные тесты
python manage.py test insurance_requests.test_authentication_system
python manage.py test insurance_requests.test_login_interface
python manage.py test insurance_requests.test_form_enhancements
python manage.py test insurance_requests.test_enhanced_email_templates
python manage.py test insurance_requests.test_new_insurance_type
python manage.py test insurance_requests.test_end_to_end_workflow
python manage.py test insurance_requests.test_performance_and_security

# Проверьте покрытие тестами
coverage run --source='.' manage.py test insurance_requests
coverage report
coverage html
```

### 2. Ручное тестирование

#### Тестирование аутентификации
1. Откройте браузер и перейдите на главную страницу
2. Убедитесь, что вас перенаправляет на `/login/`
3. Войдите с учетными данными `admin`/`admin123`
4. Проверьте доступ к основным функциям
5. Выйдите из системы и проверьте перенаправление

#### Тестирование новых функций
1. **Новый тип страхования**:
   - Создайте заявку с типом "Страхование имущества"
   - Проверьте сохранение и отображение

2. **Отдельные поля дат**:
   - Откройте форму редактирования
   - Заполните поля дат начала и окончания
   - Проверьте валидацию (начальная дата не позже конечной)

3. **Улучшенные письма**:
   - Сгенерируйте письмо для каждого типа страхования
   - Проверьте расширенные описания
   - Проверьте новый формат дат

#### Тестирование производительности
```bash
# Установите Apache Bench
sudo apt-get install apache2-utils

# Тестируйте страницу входа
ab -n 100 -c 10 http://your-domain.com/login/

# Тестируйте главную страницу (с аутентификацией)
ab -n 100 -c 10 -C "sessionid=your-session-id" http://your-domain.com/

# Мониторинг ресурсов
htop
iotop
```

### 3. Тестирование безопасности

```bash
# Проверьте настройки безопасности Django
python manage.py check --deploy

# Тестируйте SSL (если настроен)
curl -I https://your-domain.com

# Проверьте заголовки безопасности
curl -I https://your-domain.com | grep -E "(Strict-Transport-Security|X-Content-Type-Options|X-Frame-Options)"

# Тестируйте аутентификацию
curl -I http://your-domain.com/insurance-requests/
# Должен вернуть 302 (редирект на login)
```

## Мониторинг и обслуживание

### 1. Настройка мониторинга

#### Логирование
```bash
# Создайте скрипт ротации логов
sudo nano /etc/logrotate.d/insurance_system

# Содержимое файла:
/var/log/django/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 www-data www-data
    postrotate
        systemctl reload insurance_system
    endscript
}

/var/log/gunicorn/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 www-data www-data
    postrotate
        systemctl reload insurance_system
    endscript
}
```

#### Мониторинг системы
```bash
# Создайте скрипт мониторинга
cat > /usr/local/bin/insurance_monitor.sh << 'EOF'
#!/bin/bash

LOG_FILE="/var/log/insurance_monitor.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Проверка сервисов
if ! systemctl is-active --quiet insurance_system; then
    echo "[$DATE] ERROR: insurance_system service is down" >> $LOG_FILE
    systemctl restart insurance_system
fi

if ! systemctl is-active --quiet nginx; then
    echo "[$DATE] ERROR: nginx service is down" >> $LOG_FILE
    systemctl restart nginx
fi

# Проверка базы данных
if ! python3 /path/to/your/project/manage.py check --database default; then
    echo "[$DATE] ERROR: Database connection failed" >> $LOG_FILE
fi

# Проверка дискового пространства
DISK_USAGE=$(df / | awk 'NR==2{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "[$DATE] WARNING: Disk usage is ${DISK_USAGE}%" >> $LOG_FILE
fi

# Проверка памяти
MEM_USAGE=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ $MEM_USAGE -gt 80 ]; then
    echo "[$DATE] WARNING: Memory usage is ${MEM_USAGE}%" >> $LOG_FILE
fi

echo "[$DATE] INFO: System check completed" >> $LOG_FILE
EOF

chmod +x /usr/local/bin/insurance_monitor.sh

# Добавьте в crontab
echo "*/5 * * * * /usr/local/bin/insurance_monitor.sh" | sudo crontab -
```

### 2. Резервное копирование

```bash
# Создайте скрипт резервного копирования
cat > /usr/local/bin/insurance_backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/backups/insurance_system"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/path/to/your/project"

# Создайте директорию для бэкапов
mkdir -p $BACKUP_DIR

# Бэкап базы данных
cd $PROJECT_DIR
source venv/bin/activate
python manage.py dumpdata > $BACKUP_DIR/db_backup_$DATE.json

# Бэкап медиа файлов
tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz media/

# Бэкап конфигурации
cp .env $BACKUP_DIR/env_backup_$DATE
cp -r staticfiles $BACKUP_DIR/static_backup_$DATE/

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.json" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
find $BACKUP_DIR -name "env_backup_*" -mtime +30 -delete
find $BACKUP_DIR -name "static_backup_*" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /usr/local/bin/insurance_backup.sh

# Добавьте в crontab (ежедневно в 2:00)
echo "0 2 * * * /usr/local/bin/insurance_backup.sh" | sudo crontab -
```

### 3. Обновление системы

```bash
# Создайте скрипт обновления
cat > /usr/local/bin/insurance_update.sh << 'EOF'
#!/bin/bash

PROJECT_DIR="/path/to/your/project"
VENV_DIR="/path/to/your/venv"

cd $PROJECT_DIR

# Создайте бэкап перед обновлением
/usr/local/bin/insurance_backup.sh

# Обновите код
git stash
git pull origin main

# Активируйте виртуальное окружение
source $VENV_DIR/bin/activate

# Обновите зависимости
pip install -r requirements.txt

# Примените миграции
python manage.py migrate

# Соберите статические файлы
python manage.py collectstatic --noinput

# Запустите тесты
python manage.py test insurance_requests

# Перезапустите сервисы
sudo systemctl restart insurance_system
sudo systemctl reload nginx

echo "Update completed successfully"
EOF

chmod +x /usr/local/bin/insurance_update.sh
```

## Устранение неполадок

### Общие проблемы

#### 1. Сервис не запускается
```bash
# Проверьте статус сервиса
sudo systemctl status insurance_system

# Проверьте логи
sudo journalctl -u insurance_system -f

# Проверьте конфигурацию Gunicorn
/path/to/your/venv/bin/gunicorn --check-config gunicorn.conf.py

# Проверьте Django
cd /path/to/your/project
source venv/bin/activate
python manage.py check
```

#### 2. База данных недоступна
```bash
# Проверьте подключение к PostgreSQL
sudo -u postgres psql -c "SELECT version();"

# Проверьте настройки в .env
cat .env | grep DATABASE

# Тестируйте подключение Django
python manage.py dbshell
```

#### 3. Статические файлы не загружаются
```bash
# Проверьте права доступа
ls -la staticfiles/
sudo chown -R www-data:www-data staticfiles/

# Пересоберите статические файлы
python manage.py collectstatic --clear --noinput

# Проверьте конфигурацию Nginx
sudo nginx -t
```

#### 4. Проблемы с аутентификацией
```bash
# Проверьте группы пользователей
python manage.py shell -c "
from django.contrib.auth.models import Group
print([g.name for g in Group.objects.all()])
"

# Пересоздайте группы
python manage.py setup_user_groups

# Проверьте middleware
grep -n "AuthenticationMiddleware" onlineservice/settings.py
```

### Диагностические команды

```bash
# Проверка системы
python manage.py check --deploy

# Информация о базе данных
python manage.py dbshell -c "\dt"

# Статистика по заявкам
python manage.py shell -c "
from insurance_requests.models import InsuranceRequest
print(f'Всего заявок: {InsuranceRequest.objects.count()}')
print(f'С новым типом: {InsuranceRequest.objects.filter(insurance_type=\"страхование имущества\").count()}')
"

# Проверка пользователей
python manage.py shell -c "
from django.contrib.auth.models import User
for user in User.objects.all():
    groups = [g.name for g in user.groups.all()]
    print(f'{user.username}: {groups}')
"

# Тест отправки email
python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test', 'Test message', 'from@example.com', ['to@example.com'])
"
```

## Откат изменений

### Автоматический откат

Если скрипт развертывания завершился с ошибкой, он автоматически выполнит откат:

```bash
# Скрипт автоматически:
# 1. Восстановит базу данных из последнего бэкапа
# 2. Откатит код к предыдущему коммиту
# 3. Перезапустит сервисы
```

### Ручной откат

#### 1. Откат базы данных
```bash
# Найдите последний бэкап
ls -la /backups/insurance_system/

# Восстановите базу данных
cd /path/to/your/project
source venv/bin/activate

# Очистите текущую базу
python manage.py flush --noinput

# Загрузите бэкап
python manage.py loaddata /backups/insurance_system/db_backup_YYYYMMDD_HHMMSS.json
```

#### 2. Откат кода
```bash
# Посмотрите историю коммитов
git log --oneline -10

# Откатитесь к предыдущему стабильному коммиту
git checkout COMMIT_HASH

# Или создайте новую ветку для отката
git checkout -b rollback_$(date +%Y%m%d)
git reset --hard COMMIT_HASH
```

#### 3. Откат конфигурации
```bash
# Восстановите конфигурацию
cp /backups/insurance_system/env_backup_YYYYMMDD .env

# Восстановите статические файлы
rm -rf staticfiles/
cp -r /backups/insurance_system/static_backup_YYYYMMDD/ staticfiles/
```

#### 4. Перезапуск сервисов
```bash
# Перезапустите все сервисы
sudo systemctl restart insurance_system
sudo systemctl reload nginx

# Проверьте статус
sudo systemctl status insurance_system
sudo systemctl status nginx
```

### План восстановления после сбоя

1. **Оценка ущерба**
   - Определите масштаб проблемы
   - Проверьте доступность данных
   - Оцените время восстановления

2. **Восстановление данных**
   - Восстановите базу данных из последнего бэкапа
   - Проверьте целостность данных
   - Восстановите медиа файлы

3. **Восстановление кода**
   - Откатитесь к последней стабильной версии
   - Проверьте конфигурацию
   - Запустите тесты

4. **Проверка системы**
   - Протестируйте основные функции
   - Проверьте производительность
   - Убедитесь в безопасности

5. **Документирование**
   - Задокументируйте причину сбоя
   - Обновите процедуры восстановления
   - Проведите анализ для предотвращения повторения

## Заключение

Данное руководство содержит исчерпывающие инструкции по развертыванию системы управления страховыми заявками с новыми функциями. Следуйте инструкциям последовательно и не пропускайте этапы тестирования.

### Контрольный список развертывания

- [ ] Проверены предварительные требования
- [ ] Создано виртуальное окружение
- [ ] Установлены зависимости
- [ ] Настроена база данных
- [ ] Применены миграции
- [ ] Созданы группы пользователей
- [ ] Собраны статические файлы
- [ ] Настроена конфигурация для продакшена
- [ ] Запущены тесты
- [ ] Настроен мониторинг
- [ ] Настроено резервное копирование
- [ ] Протестирована система
- [ ] Документированы процедуры

### Поддержка

При возникновении проблем:
1. Проверьте логи системы
2. Обратитесь к разделу "Устранение неполадок"
3. Свяжитесь с технической поддержкой

---

**Версия документа**: 1.0  
**Дата создания**: $(date +%d.%m.%Y)  
**Автор**: Команда разработки системы управления страховыми заявками
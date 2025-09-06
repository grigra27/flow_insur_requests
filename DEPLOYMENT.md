# Руководство по развертыванию

Подробное руководство по развертыванию системы управления страховыми заявками в различных средах.

## Содержание

1. [Обзор процесса развертывания](#обзор-процесса-развертывания)
2. [Автоматическое развертывание](#автоматическое-развертывание)
3. [Ручное развертывание](#ручное-развертывание)
4. [Настройка для продакшена](#настройка-для-продакшена)
5. [Мониторинг и обслуживание](#мониторинг-и-обслуживание)
6. [Резервное копирование](#резервное-копирование)
7. [Обновление системы](#обновление-системы)
8. [Устранение неполадок](#устранение-неполадок)

## Обзор процесса развертывания

### Этапы развертывания

1. **Подготовка сервера** - установка необходимого ПО
2. **Настройка базы данных** - PostgreSQL или SQLite
3. **Установка приложения** - код, зависимости, конфигурация
4. **Настройка веб-сервера** - Nginx, SSL
5. **Настройка сервисов** - systemd, мониторинг
6. **Тестирование** - проверка функциональности
7. **Мониторинг** - логи, метрики, резервное копирование

### Архитектура развертывания

```
[Пользователь] → [Nginx] → [Gunicorn] → [Django] → [PostgreSQL]
                     ↓
                [Статические файлы]
```

## Автоматическое развертывание

### Использование скрипта развертывания

```bash
# Скачайте и настройте скрипт
wget https://raw.githubusercontent.com/your-repo/insurance-system/main/scripts/deploy.sh
chmod +x deploy.sh

# Отредактируйте настройки в скрипте
nano deploy.sh

# Запустите развертывание
./deploy.sh
```

### Настройка скрипта развертывания

Отредактируйте переменные в `deploy.sh`:

```bash
# Основные настройки
PROJECT_NAME="insurance-system"
PROJECT_DIR="/opt/insurance-system"
VENV_DIR="/opt/insurance-system/venv"
USER="insurance"
GROUP="www-data"

# База данных
DB_NAME="insurance_db"
DB_USER="insurance_user"
DB_PASSWORD="secure_password"

# Домен
DOMAIN="your-domain.com"
EMAIL="admin@your-domain.com"

# Резервное копирование
BACKUP_DIR="/backups/insurance-system"
```

### Что делает автоматический скрипт

1. **Проверка системы** - требования, права доступа
2. **Установка зависимостей** - Python, PostgreSQL, Nginx
3. **Создание пользователя** - системный пользователь для приложения
4. **Настройка базы данных** - создание БД и пользователя
5. **Установка приложения** - клонирование, зависимости
6. **Конфигурация** - настройка всех сервисов
7. **Запуск** - активация всех компонентов
8. **Тестирование** - проверка работоспособности

## Ручное развертывание

### Шаг 1: Подготовка сервера

#### Ubuntu/Debian

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка базовых пакетов
sudo apt install -y python3 python3-pip python3-venv git curl wget

# Установка веб-сервера и базы данных
sudo apt install -y nginx postgresql postgresql-contrib

# Установка дополнительных инструментов
sudo apt install -y supervisor redis-server htop
```

#### CentOS/RHEL

```bash
# Обновление системы
sudo yum update -y

# Установка EPEL репозитория
sudo yum install -y epel-release

# Установка базовых пакетов
sudo yum install -y python3 python3-pip git curl wget

# Установка веб-сервера и базы данных
sudo yum install -y nginx postgresql postgresql-server postgresql-contrib

# Инициализация PostgreSQL
sudo postgresql-setup initdb
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### Шаг 2: Создание пользователя приложения

```bash
# Создание пользователя
sudo useradd -m -s /bin/bash insurance
sudo usermod -aG www-data insurance

# Создание директорий
sudo mkdir -p /opt/insurance-system
sudo mkdir -p /var/log/insurance-system
sudo mkdir -p /backups/insurance-system

# Установка прав доступа
sudo chown insurance:www-data /opt/insurance-system
sudo chown insurance:www-data /var/log/insurance-system
sudo chown insurance:www-data /backups/insurance-system
```

### Шаг 3: Настройка PostgreSQL

```bash
# Переключение на пользователя postgres
sudo -u postgres psql

# Создание базы данных и пользователя
CREATE DATABASE insurance_db;
CREATE USER insurance_user WITH PASSWORD 'secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE insurance_db TO insurance_user;
ALTER USER insurance_user CREATEDB;
\q

# Настройка аутентификации
sudo nano /etc/postgresql/12/main/pg_hba.conf
# Добавьте строку:
# local   insurance_db    insurance_user                  md5

# Перезапуск PostgreSQL
sudo systemctl restart postgresql
```

### Шаг 4: Установка приложения

```bash
# Переключение на пользователя приложения
sudo su - insurance

# Переход в рабочую директорию
cd /opt/insurance-system

# Клонирование репозитория
git clone https://github.com/your-repo/insurance-system.git .

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn psycopg2-binary
```

### Шаг 5: Конфигурация приложения

```bash
# Создание конфигурационного файла
cp .env.example .env

# Редактирование конфигурации
nano .env
```

Пример продакшен конфигурации:
```env
# Django настройки
SECRET_KEY=your-very-secure-secret-key-here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# База данных
DB_ENGINE=django.db.backends.postgresql
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure_password_here
DB_HOST=localhost
DB_PORT=5432

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.your-provider.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-app-password

# Безопасность
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

### Шаг 6: Настройка базы данных

```bash
# Применение миграций
python manage.py migrate

# Создание групп пользователей
python manage.py setup_user_groups

# Создание суперпользователя
python manage.py createsuperuser

# Сбор статических файлов
python manage.py collectstatic --noinput

# Проверка настроек
python manage.py check --deploy
```

### Шаг 7: Настройка Gunicorn

Создайте файл `gunicorn.conf.py`:
```python
import multiprocessing
import os

# Определение путей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "/var/log/insurance-system/gunicorn_access.log"
errorlog = "/var/log/insurance-system/gunicorn_error.log"
loglevel = "info"

# Process naming
proc_name = "insurance_system"

# Server mechanics
daemon = False
pidfile = "/var/run/gunicorn/insurance_system.pid"
user = "insurance"
group = "www-data"
tmp_upload_dir = None

# Environment
raw_env = [
    f'DJANGO_SETTINGS_MODULE=onlineservice.settings',
    f'PYTHONPATH={BASE_DIR}',
]
```

### Шаг 8: Настройка systemd

Создайте `/etc/systemd/system/insurance-system.service`:
```ini
[Unit]
Description=Insurance System Gunicorn daemon
Requires=insurance-system.socket
After=network.target

[Service]
Type=notify
User=insurance
Group=www-data
RuntimeDirectory=gunicorn
WorkingDirectory=/opt/insurance-system
Environment="PATH=/opt/insurance-system/venv/bin"
ExecStart=/opt/insurance-system/venv/bin/gunicorn --config gunicorn.conf.py onlineservice.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Создайте `/etc/systemd/system/insurance-system.socket`:
```ini
[Unit]
Description=Insurance System gunicorn socket

[Socket]
ListenStream=/run/gunicorn/insurance_system.sock
SocketUser=insurance
SocketGroup=www-data
SocketMode=0600

[Install]
WantedBy=sockets.target
```

### Шаг 9: Настройка Nginx

Создайте `/etc/nginx/sites-available/insurance-system`:
```nginx
# Upstream для Gunicorn
upstream insurance_system {
    server 127.0.0.1:8000;
}

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
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
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
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;

    # Client settings
    client_max_body_size 50M;
    client_body_timeout 60s;
    client_header_timeout 60s;

    # Proxy to Django
    location / {
        proxy_pass http://insurance_system;
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
        alias /opt/insurance-system/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Gzip static files
        gzip_static on;
    }

    # Media files
    location /media/ {
        alias /opt/insurance-system/media/;
        expires 1y;
        add_header Cache-Control "public";
    }

    # Favicon
    location = /favicon.ico {
        alias /opt/insurance-system/staticfiles/favicon.ico;
        expires 1y;
        add_header Cache-Control "public";
    }

    # Robots.txt
    location = /robots.txt {
        alias /opt/insurance-system/staticfiles/robots.txt;
        expires 1y;
        add_header Cache-Control "public";
    }

    # Security
    location ~ /\. {
        deny all;
    }
}
```

### Шаг 10: Запуск сервисов

```bash
# Создание необходимых директорий
sudo mkdir -p /var/run/gunicorn
sudo chown insurance:www-data /var/run/gunicorn

# Активация и запуск systemd сервисов
sudo systemctl daemon-reload
sudo systemctl enable insurance-system.socket
sudo systemctl start insurance-system.socket
sudo systemctl enable insurance-system.service
sudo systemctl start insurance-system.service

# Настройка Nginx
sudo ln -s /etc/nginx/sites-available/insurance-system /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# Проверка статуса
sudo systemctl status insurance-system
sudo systemctl status nginx
```

## Настройка для продакшена

### SSL/HTTPS с Let's Encrypt

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Проверка автоматического обновления
sudo certbot renew --dry-run

# Настройка автоматического обновления
echo "0 12 * * * /usr/bin/certbot renew --quiet" | sudo crontab -
```

### Настройка файрвола

```bash
# UFW (Ubuntu)
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable

# Firewalld (CentOS)
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### Оптимизация производительности

#### PostgreSQL

Отредактируйте `/etc/postgresql/12/main/postgresql.conf`:
```ini
# Memory settings
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# Connection settings
max_connections = 100

# Logging
log_statement = 'all'
log_duration = on
log_min_duration_statement = 1000
```

#### Nginx

Отредактируйте `/etc/nginx/nginx.conf`:
```nginx
worker_processes auto;
worker_connections 1024;

# Gzip settings
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_comp_level 6;
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/javascript
    application/xml+rss
    application/json;

# Buffer settings
client_body_buffer_size 128k;
client_max_body_size 50m;
client_header_buffer_size 1k;
large_client_header_buffers 4 4k;
output_buffers 1 32k;
postpone_output 1460;
```

## Мониторинг и обслуживание

### Настройка логирования

#### Django логи

Добавьте в `settings.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/insurance-system/django.log',
            'maxBytes': 1024*1024*10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'auth_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/insurance-system/auth.log',
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
```

#### Ротация логов

Создайте `/etc/logrotate.d/insurance-system`:
```
/var/log/insurance-system/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 insurance www-data
    postrotate
        systemctl reload insurance-system
    endscript
}

/var/log/nginx/access.log /var/log/nginx/error.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 www-data adm
    postrotate
        systemctl reload nginx
    endscript
}
```

### Мониторинг системы

Создайте скрипт мониторинга `/usr/local/bin/insurance_monitor.sh`:
```bash
#!/bin/bash

LOG_FILE="/var/log/insurance-system/monitor.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Функция логирования
log_message() {
    echo "[$DATE] $1" >> $LOG_FILE
}

# Проверка сервисов
check_service() {
    local service=$1
    if ! systemctl is-active --quiet $service; then
        log_message "ERROR: $service service is down"
        systemctl restart $service
        log_message "INFO: Restarted $service service"
    fi
}

# Проверка основных сервисов
check_service insurance-system
check_service nginx
check_service postgresql

# Проверка базы данных
if ! sudo -u insurance /opt/insurance-system/venv/bin/python /opt/insurance-system/manage.py check --database default > /dev/null 2>&1; then
    log_message "ERROR: Database connection failed"
fi

# Проверка дискового пространства
DISK_USAGE=$(df / | awk 'NR==2{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    log_message "WARNING: Disk usage is ${DISK_USAGE}%"
fi

# Проверка памяти
MEM_USAGE=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ $MEM_USAGE -gt 80 ]; then
    log_message "WARNING: Memory usage is ${MEM_USAGE}%"
fi

# Проверка процессов Gunicorn
GUNICORN_PROCESSES=$(pgrep -f "gunicorn.*insurance" | wc -l)
if [ $GUNICORN_PROCESSES -lt 2 ]; then
    log_message "WARNING: Only $GUNICORN_PROCESSES Gunicorn processes running"
fi

log_message "INFO: System check completed"
```

Сделайте скрипт исполняемым и добавьте в cron:
```bash
sudo chmod +x /usr/local/bin/insurance_monitor.sh
echo "*/5 * * * * /usr/local/bin/insurance_monitor.sh" | sudo crontab -
```

## Резервное копирование

### Автоматическое резервное копирование

Создайте скрипт `/usr/local/bin/insurance_backup.sh`:
```bash
#!/bin/bash

BACKUP_DIR="/backups/insurance-system"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/opt/insurance-system"
RETENTION_DAYS=30

# Создание директории для бэкапов
mkdir -p $BACKUP_DIR

# Функция логирования
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $BACKUP_DIR/backup.log
}

log_message "Starting backup process"

# Бэкап базы данных
log_message "Backing up database"
cd $PROJECT_DIR
sudo -u insurance $PROJECT_DIR/venv/bin/python manage.py dumpdata > $BACKUP_DIR/db_backup_$DATE.json
if [ $? -eq 0 ]; then
    log_message "Database backup completed successfully"
else
    log_message "ERROR: Database backup failed"
    exit 1
fi

# Бэкап медиа файлов
log_message "Backing up media files"
tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz -C $PROJECT_DIR media/
if [ $? -eq 0 ]; then
    log_message "Media backup completed successfully"
else
    log_message "ERROR: Media backup failed"
fi

# Бэкап конфигурации
log_message "Backing up configuration"
cp $PROJECT_DIR/.env $BACKUP_DIR/env_backup_$DATE
cp -r $PROJECT_DIR/staticfiles $BACKUP_DIR/static_backup_$DATE/

# Удаление старых бэкапов
log_message "Cleaning up old backups"
find $BACKUP_DIR -name "db_backup_*.json" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "media_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "env_backup_*" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "static_backup_*" -mtime +$RETENTION_DAYS -delete

# Проверка размера бэкапов
BACKUP_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
log_message "Backup completed. Total size: $BACKUP_SIZE"

# Отправка уведомления (опционально)
# echo "Backup completed successfully. Size: $BACKUP_SIZE" | mail -s "Insurance System Backup" admin@your-domain.com
```

Настройте автоматическое выполнение:
```bash
sudo chmod +x /usr/local/bin/insurance_backup.sh
echo "0 2 * * * /usr/local/bin/insurance_backup.sh" | sudo crontab -
```

### Восстановление из резервной копии

```bash
# Остановите сервисы
sudo systemctl stop insurance-system
sudo systemctl stop nginx

# Восстановите базу данных
cd /opt/insurance-system
sudo -u insurance venv/bin/python manage.py flush --noinput
sudo -u insurance venv/bin/python manage.py loaddata /backups/insurance-system/db_backup_YYYYMMDD_HHMMSS.json

# Восстановите медиа файлы
rm -rf media/
tar -xzf /backups/insurance-system/media_backup_YYYYMMDD_HHMMSS.tar.gz

# Восстановите конфигурацию
cp /backups/insurance-system/env_backup_YYYYMMDD .env

# Запустите сервисы
sudo systemctl start insurance-system
sudo systemctl start nginx
```

## Обновление системы

### Автоматическое обновление

Создайте скрипт `/usr/local/bin/insurance_update.sh`:
```bash
#!/bin/bash

PROJECT_DIR="/opt/insurance-system"
VENV_DIR="/opt/insurance-system/venv"
BACKUP_SCRIPT="/usr/local/bin/insurance_backup.sh"

# Функция логирования
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_message "Starting update process"

# Создание бэкапа перед обновлением
log_message "Creating backup before update"
$BACKUP_SCRIPT

cd $PROJECT_DIR

# Сохранение локальных изменений
log_message "Stashing local changes"
sudo -u insurance git stash

# Обновление кода
log_message "Pulling latest changes"
sudo -u insurance git pull origin main

# Активация виртуального окружения
source $VENV_DIR/bin/activate

# Обновление зависимостей
log_message "Updating dependencies"
sudo -u insurance pip install -r requirements.txt

# Применение миграций
log_message "Applying database migrations"
sudo -u insurance python manage.py migrate

# Сбор статических файлов
log_message "Collecting static files"
sudo -u insurance python manage.py collectstatic --noinput

# Проверка системы
log_message "Running system checks"
sudo -u insurance python manage.py check --deploy

# Запуск тестов
log_message "Running tests"
sudo -u insurance python manage.py test insurance_requests --verbosity=0

if [ $? -eq 0 ]; then
    log_message "Tests passed successfully"
    
    # Перезапуск сервисов
    log_message "Restarting services"
    sudo systemctl restart insurance-system
    sudo systemctl reload nginx
    
    log_message "Update completed successfully"
else
    log_message "ERROR: Tests failed, rolling back"
    
    # Откат изменений
    sudo -u insurance git reset --hard HEAD~1
    sudo systemctl restart insurance-system
    
    log_message "Rollback completed"
    exit 1
fi
```

### Ручное обновление

```bash
# Переключитесь на пользователя приложения
sudo su - insurance
cd /opt/insurance-system

# Создайте бэкап
/usr/local/bin/insurance_backup.sh

# Сохраните локальные изменения
git stash

# Обновите код
git pull origin main

# Активируйте виртуальное окружение
source venv/bin/activate

# Обновите зависимости
pip install -r requirements.txt

# Примените миграции
python manage.py migrate

# Соберите статические файлы
python manage.py collectstatic --noinput

# Запустите тесты
python manage.py test

# Перезапустите сервисы
sudo systemctl restart insurance-system
sudo systemctl reload nginx
```

## Устранение неполадок

### Диагностика проблем

#### Проверка сервисов

```bash
# Статус сервисов
sudo systemctl status insurance-system
sudo systemctl status nginx
sudo systemctl status postgresql

# Логи сервисов
sudo journalctl -u insurance-system -f
sudo journalctl -u nginx -f
sudo journalctl -u postgresql -f
```

#### Проверка приложения

```bash
# Проверка Django
cd /opt/insurance-system
sudo -u insurance venv/bin/python manage.py check
sudo -u insurance venv/bin/python manage.py check --deploy

# Проверка базы данных
sudo -u insurance venv/bin/python manage.py dbshell -c "SELECT version();"

# Проверка статических файлов
ls -la staticfiles/css/
ls -la staticfiles/admin/
```

#### Проверка сети

```bash
# Проверка портов
sudo netstat -tlnp | grep :80
sudo netstat -tlnp | grep :443
sudo netstat -tlnp | grep :8000

# Проверка DNS
nslookup your-domain.com
dig your-domain.com

# Проверка SSL
openssl s_client -connect your-domain.com:443 -servername your-domain.com
```

### Общие проблемы и решения

#### 1. Сервис не запускается

```bash
# Проверьте логи
sudo journalctl -u insurance-system -n 50

# Проверьте конфигурацию Gunicorn
sudo -u insurance /opt/insurance-system/venv/bin/gunicorn --check-config gunicorn.conf.py

# Проверьте права доступа
sudo chown -R insurance:www-data /opt/insurance-system/
```

#### 2. База данных недоступна

```bash
# Проверьте статус PostgreSQL
sudo systemctl status postgresql

# Проверьте подключение
sudo -u postgres psql -c "SELECT version();"

# Проверьте настройки в .env
grep DB_ /opt/insurance-system/.env
```

#### 3. Статические файлы не загружаются

```bash
# Пересоберите статические файлы
cd /opt/insurance-system
sudo -u insurance venv/bin/python manage.py collectstatic --clear --noinput

# Проверьте права доступа
sudo chown -R insurance:www-data staticfiles/
sudo chmod -R 755 staticfiles/

# Проверьте конфигурацию Nginx
sudo nginx -t
```

#### 4. SSL сертификат не работает

```bash
# Обновите сертификат
sudo certbot renew

# Проверьте конфигурацию Nginx
sudo nginx -t

# Проверьте сертификат
openssl x509 -in /etc/letsencrypt/live/your-domain.com/fullchain.pem -text -noout
```

### Мониторинг производительности

```bash
# Мониторинг системных ресурсов
htop
iotop
nethogs

# Мониторинг базы данных
sudo -u postgres psql insurance_db -c "SELECT * FROM pg_stat_activity;"

# Мониторинг Nginx
sudo tail -f /var/log/nginx/access.log | grep -E "(POST|GET)"

# Мониторинг Django
sudo tail -f /var/log/insurance-system/django.log
```

### Контрольный список развертывания

- [ ] Сервер подготовлен и обновлен
- [ ] PostgreSQL установлен и настроен
- [ ] Пользователь приложения создан
- [ ] Приложение установлено и настроено
- [ ] База данных мигрирована
- [ ] Статические файлы собраны
- [ ] Gunicorn настроен и запущен
- [ ] Nginx настроен и запущен
- [ ] SSL сертификат установлен
- [ ] Файрвол настроен
- [ ] Мониторинг настроен
- [ ] Резервное копирование настроено
- [ ] Тесты пройдены успешно
- [ ] Документация обновлена

---

**Примечание**: Данное руководство покрывает основные сценарии развертывания. Для специфических конфигураций может потребоваться дополнительная настройка.
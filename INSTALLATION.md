# Руководство по установке

Подробное руководство по установке системы управления страховыми заявками для различных сред.

## Содержание

1. [Системные требования](#системные-требования)
2. [Установка для разработки](#установка-для-разработки)
3. [Установка для тестирования](#установка-для-тестирования)
4. [Установка для продакшена](#установка-для-продакшена)
5. [Настройка переменных окружения](#настройка-переменных-окружения)
6. [Загрузка демонстрационных данных](#загрузка-демонстрационных-данных)
7. [Проверка установки](#проверка-установки)
8. [Устранение неполадок](#устранение-неполадок)

## Системные требования

### Минимальные требования
- **ОС**: Ubuntu 18.04+ / CentOS 7+ / macOS 10.14+ / Windows 10+
- **Python**: 3.8+ (рекомендуется 3.9+)
- **RAM**: 2 GB
- **Диск**: 5 GB свободного места
- **CPU**: 1 ядро

### Рекомендуемые требования для продакшена
- **ОС**: Ubuntu 20.04 LTS / CentOS 8
- **Python**: 3.9+
- **RAM**: 8 GB
- **Диск**: 50 GB SSD
- **CPU**: 4 ядра
- **База данных**: PostgreSQL 12+
- **Веб-сервер**: Nginx
- **Кэш**: Redis (опционально)

### Проверка готовности системы

```bash
# Проверка Python
python3 --version  # Должно быть >= 3.8

# Проверка pip
pip3 --version

# Проверка Git
git --version

# Проверка виртуального окружения
python3 -m venv --help
```

## Установка для разработки

### Быстрая установка

```bash
# 1. Клонирование репозитория
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# 2. Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# 3. Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt

# 4. Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env при необходимости

# 5. Настройка базы данных
python manage.py migrate
python manage.py setup_user_groups

# 6. Создание администратора
python manage.py createsuperuser

# 7. Загрузка демо-данных (опционально)
python manage.py loaddata insurance_requests/fixtures/sample_data.json

# 8. Запуск сервера
python manage.py runserver
```

### Пошаговая установка

#### Шаг 1: Подготовка

```bash
# Создайте директорию для проекта
mkdir ~/projects
cd ~/projects

# Клонируйте репозиторий
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# Проверьте содержимое
ls -la
```

#### Шаг 2: Виртуальное окружение

```bash
# Создайте виртуальное окружение
python3 -m venv venv

# Активируйте окружение
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# Проверьте активацию
which python  # Должно показать путь к venv/bin/python
```

#### Шаг 3: Зависимости

```bash
# Обновите pip
pip install --upgrade pip

# Установите зависимости
pip install -r requirements.txt

# Проверьте установку ключевых пакетов
pip list | grep -E "(Django|pandas|openpyxl)"
```

#### Шаг 4: Конфигурация

```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Отредактируйте конфигурацию (опционально)
nano .env  # или любой другой редактор
```

#### Шаг 5: База данных

```bash
# Создайте миграции (если нужно)
python manage.py makemigrations

# Примените миграции
python manage.py migrate

# Создайте группы пользователей
python manage.py setup_user_groups

# Проверьте создание таблиц
python manage.py dbshell -c ".tables"  # SQLite
```

#### Шаг 6: Пользователи

```bash
# Создайте суперпользователя
python manage.py createsuperuser
# Введите: username, email, password

# Или загрузите демо-пользователей
python manage.py loaddata insurance_requests/fixtures/sample_data.json
# Демо-пользователи: admin/admin123, user/user123
```

#### Шаг 7: Статические файлы

```bash
# Соберите статические файлы
python manage.py collectstatic --noinput

# Проверьте создание
ls -la staticfiles/
```

#### Шаг 8: Запуск

```bash
# Запустите сервер разработки
python manage.py runserver

# Или на другом порту
python manage.py runserver 8080

# Или для доступа извне
python manage.py runserver 0.0.0.0:8000
```

## Установка для тестирования

### Настройка тестовой среды

```bash
# Клонируйте в отдельную директорию
git clone https://github.com/your-repo/insurance-system.git insurance-system-test
cd insurance-system-test

# Создайте отдельное виртуальное окружение
python3 -m venv venv-test
source venv-test/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Настройте тестовую конфигурацию
cp .env.example .env.test
```

### Конфигурация для тестирования

Отредактируйте `.env.test`:
```env
# Тестовые настройки
DEBUG=False
SECRET_KEY=test-secret-key-not-for-production
ALLOWED_HOSTS=localhost,127.0.0.1,testserver

# Тестовая база данных
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=test_db.sqlite3

# Тестовый email backend
EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend

# Отключение внешних сервисов
CELERY_TASK_ALWAYS_EAGER=True
```

### Запуск тестов

```bash
# Используйте тестовую конфигурацию
export DJANGO_SETTINGS_MODULE=onlineservice.settings
export ENV_FILE=.env.test

# Настройте тестовую базу данных
python manage.py migrate

# Запустите все тесты
python manage.py test

# Запустите тесты с покрытием
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html
```

## Установка для продакшена

### Подготовка сервера

```bash
# Обновите систему (Ubuntu/Debian)
sudo apt update && sudo apt upgrade -y

# Установите необходимые пакеты
sudo apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib redis-server supervisor

# Создайте пользователя для приложения
sudo useradd -m -s /bin/bash insurance
sudo usermod -aG www-data insurance
```

### Настройка PostgreSQL

```bash
# Переключитесь на пользователя postgres
sudo -u postgres psql

# Создайте базу данных и пользователя
CREATE DATABASE insurance_db;
CREATE USER insurance_user WITH PASSWORD 'secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE insurance_db TO insurance_user;
ALTER USER insurance_user CREATEDB;
\q

# Настройте аутентификацию (отредактируйте pg_hba.conf)
sudo nano /etc/postgresql/12/main/pg_hba.conf
# Добавьте: local   insurance_db    insurance_user                  md5
sudo systemctl restart postgresql
```

### Установка приложения

```bash
# Переключитесь на пользователя приложения
sudo su - insurance

# Клонируйте репозиторий
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn psycopg2-binary

# Настройте продакшен конфигурацию
cp .env.example .env
```

### Продакшен конфигурация

Отредактируйте `.env`:
```env
# Продакшен настройки
DEBUG=False
SECRET_KEY=your-very-secure-secret-key-here
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# PostgreSQL база данных
DB_ENGINE=django.db.backends.postgresql
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure_password_here
DB_HOST=localhost
DB_PORT=5432

# Email настройки
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

### Настройка базы данных

```bash
# Примените миграции
python manage.py migrate

# Создайте группы пользователей
python manage.py setup_user_groups

# Создайте суперпользователя
python manage.py createsuperuser

# Соберите статические файлы
python manage.py collectstatic --noinput

# Проверьте настройки для продакшена
python manage.py check --deploy
```

### Настройка Gunicorn

Создайте `gunicorn.conf.py`:
```python
# Gunicorn configuration
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
user = "insurance"
group = "www-data"
```

### Настройка systemd

Создайте `/etc/systemd/system/insurance-system.service`:
```ini
[Unit]
Description=Insurance System Gunicorn daemon
After=network.target

[Service]
Type=notify
User=insurance
Group=www-data
RuntimeDirectory=gunicorn
WorkingDirectory=/home/insurance/insurance-system
ExecStart=/home/insurance/insurance-system/venv/bin/gunicorn --config gunicorn.conf.py onlineservice.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Настройка Nginx

Создайте `/etc/nginx/sites-available/insurance-system`:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;
    
    # SSL configuration (настройте SSL сертификаты)
    # ssl_certificate /path/to/your/certificate.crt;
    # ssl_certificate_key /path/to/your/private.key;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    
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
    }
    
    # Static files
    location /static/ {
        alias /home/insurance/insurance-system/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files
    location /media/ {
        alias /home/insurance/insurance-system/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
}
```

### Запуск сервисов

```bash
# Создайте директории для логов
sudo mkdir -p /var/log/gunicorn
sudo chown insurance:www-data /var/log/gunicorn

# Включите и запустите сервисы
sudo systemctl daemon-reload
sudo systemctl enable insurance-system
sudo systemctl start insurance-system

# Настройте Nginx
sudo ln -s /etc/nginx/sites-available/insurance-system /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# Проверьте статус
sudo systemctl status insurance-system
sudo systemctl status nginx
```

## Настройка переменных окружения

### Обязательные переменные

```env
# Django основные настройки
SECRET_KEY=your-secret-key-here
DEBUG=False  # True только для разработки
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# База данных
DB_ENGINE=django.db.backends.sqlite3  # или postgresql
DB_NAME=db.sqlite3  # или имя PostgreSQL базы
DB_USER=  # для PostgreSQL
DB_PASSWORD=  # для PostgreSQL
DB_HOST=  # для PostgreSQL
DB_PORT=  # для PostgreSQL
```

### Опциональные переменные

```env
# Email настройки
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Безопасность (для продакшена)
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True

# Celery (для фоновых задач)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Логирование
LOG_LEVEL=INFO
LOG_FILE=/var/log/django/insurance_system.log
```

### Генерация SECRET_KEY

```python
# В Django shell или отдельном скрипте
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

## Загрузка демонстрационных данных

### Автоматическая загрузка

```bash
# Загрузите все демонстрационные данные
python manage.py loaddata insurance_requests/fixtures/sample_data.json

# Проверьте загрузку
python manage.py shell -c "
from django.contrib.auth.models import User
from insurance_requests.models import InsuranceRequest
print(f'Пользователей: {User.objects.count()}')
print(f'Заявок: {InsuranceRequest.objects.count()}')
"
```

### Демонстрационные пользователи

После загрузки доступны:
- **admin** / **admin123** (администратор)
- **user** / **user123** (обычный пользователь)

### Создание собственных данных

```bash
# Создайте пользователей
python manage.py shell
>>> from django.contrib.auth.models import User, Group
>>> admin_group = Group.objects.get(name='Администраторы')
>>> user_group = Group.objects.get(name='Пользователи')
>>> 
>>> # Создайте администратора
>>> admin = User.objects.create_user('admin', 'admin@example.com', 'password')
>>> admin.groups.add(admin_group)
>>> admin.is_staff = True
>>> admin.save()
>>> 
>>> # Создайте обычного пользователя
>>> user = User.objects.create_user('user', 'user@example.com', 'password')
>>> user.groups.add(user_group)
>>> user.save()
```

## Проверка установки

### Базовая проверка

```bash
# Проверьте Django
python manage.py check

# Проверьте базу данных
python manage.py dbshell -c "SELECT COUNT(*) FROM django_migrations;"

# Проверьте статические файлы
ls -la staticfiles/css/
ls -la staticfiles/admin/

# Проверьте пользователей
python manage.py shell -c "
from django.contrib.auth.models import User
print([u.username for u in User.objects.all()])
"
```

### Проверка веб-интерфейса

1. Запустите сервер: `python manage.py runserver`
2. Откройте браузер: http://127.0.0.1:8000/
3. Проверьте перенаправление на страницу входа
4. Войдите с демо-пользователем: admin/admin123
5. Проверьте доступ к основным функциям

### Проверка функциональности

```bash
# Запустите тесты
python manage.py test insurance_requests

# Проверьте конкретные функции
python manage.py test insurance_requests.test_authentication_system
python manage.py test insurance_requests.test_form_enhancements
python manage.py test insurance_requests.test_enhanced_email_templates
```

## Устранение неполадок

### Проблемы с зависимостями

```bash
# Переустановите зависимости
pip install --upgrade --force-reinstall -r requirements.txt

# Проверьте конфликты
pip check

# Обновите pip
pip install --upgrade pip
```

### Проблемы с базой данных

```bash
# Пересоздайте базу данных (SQLite)
rm db.sqlite3
python manage.py migrate

# Проверьте подключение к PostgreSQL
python manage.py dbshell
\l  # список баз данных
\q  # выход
```

### Проблемы с миграциями

```bash
# Проверьте статус миграций
python manage.py showmigrations

# Примените конкретную миграцию
python manage.py migrate insurance_requests 0001

# Откатите миграцию
python manage.py migrate insurance_requests 0001

# Пересоздайте миграции (осторожно!)
rm insurance_requests/migrations/0*.py
python manage.py makemigrations insurance_requests
python manage.py migrate
```

### Проблемы с правами доступа

```bash
# Исправьте права на файлы (Linux)
sudo chown -R insurance:www-data /home/insurance/insurance-system/
sudo chmod -R 755 /home/insurance/insurance-system/
sudo chmod -R 644 /home/insurance/insurance-system/media/

# Проверьте права на директории
ls -la media/
ls -la staticfiles/
```

### Проблемы с сервисами (продакшен)

```bash
# Проверьте статус сервисов
sudo systemctl status insurance-system
sudo systemctl status nginx

# Проверьте логи
sudo journalctl -u insurance-system -f
sudo tail -f /var/log/nginx/error.log

# Перезапустите сервисы
sudo systemctl restart insurance-system
sudo systemctl reload nginx
```

### Диагностические команды

```bash
# Информация о системе
python --version
pip --version
python manage.py version

# Информация о Django
python manage.py diffsettings
python manage.py check --deploy

# Информация о базе данных
python manage.py inspectdb | head -20
python manage.py dbshell -c ".schema" | head -10  # SQLite
```

### Получение помощи

1. Проверьте логи приложения
2. Запустите диагностические команды
3. Проверьте документацию Django
4. Обратитесь к команде разработки

---

**Примечание**: Данное руководство покрывает основные сценарии установки. Для специфических конфигураций может потребоваться дополнительная настройка.
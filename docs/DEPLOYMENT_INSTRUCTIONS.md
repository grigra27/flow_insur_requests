# Инструкции по развертыванию новых функций

## Обзор

Данный документ содержит пошаговые инструкции по развертыванию новых функций системы управления страховыми заявками, включая:

- Новый тип страхования "страхование имущества"
- Улучшенные шаблоны писем с расширенными описаниями
- Отдельные поля дат страхования
- Систему аутентификации с ролевой моделью
- Современный интерфейс входа в систему

## Предварительные требования

### Системные требования
- Python 3.8+
- Django 4.2+
- PostgreSQL или SQLite (для разработки)
- Redis (опционально, для кэширования)

### Зависимости
Убедитесь, что установлены все необходимые пакеты из `requirements.txt`:
```bash
pip install -r requirements.txt
```

## Пошаговое развертывание

### Шаг 1: Подготовка базы данных

#### 1.1 Создание миграций
```bash
python manage.py makemigrations insurance_requests
```

#### 1.2 Применение миграций
```bash
python manage.py migrate
```

#### 1.3 Проверка миграций
```bash
python manage.py showmigrations
```

Убедитесь, что все миграции применены успешно.

### Шаг 2: Настройка групп пользователей и разрешений

#### 2.1 Создание групп пользователей
```bash
python manage.py setup_user_groups
```

Эта команда создаст:
- Группу "Администраторы" с полными правами
- Группу "Пользователи" с ограниченными правами
- Пользователя `admin` с правами администратора
- Пользователя `user` с правами обычного пользователя

#### 2.2 Проверка созданных групп
```bash
python manage.py shell
```

```python
from django.contrib.auth.models import Group, User
print("Группы:", [g.name for g in Group.objects.all()])
print("Пользователи:", [u.username for u in User.objects.all()])
```

### Шаг 3: Настройка статических файлов

#### 3.1 Сбор статических файлов
```bash
python manage.py collectstatic --noinput
```

#### 3.2 Проверка CSS файлов
Убедитесь, что файл `static/css/login.css` доступен и содержит стили для страницы входа.

### Шаг 4: Настройка конфигурации Django

#### 4.1 Обновление settings.py
Убедитесь, что в `settings.py` добавлены следующие настройки:

```python
# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'insurance_requests.middleware.AuthenticationMiddleware',  # Новый middleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Настройки аутентификации
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/insurance-requests/'
LOGOUT_REDIRECT_URL = '/login/'

# Настройки сессий
SESSION_COOKIE_AGE = 86400  # 24 часа
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE = True  # Только для HTTPS в продакшене
SESSION_COOKIE_HTTPONLY = True
```

#### 4.2 Обновление urls.py
Убедитесь, что в главном `urls.py` добавлены маршруты аутентификации:

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('insurance_requests.urls')),
    path('summaries/', include('summaries.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### Шаг 5: Проверка функциональности

#### 5.1 Запуск сервера разработки
```bash
python manage.py runserver
```

#### 5.2 Тестирование аутентификации
1. Откройте браузер и перейдите на `http://localhost:8000`
2. Убедитесь, что вас перенаправляет на страницу входа
3. Войдите с учетными данными `admin`/`admin123`
4. Проверьте доступ к основным функциям

#### 5.3 Тестирование новых функций
1. **Новый тип страхования**: Создайте заявку с типом "страхование имущества"
2. **Отдельные даты**: Отредактируйте заявку и проверьте поля дат
3. **Улучшенные письма**: Сгенерируйте письмо и проверьте расширенные описания
4. **Ролевая модель**: Войдите как обычный пользователь и проверьте ограничения

### Шаг 6: Запуск тестов

#### 6.1 Запуск всех тестов
```bash
python manage.py test insurance_requests
```

#### 6.2 Запуск конкретных тестов
```bash
# Тесты аутентификации
python manage.py test insurance_requests.test_authentication_system

# Тесты интерфейса входа
python manage.py test insurance_requests.test_login_interface

# Тесты улучшений форм
python manage.py test insurance_requests.test_form_enhancements

# Тесты улучшенных шаблонов писем
python manage.py test insurance_requests.test_enhanced_email_templates

# Тесты нового типа страхования
python manage.py test insurance_requests.test_new_insurance_type

# End-to-end тесты
python manage.py test insurance_requests.test_end_to_end_workflow

# Тесты производительности и безопасности
python manage.py test insurance_requests.test_performance_and_security
```

#### 6.3 Проверка покрытия тестами
```bash
coverage run --source='.' manage.py test insurance_requests
coverage report
coverage html
```

## Развертывание в продакшене

### Настройки безопасности для продакшена

#### 1. Обновите settings.py для продакшена:
```python
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

# Безопасность
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# База данных (PostgreSQL для продакшена)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'insurance_db',
        'USER': 'insurance_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

#### 2. Настройка веб-сервера (Nginx + Gunicorn)

**Gunicorn конфигурация** (`gunicorn.conf.py`):
```python
bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2
```

**Nginx конфигурация**:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /static/ {
        alias /path/to/your/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    location /media/ {
        alias /path/to/your/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
}
```

### Скрипт развертывания

Создайте скрипт `deploy.sh`:
```bash
#!/bin/bash

echo "Начало развертывания..."

# Обновление кода
git pull origin main

# Установка зависимостей
pip install -r requirements.txt

# Применение миграций
python manage.py migrate

# Настройка групп пользователей
python manage.py setup_user_groups

# Сбор статических файлов
python manage.py collectstatic --noinput

# Запуск тестов
python manage.py test insurance_requests

# Перезапуск Gunicorn
sudo systemctl restart gunicorn

# Перезапуск Nginx
sudo systemctl restart nginx

echo "Развертывание завершено!"
```

## Мониторинг и обслуживание

### Логирование

Добавьте в `settings.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/django/insurance_system.log',
        },
        'auth_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/django/auth.log',
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

### Резервное копирование

Создайте скрипт резервного копирования `backup.sh`:
```bash
#!/bin/bash

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/insurance_system"

# Создание директории для бэкапов
mkdir -p $BACKUP_DIR

# Бэкап базы данных
pg_dump insurance_db > $BACKUP_DIR/db_backup_$DATE.sql

# Бэкап медиа файлов
tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz /path/to/media/

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Резервное копирование завершено: $DATE"
```

### Мониторинг производительности

Рекомендуемые инструменты:
- **Django Debug Toolbar** (только для разработки)
- **Sentry** для отслеживания ошибок
- **New Relic** или **DataDog** для мониторинга производительности
- **Prometheus + Grafana** для метрик

## Откат изменений

### В случае проблем с развертыванием:

1. **Откат миграций**:
```bash
python manage.py migrate insurance_requests 0004  # Номер предыдущей миграции
```

2. **Восстановление из резервной копии**:
```bash
# Восстановление базы данных
psql insurance_db < /backups/db_backup_YYYYMMDD_HHMMSS.sql

# Восстановление медиа файлов
tar -xzf /backups/media_backup_YYYYMMDD_HHMMSS.tar.gz -C /
```

3. **Откат кода**:
```bash
git checkout previous_stable_commit
```

## Проверочный список развертывания

- [ ] Применены все миграции базы данных
- [ ] Созданы группы пользователей и тестовые аккаунты
- [ ] Собраны статические файлы
- [ ] Обновлены настройки безопасности
- [ ] Настроен веб-сервер (Nginx/Apache)
- [ ] Настроено логирование
- [ ] Настроено резервное копирование
- [ ] Запущены все тесты
- [ ] Проверена функциональность аутентификации
- [ ] Проверены новые функции (типы страхования, даты, письма)
- [ ] Настроен мониторинг
- [ ] Документирован процесс отката

## Поддержка

При возникновении проблем с развертыванием:

1. Проверьте логи Django и веб-сервера
2. Убедитесь, что все зависимости установлены
3. Проверьте настройки базы данных
4. Запустите тесты для диагностики проблем
5. Обратитесь к документации Django для специфических ошибок

---

*Данные инструкции актуальны для текущей версии системы. При внесении изменений обновите документацию соответственно.*
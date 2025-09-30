# Система управления страховыми заявками

Корпоративный веб-сервис для автоматизации работы со страховыми заявками с современным интерфейсом и расширенными возможностями.

## Описание

Система предназначена для автоматизации процесса обработки страховых заявок:
- 📁 Загрузка и обработка Excel-заявок от клиентов
- 📝 Автоматическое извлечение данных из Excel (поддержка .xls, .xlsx и .xltx)
- 📧 Генерация писем по настраиваемым шаблонам
- 🔐 Система аутентификации и авторизации пользователей
- 🖥️ Современный веб-интерфейс для управления заявками
- 📊 Детальный просмотр и редактирование заявок
- 📈 Генерация сводных отчетов

## Возможности

### ✅ Реализовано
- 📁 Загрузка и обработка Excel файлов с заявками
- 📝 Автоматическое извлечение данных из Excel (поддержка .xls, .xlsx и .xltx)
- 📧 Генерация писем по расширенным шаблонам
- 🔐 Система аутентификации с группами пользователей
- 🖥️ Веб-интерфейс для управления заявками
- 📊 Детальный просмотр и редактирование заявок
- 🎨 Адаптивный интерфейс на Bootstrap 5
- 📱 Мобильная адаптация
- 🏢 Поддержка филиалов с выпадающим списком
- 📅 Отдельные поля для дат начала и окончания страхования
- 🚗 Поддержка КАСКО категории C/E
- 🏠 Новый тип страхования "Страхование имущества"
- 📧 Расширенные шаблоны писем с детальными описаниями

### 🚧 В разработке
- 📤 Отправка писем через SMTP
- 📥 Автоматическая проверка входящих писем
- 🤖 Парсинг ответов от страховых компаний
- 📈 Генерация Excel отчетов
- ⚡ Фоновые задачи через Celery
- 🐳 Контейнеризация Docker

## Технологии

- **Backend**: Django 4.2, Python 3.9+
- **Frontend**: Bootstrap 5, HTML5, CSS3, JavaScript
- **База данных**: SQLite (готовность к PostgreSQL)
- **Обработка Excel**: pandas, openpyxl
- **Очереди задач**: Celery + Redis (настроено)
- **Email**: smtplib, imaplib, exchangelib
- **Аутентификация**: Django Auth с кастомными группами

## Быстрый старт

### Предварительные требования

- Python 3.8+ (рекомендуется 3.9+)
- pip (менеджер пакетов Python)
- Git
- Виртуальное окружение (venv)

### Установка для разработки

1. **Клонирование репозитория**
```bash
git clone https://github.com/grigra27/flow_insur_requests.git
cd flow_insur_requests
```

2. **Создание виртуального окружения**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows
```

3. **Установка зависимостей**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Настройка переменных окружения**
```bash
cp .env.example .env
# Отредактируйте .env файл согласно вашим настройкам
```

5. **Настройка базы данных**
```bash
python manage.py migrate
python manage.py setup_user_groups  # Создание групп пользователей
python manage.py createsuperuser    # Создание администратора
```

6. **Загрузка демонстрационных данных (опционально)**
```bash
python manage.py loaddata insurance_requests/fixtures/sample_data.json
```

7. **Запуск сервера разработки**
```bash
python manage.py runserver
```

Сервис будет доступен по адресу: http://127.0.0.1:8000/

### Быстрая установка с демо-данными

```bash
# Клонирование и настройка
git clone https://github.com/grigra27/flow_insur_requests.git
cd flow_insur_requests
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Настройка с демо-данными
cp .env.example .env
python manage.py migrate
python manage.py setup_user_groups
python manage.py loaddata insurance_requests/fixtures/sample_data.json
python manage.py runserver
```

**Демо-пользователи:**
- Администратор: `admin` / `admin123`
- Пользователь: `user` / `user123`

## Структура проекта

```
onlineservice/
├── core/                    # Универсальные модули
│   ├── excel_utils.py      # Работа с Excel файлами
│   ├── mail_utils.py       # Работа с почтой
│   ├── templates.py        # Генерация писем
│   └── tasks.py            # Фоновые задачи Celery
├── insurance_requests/      # Django-приложение "Заявки"
│   ├── models.py           # Модели данных
│   ├── views.py            # Представления
│   ├── forms.py            # Формы
│   └── templates/          # HTML шаблоны
├── reports/                # Django-приложение "Отчёты"
├── templates/              # Общие шаблоны
├── static/                 # Статические файлы
└── media/                  # Загруженные файлы
```

## Использование

### 1. Загрузка заявки
1. Перейдите на главную страницу
2. Нажмите "Загрузить новую заявку"
3. Выберите Excel файл с данными заявки
4. Система автоматически извлечет данные

### 2. Генерация письма
1. Откройте детали заявки
2. Нажмите "Сгенерировать письмо"
3. Система создаст письмо по шаблону
4. При необходимости отредактируйте текст

### 3. Формат Excel файла
Система извлекает данные из следующих ячеек:
- **HIJ2**: Номер ДФА (договор финансовой аренды)
- **CDEF4**: Филиал
- **D7**: Название клиента (объединенная ячейка D-F)
- **D9**: ИНН клиента (объединенная ячейка D-F)
- **D21**: Если заполнена → тип страхования "КАСКО"
- **D22**: Если заполнена → тип страхования "страхование спецтехники"
- **N17**: Если заполнена → период страхования "1 год"
- **N18**: Если заполнена → период страхования "на весь срок лизинга"
- **CDEFGHI43-49**: Информация о предмете лизинга (поиск в указанных строках)
- **D29**: Если заполнена → франшизы НЕТ
- **F34**: Если заполнена → рассрочки нет
- **M24**: Если "нет" → автозапуска нет, иначе есть

**Поддерживаемые форматы файлов**: .xls, .xlsx, .xltx

**Пример извлеченных данных:**
- ДФА: `ТС-20212-ГА-КЗ`
- Филиал: `Казанский филиал`
- Клиент: `ООО "АЛТЫН ЯР"`
- Предмет лизинга: `специальный, грузовой бортовой оснащенный краном-манипулятором СПМ Авто 732457`

**Тема письма формируется по шаблону:**
`ДФА - Филиал - Информация о предмете лизинга - порядковый номер письма`

Подробное описание логики обработки см. в [EXCEL_PROCESSING.md](EXCEL_PROCESSING.md)

## Конфигурация

### Переменные окружения

Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

#### Основные настройки
```env
# Django настройки
SECRET_KEY=your-secret-key-here-change-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# База данных (SQLite для разработки)
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# База данных (PostgreSQL для продакшена)
# DB_ENGINE=django.db.backends.postgresql
# DB_NAME=insurance_db
# DB_USER=insurance_user
# DB_PASSWORD=secure_password
# DB_HOST=localhost
# DB_PORT=5432
```

#### Настройки безопасности (для продакшена)
```env
# Security настройки
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

#### Email настройки
```env
# Email настройки (для разработки - консольный вывод)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Email настройки (для продакшена - SMTP)
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_HOST_USER=your-email@gmail.com
# EMAIL_HOST_PASSWORD=your-app-password
```

#### Celery настройки (опционально)
```env
# Celery настройки для фоновых задач
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### Настройка для разных сред

#### Разработка
- Используйте SQLite базу данных
- DEBUG=True
- Консольный email backend
- Минимальные настройки безопасности

#### Staging
- Используйте отдельную базу данных
- DEBUG=False
- Консольный email backend
- Базовые настройки безопасности

#### Продакшен
- Используйте PostgreSQL
- DEBUG=False
- SMTP email backend
- Полные настройки безопасности
- HTTPS обязательно

## Разработка

### Настройка среды разработки

1. **Активация виртуального окружения**
```bash
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows
```

2. **Установка зависимостей для разработки**
```bash
pip install -r requirements.txt
```

3. **Проверка конфигурации**
```bash
# Проверка настроек Django
python manage.py check

# Проверка готовности к деплою
python manage.py check --deploy
```

4. **Создание миграций**
```bash
# Создание миграций
python manage.py makemigrations

# Применение миграций
python manage.py migrate

# Просмотр SQL миграций
python manage.py sqlmigrate insurance_requests 0001
```

5. **Работа с данными**
```bash
# Django shell
python manage.py shell

# Создание суперпользователя
python manage.py createsuperuser

# Загрузка фикстур
python manage.py loaddata insurance_requests/fixtures/sample_data.json

# Создание дампа данных
python manage.py dumpdata insurance_requests > backup.json
```

### Запуск Celery (для фоновых задач)
```bash
# В отдельном терминале
celery -A onlineservice worker -l info

# Для периодических задач
celery -A onlineservice beat -l info

# Мониторинг Celery
celery -A onlineservice flower
```

### Структура данных

#### Основные модели
- `InsuranceRequest` - основная модель заявки
  - Поддержка всех типов страхования
  - Отдельные поля для дат начала и окончания
  - Поддержка КАСКО категории C/E
  - Связь с пользователем-создателем
- `RequestAttachment` - вложения к заявке
- `InsuranceResponse` - ответы от страховых компаний
- `ResponseAttachment` - вложения к ответам

#### Группы пользователей
- `Администраторы` - полный доступ ко всем функциям
- `Пользователи` - доступ к основным функциям работы с заявками

### Стандарты кодирования

1. **Python код**
   - Следуйте PEP 8
   - Используйте type hints где возможно
   - Документируйте функции и классы
   - Максимальная длина строки: 88 символов

2. **Django код**
   - Используйте Django best practices
   - Валидация данных в формах и моделях
   - Используйте Django ORM вместо raw SQL
   - Правильная обработка исключений

3. **Frontend код**
   - Используйте Bootstrap классы
   - Минимум кастомного CSS
   - Прогрессивное улучшение
   - Доступность (accessibility)

### Отладка

1. **Django Debug Toolbar** (для разработки)
```bash
pip install django-debug-toolbar
# Добавьте в INSTALLED_APPS и MIDDLEWARE
```

2. **Логирование**
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Сообщение для отладки")
```

3. **Django shell для отладки**
```bash
python manage.py shell
>>> from insurance_requests.models import InsuranceRequest
>>> InsuranceRequest.objects.all()
```

## Развертывание в продакшене

### Автоматическое развертывание

Используйте скрипт автоматического развертывания:

```bash
# Сделайте скрипт исполняемым
chmod +x scripts/deploy.sh

# Отредактируйте пути в скрипте
nano scripts/deploy.sh

# Запустите развертывание
./scripts/deploy.sh
```

### Ручное развертывание

#### 1. Подготовка сервера

```bash
# Обновите систему
sudo apt update && sudo apt upgrade -y

# Установите необходимые пакеты
sudo apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib redis-server

# Создайте пользователя для приложения
sudo useradd -m -s /bin/bash insurance
sudo usermod -aG www-data insurance
```

#### 2. Настройка PostgreSQL

```bash
# Создайте базу данных и пользователя
sudo -u postgres psql
CREATE DATABASE insurance_db;
CREATE USER insurance_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE insurance_db TO insurance_user;
ALTER USER insurance_user CREATEDB;
\q
```

#### 3. Настройка приложения

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
pip install -r requirements.txt
pip install gunicorn psycopg2-binary

# Настройте переменные окружения для продакшена
cp .env.example .env
# Отредактируйте .env с настройками продакшена
```

#### 4. Настройка базы данных

```bash
# Примените миграции
python manage.py migrate

# Создайте группы пользователей
python manage.py setup_user_groups

# Создайте суперпользователя
python manage.py createsuperuser

# Соберите статические файлы
python manage.py collectstatic --noinput
```

#### 5. Настройка Gunicorn

Создайте файл `gunicorn.conf.py`:
```python
bind = "127.0.0.1:8000"
workers = 3
timeout = 30
keepalive = 2
max_requests = 1000
preload_app = True
```

#### 6. Настройка systemd

Создайте `/etc/systemd/system/insurance-system.service`:
```ini
[Unit]
Description=Insurance System Gunicorn daemon
After=network.target

[Service]
User=insurance
Group=www-data
WorkingDirectory=/home/insurance/insurance-system
ExecStart=/home/insurance/insurance-system/venv/bin/gunicorn --config gunicorn.conf.py onlineservice.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

#### 7. Настройка Nginx

Создайте `/etc/nginx/sites-available/insurance-system`:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /static/ {
        alias /home/insurance/insurance-system/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    location /media/ {
        alias /home/insurance/insurance-system/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
    
    client_max_body_size 50M;
}
```

#### 8. Запуск сервисов

```bash
# Включите и запустите сервисы
sudo systemctl daemon-reload
sudo systemctl enable insurance-system
sudo systemctl start insurance-system

# Настройте Nginx
sudo ln -s /etc/nginx/sites-available/insurance-system /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Проверьте статус
sudo systemctl status insurance-system
sudo systemctl status nginx
```

### Мониторинг и обслуживание

#### Логи
```bash
# Логи приложения
sudo journalctl -u insurance-system -f

# Логи Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Логи Django (если настроены)
tail -f /var/log/django/insurance_system.log
```

#### Резервное копирование
```bash
# Создайте скрипт резервного копирования
cat > /home/insurance/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/insurance_system"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Бэкап базы данных
cd /home/insurance/insurance-system
source venv/bin/activate
python manage.py dumpdata > $BACKUP_DIR/db_backup_$DATE.json

# Бэкап медиа файлов
tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz media/

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.json" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
EOF

chmod +x /home/insurance/backup.sh

# Добавьте в crontab (ежедневно в 2:00)
echo "0 2 * * * /home/insurance/backup.sh" | crontab -
```

#### Обновление системы
```bash
# Создайте скрипт обновления
cat > /home/insurance/update.sh << 'EOF'
#!/bin/bash
cd /home/insurance/insurance-system

# Создайте бэкап
/home/insurance/backup.sh

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

# Перезапустите сервис
sudo systemctl restart insurance-system
EOF

chmod +x /home/insurance/update.sh
```

### SSL/HTTPS настройка

Для настройки HTTPS используйте Let's Encrypt:

```bash
# Установите Certbot
sudo apt install certbot python3-certbot-nginx

# Получите сертификат
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление
sudo crontab -e
# Добавьте: 0 12 * * * /usr/bin/certbot renew --quiet
```

## Проверка системы

### Диагностика

```bash
# Проверка конфигурации Django
python manage.py check

# Проверка готовности к деплою
python manage.py check --deploy

# Проверка миграций
python manage.py showmigrations

# Проверка подключения к базе данных
python manage.py dbshell
```

## Устранение неполадок

### Общие проблемы

1. **Сервис не запускается**
```bash
sudo systemctl status insurance-system
sudo journalctl -u insurance-system -f
```

2. **База данных недоступна**
```bash
python manage.py dbshell
python manage.py check --database default
```

3. **Статические файлы не загружаются**
```bash
python manage.py collectstatic --clear --noinput
sudo chown -R insurance:www-data staticfiles/
```

4. **Проблемы с аутентификацией**
```bash
python manage.py setup_user_groups
python manage.py shell -c "from django.contrib.auth.models import Group; print([g.name for g in Group.objects.all()])"
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
```

## Загрузка демонстрационных данных

### Автоматическая загрузка

```bash
# Загрузите демонстрационные данные
python manage.py loaddata insurance_requests/fixtures/sample_data.json
```

### Ручное создание данных

```bash
# Создайте демонстрационные данные
python manage.py create_demo_data

# Или используйте Django shell
python manage.py shell
>>> from insurance_requests.models import InsuranceRequest
>>> from django.contrib.auth.models import User
>>> user = User.objects.first()
>>> InsuranceRequest.objects.create(
...     client_name="Демо клиент",
...     inn="1234567890",
...     insurance_type="КАСКО",
...     created_by=user
... )
```

### Демонстрационные пользователи

После загрузки sample_data.json доступны следующие пользователи:

- **Администратор**: 
  - Логин: `admin`
  - Пароль: `admin123`
  - Права: полный доступ ко всем функциям

- **Пользователь**: 
  - Логин: `user`
  - Пароль: `user123`
  - Права: доступ к основным функциям

### Демонстрационные заявки

Система включает 5 демонстрационных заявок с различными статусами:
1. Заявка с сгенерированным письмом (КАСКО)
2. Загруженная заявка (страхование спецтехники)
3. Отправленная заявка (КАСКО с C/E)
4. Завершенная заявка (страхование имущества)
5. Заявка с ошибкой (КАСКО с C/E)

## Автор

**Григорий Грачев**  
Система управления страховыми заявками / 2025

## Лицензия

Проект разработан для внутреннего корпоративного использования.
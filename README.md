# Система управления страховыми заявками

Корпоративный веб-сервис для автоматизации работы со страховыми заявками с современным интерфейсом и расширенными возможностями.

## Описание

Система предназначена для автоматизации процесса обработки страховых заявок:
- 📁 Загрузка и обработка Excel-заявок от клиентов
- 📝 Автоматическое извлечение данных из Excel (поддержка .xls, .xlsx и .xltx)
- 📧 Генерация содержимого писем по настраиваемым шаблонам (без отправки)
- 🔐 Система аутентификации и авторизации пользователей
- 🖥️ Современный веб-интерфейс для управления заявками
- 📊 Детальный просмотр и редактирование заявок
- 📈 Генерация сводных отчетов

## Возможности

### ✅ Реализовано
- 📁 Загрузка и обработка Excel файлов с заявками
- 📝 Автоматическое извлечение данных из Excel (поддержка .xls, .xlsx и .xltx)
- 📧 Генерация содержимого писем по расширенным шаблонам (с возможностью редактирования)
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
- ❓ Интегрированная система справочной документации
- 📋 Справочная страница для модуля сводов
- 🔄 Обновленная документация по обработке Excel файлов
- 🐳 Контейнеризация Docker

### 🚧 В разработке
- 📈 Генерация Excel отчетов

## Технологии

- **Backend**: Django 4.2, Python 3.9+
- **Frontend**: Bootstrap 5, HTML5, CSS3, JavaScript
- **База данных**: SQLite (готовность к PostgreSQL)
- **Обработка Excel**: pandas, openpyxl
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
│   └── templates.py        # Генерация содержимого писем
├── insurance_requests/      # Django-приложение "Заявки"
│   ├── models.py           # Модели данных
│   ├── views.py            # Представления
│   ├── forms.py            # Формы
│   └── templates/          # HTML шаблоны
├── summaries/              # Django-приложение "Сводки"
├── nginx-timeweb/          # Конфигурация Nginx для HTTPS
│   ├── default.conf        # HTTPS конфигурация (активная)
│   └── default-acme.conf   # ACME challenge / fallback конфигурация
├── scripts/                # Скрипты управления
│   ├── ssl/               # Скрипты управления SSL
│   └── monitoring/        # Скрипты мониторинга
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

### 2. Генерация содержимого письма
1. Откройте детали заявки
2. Нажмите "Сгенерировать письмо"
3. Система создаст содержимое письма по шаблону
4. При необходимости отредактируйте текст и сохраните

### 3. Использование справочной системы
1. **Справка по заявкам**: На странице загрузки Excel файлов доступна актуальная информация о структуре файлов
2. **Справка по сводам**: В модуле сводов нажмите "Справка" для получения информации о:
   - Загрузке ответов страховых компаний
   - Выгрузке сводов в Excel
   - Рабочем процессе и статусах
   - Примерах и решении типичных проблем

### 4. Формат Excel файла
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
- **F34 + D32/33/34/35**: Если F34 пустая И D32/33/34/35 пустая → есть рассрочка; если F34 не пустая ИЛИ D32/33/34/35 не пустая → НЕТ рассрочки (для ИП: F35 + D33/34/35/36)
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



### Настройка для разных сред

#### Разработка
- Используйте SQLite базу данных
- DEBUG=True
- Минимальные настройки безопасности

#### Staging
- Используйте отдельную базу данных
- DEBUG=False
- Базовые настройки безопасности

#### Продакшен
- Используйте PostgreSQL
- DEBUG=False
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



### Структура данных

#### Основные модели
- `InsuranceRequest` - основная модель заявки
  - Поддержка всех типов страхования
  - Отдельные поля для дат начала и окончания
  - Поддержка КАСКО категории C/E
  - Связь с пользователем-создателем
  - Поля для хранения сгенерированного содержимого писем
- `RequestAttachment` - вложения к заявке

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

### Docker развертывание (рекомендуется)

#### Быстрый старт с Docker

1. **Подготовка окружения**
```bash
# Клонируйте репозиторий
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# Настройте переменные окружения
cp .env.example .env
# Отредактируйте .env для продакшена
```

2. **Запуск сервисов**
```bash
# Соберите и запустите контейнеры
docker compose up -d

# Проверьте статус сервисов
docker compose ps

# Проверьте здоровье сервисов
./check-services.sh
```

3. **Первоначальная настройка**
```bash
# Создайте суперпользователя
docker compose exec web python manage.py createsuperuser

# Настройте группы пользователей
docker compose exec web python manage.py setup_user_groups
```

#### Структура Docker сервисов

- **db** - PostgreSQL база данных
- **web** - Django приложение с Gunicorn
- **nginx** - Веб-сервер и прокси

#### Мониторинг Docker сервисов

```bash
# Просмотр логов
docker compose logs -f web
docker compose logs -f nginx
docker compose logs -f db

# Проверка здоровья
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Выполнение команд в контейнере
docker compose exec web python manage.py shell
docker compose exec web python manage.py migrate
```

#### Обновление Docker деплоя

```bash
# Остановите сервисы
docker compose down

# Обновите код
git pull origin main

# Пересоберите и запустите
docker compose up -d --build

# Примените миграции
docker compose exec web python manage.py migrate
```

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
sudo apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib

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

## Документация

### Руководства по развертыванию

- **[docs/SSL_CERTIFICATES_GUIDE.md](docs/SSL_CERTIFICATES_GUIDE.md)** - Руководство по управлению SSL сертификатами
- **[docs/HTTPS_TROUBLESHOOTING_GUIDE.md](docs/HTTPS_TROUBLESHOOTING_GUIDE.md)** - Устранение проблем с HTTPS
- **[docs/MONITORING_SYSTEM.md](docs/MONITORING_SYSTEM.md)** - Система мониторинга
- **[docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)** - Структура проекта

### Дополнительная документация

- **[docs/USER_MANUAL.md](docs/USER_MANUAL.md)** - Руководство пользователя ([HTML](docs/USER_MANUAL.html) | [PDF](docs/USER_MANUAL.pdf))
- **[docs/HELP_SYSTEM_DEVELOPER_GUIDE.md](docs/HELP_SYSTEM_DEVELOPER_GUIDE.md)** - Руководство разработчика: Система справочной документации
- **[EXCEL_PROCESSING.md](EXCEL_PROCESSING.md)** - Обработка Excel файлов

### Структура документации

```
docs/
├── USER_MANUAL.md                     # Руководство пользователя (Markdown)
├── USER_MANUAL.html                   # Руководство пользователя (HTML)
├── USER_MANUAL.pdf                    # Руководство пользователя (PDF)
├── HELP_SYSTEM_DEVELOPER_GUIDE.md     # Руководство разработчика: Система справки
├── SSL_CERTIFICATES_GUIDE.md          # Управление SSL сертификатами
├── HTTPS_TROUBLESHOOTING_GUIDE.md     # Устранение проблем с HTTPS
├── MONITORING_SYSTEM.md               # Система мониторинга
└── PROJECT_STRUCTURE.md               # Структура проекта
```

## 🚀 Развертывание в продакшене (Timeweb HTTPS)

Проект развертывается на хостинге **Timeweb** с поддержкой HTTPS и автоматическими SSL сертификатами.

### Характеристики развертывания

- **Протокол**: HTTPS с SSL
- **Домены**: insflow.ru, insflow.tw1.su, zs.insflow.ru, zs.insflow.tw1.su
- **SSL сертификаты**: Let's Encrypt (автоматическое обновление)
- **Конфигурация**: Автоматическое определение SSL
- **Мониторинг**: Расширенный с SSL мониторингом
- **Резервное копирование**: HTTP/HTTPS автопереключение

### Быстрое развертывание

```bash
# Клонирование и настройка
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# Настройка окружения
cp .env.example .env
nano .env  # Настройте домены и SSL

# Развертывание
docker compose up -d

# Проверка HTTPS
curl -f https://insflow.ru/healthz/
```

### Конфигурационные файлы

- `docker-compose.yml` - HTTPS конфигурация с SSL
- `nginx-timeweb/default.conf` - HTTPS конфигурация Nginx (активная)
- `nginx-timeweb/default-acme.conf` - ACME challenge / fallback конфигурация
- `.env.example` - Пример переменных окружения с SSL настройками
- `scripts/ssl/` - Скрипты управления SSL сертификатами

### Управление SSL сертификатами

```bash
# Получение сертификатов
./scripts/ssl/obtain-certificates.sh

# Мониторинг сертификатов
./scripts/ssl/monitor-ssl-status.sh

# Настройка автообновления
./scripts/ssl/ssl-cron-setup.sh

# Проверка сертификатов
./scripts/ssl/check-certificates.sh
```

### Локальная разработка

```bash
# Запуск в режиме разработки
docker compose up --build

# В фоновом режиме
docker compose up -d

# Просмотр логов
docker compose logs -f
```

### Мониторинг и обслуживание

```bash
# Просмотр логов всех сервисов
docker compose logs -f

# Проверка статуса
docker compose ps

# Обновление
docker compose pull && docker compose up -d

# Проверка HTTPS доступности
curl -f https://insflow.ru/healthz/

# Мониторинг SSL сертификатов
./scripts/ssl/monitor-ssl-status.sh --alert

# Системный мониторинг
python scripts/monitoring-dashboard.py
```

### Общие проблемы и решения

#### Проблема: Сервисы не запускаются
```bash
# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs service-name

# Перезапуск
docker compose restart
```

#### Проблема: База данных недоступна
```bash
# Проверка подключения
docker compose exec web python manage.py dbshell

# Перезапуск базы данных
docker compose restart db
```

#### Проблема: Статические файлы не загружаются
```bash
# Сбор статических файлов
docker compose exec web python manage.py collectstatic --noinput

# Перезапуск nginx
docker compose restart nginx
```

#### Проблема: SSL сертификаты
```bash
# Проверка сертификатов
./scripts/ssl/check-certificates.sh

# Принудительное обновление
./scripts/ssl/obtain-certificates.sh --force-renewal

# Просмотр логов SSL
docker compose logs certbot
```

## Автор

**Григорий Грачев**  
Система управления страховыми заявками / 2025

## Лицензия

Проект разработан для внутреннего корпоративного использования.
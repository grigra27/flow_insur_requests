# Развертывание улучшений системы управления страховыми заявками

## Обзор новых функций

Данное обновление включает следующие улучшения:

### 🆕 Новый тип страхования
- Добавлен тип "страхование имущества"
- Автоматическое определение типа при загрузке Excel файлов
- Поддержка в формах и шаблонах писем

### 📧 Улучшенные шаблоны писем
- Расширенные описания типов страхования:
  - **КАСКО**: "страхование каско по условиям клиента"
  - **Спецтехника**: "спецтезника под клиента"
  - **Имущество**: "клиентское имузество"
  - **Другое**: "разная другая фигня"

### 📅 Отдельные поля дат страхования
- Раздельные поля для даты начала и окончания страхования
- Улучшенная валидация дат
- Автоматическое форматирование в письмах: "с ДД.ММ.ГГГГ по ДД.ММ.ГГГГ"

### 🔐 Система аутентификации
- Ролевая модель с двумя типами пользователей
- Защита всех страниц системы
- Современный интерфейс входа

### 👥 Типы пользователей
- **Администратор** (`admin`/`admin123`): полный доступ
- **Пользователь** (`user`/`user123`): доступ к основным функциям

## Быстрое развертывание

### Автоматическое развертывание
```bash
# Клонируйте репозиторий (если еще не сделано)
git clone <repository-url>
cd onlineservice

# Запустите скрипт автоматического развертывания
./scripts/deploy.sh
```

### Ручное развертывание
```bash
# 1. Активируйте виртуальное окружение
source venv/bin/activate

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Запустите миграцию базы данных
python scripts/migrate_database.py

# 4. Соберите статические файлы
python manage.py collectstatic --noinput

# 5. Запустите тесты
python manage.py test insurance_requests

# 6. Запустите сервер
python manage.py runserver
```

## Подробные инструкции

### Предварительные требования
- Python 3.8+
- Django 4.2+
- Виртуальное окружение
- База данных (SQLite для разработки, PostgreSQL для продакшена)

### Структура файлов развертывания
```
scripts/
├── deploy.sh              # Основной скрипт развертывания
├── migrate_database.py     # Скрипт миграции базы данных
docs/
├── AUTHENTICATION_SYSTEM.md    # Руководство по аутентификации
├── DEPLOYMENT_INSTRUCTIONS.md  # Подробные инструкции
└── README_DEPLOYMENT.md        # Этот файл
```

### Процесс развертывания

#### Шаг 1: Подготовка
```bash
# Создайте резервную копию (автоматически в скрипте)
python manage.py dumpdata > backup_$(date +%Y%m%d).json

# Обновите код
git pull origin main
```

#### Шаг 2: Миграция базы данных
```bash
# Запустите кастомный скрипт миграции
python scripts/migrate_database.py
```

Скрипт выполнит:
- Применение Django миграций
- Создание групп пользователей и разрешений
- Миграцию существующих данных периодов страхования
- Обновление типов страхования
- Валидацию результатов

#### Шаг 3: Настройка статических файлов
```bash
python manage.py collectstatic --noinput
```

#### Шаг 4: Тестирование
```bash
# Запуск всех тестов новых функций
python manage.py test insurance_requests.test_authentication_system
python manage.py test insurance_requests.test_login_interface
python manage.py test insurance_requests.test_form_enhancements
python manage.py test insurance_requests.test_enhanced_email_templates
python manage.py test insurance_requests.test_new_insurance_type
python manage.py test insurance_requests.test_end_to_end_workflow
python manage.py test insurance_requests.test_performance_and_security
```

## Проверка развертывания

### 1. Проверка аутентификации
```bash
# Откройте браузер и перейдите на главную страницу
# Должно перенаправить на /login/

# Войдите с учетными данными:
# Администратор: admin / admin123
# Пользователь: user / user123
```

### 2. Проверка новых функций

#### Новый тип страхования
1. Создайте новую заявку
2. Выберите тип "Страхование имущества"
3. Сохраните и проверьте отображение

#### Отдельные поля дат
1. Откройте форму редактирования заявки
2. Найдите поля "Дата начала страхования" и "Дата окончания страхования"
3. Введите даты и сохраните
4. Проверьте форматирование в письме

#### Улучшенные письма
1. Откройте детали заявки
2. Нажмите "Предварительный просмотр письма"
3. Проверьте расширенные описания типов страхования
4. Проверьте новый формат дат

### 3. Проверка безопасности
```bash
# Выйдите из системы
# Попробуйте получить доступ к защищенным страницам
# Должно перенаправлять на страницу входа
```

## Откат изменений

### Автоматический откат
Если скрипт развертывания завершился с ошибкой, он автоматически выполнит откат.

### Ручной откат
```bash
# 1. Восстановите базу данных из резервной копии
python manage.py flush --noinput
python manage.py loaddata backup_YYYYMMDD.json

# 2. Откатите код к предыдущей версии
git checkout previous_stable_commit

# 3. Перезапустите сервисы
sudo systemctl restart gunicorn nginx
```

## Мониторинг после развертывания

### Логи для проверки
```bash
# Логи Django
tail -f /var/log/django/insurance_system.log

# Логи аутентификации
tail -f /var/log/django/auth.log

# Логи веб-сервера
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### Метрики для мониторинга
- Время отклика страниц
- Количество успешных/неуспешных входов
- Использование памяти и CPU
- Количество активных сессий

## Устранение неполадок

### Проблема: Миграции не применяются
```bash
# Проверьте статус миграций
python manage.py showmigrations

# Примените миграции вручную
python manage.py migrate insurance_requests
```

### Проблема: Группы пользователей не созданы
```bash
# Запустите команду создания групп
python manage.py setup_user_groups
```

### Проблема: Статические файлы не загружаются
```bash
# Проверьте настройки STATIC_ROOT в settings.py
# Соберите статические файлы заново
python manage.py collectstatic --clear --noinput
```

### Проблема: Ошибки аутентификации
```bash
# Проверьте middleware в settings.py
# Убедитесь, что AuthenticationMiddleware добавлен

# Проверьте URL конфигурацию
python manage.py show_urls | grep login
```

### Проблема: Тесты не проходят
```bash
# Запустите тесты с подробным выводом
python manage.py test insurance_requests --verbosity=2

# Проверьте конкретный тест
python manage.py test insurance_requests.test_authentication_system.UserGroupCreationTests.test_setup_user_groups_command_creates_groups
```

## Производительность

### Рекомендации по оптимизации
1. **База данных**: Используйте PostgreSQL в продакшене
2. **Кэширование**: Настройте Redis для кэширования сессий
3. **Статические файлы**: Используйте CDN для статических файлов
4. **Мониторинг**: Настройте APM (New Relic, DataDog)

### Настройка для высокой нагрузки
```python
# settings.py для продакшена
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

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

## Безопасность

### Настройки безопасности для продакшена
```python
# settings.py
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

### Регулярные задачи безопасности
1. Обновление зависимостей: `pip list --outdated`
2. Проверка уязвимостей: `safety check`
3. Аудит безопасности: `python manage.py check --deploy`
4. Мониторинг логов аутентификации

## Поддержка

### Контакты
- Техническая поддержка: [email]
- Документация: `/docs/`
- Репозиторий: [repository-url]

### Полезные команды
```bash
# Проверка состояния системы
python manage.py check --deploy

# Информация о пользователях
python manage.py shell -c "from django.contrib.auth.models import User; print(f'Пользователей: {User.objects.count()}')"

# Информация о заявках
python manage.py shell -c "from insurance_requests.models import InsuranceRequest; print(f'Заявок: {InsuranceRequest.objects.count()}')"

# Очистка сессий
python manage.py clearsessions
```

---

**Важно**: После развертывания обязательно протестируйте все новые функции и убедитесь, что система работает корректно перед переводом в продакшен.
# Развертывание системы управления страховыми заявками - Полное руководство

## 🚀 Быстрый старт

### Автоматическое развертывание (рекомендуется)
```bash
# 1. Клонируйте репозиторий
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# 2. Настройте пути в скрипте развертывания
nano scripts/deploy.sh
# Обновите PROJECT_DIR и VENV_DIR

# 3. Запустите автоматическое развертывание
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### Ручное развертывание
```bash
# 1. Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Настройте базу данных
cp .env.example .env
# Отредактируйте .env под ваши настройки

# 4. Запустите миграцию
python scripts/enhanced_migrate_database.py

# 5. Соберите статические файлы
python manage.py collectstatic --noinput

# 6. Запустите тесты
python manage.py test insurance_requests

# 7. Запустите сервер
python manage.py runserver
```

## 📋 Что включает это обновление

### 🔐 Система аутентификации
- **Ролевая модель**: Администраторы и обычные пользователи
- **Защита всех страниц**: Автоматическое перенаправление на вход
- **Современный интерфейс**: Красивая страница входа в систему
- **Безопасность**: Хеширование паролей, защита от CSRF

**Учетные записи по умолчанию:**
- Администратор: `admin` / `admin123`
- Пользователь: `user` / `user123`

### 🏢 Новый тип страхования
- **"Страхование имущества"**: Добавлен как отдельный тип
- **Автоматическое определение**: При загрузке Excel файлов
- **Полная интеграция**: В формах, письмах и отчетах

### 📧 Улучшенные шаблоны писем
Расширенные описания типов страхования:
- **КАСКО** → "страхование каско по условиям клиента"
- **Спецтехника** → "спецтезника под клиента"
- **Имущество** → "клиентское имузество"
- **Другое** → "разная другая фигня"

### 📅 Отдельные поля дат
- **Дата начала страхования**: Отдельное поле с валидацией
- **Дата окончания страхования**: Отдельное поле с валидацией
- **Новый формат в письмах**: "с ДД.ММ.ГГГГ по ДД.ММ.ГГГГ"
- **Автоматическая миграция**: Существующие данные мигрируются автоматически

## 📁 Структура документации

```
docs/
├── AUTHENTICATION_SYSTEM.md      # Руководство пользователя по аутентификации
├── DEPLOYMENT_INSTRUCTIONS.md    # Подробные инструкции по развертыванию
├── DEPLOYMENT_GUIDE_COMPLETE.md  # Полное руководство по развертыванию
├── DEPLOYMENT_CHECKLIST.md       # Контрольный список развертывания
├── DEPLOYMENT_README.md          # Этот файл - краткое руководство
└── README_DEPLOYMENT.md          # Существующее руководство по развертыванию

scripts/
├── deploy.sh                     # Основной скрипт автоматического развертывания
├── migrate_database.py           # Базовый скрипт миграции
└── enhanced_migrate_database.py  # Расширенный скрипт миграции с детальным логированием
```

## 🔧 Выбор метода развертывания

### Автоматическое развертывание
**Используйте если:**
- Развертываете на новом сервере
- Хотите минимизировать ручные операции
- Нужна автоматическая проверка и откат при ошибках

**Команда:**
```bash
./scripts/deploy.sh
```

### Ручное развертывание
**Используйте если:**
- Нужен полный контроль над процессом
- Развертываете в специфической среде
- Хотите понимать каждый шаг

**Следуйте:** [DEPLOYMENT_GUIDE_COMPLETE.md](DEPLOYMENT_GUIDE_COMPLETE.md)

### Миграция базы данных

#### Базовая миграция
```bash
python scripts/migrate_database.py
```

#### Расширенная миграция (рекомендуется)
```bash
python scripts/enhanced_migrate_database.py
```

**Расширенная миграция включает:**
- Детальное логирование всех операций
- Автоматическое создание резервных копий
- Комплексную валидацию результатов
- Генерацию подробного отчета
- Улучшенную обработку ошибок

## ✅ Проверка развертывания

### 1. Быстрая проверка
```bash
# Проверьте статус Django
python manage.py check --deploy

# Проверьте подключение к базе данных
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('DB OK')"

# Проверьте аутентификацию
python manage.py shell -c "from django.contrib.auth.models import User; print(f'Users: {User.objects.count()}')"
```

### 2. Веб-интерфейс
1. Откройте браузер и перейдите на главную страницу
2. Убедитесь, что вас перенаправляет на `/login/`
3. Войдите с учетными данными `admin`/`admin123`
4. Проверьте доступ к основным функциям

### 3. Новые функции
- [ ] Создайте заявку с типом "Страхование имущества"
- [ ] Отредактируйте даты страхования в форме
- [ ] Сгенерируйте письмо и проверьте расширенные описания
- [ ] Проверьте новый формат дат в письмах

## 🧪 Тестирование

### Запуск всех тестов
```bash
python manage.py test insurance_requests --verbosity=2
```

### Тестирование конкретных функций
```bash
# Аутентификация
python manage.py test insurance_requests.test_authentication_system

# Интерфейс входа
python manage.py test insurance_requests.test_login_interface

# Улучшения форм
python manage.py test insurance_requests.test_form_enhancements

# Улучшенные письма
python manage.py test insurance_requests.test_enhanced_email_templates

# Новый тип страхования
python manage.py test insurance_requests.test_new_insurance_type

# End-to-end тесты
python manage.py test insurance_requests.test_end_to_end_workflow
```

## 🚨 Устранение неполадок

### Частые проблемы

#### Проблема: Миграции не применяются
```bash
# Проверьте статус миграций
python manage.py showmigrations

# Примените миграции вручную
python manage.py migrate insurance_requests
```

#### Проблема: Группы пользователей не созданы
```bash
# Запустите команду создания групп
python manage.py setup_user_groups
```

#### Проблема: Не работает аутентификация
```bash
# Проверьте middleware в settings.py
grep -n "AuthenticationMiddleware" onlineservice/settings.py

# Проверьте URL конфигурацию
python manage.py show_urls | grep login
```

#### Проблема: Статические файлы не загружаются
```bash
# Пересоберите статические файлы
python manage.py collectstatic --clear --noinput

# Проверьте права доступа
ls -la staticfiles/
```

### Получение помощи

1. **Проверьте логи**: `tail -f logs/django.log`
2. **Запустите диагностику**: `python manage.py check --deploy`
3. **Обратитесь к документации**: См. файлы в папке `docs/`
4. **Свяжитесь с поддержкой**: support@insurance-system.com

## 🔄 Откат изменений

### Автоматический откат
Если скрипт развертывания завершился с ошибкой, он автоматически выполнит откат.

### Ручной откат
```bash
# 1. Найдите последний бэкап
ls -la backups/

# 2. Восстановите базу данных
python manage.py flush --noinput
python manage.py loaddata backups/backup_YYYYMMDD_HHMMSS.json

# 3. Откатите код
git checkout previous_stable_commit

# 4. Перезапустите сервисы
sudo systemctl restart gunicorn nginx
```

## 📊 Мониторинг

### Логи для отслеживания
```bash
# Логи Django
tail -f /var/log/django/insurance_system.log

# Логи аутентификации
tail -f /var/log/django/auth.log

# Логи веб-сервера
tail -f /var/log/nginx/access.log
```

### Ключевые метрики
- Время отклика страниц
- Количество успешных/неуспешных входов
- Использование памяти и CPU
- Количество активных сессий

## 🔒 Безопасность

### Рекомендации для продакшена
1. **Смените пароли по умолчанию** для пользователей admin и user
2. **Настройте SSL** для защищенного соединения
3. **Обновите SECRET_KEY** в настройках Django
4. **Настройте файрвол** для ограничения доступа
5. **Регулярно обновляйте** зависимости

### Настройки безопасности
```python
# В settings.py для продакшена
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
```

## 📈 Производительность

### Оптимизация для продакшена
1. **Используйте PostgreSQL** вместо SQLite
2. **Настройте Redis** для кэширования сессий
3. **Используйте CDN** для статических файлов
4. **Настройте Gunicorn** с оптимальным количеством воркеров

### Мониторинг производительности
- **Django Debug Toolbar** (только для разработки)
- **Sentry** для отслеживания ошибок
- **New Relic** или **DataDog** для APM

## 📞 Поддержка

### Контакты
- **Техническая поддержка**: support@insurance-system.com
- **Документация**: См. папку `docs/`
- **Репозиторий**: https://github.com/your-repo/insurance-system

### Полезные команды
```bash
# Информация о системе
python manage.py check --deploy

# Статистика пользователей
python manage.py shell -c "from django.contrib.auth.models import User; print(f'Пользователей: {User.objects.count()}')"

# Статистика заявок
python manage.py shell -c "from insurance_requests.models import InsuranceRequest; print(f'Заявок: {InsuranceRequest.objects.count()}')"

# Очистка сессий
python manage.py clearsessions
```

---

## 🎯 Заключение

Данное обновление значительно улучшает функциональность и безопасность системы управления страховыми заявками. Следуйте инструкциям последовательно и не пропускайте этапы тестирования.

**Успешного развертывания! 🚀**

---

**Версия документа**: 1.0  
**Дата создания**: $(date +%d.%m.%Y)  
**Статус**: Актуальная
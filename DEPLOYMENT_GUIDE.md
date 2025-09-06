# Руководство по деплою Insurance System

Это руководство поможет вам настроить автоматический деплой Django-приложения на Digital Ocean с использованием Docker и GitHub Actions.

## 🏗️ Архитектура деплоя

### Компоненты системы
- **Django приложение** - основное веб-приложение
- **PostgreSQL** - база данных
- **Redis** - брокер сообщений для Celery
- **Celery** - фоновые задачи
- **Nginx** - веб-сервер и прокси
- **Docker** - контейнеризация
- **GitHub Actions** - CI/CD

### Окружения
- **Development** - локальная разработка
- **Staging** - тестовое окружение (ветка `develop`)
- **Production** - продакшн окружение (ветка `main`)

## 🚀 Быстрый старт

### 1. Локальная разработка

```bash
# Клонируйте репозиторий
git clone <your-repo-url>
cd insurance-system

# Запустите скрипт настройки
./scripts/local-dev.sh

# Или используйте Docker
docker-compose up -d
```

### 2. Настройка сервера Digital Ocean

```bash
# На сервере (под root)
curl -sSL https://raw.githubusercontent.com/grigra27/flow_insur_requests/main/scripts/setup-server.sh | bash
```

### 3. Настройка GitHub Secrets

В настройках репозитория GitHub добавьте следующие секреты:

#### Production секреты
```
DO_HOST=your-server-ip
DO_USERNAME=deploy
DO_SSH_KEY=your-private-ssh-key
DO_PORT=22
DO_PASSPHRASE=passphrase
SECRET_KEY=your-django-secret-key
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure-database-password
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
SLACK_WEBHOOK_URL=your-slack-webhook-url (optional)
```

#### Staging секреты
```
STAGING_HOST=your-staging-server-ip
STAGING_USERNAME=deploy
STAGING_SSH_KEY=your-staging-private-ssh-key
STAGING_PORT=22
STAGING_SECRET_KEY=staging-secret-key
STAGING_DB_PASSWORD=staging-db-password
STAGING_ALLOWED_HOSTS=staging.your-domain.com
STAGING_URL=https://staging.your-domain.com
```

## 📋 Детальная настройка

### Настройка сервера Digital Ocean

#### 1. Создание дроплета
- Выберите Ubuntu 22.04 LTS
- Минимум 2GB RAM, 1 CPU
- Добавьте SSH ключ

#### 2. Первоначальная настройка
```bash
# Подключитесь к серверу
ssh root@your-server-ip

# Запустите скрипт настройки
curl -sSL https://raw.githubusercontent.com/grigra27/flow_insur_requests/main/scripts/setup-server.sh | bash

# Добавьте ваш SSH ключ
echo "your-public-ssh-key" >> /home/deploy/.ssh/authorized_keys
```

#### 3. Клонирование репозитория
```bash
# Переключитесь на пользователя deploy
su - deploy

# Клонируйте репозиторий
cd /opt
git clone https://github.com/grigra27/flow_insur_requests.git
cd flow_insur_requests

# Создайте файл с переменными окружения
cp .env.example .env.prod
# Отредактируйте .env.prod с продакшн настройками
```

#### 4. Настройка SSL
```bash
# После настройки DNS записей
sudo /opt/setup-ssl.sh your-domain.com
```

### Настройка GitHub Actions

#### 1. Структура workflow
- `.github/workflows/deploy.yml` - деплой в продакшн
- `.github/workflows/staging.yml` - деплой в staging

#### 2. Процесс деплоя
1. **Сборка** - создание Docker образа
2. **Деплой** - развертывание на сервере
3. **Проверка** - health check
4. **Откат** - при неудаче

### Конфигурация Docker

#### Dockerfile особенности
- **Многоэтапная сборка**: оптимизация размера образа
- **Entrypoint скрипт**: автоматические миграции и настройка
- **Статические файлы**: собираются во время сборки с временными переменными
- **Пользователь app**: безопасность контейнера
- **Health checks**: проверка работоспособности

#### Сборка образа
```bash
# Локальная сборка
./build.sh

# Или вручную
docker build -t flow-insur-requests .

# Проверка образа
docker run --rm -p 8000:8000 --env-file .env flow-insur-requests
```

#### Production (docker-compose.prod.yml)
- PostgreSQL с persistent storage
- Redis для Celery
- Nginx с SSL
- Health checks
- Restart policies
- Автоматическое создание суперпользователя

#### Staging (docker-compose.staging.yml)
- Отдельная база данных
- Порт 8001
- Демо данные
- Консольный email backend

#### Development (docker-compose.yml)
- SQLite или PostgreSQL
- Без SSL
- Debug режим
- Volume mounts для разработки

## 🔄 Процессы деплоя

### Автоматический деплой

#### Production
```bash
# Пуш в main ветку запускает деплой
git checkout main
git merge develop
git push origin main
```

#### Staging
```bash
# Пуш в develop ветку запускает staging деплой
git checkout develop
git push origin develop
```

### Ручной деплой

#### Production
```bash
# На сервере
cd /opt/insurance-system
./scripts/deploy.sh production
```

#### Staging
```bash
# На сервере
cd /opt/insurance-system-staging
./scripts/deploy.sh staging
```

### Откат

#### Быстрый откат
```bash
# На сервере
cd /opt/insurance-system
./scripts/rollback.sh production
```

#### Откат через GitHub Actions
```bash
# Локально - откат коммита и пуш
git revert HEAD
git push origin main
```

## 🔍 Мониторинг и логи

### Проверка статуса
```bash
# Статус сервисов
docker-compose -f docker-compose.prod.yml ps

# Логи приложения
docker-compose -f docker-compose.prod.yml logs -f web

# Системные логи
journalctl -u insurance-system -f

# Мониторинг
/opt/insurance-system/monitor.sh
```

### Health checks
- **Application**: `https://your-domain.com/health/`
- **Database**: автоматическая проверка в Docker
- **Redis**: автоматическая проверка в Docker

### Логи
- **Application**: `/opt/insurance-system/logs/`
- **Nginx**: `/var/log/nginx/`
- **System**: `journalctl -u insurance-system`

## 🔒 Безопасность

### Настройки сервера
- Firewall (UFW) - только порты 22, 80, 443
- Fail2ban - защита от брутфорса
- SSH ключи - отключен пароль
- Автоматические обновления безопасности

### Настройки приложения
- HTTPS обязательно
- Secure cookies
- HSTS headers
- XSS protection
- CSRF protection

### Секреты
- GitHub Secrets для CI/CD
- Environment variables в Docker
- Никаких секретов в коде

## 📊 Бэкапы

### Автоматические бэкапы
- **Расписание**: ежедневно в 2:00 AM
- **Хранение**: 30 дней
- **Локация**: `/backups/insurance-system/`

### Ручной бэкап
```bash
# Создание бэкапа
docker-compose -f docker-compose.prod.yml exec web python manage.py dumpdata > backup_$(date +%Y%m%d_%H%M%S).json

# Восстановление
docker-compose -f docker-compose.prod.yml exec web python manage.py loaddata backup_file.json
```

## 🛠️ Устранение неполадок

### Частые проблемы

#### 1. Сервис не запускается
```bash
# Проверить логи
docker-compose -f docker-compose.prod.yml logs web

# Проверить конфигурацию
docker-compose -f docker-compose.prod.yml config

# Перезапустить сервисы
docker-compose -f docker-compose.prod.yml restart
```

#### 2. База данных недоступна
```bash
# Проверить статус PostgreSQL
docker-compose -f docker-compose.prod.yml exec db pg_isready

# Подключиться к базе
docker-compose -f docker-compose.prod.yml exec db psql -U insurance_user -d insurance_db
```

#### 3. SSL проблемы
```bash
# Проверить сертификат
openssl x509 -in /etc/letsencrypt/live/your-domain.com/cert.pem -text -noout

# Обновить сертификат
certbot renew --dry-run
```

#### 4. Проблемы с памятью
```bash
# Проверить использование памяти
free -h
docker stats

# Очистить неиспользуемые образы
docker system prune -a
```

### Диагностические команды
```bash
# Общая диагностика
/opt/insurance-system/monitor.sh

# Проверка конфигурации Django
docker-compose -f docker-compose.prod.yml exec web python manage.py check --deploy

# Проверка миграций
docker-compose -f docker-compose.prod.yml exec web python manage.py showmigrations

# Подключение к базе данных
docker-compose -f docker-compose.prod.yml exec web python manage.py dbshell
```

## 📈 Масштабирование

### Горизонтальное масштабирование
```yaml
# В docker-compose.prod.yml
web:
  deploy:
    replicas: 3
  
# Добавить load balancer
nginx:
  # Конфигурация upstream с несколькими серверами
```

### Вертикальное масштабирование
```yaml
# Увеличить ресурсы контейнеров
web:
  deploy:
    resources:
      limits:
        memory: 2G
        cpus: '1.0'
```

### Оптимизация производительности
- Настройка Gunicorn workers
- Redis для кэширования
- CDN для статических файлов
- Database connection pooling

## 🔄 Обновления

### Обновление зависимостей
```bash
# Локально
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt

# Проверка конфигурации
python manage.py check

# Коммит и пуш
git add requirements.txt
git commit -m "Update dependencies"
git push
```

### Обновление Django
```bash
# Проверить совместимость
python -m django --version

# Обновить в requirements.txt
# Проверить локально
# Деплой через staging
```

## 📞 Поддержка

### Контакты
- **Разработчик**: Григорий Грачев

### Документация
- **API**: `/api/docs/`
- **Admin**: `/admin/`
- **Health**: `/health/`

### Полезные ссылки
- [Django Deployment Checklist](https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/)
- [Docker Best Practices](https://docs.docker.com/develop/best-practices/)
- [Digital Ocean Tutorials](https://www.digitalocean.com/community/tutorials)

---

**Примечание**: Это руководство предполагает базовые знания Django, Docker и Linux. Для продакшн использования рекомендуется дополнительная настройка мониторинга, логирования и резервного копирования.
# Руководство по деплою

Простой деплой Django-приложения на Digital Ocean через GitHub Actions.

## 🏗️ Архитектура

- **Django** - веб-приложение
- **PostgreSQL** - база данных  
- **Redis** - кэш и очереди
- **Docker** - контейнеризация
- **GitHub Actions** - автодеплой

## 🚀 Быстрый старт

### 1. Настройка GitHub Secrets

В настройках репозитория добавьте секреты:

```
DO_HOST=your-server-ip
DO_USERNAME=deploy  
DO_SSH_KEY=your-private-ssh-key
DO_PORT=22
SECRET_KEY=your-django-secret-key
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure-database-password
ALLOWED_HOSTS=your-domain.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

### 2. Настройка сервера

```bash
# На сервере создайте директорию и клонируйте репозиторий
mkdir -p /opt/insurance-system
cd /opt/insurance-system
git clone https://github.com/grigra27/flow_insur_requests.git .
```

### 3. Деплой

Просто пушьте в main ветку - деплой произойдет автоматически:

```bash
git push origin main
```

## 🔧 Команды на сервере

```bash
# Проверить статус
docker-compose ps

# Посмотреть логи
docker-compose logs -f web

# Перезапустить
docker-compose restart

# Обновить вручную
git pull origin main
docker-compose down
docker-compose up -d
```

## 📝 Структура проекта

- `Dockerfile` - образ приложения
- `docker-compose.yml` - сервисы (web, db, redis)
- `entrypoint.sh` - скрипт запуска
- `.github/workflows/deploy.yml` - автодеплой
- `.env.example` - пример переменных окружения
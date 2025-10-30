# Руководство по деплою

Деплой Django-приложения на два хостинга через GitHub Actions:
- **Digital Ocean** - домен onbr.site
- **Timeweb** - домен zs.insflow.tw1.su

## 🏗️ Архитектура

- **Django** - веб-приложение
- **PostgreSQL** - база данных  
- **Docker** - контейнеризация
- **GitHub Actions** - автодеплой

## 🚀 Быстрый старт

### 1. Настройка GitHub Secrets

В настройках репозитория добавьте секреты для Digital Ocean:

```
DO_HOST=your-server-ip
DO_USERNAME=deploy  
DO_SSH_KEY=your-private-ssh-key
DO_PORT=22
SECRET_KEY=your-django-secret-key
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure-database-password
ALLOWED_HOSTS=onbr.site,64.227.75.233
```

И секреты для Timeweb:

```
TIMEWEB_HOST=your-timeweb-server-ip
TIMEWEB_USERNAME=deploy  
TIMEWEB_SSH_KEY=your-timeweb-private-ssh-key
TIMEWEB_PORT=22
TIMEWEB_SECRET_KEY=your-timeweb-django-secret-key
TIMEWEB_DB_NAME=insflow_db
TIMEWEB_DB_USER=insflow_user
TIMEWEB_DB_PASSWORD=secure-timeweb-database-password
TIMEWEB_ALLOWED_HOSTS=zs.insflow.tw1.su
```

### 2. Настройка серверов

**Digital Ocean:**
```bash
mkdir -p /opt/insurance-system
cd /opt/insurance-system
git clone https://github.com/grigra27/flow_insur_requests.git .
```

**Timeweb:**
```bash
mkdir -p /opt/insflow-system
cd /opt/insflow-system
git clone https://github.com/grigra27/flow_insur_requests.git .
```

### 3. Деплой

Просто пушьте в main ветку - деплой произойдет автоматически на оба хостинга:

```bash
git push origin main
```

## 🌐 Доступ к сайтам

После деплоя сайты будут доступны:

**Digital Ocean:**
- По домену: **http://onbr.site**
- По IP: **http://64.227.75.233**

**Timeweb:**
- По домену: **http://zs.insflow.tw1.su**

**Локально:** **http://localhost** (при локальном запуске)

## 🔧 Команды на серверах

**Digital Ocean:**
```bash
# Проверить статус
docker-compose ps

# Посмотреть логи
docker-compose logs -f web
docker-compose logs -f nginx

# Перезапустить
docker-compose restart

# Обновить вручную
git pull origin main
docker-compose down
docker-compose up -d
```

**Timeweb:**
```bash
# Проверить статус
docker-compose -f docker-compose.timeweb.yml ps

# Посмотреть логи
docker-compose -f docker-compose.timeweb.yml logs -f web
docker-compose -f docker-compose.timeweb.yml logs -f nginx

# Перезапустить
docker-compose -f docker-compose.timeweb.yml restart

# Обновить вручную
git pull origin main
docker-compose -f docker-compose.timeweb.yml down
docker-compose -f docker-compose.timeweb.yml up -d
```

## 📝 Структура проекта

**Общие файлы:**
- `Dockerfile` - образ приложения
- `entrypoint.sh` - скрипт запуска
- `.env.example` - пример переменных окружения

**Digital Ocean (onbr.site):**
- `docker-compose.yml` - сервисы для DO
- `nginx/default.conf` - конфигурация nginx для onbr.site
- `.github/workflows/deploy_do.yml` - автодеплой на DO

**Timeweb (zs.insflow.tw1.su):**
- `docker-compose.timeweb.yml` - сервисы для Timeweb
- `nginx-timeweb/default.conf` - конфигурация nginx для zs.insflow.tw1.su
- `.github/workflows/deploy_timeweb.yml` - автодеплой на Timeweb
- `.env.timeweb.example` - пример переменных для Timeweb

## ⚡ Что добавилось

- **Nginx** как reverse proxy на порту 80
- Статические файлы отдаются через nginx (быстрее)
- Стандартный веб-доступ без указания порта
- **Favicon** для всех страниц системы

## 🎨 Настройка favicon

После деплоя убедитесь, что favicon отображается корректно:

```bash
# Проверьте наличие файлов favicon
ls -la staticfiles/favicon*

# Проверьте доступность через браузер
curl -I http://onbr.site/favicon.ico

# Если favicon не отображается, пересоберите статические файлы
docker-compose exec web python manage.py collectstatic --noinput
```
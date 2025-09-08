#!/bin/bash

set -e

# Функция для ожидания базы данных
wait_for_db() {
    if [ "$DB_ENGINE" = "django.db.backends.postgresql" ]; then
        echo "Waiting for PostgreSQL..."
        while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
            sleep 1
        done
        echo "PostgreSQL is ready!"
    fi
}

# Функция для запуска миграций
run_migrations() {
    echo "Running migrations..."
    python manage.py migrate --noinput
}

# Функция для сбора статики
collect_static() {
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
}

# Если это команда деплоя
if [ "$1" = "deploy" ]; then
    echo "🚀 Starting deployment..."
    
    wait_for_db
    run_migrations
    collect_static
    
    echo "✅ Deployment completed!"
    exit 0
fi

# Обычный запуск контейнера
wait_for_db

# Если это веб-сервер, запускаем миграции и собираем статику
if [ "$1" = "gunicorn" ] || [ "$1" = "python" ] && [ "$2" = "manage.py" ] && [ "$3" = "runserver" ]; then
    run_migrations
    collect_static
fi

# Execute the main command
exec "$@"
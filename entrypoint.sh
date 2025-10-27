#!/bin/bash
set -e

# Wait for database
if [ "$DB_ENGINE" = "django.db.backends.postgresql" ]; then
    echo "Waiting for PostgreSQL..."
    until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
        sleep 1
    done
    echo "PostgreSQL is ready!"
fi

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Optionally create superuser or run other management commands here

# Execute the main command (gunicorn)
exec "$@"

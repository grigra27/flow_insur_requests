#!/bin/bash

# Exit on any error
set -e

# Wait for database to be ready (if using PostgreSQL)
if [ "$DB_ENGINE" = "django.db.backends.postgresql" ]; then
    echo "Waiting for PostgreSQL..."
    while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
        sleep 1
    done
    echo "PostgreSQL is ready!"
fi

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files if needed (in case they weren't collected during build)
if [ "$COLLECT_STATIC" = "true" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Create superuser if specified
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
    echo "Creating superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
"
fi

# Execute the main command
exec "$@"
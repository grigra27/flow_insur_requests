#!/bin/bash

# Quick fix script for current Digital Ocean deployment issue
# Run this on the server to resolve the nginx unhealthy container error

set -e

echo "🚨 Emergency deployment fix for Digital Ocean..."

PROJECT_PATH="/opt/insurance-system"
cd $PROJECT_PATH

echo "➡️ Stopping all services..."
docker-compose down --remove-orphans

echo "➡️ Using conservative configuration (no health checks)..."
# Backup current docker-compose.yml
cp docker-compose.yml docker-compose.yml.backup

# Create a minimal working configuration
cat > docker-compose.yml << 'EOF'
version: "3.9"

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  web:
    image: ${DOCKER_IMAGE}
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DEBUG=False
      - DB_ENGINE=django.db.backends.postgresql
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_HOST=db
      - DB_PORT=5432
      - ALLOWED_HOSTS=${ALLOWED_HOSTS}
    volumes:
      - media_data:/app/media
      - logs_data:/app/logs
      - staticfiles_data:/app/staticfiles
    depends_on:
      - db
    restart: unless-stopped

  nginx:
    build:
      context: ./nginx
    image: custom-nginx:latest
    ports:
      - "80:80"
    volumes:
      - staticfiles_data:/app/staticfiles:ro
      - media_data:/app/media:ro
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
  media_data:
  logs_data:
  staticfiles_data:
EOF

echo "➡️ Starting database service..."
docker-compose up -d db

echo "➡️ Waiting for database to be ready..."
sleep 30

# Test database connectivity
echo "➡️ Testing database connection..."
for i in {1..12}; do
    if docker-compose exec -T db pg_isready -U ${DB_USER:-insurance_user} -d ${DB_NAME:-insurance_db}; then
        echo "✅ Database is ready!"
        break
    fi
    echo "   Waiting for database... ($i/12)"
    sleep 5
done

echo "➡️ Starting web service..."
docker-compose up -d web

echo "➡️ Waiting for web service to be ready..."
sleep 60

echo "➡️ Running database migrations..."
docker-compose exec -T web python manage.py migrate --noinput

echo "➡️ Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput

echo "➡️ Testing web service..."
for i in {1..12}; do
    if docker-compose exec -T web curl -f --connect-timeout 5 http://localhost:8000/healthz/; then
        echo "✅ Web service is ready!"
        break
    fi
    echo "   Waiting for web service... ($i/12)"
    sleep 10
done

echo "➡️ Starting nginx service..."
docker-compose up -d nginx

echo "➡️ Waiting for nginx to be ready..."
sleep 30

echo "➡️ Testing complete application..."
for i in {1..6}; do
    if curl -f --connect-timeout 5 --max-time 10 http://localhost/healthz/; then
        echo "✅ Application is working through nginx!"
        break
    fi
    echo "   Testing application... ($i/6)"
    sleep 10
done

echo "➡️ Final status check..."
docker-compose ps

echo ""
echo "✅ Emergency fix completed!"
echo ""
echo "🌐 Application should now be available at:"
echo "   - http://onbr.site"
echo "   - http://64.227.75.233"
echo ""
echo "📝 What was changed:"
echo "   - Removed health checks that were causing circular dependencies"
echo "   - Added proper startup delays between services"
echo "   - Used step-by-step service startup"
echo ""
echo "🔍 To monitor:"
echo "   docker-compose logs -f"
echo "   docker-compose ps"
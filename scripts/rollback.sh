#!/bin/bash

# Скрипт для быстрого отката к предыдущей версии
# Использование: ./scripts/rollback.sh [production|staging]

set -e

ENVIRONMENT=${1:-production}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔄 Starting rollback for $ENVIRONMENT environment..."

# Функция для проверки здоровья приложения
check_health() {
    local url=$1
    local max_attempts=15
    local attempt=1
    
    echo "🔍 Checking application health at $url..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f "$url/health/" > /dev/null 2>&1; then
            echo "✅ Application is healthy!"
            return 0
        fi
        
        echo "⏳ Attempt $attempt/$max_attempts failed, waiting 5 seconds..."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo "❌ Health check failed after $max_attempts attempts"
    return 1
}

# Определяем файлы конфигурации
if [ "$ENVIRONMENT" = "production" ]; then
    ENV_FILE=".env.prod"
    COMPOSE_FILE="docker-compose.prod.yml"
    HEALTH_URL="https://$(grep ALLOWED_HOSTS .env.prod | cut -d'=' -f2 | cut -d',' -f1)"
    BACKUP_PATTERN="backup_prod_*.json"
else
    ENV_FILE=".env.staging"
    COMPOSE_FILE="docker-compose.staging.yml"
    HEALTH_URL="http://localhost:8001"
    BACKUP_PATTERN="backup_staging_*.json"
fi

# Проверяем наличие файлов конфигурации
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: $ENV_FILE file not found"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Error: $COMPOSE_FILE file not found"
    exit 1
fi

# Создаем бэкап текущего состояния
echo "💾 Creating backup of current state..."
BACKUP_FILE="rollback_backup_$(date +%Y%m%d_%H%M%S).json"
docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE exec -T web python manage.py dumpdata > "$BACKUP_FILE"
echo "✅ Backup saved as $BACKUP_FILE"

# Останавливаем текущие сервисы
echo "🛑 Stopping current services..."
docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE down

# Получаем информацию о репозитории
REPO_NAME=$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^.]*\).*/\1/')

# Ищем предыдущий коммит
CURRENT_COMMIT=$(git rev-parse HEAD)
PREVIOUS_COMMIT=$(git rev-parse HEAD~1)

echo "📋 Current commit: $CURRENT_COMMIT"
echo "📋 Rolling back to: $PREVIOUS_COMMIT"

# Проверяем, существует ли образ для предыдущего коммита
PREVIOUS_IMAGE="ghcr.io/$REPO_NAME:$PREVIOUS_COMMIT"
if docker pull $PREVIOUS_IMAGE > /dev/null 2>&1; then
    echo "✅ Found previous image: $PREVIOUS_IMAGE"
    
    # Обновляем переменную DOCKER_IMAGE в env файле
    sed -i.bak "s|DOCKER_IMAGE=.*|DOCKER_IMAGE=$PREVIOUS_IMAGE|" $ENV_FILE
else
    echo "⚠️  Previous commit image not found, using latest tag"
    PREVIOUS_IMAGE="ghcr.io/$REPO_NAME:latest"
    sed -i.bak "s|DOCKER_IMAGE=.*|DOCKER_IMAGE=$PREVIOUS_IMAGE|" $ENV_FILE
fi

# Запускаем предыдущую версию
echo "🚀 Starting previous version..."
docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d

# Проверяем здоровье приложения
if check_health "$HEALTH_URL"; then
    echo "✅ Rollback successful!"
    echo "🎉 Application is running on previous version"
    echo "Application is available at: $HEALTH_URL"
    
    # Показываем статус сервисов
    echo "📊 Service status:"
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE ps
    
    # Предлагаем восстановить данные из бэкапа
    echo ""
    echo "💡 If you need to restore data from backup, run:"
    echo "   docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE exec web python manage.py loaddata $BACKUP_FILE"
    
    # Показываем доступные бэкапы
    echo ""
    echo "📁 Available backups:"
    ls -la $BACKUP_PATTERN 2>/dev/null | tail -5 || echo "   No backups found"
    
else
    echo "❌ Rollback failed!"
    echo "🆘 Manual intervention required"
    
    # Показываем логи для диагностики
    echo "📋 Recent logs:"
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE logs --tail=20 web
    
    exit 1
fi
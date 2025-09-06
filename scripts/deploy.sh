#!/bin/bash

# Скрипт для ручного деплоя на Digital Ocean
# Использование: ./scripts/deploy.sh [production|staging]

set -e

ENVIRONMENT=${1:-production}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting deployment to $ENVIRONMENT..."

# Проверяем, что мы в правильной директории
if [ ! -f "$PROJECT_DIR/manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run this script from the project root."
    exit 1
fi

# Функция для проверки здоровья приложения
check_health() {
    local url=$1
    local max_attempts=30
    local attempt=1
    
    echo "🔍 Checking application health at $url..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f "$url/health/" > /dev/null 2>&1; then
            echo "✅ Application is healthy!"
            return 0
        fi
        
        echo "⏳ Attempt $attempt/$max_attempts failed, waiting 10 seconds..."
        sleep 10
        attempt=$((attempt + 1))
    done
    
    echo "❌ Health check failed after $max_attempts attempts"
    return 1
}

# Функция для отката
rollback() {
    echo "🔄 Rolling back to previous version..."
    
    if [ "$ENVIRONMENT" = "production" ]; then
        docker-compose -f docker-compose.prod.yml down
        docker tag ghcr.io/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^.]*\).*/\1/'):latest \
                  ghcr.io/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^.]*\).*/\1/'):$(git rev-parse HEAD)
        docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
    else
        docker-compose -f docker-compose.staging.yml down
        docker-compose -f docker-compose.staging.yml --env-file .env.staging up -d
    fi
    
    if check_health "http://localhost"; then
        echo "✅ Rollback successful!"
    else
        echo "❌ Rollback failed! Manual intervention required."
        exit 1
    fi
}

# Создаем бэкап базы данных
echo "💾 Creating database backup..."
if [ "$ENVIRONMENT" = "production" ]; then
    docker-compose -f docker-compose.prod.yml exec -T web python manage.py dumpdata > "backup_prod_$(date +%Y%m%d_%H%M%S).json"
else
    docker-compose -f docker-compose.staging.yml exec -T web python manage.py dumpdata > "backup_staging_$(date +%Y%m%d_%H%M%S).json"
fi

# Проверяем переменные окружения
if [ "$ENVIRONMENT" = "production" ]; then
    if [ ! -f ".env.prod" ]; then
        echo "❌ Error: .env.prod file not found"
        echo "Please create .env.prod with production environment variables"
        exit 1
    fi
    ENV_FILE=".env.prod"
    COMPOSE_FILE="docker-compose.prod.yml"
    HEALTH_URL="https://$(grep ALLOWED_HOSTS .env.prod | cut -d'=' -f2 | cut -d',' -f1)"
else
    if [ ! -f ".env.staging" ]; then
        echo "❌ Error: .env.staging file not found"
        echo "Please create .env.staging with staging environment variables"
        exit 1
    fi
    ENV_FILE=".env.staging"
    COMPOSE_FILE="docker-compose.staging.yml"
    HEALTH_URL="http://localhost:8001"
fi

# Собираем новый образ
echo "🔨 Building Docker image..."
docker build -t insurance-system:latest .

# Тегируем образ
REPO_NAME=$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^.]*\).*/\1/')
COMMIT_SHA=$(git rev-parse HEAD)
docker tag insurance-system:latest ghcr.io/$REPO_NAME:$COMMIT_SHA
docker tag insurance-system:latest ghcr.io/$REPO_NAME:latest

# Обновляем переменную DOCKER_IMAGE в env файле
sed -i.bak "s|DOCKER_IMAGE=.*|DOCKER_IMAGE=ghcr.io/$REPO_NAME:$COMMIT_SHA|" $ENV_FILE

# Запускаем новую версию
echo "🚀 Starting new version..."
docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d

# Проверяем здоровье приложения
if check_health "$HEALTH_URL"; then
    echo "✅ Deployment successful!"
    
    # Очищаем старые образы
    echo "🧹 Cleaning up old images..."
    docker image prune -f
    
    echo "🎉 Deployment completed successfully!"
    echo "Application is available at: $HEALTH_URL"
else
    echo "❌ Deployment failed! Starting rollback..."
    rollback
    exit 1
fi

# Показываем статус сервисов
echo "📊 Service status:"
docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE ps
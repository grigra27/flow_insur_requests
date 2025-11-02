#!/bin/bash

# Improved Digital Ocean deployment script
set -e

PROJECT_PATH="/opt/insurance-system"
DOCKER_IMAGE="ghcr.io/grigra27/flow_insur_requests:latest"

echo "🚀 Starting improved Digital Ocean deployment..."

# Function to wait for service health
wait_for_service_health() {
    local service_name=$1
    local max_attempts=$2
    local attempt=1
    
    echo "⏳ Waiting for $service_name to be healthy..."
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$service_name.*healthy"; then
            echo "✅ $service_name is healthy!"
            return 0
        fi
        
        echo "   Attempt $attempt/$max_attempts - $service_name not ready yet..."
        sleep 10
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service_name failed to become healthy after $max_attempts attempts"
    return 1
}

# Function to test endpoint
test_endpoint() {
    local url=$1
    local description=$2
    local max_attempts=${3:-6}
    local attempt=1
    
    echo "🔍 Testing $description..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s --connect-timeout 5 --max-time 10 "$url" > /dev/null; then
            echo "✅ $description is working!"
            return 0
        fi
        
        echo "   Attempt $attempt/$max_attempts - $description not ready yet..."
        sleep 10
        attempt=$((attempt + 1))
    done
    
    echo "❌ $description failed after $max_attempts attempts"
    return 1
}

echo "➡️ Changing to project directory..."
cd $PROJECT_PATH

echo "➡️ Fetching latest code..."
git fetch origin main
git reset --hard origin/main

echo "➡️ Updating environment configuration..."
cat > .env << EOF
SECRET_KEY=$SECRET_KEY
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=db
DB_PORT=5432
ALLOWED_HOSTS=$ALLOWED_HOSTS
DOCKER_IMAGE=$DOCKER_IMAGE
EOF

echo "➡️ Logging into GitHub Container Registry..."
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_ACTOR --password-stdin

echo "➡️ Pulling latest Docker image..."
docker pull $DOCKER_IMAGE

echo "➡️ Stopping existing services..."
docker-compose down --remove-orphans

echo "➡️ Starting database service first..."
docker-compose up -d db

echo "➡️ Waiting for database to be ready..."
wait_for_service_health "db" 12

echo "➡️ Starting web service..."
docker-compose up -d web

echo "➡️ Waiting for web service to be ready..."
wait_for_service_health "web" 18

echo "➡️ Running database migrations..."
docker-compose exec -T web python manage.py migrate --noinput

echo "➡️ Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput

echo "➡️ Testing web service directly..."
test_endpoint "http://localhost:8000/healthz/" "Web service health check"

echo "➡️ Starting nginx service..."
docker-compose up -d nginx

echo "➡️ Waiting for nginx to be ready..."
wait_for_service_health "nginx" 12

echo "➡️ Testing complete application..."
test_endpoint "http://localhost/healthz/" "Application through nginx"

echo "➡️ Final service status check..."
docker-compose ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "➡️ Running comprehensive health check..."
if docker-compose exec -T web python /app/simple_healthcheck.py; then
    echo "✅ Comprehensive health check passed!"
else
    echo "⚠️  Comprehensive health check had issues, but basic functionality is working"
fi

echo "➡️ Cleaning up unused images..."
docker image prune -f

echo "✅ Deployment completed successfully!"
echo ""
echo "🌐 Application should be available at:"
echo "   - http://onbr.site"
echo "   - http://64.227.75.233"
echo ""
echo "🔍 To monitor the application:"
echo "   docker-compose logs -f"
echo "   docker-compose ps"
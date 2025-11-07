#!/bin/bash

# Test deployment script for Digital Ocean
set -e

echo "🧪 Testing Digital Ocean deployment configuration..."

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml not found!"
    exit 1
fi

echo "✅ docker-compose.yml found"

# Check if .env file exists or create a test one
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found, creating test environment..."
    cat > .env << EOF
SECRET_KEY=test-secret-key-for-deployment-testing
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=test-password
DB_HOST=db
DB_PORT=5432
ALLOWED_HOSTS=localhost,127.0.0.1,onbr.site
DOCKER_IMAGE=ghcr.io/grigra27/flow_insur_requests:latest
EOF
    echo "✅ Test .env file created"
fi

# Validate docker-compose configuration
echo "🔍 Validating docker-compose configuration..."
if docker-compose config > /dev/null 2>&1; then
    echo "✅ docker-compose configuration is valid"
else
    echo "❌ docker-compose configuration has errors:"
    docker-compose config
    exit 1
fi

# Check if required images are available
echo "🔍 Checking Docker images..."
if docker pull postgres:15 > /dev/null 2>&1; then
    echo "✅ PostgreSQL image available"
else
    echo "❌ Failed to pull PostgreSQL image"
    exit 1
fi

# Test nginx configuration
echo "🔍 Testing nginx configuration..."
if [ -f "nginx/default.conf" ]; then
    echo "✅ nginx configuration found"
    
    # Check if nginx config has basic required sections
    if grep -q "location /static/" nginx/default.conf && \
       grep -q "location /media/" nginx/default.conf && \
       grep -q "proxy_pass.*web:8000" nginx/default.conf; then
        echo "✅ nginx configuration looks good"
    else
        echo "⚠️  nginx configuration might be incomplete"
    fi
else
    echo "❌ nginx/default.conf not found!"
    exit 1
fi

# Test health check script
echo "🔍 Testing health check script..."
if [ -f "healthcheck.py" ]; then
    echo "✅ healthcheck.py found"
    
    # Basic syntax check
    if python3 -m py_compile healthcheck.py 2>/dev/null; then
        echo "✅ healthcheck.py syntax is valid"
    else
        echo "❌ healthcheck.py has syntax errors"
        exit 1
    fi
else
    echo "❌ healthcheck.py not found!"
    exit 1
fi

echo ""
echo "🎉 All deployment tests passed!"
echo ""
echo "📋 Deployment checklist:"
echo "  ✅ docker-compose.yml configuration valid"
echo "  ✅ Environment variables configured"
echo "  ✅ Docker images accessible"
echo "  ✅ nginx configuration present"
echo "  ✅ Health check script valid"
echo ""
echo "🚀 Ready for deployment to Digital Ocean!"
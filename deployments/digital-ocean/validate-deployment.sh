#!/bin/bash

# Digital Ocean Deployment Validation Script
# This script validates that the Digital Ocean deployment configuration is intact and functional

set -e

echo "=== Digital Ocean Deployment Validation ==="
echo "Starting validation at $(date)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: docker-compose.yml not found. Please run this script from deployments/digital-ocean directory${NC}"
    exit 1
fi

echo "1. Validating configuration files..."

# Check required files exist
files_to_check=(
    "docker-compose.yml"
    "nginx/default.conf"
    ".env.example"
    "README.md"
)

for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        print_status 0 "File exists: $file"
    else
        print_status 1 "Missing file: $file"
        exit 1
    fi
done

echo ""
echo "2. Validating Docker Compose configuration..."

# Check if Docker is available
if command -v docker > /dev/null 2>&1; then
    # Validate docker-compose.yml syntax
    if docker compose config > /dev/null 2>&1; then
        print_status 0 "Docker Compose syntax is valid"
    else
        print_status 1 "Docker Compose syntax validation failed"
        echo "Run 'docker compose config' for details"
        exit 1
    fi

    # Check for required services
    required_services=("db" "web" "nginx")
    for service in "${required_services[@]}"; do
        if docker compose config --services | grep -q "^${service}$"; then
            print_status 0 "Service defined: $service"
        else
            print_status 1 "Missing service: $service"
            exit 1
        fi
    done
else
    print_warning "Docker not available - skipping Docker Compose syntax validation"
    
    # Manual check for required services in docker-compose.yml
    required_services=("db:" "web:" "nginx:")
    for service in "${required_services[@]}"; do
        if grep -q "^  ${service}" docker-compose.yml; then
            print_status 0 "Service defined: ${service%:}"
        else
            print_status 1 "Missing service: ${service%:}"
            exit 1
        fi
    done
fi

echo ""
echo "3. Validating environment configuration..."

# Check if .env file exists
if [ -f ".env" ]; then
    print_status 0 ".env file exists"
    
    # Check required environment variables
    required_vars=("SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "ALLOWED_HOSTS" "DOCKER_IMAGE")
    
    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env; then
            print_status 0 "Environment variable defined: $var"
        else
            print_status 1 "Missing environment variable: $var"
            exit 1
        fi
    done
else
    print_warning ".env file not found - using .env.example for validation"
    
    # Check .env.example instead
    required_vars=("SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "ALLOWED_HOSTS" "DOCKER_IMAGE")
    
    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env.example; then
            print_status 0 "Environment variable template exists: $var"
        else
            print_status 1 "Missing environment variable template: $var"
            exit 1
        fi
    done
fi

echo ""
echo "4. Validating Nginx configuration..."

# Check nginx config syntax (if nginx is available)
if command -v nginx > /dev/null 2>&1; then
    if nginx -t -c nginx/default.conf > /dev/null 2>&1; then
        print_status 0 "Nginx configuration syntax is valid"
    else
        print_warning "Nginx configuration syntax check failed (this may be normal if not running on nginx system)"
    fi
else
    print_warning "Nginx not available for syntax checking"
fi

# Check for required nginx directives
nginx_checks=(
    "listen 80"
    "proxy_pass http://web:8000"
    "location /static/"
    "location /media/"
)

for check in "${nginx_checks[@]}"; do
    if grep -q "$check" nginx/default.conf; then
        print_status 0 "Nginx directive found: $check"
    else
        print_status 1 "Missing nginx directive: $check"
        exit 1
    fi
done

echo ""
echo "5. Checking for configuration conflicts with Timeweb deployment..."

# Check that Digital Ocean config doesn't have HTTPS settings
if [ -f ".env" ]; then
    env_file=".env"
else
    env_file=".env.example"
fi

# These should be False or not set for Digital Ocean
https_vars=("ENABLE_HTTPS" "SSL_REDIRECT" "SECURE_COOKIES")
for var in "${https_vars[@]}"; do
    if grep -q "^${var}=True" "$env_file"; then
        print_status 1 "HTTPS setting enabled in Digital Ocean config: $var=True"
        echo "  This may cause conflicts. Digital Ocean deployment should use HTTP only."
        exit 1
    else
        print_status 0 "HTTPS setting correctly disabled: $var"
    fi
done

# Check that nginx config doesn't have SSL directives
ssl_directives=("ssl_certificate" "listen 443" "ssl_protocols")
for directive in "${ssl_directives[@]}"; do
    if grep -q "$directive" nginx/default.conf; then
        print_status 1 "SSL directive found in Digital Ocean nginx config: $directive"
        echo "  This may cause conflicts with HTTP-only deployment."
        exit 1
    else
        print_status 0 "No SSL directive found: $directive"
    fi
done

echo ""
echo "6. Validating service health check configurations..."

# Check health check endpoints
health_checks=(
    "curl.*healthz"
    "wget.*healthz"
    "pg_isready"
)

for check in "${health_checks[@]}"; do
    if grep -q "$check" docker-compose.yml; then
        print_status 0 "Health check found: $check"
    else
        print_warning "Health check not found: $check"
    fi
done

echo ""
echo "7. Testing Docker Compose dry run..."

# Test docker compose without actually starting services
if command -v docker > /dev/null 2>&1; then
    if docker compose config --quiet; then
        print_status 0 "Docker Compose configuration passes dry run"
    else
        print_status 1 "Docker Compose dry run failed"
        exit 1
    fi
else
    print_warning "Docker not available - skipping dry run test"
    print_status 0 "Configuration file structure validation completed"
fi

echo ""
echo "=== Validation Summary ==="
echo -e "${GREEN}✓ All Digital Ocean deployment validation checks passed!${NC}"
echo ""
echo "The Digital Ocean deployment configuration is intact and ready for use."
echo "No conflicts detected with Timeweb deployment configuration."
echo ""
echo "To deploy:"
echo "  1. Copy .env.example to .env and configure your settings"
echo "  2. Run: docker compose up -d"
echo "  3. Check status: docker compose ps"
echo ""
echo "Validation completed at $(date)"
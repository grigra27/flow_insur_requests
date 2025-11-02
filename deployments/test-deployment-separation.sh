#!/bin/bash

# Deployment Separation Validation Script
# This script ensures Digital Ocean and Timeweb deployments don't conflict with each other

set -e

echo "=== Deployment Separation Validation ==="
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
if [ ! -d "digital-ocean" ] || [ ! -d "timeweb" ]; then
    echo -e "${RED}Error: Please run this script from the deployments directory${NC}"
    exit 1
fi

echo "1. Validating deployment directory structure..."

# Check required directories and files exist
do_files=(
    "digital-ocean/docker-compose.yml"
    "digital-ocean/nginx/default.conf"
    "digital-ocean/.env.example"
    "digital-ocean/README.md"
)

tw_files=(
    "timeweb/docker-compose.yml"
    "timeweb/nginx/default.conf"
    "timeweb/.env.example"
    "timeweb/README.md"
)

for file in "${do_files[@]}"; do
    if [ -f "$file" ]; then
        print_status 0 "Digital Ocean file exists: $file"
    else
        print_status 1 "Missing Digital Ocean file: $file"
        exit 1
    fi
done

for file in "${tw_files[@]}"; do
    if [ -f "$file" ]; then
        print_status 0 "Timeweb file exists: $file"
    else
        print_status 1 "Missing Timeweb file: $file"
        exit 1
    fi
done

echo ""
echo "2. Checking for configuration conflicts..."

# Check that Digital Ocean uses HTTP and Timeweb uses HTTPS
echo "2.1 Validating protocol separation..."

# Digital Ocean should have HTTP settings
if grep -q "listen 80" digital-ocean/nginx/default.conf; then
    print_status 0 "Digital Ocean correctly configured for HTTP (port 80)"
else
    print_status 1 "Digital Ocean missing HTTP configuration"
    exit 1
fi

if ! grep -q "listen 443" digital-ocean/nginx/default.conf; then
    print_status 0 "Digital Ocean correctly excludes HTTPS (no port 443)"
else
    print_status 1 "Digital Ocean incorrectly includes HTTPS configuration"
    exit 1
fi

# Timeweb should have HTTPS settings (check both default.conf and default-https.conf)
if grep -q "listen 443" timeweb/nginx/default.conf || grep -q "listen 443" timeweb/nginx/default-https.conf 2>/dev/null; then
    print_status 0 "Timeweb correctly configured for HTTPS (port 443)"
else
    print_status 1 "Timeweb missing HTTPS configuration"
    exit 1
fi

# Check for HTTP configuration in Timeweb (should exist for redirects and ACME challenges)
if grep -q "listen 80" timeweb/nginx/default.conf || grep -q "listen 80" timeweb/nginx/default-https.conf 2>/dev/null; then
    print_status 0 "Timeweb includes HTTP for redirects (port 80)"
else
    print_warning "Timeweb missing HTTP redirect configuration"
fi

echo ""
echo "2.2 Validating environment variable separation..."

# Check Digital Ocean environment settings
if [ -f "digital-ocean/.env.example" ]; then
    if grep -q "ENABLE_HTTPS=False" digital-ocean/.env.example; then
        print_status 0 "Digital Ocean correctly disables HTTPS"
    else
        print_status 1 "Digital Ocean HTTPS setting incorrect"
        exit 1
    fi
    
    if grep -q "SSL_REDIRECT=False" digital-ocean/.env.example; then
        print_status 0 "Digital Ocean correctly disables SSL redirect"
    else
        print_status 1 "Digital Ocean SSL redirect setting incorrect"
        exit 1
    fi
fi

# Check Timeweb environment settings
if [ -f "timeweb/.env.example" ]; then
    if grep -q "ENABLE_HTTPS=True" timeweb/.env.example; then
        print_status 0 "Timeweb correctly enables HTTPS"
    else
        print_status 1 "Timeweb HTTPS setting incorrect"
        exit 1
    fi
    
    if grep -q "SSL_REDIRECT=True" timeweb/.env.example; then
        print_status 0 "Timeweb correctly enables SSL redirect"
    else
        print_status 1 "Timeweb SSL redirect setting incorrect"
        exit 1
    fi
fi

echo ""
echo "3. Checking for shared dependencies..."

# Check that both deployments use the same base application
echo "3.1 Validating service consistency..."

# Both should have the same core services
core_services=("db:" "web:" "nginx:")
for service in "${core_services[@]}"; do
    if grep -q "^  ${service}" digital-ocean/docker-compose.yml && grep -q "^  ${service}" timeweb/docker-compose.yml; then
        print_status 0 "Both deployments include service: ${service%:}"
    else
        print_status 1 "Service inconsistency: ${service%:}"
        exit 1
    fi
done

echo ""
echo "3.2 Validating volume consistency..."

# Check that both use similar volume structures
volume_types=("postgres_data" "media_data" "staticfiles_data")
for volume in "${volume_types[@]}"; do
    if grep -q "$volume" digital-ocean/docker-compose.yml && grep -q "$volume" timeweb/docker-compose.yml; then
        print_status 0 "Both deployments use volume: $volume"
    else
        print_warning "Volume difference detected: $volume"
    fi
done

echo ""
echo "4. Checking for file conflicts..."

# Ensure no shared configuration files that could cause conflicts
shared_files=(
    "docker-compose.yml"
    ".env"
    "nginx.conf"
)

echo "4.1 Validating file isolation..."
for file in "${shared_files[@]}"; do
    do_file="digital-ocean/$file"
    tw_file="timeweb/$file"
    
    if [ -f "$do_file" ] && [ -f "$tw_file" ]; then
        if ! diff -q "$do_file" "$tw_file" > /dev/null 2>&1; then
            print_status 0 "Deployments have separate $file files (good)"
        else
            print_warning "Deployments have identical $file files - may cause confusion"
        fi
    fi
done

echo ""
echo "5. Validating deployment scripts..."

# Check for deployment-specific scripts
if [ -f "digital-ocean/validate-deployment.sh" ]; then
    print_status 0 "Digital Ocean has validation script"
else
    print_warning "Digital Ocean missing validation script"
fi

if [ -f "timeweb/scripts/deploy-timeweb.sh" ]; then
    print_status 0 "Timeweb has deployment script"
else
    print_warning "Timeweb missing deployment script"
fi

echo ""
echo "6. Testing cross-deployment compatibility..."

# Check that environment variables don't conflict
echo "6.1 Checking environment variable compatibility..."

# Extract environment variables from both deployments
if [ -f "digital-ocean/.env.example" ] && [ -f "timeweb/.env.example" ]; then
    # Check for conflicting variable definitions
    do_vars=$(grep "^[A-Z]" digital-ocean/.env.example | cut -d'=' -f1 | sort)
    tw_vars=$(grep "^[A-Z]" timeweb/.env.example | cut -d'=' -f1 | sort)
    
    common_vars=$(comm -12 <(echo "$do_vars") <(echo "$tw_vars"))
    
    if [ -n "$common_vars" ]; then
        print_status 0 "Deployments share common environment variables (expected)"
        
        # Check for conflicting values in critical variables
        conflict_vars=("ENABLE_HTTPS" "SSL_REDIRECT" "SECURE_COOKIES")
        for var in "${conflict_vars[@]}"; do
            do_val=$(grep "^${var}=" digital-ocean/.env.example 2>/dev/null | cut -d'=' -f2 || echo "")
            tw_val=$(grep "^${var}=" timeweb/.env.example 2>/dev/null | cut -d'=' -f2 || echo "")
            
            if [ "$do_val" != "$tw_val" ] && [ -n "$do_val" ] && [ -n "$tw_val" ]; then
                print_status 0 "Variable $var correctly differs: DO=$do_val, TW=$tw_val"
            elif [ "$do_val" = "$tw_val" ] && [ -n "$do_val" ]; then
                print_warning "Variable $var has same value in both deployments: $do_val"
            fi
        done
    else
        print_warning "No common environment variables found"
    fi
fi

echo ""
echo "=== Validation Summary ==="
echo -e "${GREEN}✓ Deployment separation validation completed successfully!${NC}"
echo ""
echo "Key findings:"
echo "• Digital Ocean deployment correctly configured for HTTP-only"
echo "• Timeweb deployment correctly configured for HTTPS"
echo "• No configuration conflicts detected between deployments"
echo "• Both deployments maintain proper isolation"
echo "• Shared components (database, application) are compatible"
echo ""
echo "Both deployments can coexist without conflicts."
echo "Validation completed at $(date)"
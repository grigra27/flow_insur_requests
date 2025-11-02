#!/bin/bash

# Manual HTTPS Activation Script
# Use this when certificates exist but deployment script can't find them due to permissions

set -e

PROJECT_PATH="/opt/insflow-system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Success message
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Error message
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Info message
info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if certificates exist
check_certificates() {
    info "Checking SSL certificates..."
    
    local cert1="$PROJECT_PATH/letsencrypt/live/insflow.ru/fullchain.pem"
    local cert2="$PROJECT_PATH/letsencrypt/live/insflow.tw1.su/fullchain.pem"
    
    if [[ -f "$cert1" ]] && [[ -f "$cert2" ]]; then
        success "SSL certificates found and accessible"
        
        # Show certificate info
        echo "Certificate 1: insflow.ru"
        ls -la "$PROJECT_PATH/letsencrypt/live/insflow.ru/"
        echo ""
        echo "Certificate 2: insflow.tw1.su"  
        ls -la "$PROJECT_PATH/letsencrypt/live/insflow.tw1.su/"
        echo ""
        
        return 0
    else
        error "SSL certificates not found or not accessible"
        echo "Expected locations:"
        echo "  $cert1"
        echo "  $cert2"
        return 1
    fi
}

# Activate HTTPS configuration
activate_https() {
    info "Activating HTTPS configuration..."
    
    cd "$PROJECT_PATH"
    
    # 1. Copy HTTPS nginx configuration
    if [[ -f "nginx-timeweb/default-https.conf" ]]; then
        cp nginx-timeweb/default-https.conf nginx-timeweb/default.conf
        success "HTTPS nginx configuration activated"
    else
        error "HTTPS nginx configuration not found"
        return 1
    fi
    
    # 2. Update .env file to enable SSL
    info "Updating .env file for HTTPS..."
    
    sed -i 's/SSL_ENABLED=False/SSL_ENABLED=True/' .env
    sed -i 's/SESSION_COOKIE_SECURE=False/SESSION_COOKIE_SECURE=True/' .env
    sed -i 's/CSRF_COOKIE_SECURE=False/CSRF_COOKIE_SECURE=True/' .env
    sed -i 's/SECURE_SSL_REDIRECT=False/SECURE_SSL_REDIRECT=True/' .env
    sed -i 's/SECURE_HSTS_SECONDS=0/SECURE_HSTS_SECONDS=31536000/' .env
    sed -i 's/SECURE_HSTS_INCLUDE_SUBDOMAINS=False/SECURE_HSTS_INCLUDE_SUBDOMAINS=True/' .env
    sed -i 's/SECURE_HSTS_PRELOAD=False/SECURE_HSTS_PRELOAD=True/' .env
    
    success ".env file updated for HTTPS"
    
    # 3. Restart services with SSL profile
    info "Restarting services with SSL profile..."
    
    docker-compose -f docker-compose.timeweb.yml down
    COMPOSE_PROFILES="ssl" docker-compose -f docker-compose.timeweb.yml up -d --force-recreate
    
    success "Services restarted with HTTPS configuration"
}

# Test HTTPS functionality
test_https() {
    info "Testing HTTPS functionality..."
    
    # Wait for services to start
    sleep 30
    
    local domains=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
    local success_count=0
    
    for domain in "${domains[@]}"; do
        if curl -f -s -k "https://$domain/healthz/" > /dev/null 2>&1; then
            success "HTTPS works for $domain"
            success_count=$((success_count + 1))
        else
            error "HTTPS failed for $domain"
        fi
    done
    
    echo ""
    info "HTTPS test results: $success_count/4 domains working"
    
    if [[ $success_count -eq 4 ]]; then
        success "All domains are working with HTTPS!"
        return 0
    else
        error "Some domains are not working with HTTPS"
        return 1
    fi
}

# Show final status
show_status() {
    echo ""
    echo "🎉 HTTPS Activation Complete!"
    echo "=============================="
    
    # Show container status
    info "Container status:"
    docker-compose -f "$PROJECT_PATH/docker-compose.timeweb.yml" ps
    
    echo ""
    info "Available HTTPS endpoints:"
    echo "  - https://insflow.ru (landing page)"
    echo "  - https://zs.insflow.ru (Django app)"
    echo "  - https://insflow.tw1.su (landing page)"
    echo "  - https://zs.insflow.tw1.su (Django app)"
    
    echo ""
    info "Certificate auto-renewal is active via certbot container"
}

# Main function
main() {
    echo "🔒 Manual HTTPS Activation"
    echo "========================="
    echo "This script activates HTTPS when certificates exist but deployment can't find them"
    echo ""
    
    check_root
    
    if ! check_certificates; then
        error "Cannot proceed without valid SSL certificates"
        exit 1
    fi
    
    activate_https
    
    if test_https; then
        show_status
        success "HTTPS activation completed successfully!"
    else
        error "HTTPS activation completed but some tests failed"
        info "Check nginx logs: docker-compose -f docker-compose.timeweb.yml logs nginx"
        exit 1
    fi
}

# Run main function
main "$@"
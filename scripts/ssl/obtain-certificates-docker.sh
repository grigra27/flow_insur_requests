#!/bin/bash

# Docker-based SSL Certificate Obtainment Script
# This script obtains Let's Encrypt certificates using Docker and webroot method

set -e

# Configuration
EMAIL="admin@insflow.ru"
DOMAINS_PRIMARY="insflow.ru,zs.insflow.ru"
DOMAINS_TECHNICAL="insflow.tw1.su,zs.insflow.tw1.su"
PROJECT_PATH="/opt/insflow-system"
WEBROOT_PATH="/var/www/certbot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Error handling
error_exit() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    log "ERROR: $1"
    exit 1
}

# Success message
success() {
    echo -e "${GREEN}SUCCESS: $1${NC}"
    log "SUCCESS: $1"
}

# Warning message
warning() {
    echo -e "${YELLOW}WARNING: $1${NC}"
    log "WARNING: $1"
}

# Check if domains are accessible via HTTP
check_domain_accessibility() {
    local domains="$1"
    IFS=',' read -ra DOMAIN_ARRAY <<< "$domains"
    
    for domain in "${DOMAIN_ARRAY[@]}"; do
        log "Checking HTTP accessibility for $domain..."
        
        # Create test file
        local test_file="test-$(date +%s).txt"
        echo "test" > "$PROJECT_PATH/certbot_webroot/$test_file"
        
        # Test accessibility
        if curl -f -s "http://$domain/.well-known/acme-challenge/$test_file" > /dev/null 2>&1; then
            success "Domain $domain is accessible via HTTP"
        else
            warning "Domain $domain is not accessible via HTTP - certificate generation may fail"
        fi
        
        # Clean up test file
        rm -f "$PROJECT_PATH/certbot_webroot/$test_file"
    done
}

# Prepare webroot directory
prepare_webroot() {
    log "Preparing webroot directory..."
    
    # Create webroot directory if it doesn't exist
    mkdir -p "$PROJECT_PATH/certbot_webroot/.well-known/acme-challenge"
    
    # Set proper permissions
    chmod -R 755 "$PROJECT_PATH/certbot_webroot"
    
    success "Webroot directory prepared"
}

# Start nginx with HTTP-only config for certificate generation
start_nginx_for_cert_generation() {
    log "Starting nginx with HTTP-only configuration for certificate generation..."
    
    cd "$PROJECT_PATH"
    
    # Ensure we're using HTTP-only config
    cp nginx-timeweb/default-http.conf nginx-timeweb/default.conf
    
    # Start nginx without SSL profile
    docker-compose -f docker-compose.timeweb.yml up -d nginx
    
    # Wait for nginx to be ready
    sleep 10
    
    success "Nginx started for certificate generation"
}

# Obtain certificate using Docker certbot
obtain_certificate_docker() {
    local domains="$1"
    local cert_name="$2"
    
    log "Obtaining certificate for domains: $domains using Docker certbot"
    
    cd "$PROJECT_PATH"
    
    # Run certbot in Docker container
    if docker run --rm \
        -v "$(pwd)/letsencrypt:/etc/letsencrypt" \
        -v "$(pwd)/certbot_webroot:/var/www/certbot" \
        certbot/certbot:latest \
        certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --non-interactive \
        --domains "$domains" \
        --cert-name "$cert_name" \
        --expand \
        --verbose; then
        success "Certificate obtained for $domains"
    else
        error_exit "Failed to obtain certificate for $domains"
    fi
}

# Verify certificate exists
verify_certificate_exists() {
    local cert_name="$1"
    local cert_file="$PROJECT_PATH/letsencrypt/live/$cert_name/fullchain.pem"
    
    if [[ -f "$cert_file" ]]; then
        log "Certificate file exists: $cert_file"
        
        # Check certificate details
        local expiry=$(docker run --rm -v "$(pwd)/letsencrypt:/etc/letsencrypt" certbot/certbot:latest \
            certificates --cert-name "$cert_name" | grep "Expiry Date" | head -1)
        
        success "Certificate for $cert_name: $expiry"
        return 0
    else
        error_exit "Certificate file not found: $cert_file"
    fi
}

# Switch to HTTPS configuration
switch_to_https_config() {
    log "Switching to HTTPS configuration..."
    
    cd "$PROJECT_PATH"
    
    # Copy HTTPS config
    cp nginx-timeweb/default-https.conf nginx-timeweb/default.conf
    
    # Update .env to enable SSL
    sed -i 's/SSL_ENABLED=False/SSL_ENABLED=True/' .env
    sed -i 's/SESSION_COOKIE_SECURE=False/SESSION_COOKIE_SECURE=True/' .env
    sed -i 's/CSRF_COOKIE_SECURE=False/CSRF_COOKIE_SECURE=True/' .env
    sed -i 's/SECURE_SSL_REDIRECT=False/SECURE_SSL_REDIRECT=True/' .env
    sed -i 's/SECURE_HSTS_SECONDS=0/SECURE_HSTS_SECONDS=31536000/' .env
    sed -i 's/SECURE_HSTS_INCLUDE_SUBDOMAINS=False/SECURE_HSTS_INCLUDE_SUBDOMAINS=True/' .env
    sed -i 's/SECURE_HSTS_PRELOAD=False/SECURE_HSTS_PRELOAD=True/' .env
    
    # Restart with SSL profile
    docker-compose -f docker-compose.timeweb.yml down
    COMPOSE_PROFILES="ssl" docker-compose -f docker-compose.timeweb.yml up -d
    
    success "Switched to HTTPS configuration"
}

# Test HTTPS functionality
test_https() {
    local domains="$1"
    IFS=',' read -ra DOMAIN_ARRAY <<< "$domains"
    
    log "Testing HTTPS functionality..."
    
    # Wait for services to be ready
    sleep 30
    
    for domain in "${DOMAIN_ARRAY[@]}"; do
        if curl -f -s -k "https://$domain/healthz/" > /dev/null 2>&1; then
            success "HTTPS test passed for $domain"
        else
            warning "HTTPS test failed for $domain"
        fi
    done
}

# Main execution
main() {
    log "Starting Docker-based SSL certificate obtainment..."
    
    # Prepare environment
    prepare_webroot
    
    # Start nginx for certificate generation
    start_nginx_for_cert_generation
    
    # Check domain accessibility
    check_domain_accessibility "$DOMAINS_PRIMARY"
    check_domain_accessibility "$DOMAINS_TECHNICAL"
    
    # Obtain certificates
    obtain_certificate_docker "$DOMAINS_PRIMARY" "insflow.ru"
    obtain_certificate_docker "$DOMAINS_TECHNICAL" "insflow.tw1.su"
    
    # Verify certificates
    verify_certificate_exists "insflow.ru"
    verify_certificate_exists "insflow.tw1.su"
    
    # Switch to HTTPS configuration
    switch_to_https_config
    
    # Test HTTPS functionality
    test_https "$DOMAINS_PRIMARY"
    test_https "$DOMAINS_TECHNICAL"
    
    success "SSL certificate obtainment completed successfully!"
    log "All certificates have been obtained and HTTPS is now enabled"
}

# Run main function
main "$@"
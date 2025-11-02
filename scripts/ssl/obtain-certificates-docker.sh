#!/bin/bash

# Docker-based SSL Certificate Obtainment Script for Timeweb Deployment
# This script obtains Let's Encrypt certificates using Docker containers

set -e

# Configuration
EMAIL="admin@insflow.ru"
DOMAINS_PRIMARY="insflow.ru,zs.insflow.ru"
DOMAINS_TECHNICAL="insflow.tw1.su,zs.insflow.tw1.su"
CERT_PATH="/etc/letsencrypt"
LOG_FILE="/tmp/ssl-certificates.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
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

# Check DNS resolution for domains
check_dns() {
    local domains="$1"
    IFS=',' read -ra DOMAIN_ARRAY <<< "$domains"
    
    for domain in "${DOMAIN_ARRAY[@]}"; do
        log "Checking DNS resolution for $domain..."
        if ! nslookup "$domain" > /dev/null 2>&1; then
            error_exit "DNS resolution failed for $domain"
        fi
        success "DNS resolution OK for $domain"
    done
}

# Create necessary directories
setup_directories() {
    log "Setting up certificate directories..."
    mkdir -p /etc/letsencrypt/live
    mkdir -p /etc/letsencrypt/archive
    mkdir -p /var/www/certbot
    success "Directories created"
}

# Stop nginx temporarily for certificate generation
stop_nginx() {
    if docker-compose -f docker-compose.timeweb.yml ps nginx | grep -q "Up"; then
        log "Stopping nginx container for certificate generation..."
        docker-compose -f docker-compose.timeweb.yml stop nginx
        success "Nginx stopped"
        return 0
    else
        log "Nginx container not running"
        return 1
    fi
}

# Start nginx after certificate generation
start_nginx() {
    log "Starting nginx container..."
    docker-compose -f docker-compose.timeweb.yml start nginx
    success "Nginx started"
}

# Obtain certificate using Docker certbot
obtain_certificate_docker() {
    local domains="$1"
    local cert_name="$2"
    
    log "Obtaining certificate for domains: $domains using Docker"
    
    # Use certbot Docker image in standalone mode
    if docker run --rm \
        -v "/etc/letsencrypt:/etc/letsencrypt" \
        -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
        -p 80:80 \
        certbot/certbot certonly \
        --standalone \
        --email "$EMAIL" \
        --agree-tos \
        --non-interactive \
        --domains "$domains" \
        --cert-name "$cert_name" \
        --expand; then
        success "Certificate obtained for $domains"
        return 0
    else
        warning "Standalone mode failed for $domains, trying webroot mode"
        return 1
    fi
}

# Obtain certificate using webroot mode
obtain_certificate_webroot() {
    local domains="$1"
    local cert_name="$2"
    
    log "Trying webroot mode for domains: $domains"
    
    # Ensure webroot directory exists
    mkdir -p /var/www/certbot
    
    # Use certbot Docker image in webroot mode
    if docker run --rm \
        -v "/etc/letsencrypt:/etc/letsencrypt" \
        -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
        -v "/var/www/certbot:/var/www/certbot" \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --non-interactive \
        --domains "$domains" \
        --cert-name "$cert_name" \
        --expand; then
        success "Certificate obtained for $domains using webroot"
        return 0
    else
        error_exit "Failed to obtain certificate for $domains"
    fi
}

# Obtain certificate with fallback methods
obtain_certificate() {
    local domains="$1"
    local cert_name="$2"
    
    # Try standalone mode first (requires stopping nginx)
    local nginx_was_running=false
    if stop_nginx; then
        nginx_was_running=true
    fi
    
    if obtain_certificate_docker "$domains" "$cert_name"; then
        if $nginx_was_running; then
            start_nginx
        fi
        return 0
    fi
    
    # If standalone failed, restart nginx and try webroot
    if $nginx_was_running; then
        start_nginx
        sleep 5  # Give nginx time to start
    fi
    
    obtain_certificate_webroot "$domains" "$cert_name"
}

# Verify certificate
verify_certificate() {
    local cert_name="$1"
    local cert_file="/etc/letsencrypt/live/$cert_name/cert.pem"
    
    if [[ -f "$cert_file" ]]; then
        log "Verifying certificate for $cert_name..."
        local expiry=$(openssl x509 -in "$cert_file" -noout -enddate | cut -d= -f2)
        success "Certificate for $cert_name is valid until: $expiry"
        
        # Check if certificate expires in less than 30 days
        local expiry_epoch=$(date -d "$expiry" +%s)
        local current_epoch=$(date +%s)
        local days_until_expiry=$(( (expiry_epoch - current_epoch) / 86400 ))
        
        if [[ $days_until_expiry -lt 30 ]]; then
            warning "Certificate for $cert_name expires in $days_until_expiry days"
        fi
        return 0
    else
        warning "Certificate file not found: $cert_file"
        return 1
    fi
}

# Main execution
main() {
    log "Starting Docker-based SSL certificate obtainment process..."
    
    # Setup directories
    setup_directories
    
    # Check DNS for all domains
    check_dns "$DOMAINS_PRIMARY"
    check_dns "$DOMAINS_TECHNICAL"
    
    # Obtain certificates
    obtain_certificate "$DOMAINS_PRIMARY" "insflow.ru"
    obtain_certificate "$DOMAINS_TECHNICAL" "insflow.tw1.su"
    
    # Verify certificates
    if verify_certificate "insflow.ru" && verify_certificate "insflow.tw1.su"; then
        success "SSL certificate obtainment completed successfully"
        log "All certificates have been obtained and verified"
    else
        warning "Some certificates may not have been obtained successfully"
        log "Certificate obtainment completed with warnings"
    fi
}

# Run main function
main "$@"
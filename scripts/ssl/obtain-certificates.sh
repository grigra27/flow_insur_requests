#!/bin/bash

# SSL Certificate Obtainment Script for Timeweb Deployment
# This script obtains Let's Encrypt certificates for all domains

set -e

# Configuration
EMAIL="admin@insflow.ru"
DOMAINS_PRIMARY="insflow.ru,zs.insflow.ru"
DOMAINS_TECHNICAL="insflow.tw1.su,zs.insflow.tw1.su"
WEBROOT_PATH="/var/www/html"
CERT_PATH="/etc/letsencrypt/live"
LOG_FILE="/var/log/ssl-certificates.log"

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error_exit "This script must be run as root"
    fi
}

# Check if certbot is installed
check_certbot() {
    if ! command -v certbot &> /dev/null; then
        log "Installing certbot..."
        apt update
        apt install -y certbot python3-certbot-nginx
        success "Certbot installed successfully"
    else
        log "Certbot is already installed"
    fi
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

# Stop nginx temporarily for standalone mode
stop_nginx() {
    if docker ps | grep -q nginx; then
        log "Stopping nginx container for certificate generation..."
        docker-compose -f /opt/insflow-system/docker-compose.timeweb.yml stop nginx
        success "Nginx stopped"
    fi
}

# Start nginx after certificate generation
start_nginx() {
    log "Starting nginx container..."
    docker-compose -f /opt/insflow-system/docker-compose.timeweb.yml start nginx
    success "Nginx started"
}

# Obtain certificate for a set of domains
obtain_certificate() {
    local domains="$1"
    local cert_name="$2"
    
    log "Obtaining certificate for domains: $domains"
    
    # Use standalone mode since we're in Docker environment
    if certbot certonly \
        --standalone \
        --email "$EMAIL" \
        --agree-tos \
        --non-interactive \
        --domains "$domains" \
        --cert-name "$cert_name" \
        --expand; then
        success "Certificate obtained for $domains"
    else
        error_exit "Failed to obtain certificate for $domains"
    fi
}

# Verify certificate
verify_certificate() {
    local cert_name="$1"
    local cert_file="$CERT_PATH/$cert_name/cert.pem"
    
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
    else
        error_exit "Certificate file not found: $cert_file"
    fi
}

# Main execution
main() {
    log "Starting SSL certificate obtainment process..."
    
    check_root
    check_certbot
    
    # Check DNS for all domains
    check_dns "$DOMAINS_PRIMARY"
    check_dns "$DOMAINS_TECHNICAL"
    
    # Stop nginx for standalone mode
    stop_nginx
    
    # Obtain certificates
    obtain_certificate "$DOMAINS_PRIMARY" "insflow.ru"
    obtain_certificate "$DOMAINS_TECHNICAL" "insflow.tw1.su"
    
    # Verify certificates
    verify_certificate "insflow.ru"
    verify_certificate "insflow.tw1.su"
    
    # Start nginx
    start_nginx
    
    success "SSL certificate obtainment completed successfully"
    log "All certificates have been obtained and verified"
}

# Run main function
main "$@"
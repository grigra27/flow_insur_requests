#!/bin/bash

# Post-Renewal Hook Script
# This script runs after successful certificate renewal

set -e

# Configuration
LOG_FILE="/var/log/ssl-certificates.log"
DOCKER_COMPOSE_FILE="/opt/insflow-system/docker-compose.yml"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Success message
success() {
    echo -e "${GREEN}SUCCESS: $1${NC}"
    log "SUCCESS: $1"
}

# Info message
info() {
    echo -e "${BLUE}INFO: $1${NC}"
    log "INFO: $1"
}

# Update certificate permissions
update_permissions() {
    info "Updating certificate permissions..."
    
    # Ensure certificates are readable by nginx user
    chmod -R 644 /etc/letsencrypt/live/
    chmod -R 644 /etc/letsencrypt/archive/
    
    success "Certificate permissions updated"
}

# Reload nginx configuration
reload_nginx() {
    info "Reloading nginx configuration..."
    
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec nginx nginx -s reload; then
        success "Nginx configuration reloaded"
    else
        # If exec fails, try restart
        info "Exec failed, restarting nginx container..."
        docker-compose -f "$DOCKER_COMPOSE_FILE" restart nginx
        success "Nginx container restarted"
    fi
}

# Test SSL endpoints
test_ssl_endpoints() {
    info "Testing SSL endpoints..."
    
    local domains=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
    
    for domain in "${domains[@]}"; do
        if timeout 10 openssl s_client -connect "$domain:443" -servername "$domain" < /dev/null > /dev/null 2>&1; then
            success "SSL test passed for $domain"
        else
            log "WARNING: SSL test failed for $domain"
        fi
    done
}

# Main execution
main() {
    log "Running post-renewal hook..."
    
    update_permissions
    reload_nginx
    test_ssl_endpoints
    
    success "Post-renewal hook completed"
}

# Run main function
main "$@"
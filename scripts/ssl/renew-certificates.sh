#!/bin/bash

# SSL Certificate Renewal Script
# This script handles automatic renewal of Let's Encrypt certificates

set -e

# Configuration
LOG_FILE="/var/log/ssl-certificates.log"
DOCKER_COMPOSE_FILE="/opt/insflow-system/docker-compose.yml"
NGINX_CONTAINER_NAME="nginx"
RENEWAL_HOOK_SCRIPT="/opt/insflow-system/scripts/ssl/post-renewal-hook.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# Info message
info() {
    echo -e "${BLUE}INFO: $1${NC}"
    log "INFO: $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error_exit "This script must be run as root"
    fi
}

# Check if certbot is available
check_certbot() {
    if ! command -v certbot &> /dev/null; then
        error_exit "Certbot is not installed"
    fi
}

# Check if docker-compose file exists
check_docker_compose() {
    if [[ ! -f "$DOCKER_COMPOSE_FILE" ]]; then
        error_exit "Docker compose file not found: $DOCKER_COMPOSE_FILE"
    fi
}

# Stop nginx container
stop_nginx() {
    info "Stopping nginx container for certificate renewal..."
    if docker-compose -f "$DOCKER_COMPOSE_FILE" stop "$NGINX_CONTAINER_NAME"; then
        success "Nginx container stopped"
        return 0
    else
        error_exit "Failed to stop nginx container"
    fi
}

# Start nginx container
start_nginx() {
    info "Starting nginx container..."
    if docker-compose -f "$DOCKER_COMPOSE_FILE" start "$NGINX_CONTAINER_NAME"; then
        success "Nginx container started"
        return 0
    else
        error_exit "Failed to start nginx container"
    fi
}

# Restart nginx container
restart_nginx() {
    info "Restarting nginx container to reload certificates..."
    if docker-compose -f "$DOCKER_COMPOSE_FILE" restart "$NGINX_CONTAINER_NAME"; then
        success "Nginx container restarted"
        return 0
    else
        warning "Failed to restart nginx container"
        return 1
    fi
}

# Check if any certificates were renewed
check_renewal_status() {
    local renewal_log="/var/log/letsencrypt/letsencrypt.log"
    local today=$(date '+%Y-%m-%d')
    
    if [[ -f "$renewal_log" ]]; then
        if grep -q "Certificate not yet due for renewal" "$renewal_log"; then
            info "No certificates were due for renewal"
            return 1
        elif grep -q "$today.*Renewing certificate" "$renewal_log"; then
            success "Certificates were renewed today"
            return 0
        fi
    fi
    
    # Fallback: assume renewal happened if we can't determine
    warning "Could not determine renewal status from logs"
    return 0
}

# Perform certificate renewal
renew_certificates() {
    info "Starting certificate renewal process..."
    
    # Stop nginx for standalone renewal
    stop_nginx
    
    # Perform renewal
    if certbot renew --standalone --quiet --no-self-upgrade; then
        success "Certificate renewal completed successfully"
        local renewal_occurred=0
    else
        error_exit "Certificate renewal failed"
    fi
    
    # Start nginx back up
    start_nginx
    
    # Check if any certificates were actually renewed
    if check_renewal_status; then
        info "Certificates were renewed, restarting nginx..."
        restart_nginx
        
        # Run post-renewal hook if it exists
        if [[ -f "$RENEWAL_HOOK_SCRIPT" && -x "$RENEWAL_HOOK_SCRIPT" ]]; then
            info "Running post-renewal hook..."
            "$RENEWAL_HOOK_SCRIPT"
        fi
    else
        info "No certificates were renewed, nginx restart not needed"
    fi
}

# Test certificate renewal (dry run)
test_renewal() {
    info "Testing certificate renewal (dry run)..."
    
    if certbot renew --dry-run --quiet; then
        success "Certificate renewal test passed"
        return 0
    else
        error_exit "Certificate renewal test failed"
    fi
}

# Verify certificates after renewal
verify_certificates() {
    info "Verifying certificates after renewal..."
    
    local check_script="/opt/insflow-system/scripts/ssl/check-certificates.sh"
    if [[ -f "$check_script" && -x "$check_script" ]]; then
        "$check_script" --quiet
        if [[ $? -eq 0 ]]; then
            success "Certificate verification passed"
        else
            warning "Certificate verification found issues"
        fi
    else
        warning "Certificate check script not found, skipping verification"
    fi
}

# Send notification (placeholder for future implementation)
send_notification() {
    local status="$1"
    local message="$2"
    
    # Log the notification (can be extended to send emails, webhooks, etc.)
    log "NOTIFICATION [$status]: $message"
    
    # Future: Add email notification, Slack webhook, etc.
    # Example:
    # echo "$message" | mail -s "SSL Certificate $status" admin@insflow.ru
}

# Main execution
main() {
    log "Starting SSL certificate renewal script..."
    
    # Parse command line arguments
    local dry_run=false
    local force_restart=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                dry_run=true
                shift
                ;;
            --force-restart)
                force_restart=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo "Options:"
                echo "  --dry-run       Test renewal without actually renewing"
                echo "  --force-restart Force nginx restart even if no renewal occurred"
                echo "  --help, -h      Show this help message"
                exit 0
                ;;
            *)
                error_exit "Unknown option: $1"
                ;;
        esac
    done
    
    # Perform checks
    check_root
    check_certbot
    check_docker_compose
    
    if [[ "$dry_run" == true ]]; then
        test_renewal
        success "Dry run completed successfully"
    else
        # Perform actual renewal
        renew_certificates
        
        # Verify certificates
        verify_certificates
        
        # Force restart if requested
        if [[ "$force_restart" == true ]]; then
            restart_nginx
        fi
        
        success "Certificate renewal process completed"
        send_notification "SUCCESS" "SSL certificates renewed successfully"
    fi
    
    log "SSL certificate renewal script completed"
}

# Handle script interruption
trap 'error_exit "Script interrupted"; exit 130' INT TERM

# Run main function
main "$@"
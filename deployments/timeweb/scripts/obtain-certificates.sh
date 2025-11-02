#!/bin/bash

# Certificate Acquisition Script for Timeweb Deployment
# 
# This script obtains Let's Encrypt certificates for all configured domains
# and implements proper error handling with fallback mechanisms.
#
# Requirements: 2.2, 4.2
#
# Usage:
#   ./obtain-certificates.sh [--staging] [--force-renewal]
#
# Options:
#   --staging        Use Let's Encrypt staging environment (for testing)
#   --force-renewal  Force renewal of existing certificates
#   --help          Show this help message

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/certificate-acquisition.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Default options
STAGING_MODE=false
FORCE_RENEWAL=false
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Create logs directory if it doesn't exist
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Log to file
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    # Log to console with colors
    case "$level" in
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message" >&2
            ;;
        "WARN")
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        "INFO")
            echo -e "${GREEN}[INFO]${NC} $message"
            ;;
        "DEBUG")
            if [[ "$VERBOSE" == "true" ]]; then
                echo -e "${BLUE}[DEBUG]${NC} $message"
            fi
            ;;
    esac
}

# Error handling
error_exit() {
    log "ERROR" "$1"
    exit 1
}

# Show help
show_help() {
    cat << EOF
Certificate Acquisition Script for Timeweb Deployment

This script obtains Let's Encrypt certificates for all configured domains
and implements proper error handling with fallback mechanisms.

Usage:
    $0 [OPTIONS]

Options:
    --staging        Use Let's Encrypt staging environment (for testing)
    --force-renewal  Force renewal of existing certificates
    --verbose        Enable verbose output
    --help          Show this help message

Environment Variables:
    DOMAINS         Comma-separated list of domains (required)
    SSL_EMAIL       Email for Let's Encrypt registration (required)
    CERTBOT_STAGING Override staging mode (true/false)

Examples:
    # Obtain certificates for production
    $0

    # Test certificate acquisition with staging
    $0 --staging

    # Force renewal of existing certificates
    $0 --force-renewal

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --staging)
                STAGING_MODE=true
                shift
                ;;
            --force-renewal)
                FORCE_RENEWAL=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                error_exit "Unknown option: $1. Use --help for usage information."
                ;;
        esac
    done
}

# Load environment variables
load_environment() {
    local env_file="${PROJECT_DIR}/.env"
    
    if [[ ! -f "$env_file" ]]; then
        error_exit "Environment file not found: $env_file"
    fi
    
    log "INFO" "Loading environment from: $env_file"
    
    # Source environment file
    set -a
    source "$env_file"
    set +a
    
    # Override staging mode if set via environment
    if [[ "${CERTBOT_STAGING:-}" == "true" ]]; then
        STAGING_MODE=true
    fi
    
    # Validate required environment variables
    if [[ -z "${DOMAINS:-}" ]]; then
        error_exit "DOMAINS environment variable is required"
    fi
    
    if [[ -z "${SSL_EMAIL:-}" ]]; then
        error_exit "SSL_EMAIL environment variable is required"
    fi
    
    log "INFO" "Configuration loaded:"
    log "INFO" "  Domains: $DOMAINS"
    log "INFO" "  Email: $SSL_EMAIL"
    log "INFO" "  Staging mode: $STAGING_MODE"
    log "INFO" "  Force renewal: $FORCE_RENEWAL"
}

# Check prerequisites
check_prerequisites() {
    log "INFO" "Checking prerequisites..."
    
    # Check if Docker Compose is available
    if ! command -v docker &> /dev/null; then
        error_exit "Docker is not installed or not in PATH"
    fi
    
    if ! command -v docker compose &> /dev/null; then
        error_exit "Docker Compose is not installed or not in PATH"
    fi
    
    # Check if compose file exists
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error_exit "Docker Compose file not found: $COMPOSE_FILE"
    fi
    
    # Check if nginx service is running (required for webroot validation)
    if ! docker compose -f "$COMPOSE_FILE" ps nginx | grep -q "Up"; then
        log "WARN" "Nginx service is not running. Starting nginx for certificate validation..."
        docker compose -f "$COMPOSE_FILE" up -d nginx || error_exit "Failed to start nginx service"
        
        # Wait for nginx to be ready
        log "INFO" "Waiting for nginx to be ready..."
        sleep 10
        
        # Verify nginx is responding
        if ! docker compose -f "$COMPOSE_FILE" exec nginx nginx -t; then
            error_exit "Nginx configuration test failed"
        fi
    fi
    
    log "INFO" "Prerequisites check completed successfully"
}

# Prepare certificate directories
prepare_directories() {
    log "INFO" "Preparing certificate directories..."
    
    # Create webroot directory for ACME challenges
    docker compose -f "$COMPOSE_FILE" exec nginx mkdir -p /var/www/certbot || true
    
    # Ensure proper permissions
    docker compose -f "$COMPOSE_FILE" exec nginx chown -R nginx:nginx /var/www/certbot || true
    
    log "INFO" "Certificate directories prepared"
}

# Validate domain accessibility
validate_domains() {
    local domains_array
    IFS=',' read -ra domains_array <<< "$DOMAINS"
    
    log "INFO" "Validating domain accessibility..."
    
    local failed_domains=()
    
    for domain in "${domains_array[@]}"; do
        domain=$(echo "$domain" | xargs) # Trim whitespace
        
        log "DEBUG" "Checking domain: $domain"
        
        # Test HTTP accessibility (required for webroot validation)
        if curl -s -f -L --max-time 10 "http://$domain/.well-known/acme-challenge/test" > /dev/null 2>&1; then
            log "DEBUG" "Domain $domain is accessible via HTTP"
        else
            # Create a test file to verify webroot access
            docker compose -f "$COMPOSE_FILE" exec nginx sh -c "echo 'test' > /var/www/certbot/test" || true
            
            if curl -s -f -L --max-time 10 "http://$domain/.well-known/acme-challenge/test" > /dev/null 2>&1; then
                log "DEBUG" "Domain $domain webroot is accessible"
            else
                log "WARN" "Domain $domain may not be accessible for ACME validation"
                failed_domains+=("$domain")
            fi
            
            # Clean up test file
            docker compose -f "$COMPOSE_FILE" exec nginx rm -f /var/www/certbot/test || true
        fi
    done
    
    if [[ ${#failed_domains[@]} -gt 0 ]]; then
        log "WARN" "Some domains may not be accessible: ${failed_domains[*]}"
        log "WARN" "Certificate acquisition may fail for these domains"
    fi
}

# Obtain certificates for a single domain
obtain_certificate_for_domain() {
    local domain="$1"
    local staging_flag=""
    local force_flag=""
    
    if [[ "$STAGING_MODE" == "true" ]]; then
        staging_flag="--staging"
    fi
    
    if [[ "$FORCE_RENEWAL" == "true" ]]; then
        force_flag="--force-renewal"
    fi
    
    log "INFO" "Obtaining certificate for domain: $domain"
    
    # Run certbot to obtain certificate
    local certbot_cmd="certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email $SSL_EMAIL \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        $staging_flag \
        $force_flag \
        -d $domain"
    
    log "DEBUG" "Running certbot command: $certbot_cmd"
    
    if docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "$certbot_cmd"; then
        log "INFO" "Certificate obtained successfully for domain: $domain"
        return 0
    else
        log "ERROR" "Failed to obtain certificate for domain: $domain"
        return 1
    fi
}

# Obtain certificates for all domains
obtain_certificates() {
    local domains_array
    IFS=',' read -ra domains_array <<< "$DOMAINS"
    
    log "INFO" "Starting certificate acquisition for ${#domains_array[@]} domains..."
    
    local successful_domains=()
    local failed_domains=()
    
    for domain in "${domains_array[@]}"; do
        domain=$(echo "$domain" | xargs) # Trim whitespace
        
        if obtain_certificate_for_domain "$domain"; then
            successful_domains+=("$domain")
        else
            failed_domains+=("$domain")
        fi
    done
    
    # Report results
    log "INFO" "Certificate acquisition completed:"
    log "INFO" "  Successful: ${#successful_domains[@]} domains"
    log "INFO" "  Failed: ${#failed_domains[@]} domains"
    
    if [[ ${#successful_domains[@]} -gt 0 ]]; then
        log "INFO" "Successful domains: ${successful_domains[*]}"
    fi
    
    if [[ ${#failed_domains[@]} -gt 0 ]]; then
        log "WARN" "Failed domains: ${failed_domains[*]}"
        
        # If all domains failed, this is a critical error
        if [[ ${#successful_domains[@]} -eq 0 ]]; then
            error_exit "Certificate acquisition failed for all domains"
        fi
    fi
    
    return 0
}

# Verify obtained certificates
verify_certificates() {
    local domains_array
    IFS=',' read -ra domains_array <<< "$DOMAINS"
    
    log "INFO" "Verifying obtained certificates..."
    
    local verified_count=0
    
    for domain in "${domains_array[@]}"; do
        domain=$(echo "$domain" | xargs) # Trim whitespace
        
        # Check if certificate files exist
        if docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "test -f /etc/letsencrypt/live/$domain/fullchain.pem && test -f /etc/letsencrypt/live/$domain/privkey.pem"; then
            log "INFO" "Certificate files verified for domain: $domain"
            
            # Check certificate validity
            if docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "openssl x509 -in /etc/letsencrypt/live/$domain/fullchain.pem -noout -checkend 86400"; then
                log "INFO" "Certificate is valid for domain: $domain"
                ((verified_count++))
            else
                log "WARN" "Certificate may be expired or invalid for domain: $domain"
            fi
        else
            log "WARN" "Certificate files not found for domain: $domain"
        fi
    done
    
    log "INFO" "Certificate verification completed: $verified_count/${#domains_array[@]} certificates verified"
    
    if [[ $verified_count -eq 0 ]]; then
        error_exit "No valid certificates found"
    fi
    
    return 0
}

# Reload nginx configuration
reload_nginx() {
    log "INFO" "Reloading nginx configuration..."
    
    # Test nginx configuration first
    if docker compose -f "$COMPOSE_FILE" exec nginx nginx -t; then
        # Reload nginx
        if docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload; then
            log "INFO" "Nginx configuration reloaded successfully"
        else
            log "WARN" "Failed to reload nginx configuration"
        fi
    else
        log "ERROR" "Nginx configuration test failed - not reloading"
    fi
}

# Main function
main() {
    log "INFO" "Starting certificate acquisition script..."
    log "INFO" "Script version: 1.0"
    log "INFO" "Working directory: $PROJECT_DIR"
    
    # Parse command line arguments
    parse_args "$@"
    
    # Load environment configuration
    load_environment
    
    # Check prerequisites
    check_prerequisites
    
    # Prepare directories
    prepare_directories
    
    # Validate domain accessibility
    validate_domains
    
    # Obtain certificates
    obtain_certificates
    
    # Verify obtained certificates
    verify_certificates
    
    # Reload nginx to use new certificates
    reload_nginx
    
    log "INFO" "Certificate acquisition completed successfully!"
    log "INFO" "Log file: $LOG_FILE"
    
    # Show next steps
    echo
    echo -e "${GREEN}Certificate acquisition completed!${NC}"
    echo
    echo "Next steps:"
    echo "1. Verify HTTPS is working: curl -I https://your-domain.com"
    echo "2. Set up automatic renewal with: ./setup-certificate-renewal.sh"
    echo "3. Monitor certificate expiry with: ./monitor-certificates.sh"
    echo
    echo "Log file: $LOG_FILE"
}

# Run main function with all arguments
main "$@"
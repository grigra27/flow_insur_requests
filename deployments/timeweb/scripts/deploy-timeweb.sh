#!/bin/bash

# Main Deployment Script for Timeweb HTTPS Deployment
# 
# This script provides a comprehensive deployment solution that handles:
# - Certificate detection and automatic configuration selection
# - SSL availability assessment
# - Automatic fallback to HTTP when certificates are not available
# - Health checks and service validation
#
# Requirements: 4.1, 4.2
#
# Usage:
#   ./deploy-timeweb.sh [OPTIONS]
#
# Options:
#   --http-only      Force HTTP-only deployment (skip SSL)
#   --force-ssl      Force SSL deployment (fail if certificates unavailable)
#   --staging        Use staging certificates for testing
#   --no-health      Skip health checks after deployment
#   --verbose        Enable verbose output
#   --help          Show this help message

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/deployment.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Default options
HTTP_ONLY=false
FORCE_SSL=false
STAGING_MODE=false
SKIP_HEALTH_CHECKS=false
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Deployment state
SSL_AVAILABLE=false
DEPLOYMENT_MODE=""
DEPLOYED_SERVICES=()

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
        "STEP")
            echo -e "${CYAN}[STEP]${NC} $message"
            ;;
    esac
}

# Error handling
error_exit() {
    log "ERROR" "$1"
    echo
    echo -e "${RED}Deployment failed!${NC}"
    echo "Check the log file for details: $LOG_FILE"
    exit 1
}

# Cleanup function for graceful shutdown
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log "WARN" "Deployment interrupted. Cleaning up..."
        # Stop any partially started services
        docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
    fi
    exit $exit_code
}

trap cleanup EXIT INT TERM

# Show help
show_help() {
    cat << EOF
Main Deployment Script for Timeweb HTTPS Deployment

This script provides a comprehensive deployment solution that handles certificate
detection, automatic configuration selection, and SSL availability assessment.

Usage:
    $0 [OPTIONS]

Options:
    --http-only      Force HTTP-only deployment (skip SSL)
    --force-ssl      Force SSL deployment (fail if certificates unavailable)
    --staging        Use staging certificates for testing
    --no-health      Skip health checks after deployment
    --verbose        Enable verbose output
    --help          Show this help message

Environment Variables:
    DOMAINS         Comma-separated list of domains
    SSL_EMAIL       Email for Let's Encrypt registration
    DOCKER_IMAGE    Docker image to deploy
    DB_NAME         Database name
    DB_USER         Database user
    DB_PASSWORD     Database password

Deployment Modes:
    1. HTTPS Mode: Full SSL deployment with certificates
    2. HTTP Mode: HTTP-only deployment (fallback)
    3. Mixed Mode: HTTP with SSL preparation (transition)

Examples:
    # Automatic deployment (recommended)
    $0

    # Force HTTP-only deployment
    $0 --http-only

    # Force SSL deployment (fail if no certificates)
    $0 --force-ssl

    # Deploy with staging certificates
    $0 --staging

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --http-only)
                HTTP_ONLY=true
                shift
                ;;
            --force-ssl)
                FORCE_SSL=true
                shift
                ;;
            --staging)
                STAGING_MODE=true
                shift
                ;;
            --no-health)
                SKIP_HEALTH_CHECKS=true
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
    
    # Validate conflicting options
    if [[ "$HTTP_ONLY" == "true" && "$FORCE_SSL" == "true" ]]; then
        error_exit "Cannot use --http-only and --force-ssl together"
    fi
}

# Load and validate environment
load_environment() {
    local env_file="${PROJECT_DIR}/.env"
    
    if [[ ! -f "$env_file" ]]; then
        error_exit "Environment file not found: $env_file. Please create it from .env.example"
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
    local required_vars=("DOCKER_IMAGE" "DB_NAME" "DB_USER" "DB_PASSWORD")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        error_exit "Missing required environment variables: ${missing_vars[*]}"
    fi
    
    log "INFO" "Environment configuration loaded successfully"
    log "DEBUG" "Docker image: ${DOCKER_IMAGE}"
    log "DEBUG" "Database: ${DB_NAME}"
    log "DEBUG" "Domains: ${DOMAINS:-'not set'}"
    log "DEBUG" "SSL Email: ${SSL_EMAIL:-'not set'}"
}

# Check prerequisites
check_prerequisites() {
    log "STEP" "Checking deployment prerequisites..."
    
    # Check Docker and Docker Compose
    if ! command -v docker &> /dev/null; then
        error_exit "Docker is not installed or not in PATH"
    fi
    
    if ! command -v docker compose &> /dev/null; then
        error_exit "Docker Compose is not installed or not in PATH"
    fi
    
    # Check Docker daemon
    if ! docker info &> /dev/null; then
        error_exit "Docker daemon is not running"
    fi
    
    # Check compose file
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error_exit "Docker Compose file not found: $COMPOSE_FILE"
    fi
    
    # Validate compose file
    if ! docker compose -f "$COMPOSE_FILE" config &> /dev/null; then
        error_exit "Docker Compose configuration is invalid"
    fi
    
    # Check required scripts
    local required_scripts=("obtain-certificates.sh" "monitor-certificates.sh")
    for script in "${required_scripts[@]}"; do
        if [[ ! -f "${SCRIPT_DIR}/${script}" ]]; then
            error_exit "Required script not found: ${script}"
        fi
        
        if [[ ! -x "${SCRIPT_DIR}/${script}" ]]; then
            log "WARN" "Making script executable: ${script}"
            chmod +x "${SCRIPT_DIR}/${script}"
        fi
    done
    
    log "INFO" "Prerequisites check completed successfully"
}

# Detect SSL certificate availability
detect_ssl_certificates() {
    log "STEP" "Detecting SSL certificate availability..."
    
    # Skip SSL detection if HTTP-only mode is forced
    if [[ "$HTTP_ONLY" == "true" ]]; then
        log "INFO" "HTTP-only mode forced - skipping SSL detection"
        SSL_AVAILABLE=false
        return 0
    fi
    
    # Check if domains are configured
    if [[ -z "${DOMAINS:-}" ]]; then
        log "WARN" "No domains configured - SSL not available"
        SSL_AVAILABLE=false
        return 0
    fi
    
    # Check if SSL email is configured
    if [[ -z "${SSL_EMAIL:-}" ]]; then
        log "WARN" "No SSL email configured - SSL not available"
        SSL_AVAILABLE=false
        return 0
    fi
    
    # Start minimal services to check for existing certificates
    log "INFO" "Starting services to check certificate availability..."
    docker compose -f "$COMPOSE_FILE" up -d db web nginx
    
    # Wait for services to be ready
    sleep 10
    
    # Check for existing certificates
    local domains_array
    IFS=',' read -ra domains_array <<< "$DOMAINS"
    local cert_count=0
    local valid_cert_count=0
    
    for domain in "${domains_array[@]}"; do
        domain=$(echo "$domain" | xargs) # Trim whitespace
        
        log "DEBUG" "Checking certificate for domain: $domain"
        
        # Check if certificate files exist
        if docker compose -f "$COMPOSE_FILE" run --rm --no-deps certbot sh -c "test -f /etc/letsencrypt/live/$domain/fullchain.pem && test -f /etc/letsencrypt/live/$domain/privkey.pem" 2>/dev/null; then
            ((cert_count++))
            log "DEBUG" "Certificate files found for domain: $domain"
            
            # Check if certificate is valid (not expired)
            if docker compose -f "$COMPOSE_FILE" run --rm --no-deps certbot sh -c "openssl x509 -in /etc/letsencrypt/live/$domain/fullchain.pem -noout -checkend 86400" 2>/dev/null; then
                ((valid_cert_count++))
                log "DEBUG" "Valid certificate found for domain: $domain"
            else
                log "WARN" "Certificate expired or invalid for domain: $domain"
            fi
        else
            log "DEBUG" "No certificate found for domain: $domain"
        fi
    done
    
    # Determine SSL availability
    if [[ $valid_cert_count -gt 0 ]]; then
        SSL_AVAILABLE=true
        log "INFO" "SSL certificates available: $valid_cert_count/${#domains_array[@]} domains have valid certificates"
    else
        SSL_AVAILABLE=false
        log "INFO" "No valid SSL certificates found"
        
        if [[ $cert_count -gt 0 ]]; then
            log "WARN" "Found $cert_count certificate(s) but none are valid"
        fi
    fi
    
    # Handle force SSL mode
    if [[ "$FORCE_SSL" == "true" && "$SSL_AVAILABLE" == "false" ]]; then
        error_exit "SSL deployment forced but no valid certificates available"
    fi
}

# Obtain SSL certificates if needed
obtain_ssl_certificates() {
    if [[ "$HTTP_ONLY" == "true" ]]; then
        log "INFO" "HTTP-only mode - skipping certificate acquisition"
        return 0
    fi
    
    if [[ "$SSL_AVAILABLE" == "true" ]]; then
        log "INFO" "Valid SSL certificates already available"
        return 0
    fi
    
    if [[ -z "${DOMAINS:-}" || -z "${SSL_EMAIL:-}" ]]; then
        log "WARN" "SSL configuration incomplete - skipping certificate acquisition"
        return 0
    fi
    
    log "STEP" "Obtaining SSL certificates..."
    
    # Prepare certificate acquisition arguments
    local cert_args=()
    if [[ "$STAGING_MODE" == "true" ]]; then
        cert_args+=("--staging")
    fi
    
    if [[ "$VERBOSE" == "true" ]]; then
        cert_args+=("--verbose")
    fi
    
    # Run certificate acquisition script
    if "${SCRIPT_DIR}/obtain-certificates.sh" "${cert_args[@]}"; then
        log "INFO" "Certificate acquisition completed successfully"
        SSL_AVAILABLE=true
    else
        log "WARN" "Certificate acquisition failed"
        SSL_AVAILABLE=false
        
        if [[ "$FORCE_SSL" == "true" ]]; then
            error_exit "SSL deployment forced but certificate acquisition failed"
        fi
    fi
}

# Determine deployment mode
determine_deployment_mode() {
    log "STEP" "Determining deployment mode..."
    
    if [[ "$HTTP_ONLY" == "true" ]]; then
        DEPLOYMENT_MODE="HTTP"
        log "INFO" "Deployment mode: HTTP (forced)"
    elif [[ "$SSL_AVAILABLE" == "true" ]]; then
        DEPLOYMENT_MODE="HTTPS"
        log "INFO" "Deployment mode: HTTPS (certificates available)"
    else
        DEPLOYMENT_MODE="HTTP"
        log "INFO" "Deployment mode: HTTP (fallback - no certificates)"
    fi
    
    # Update environment variables based on deployment mode
    if [[ "$DEPLOYMENT_MODE" == "HTTPS" ]]; then
        export ENABLE_HTTPS=True
        export SSL_REDIRECT=True
        export SECURE_COOKIES=True
    else
        export ENABLE_HTTPS=False
        export SSL_REDIRECT=False
        export SECURE_COOKIES=False
    fi
    
    log "DEBUG" "HTTPS settings: ENABLE_HTTPS=$ENABLE_HTTPS, SSL_REDIRECT=$SSL_REDIRECT"
}

# Deploy services
deploy_services() {
    log "STEP" "Deploying services in $DEPLOYMENT_MODE mode..."
    
    # Stop any existing services
    log "INFO" "Stopping existing services..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    
    # Pull latest images
    log "INFO" "Pulling latest Docker images..."
    docker compose -f "$COMPOSE_FILE" pull
    
    # Start core services
    log "INFO" "Starting core services (db, web, nginx)..."
    docker compose -f "$COMPOSE_FILE" up -d db web nginx
    
    DEPLOYED_SERVICES=("db" "web" "nginx")
    
    # Start SSL services if in HTTPS mode
    if [[ "$DEPLOYMENT_MODE" == "HTTPS" ]]; then
        log "INFO" "Starting SSL services (certbot)..."
        docker compose -f "$COMPOSE_FILE" --profile ssl up -d certbot
        DEPLOYED_SERVICES+=("certbot")
    fi
    
    log "INFO" "Services deployed: ${DEPLOYED_SERVICES[*]}"
}

# Wait for services to be ready
wait_for_services() {
    log "STEP" "Waiting for services to be ready..."
    
    local max_wait=300  # 5 minutes
    local wait_interval=10
    local elapsed=0
    
    while [[ $elapsed -lt $max_wait ]]; do
        log "DEBUG" "Checking service health... (${elapsed}s/${max_wait}s)"
        
        # Check if all services are healthy
        local all_healthy=true
        
        for service in "${DEPLOYED_SERVICES[@]}"; do
            if [[ "$service" == "certbot" ]]; then
                # Certbot doesn't have health checks, just check if it's running
                if ! docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
                    log "DEBUG" "Service $service is not running"
                    all_healthy=false
                    break
                fi
            else
                # Check health status for services with health checks
                local health_status
                health_status=$(docker compose -f "$COMPOSE_FILE" ps "$service" --format "table {{.Service}}\t{{.Status}}" | tail -n +2 | awk '{print $2}')
                
                if [[ "$health_status" != *"healthy"* && "$health_status" != *"Up"* ]]; then
                    log "DEBUG" "Service $service is not healthy: $health_status"
                    all_healthy=false
                    break
                fi
            fi
        done
        
        if [[ "$all_healthy" == "true" ]]; then
            log "INFO" "All services are ready"
            return 0
        fi
        
        sleep $wait_interval
        elapsed=$((elapsed + wait_interval))
    done
    
    log "WARN" "Services did not become ready within ${max_wait} seconds"
    
    # Show service status for debugging
    log "DEBUG" "Current service status:"
    docker compose -f "$COMPOSE_FILE" ps
    
    return 1
}

# Perform health checks
perform_health_checks() {
    if [[ "$SKIP_HEALTH_CHECKS" == "true" ]]; then
        log "INFO" "Health checks skipped"
        return 0
    fi
    
    log "STEP" "Performing deployment health checks..."
    
    local health_check_passed=true
    
    # Check database connectivity
    log "INFO" "Checking database connectivity..."
    if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U "$DB_USER" -d "$DB_NAME"; then
        log "INFO" "Database connectivity: OK"
    else
        log "ERROR" "Database connectivity: FAILED"
        health_check_passed=false
    fi
    
    # Check web application
    log "INFO" "Checking web application..."
    if docker compose -f "$COMPOSE_FILE" exec -T web python /app/simple_healthcheck.py; then
        log "INFO" "Web application: OK"
    else
        log "ERROR" "Web application: FAILED"
        health_check_passed=false
    fi
    
    # Check nginx
    log "INFO" "Checking nginx configuration..."
    if docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t; then
        log "INFO" "Nginx configuration: OK"
    else
        log "ERROR" "Nginx configuration: FAILED"
        health_check_passed=false
    fi
    
    # Check HTTP accessibility
    log "INFO" "Checking HTTP accessibility..."
    local http_check_passed=false
    for i in {1..5}; do
        if curl -s -f -L --max-time 10 "http://localhost/healthz/" > /dev/null 2>&1; then
            log "INFO" "HTTP accessibility: OK"
            http_check_passed=true
            break
        else
            log "DEBUG" "HTTP check attempt $i failed, retrying..."
            sleep 2
        fi
    done
    
    if [[ "$http_check_passed" == "false" ]]; then
        log "ERROR" "HTTP accessibility: FAILED"
        health_check_passed=false
    fi
    
    # Check HTTPS accessibility (if in HTTPS mode)
    if [[ "$DEPLOYMENT_MODE" == "HTTPS" ]]; then
        log "INFO" "Checking HTTPS accessibility..."
        local https_check_passed=false
        for i in {1..5}; do
            if curl -s -f -L --max-time 10 --insecure "https://localhost/healthz/" > /dev/null 2>&1; then
                log "INFO" "HTTPS accessibility: OK"
                https_check_passed=true
                break
            else
                log "DEBUG" "HTTPS check attempt $i failed, retrying..."
                sleep 2
            fi
        done
        
        if [[ "$https_check_passed" == "false" ]]; then
            log "WARN" "HTTPS accessibility: FAILED (may be expected during initial setup)"
        fi
    fi
    
    # Check SSL certificate validity (if in HTTPS mode)
    if [[ "$DEPLOYMENT_MODE" == "HTTPS" && -n "${DOMAINS:-}" ]]; then
        log "INFO" "Checking SSL certificate validity..."
        local domains_array
        IFS=',' read -ra domains_array <<< "$DOMAINS"
        local first_domain
        first_domain=$(echo "${domains_array[0]}" | xargs)
        
        if docker compose -f "$COMPOSE_FILE" run --rm --no-deps certbot sh -c "openssl x509 -in /etc/letsencrypt/live/$first_domain/fullchain.pem -noout -dates" 2>/dev/null; then
            log "INFO" "SSL certificate validity: OK"
        else
            log "WARN" "SSL certificate validity: Could not verify"
        fi
    fi
    
    if [[ "$health_check_passed" == "true" ]]; then
        log "INFO" "All health checks passed"
        return 0
    else
        log "ERROR" "Some health checks failed"
        return 1
    fi
}

# Show deployment summary
show_deployment_summary() {
    log "STEP" "Deployment Summary"
    
    echo
    echo -e "${GREEN}=== Timeweb Deployment Summary ===${NC}"
    echo
    echo -e "Deployment Mode: ${CYAN}$DEPLOYMENT_MODE${NC}"
    echo -e "Services Deployed: ${CYAN}${DEPLOYED_SERVICES[*]}${NC}"
    echo -e "SSL Available: ${CYAN}$SSL_AVAILABLE${NC}"
    
    if [[ -n "${DOMAINS:-}" ]]; then
        echo -e "Configured Domains: ${CYAN}$DOMAINS${NC}"
    fi
    
    echo
    echo -e "${GREEN}Service Status:${NC}"
    docker compose -f "$COMPOSE_FILE" ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
    
    echo
    echo -e "${GREEN}Access URLs:${NC}"
    if [[ "$DEPLOYMENT_MODE" == "HTTPS" && -n "${DOMAINS:-}" ]]; then
        local domains_array
        IFS=',' read -ra domains_array <<< "$DOMAINS"
        for domain in "${domains_array[@]}"; do
            domain=$(echo "$domain" | xargs)
            echo -e "  HTTPS: ${CYAN}https://$domain${NC}"
            echo -e "  HTTP:  ${CYAN}http://$domain${NC} (redirects to HTTPS)"
        done
    else
        echo -e "  HTTP:  ${CYAN}http://localhost${NC}"
        if [[ -n "${DOMAINS:-}" ]]; then
            local domains_array
            IFS=',' read -ra domains_array <<< "$DOMAINS"
            for domain in "${domains_array[@]}"; do
                domain=$(echo "$domain" | xargs)
                echo -e "  HTTP:  ${CYAN}http://$domain${NC}"
            done
        fi
    fi
    
    echo
    echo -e "${GREEN}Log Files:${NC}"
    echo -e "  Deployment: ${CYAN}$LOG_FILE${NC}"
    echo -e "  Application: ${CYAN}${PROJECT_DIR}/logs/django.log${NC}"
    echo -e "  Nginx: ${CYAN}docker compose -f $COMPOSE_FILE logs nginx${NC}"
    
    echo
    echo -e "${GREEN}Management Commands:${NC}"
    echo -e "  View logs: ${CYAN}docker compose -f $COMPOSE_FILE logs -f${NC}"
    echo -e "  Stop services: ${CYAN}docker compose -f $COMPOSE_FILE down${NC}"
    echo -e "  Monitor certificates: ${CYAN}${SCRIPT_DIR}/monitor-certificates.sh${NC}"
    
    if [[ "$DEPLOYMENT_MODE" == "HTTPS" ]]; then
        echo -e "  Renew certificates: ${CYAN}${SCRIPT_DIR}/obtain-certificates.sh --force-renewal${NC}"
    else
        echo -e "  Setup SSL: ${CYAN}${SCRIPT_DIR}/obtain-certificates.sh${NC}"
    fi
    
    echo
}

# Main deployment function
main() {
    echo -e "${CYAN}=== Timeweb HTTPS Deployment Script ===${NC}"
    echo
    
    log "INFO" "Starting Timeweb deployment..."
    log "INFO" "Script version: 1.0"
    log "INFO" "Working directory: $PROJECT_DIR"
    log "INFO" "Log file: $LOG_FILE"
    
    # Parse command line arguments
    parse_args "$@"
    
    # Load and validate environment
    load_environment
    
    # Check prerequisites
    check_prerequisites
    
    # Detect SSL certificate availability
    detect_ssl_certificates
    
    # Obtain SSL certificates if needed
    obtain_ssl_certificates
    
    # Determine deployment mode
    determine_deployment_mode
    
    # Deploy services
    deploy_services
    
    # Wait for services to be ready
    if ! wait_for_services; then
        log "WARN" "Services took longer than expected to become ready"
    fi
    
    # Perform health checks
    if ! perform_health_checks; then
        log "WARN" "Some health checks failed, but deployment may still be functional"
    fi
    
    # Show deployment summary
    show_deployment_summary
    
    log "INFO" "Timeweb deployment completed successfully!"
    
    echo -e "${GREEN}Deployment completed successfully!${NC}"
    echo
    echo "The application is now running. Check the summary above for access URLs."
    echo
}

# Run main function with all arguments
main "$@"
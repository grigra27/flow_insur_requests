#!/bin/bash

# Comprehensive Health Check Script for Timeweb Deployment
# 
# This script performs comprehensive health checks for the Timeweb deployment
# including service health, HTTPS functionality, and system status.
#
# Requirements: 4.3, 4.4
#
# Usage:
#   ./health-check.sh [OPTIONS]
#
# Options:
#   --services       Check service health (default)
#   --https          Check HTTPS functionality
#   --database       Check database connectivity
#   --application    Check application functionality
#   --all           Check everything
#   --json          Output results in JSON format
#   --quiet         Minimal output (exit codes only)
#   --help          Show this help message

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/health-check.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Default options
CHECK_SERVICES=true
CHECK_HTTPS=false
CHECK_DATABASE=false
CHECK_APPLICATION=false
JSON_OUTPUT=false
QUIET_MODE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Health check results
HEALTH_RESULTS=()
OVERALL_STATUS="healthy"
FAILED_CHECKS=0
TOTAL_CHECKS=0

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
    
    # Log to console (unless quiet mode or JSON output)
    if [[ "$QUIET_MODE" != "true" && "$JSON_OUTPUT" != "true" ]]; then
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
                echo -e "${BLUE}[DEBUG]${NC} $message"
                ;;
        esac
    fi
}

# Error handling
error_exit() {
    log "ERROR" "$1"
    exit 1
}

# Show help
show_help() {
    cat << EOF
Comprehensive Health Check Script for Timeweb Deployment

This script performs comprehensive health checks for the Timeweb deployment
including service health, HTTPS functionality, and system status.

Usage:
    $0 [OPTIONS]

Options:
    --services       Check service health (default)
    --https          Check HTTPS functionality
    --database       Check database connectivity
    --application    Check application functionality
    --all           Check everything
    --json          Output results in JSON format
    --quiet         Minimal output (exit codes only)
    --help          Show this help message

Exit Codes:
    0 - All checks passed
    1 - Some checks failed
    2 - Critical failure (services not running)

Examples:
    # Basic service health check
    $0

    # Full health check
    $0 --all

    # HTTPS-specific checks
    $0 --https

    # JSON output for monitoring
    $0 --all --json

    # Quiet mode for scripts
    $0 --all --quiet

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --services)
                CHECK_SERVICES=true
                shift
                ;;
            --https)
                CHECK_HTTPS=true
                shift
                ;;
            --database)
                CHECK_DATABASE=true
                shift
                ;;
            --application)
                CHECK_APPLICATION=true
                shift
                ;;
            --all)
                CHECK_SERVICES=true
                CHECK_HTTPS=true
                CHECK_DATABASE=true
                CHECK_APPLICATION=true
                shift
                ;;
            --json)
                JSON_OUTPUT=true
                shift
                ;;
            --quiet)
                QUIET_MODE=true
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
    
    if [[ -f "$env_file" ]]; then
        # Source environment file
        set -a
        source "$env_file"
        set +a
    fi
}

# Add health check result
add_result() {
    local check_name="$1"
    local status="$2"
    local message="$3"
    local details="${4:-}"
    
    ((TOTAL_CHECKS++))
    
    if [[ "$status" != "pass" ]]; then
        ((FAILED_CHECKS++))
        OVERALL_STATUS="unhealthy"
    fi
    
    local result=$(cat << EOF
{
    "check": "$check_name",
    "status": "$status",
    "message": "$message",
    "details": "$details",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)
    
    HEALTH_RESULTS+=("$result")
    
    # Log result
    case "$status" in
        "pass")
            log "INFO" "✓ $check_name: $message"
            ;;
        "warn")
            log "WARN" "⚠ $check_name: $message"
            ;;
        "fail")
            log "ERROR" "✗ $check_name: $message"
            ;;
    esac
}

# Check if Docker services are available
check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        add_result "docker_available" "fail" "Docker is not installed or not in PATH"
        return 1
    fi
    
    if ! command -v docker compose &> /dev/null; then
        add_result "docker_compose_available" "fail" "Docker Compose is not installed or not in PATH"
        return 1
    fi
    
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        add_result "compose_file_exists" "fail" "Docker Compose file not found: $COMPOSE_FILE"
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        add_result "docker_daemon" "fail" "Docker daemon is not running"
        return 1
    fi
    
    add_result "prerequisites" "pass" "All prerequisites are available"
    return 0
}

# Check service health
check_service_health() {
    if [[ "$CHECK_SERVICES" != "true" ]]; then
        return 0
    fi
    
    log "DEBUG" "Checking service health..."
    
    # Get list of running services
    local running_services
    running_services=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null || echo "")
    
    if [[ -z "$running_services" ]]; then
        add_result "services_running" "fail" "No services are running"
        return 1
    fi
    
    local services_array
    readarray -t services_array <<< "$running_services"
    
    add_result "services_running" "pass" "${#services_array[@]} services are running" "$(echo "$running_services" | tr '\n' ',')"
    
    # Check individual service health
    local unhealthy_services=()
    
    for service in "${services_array[@]}"; do
        if [[ -z "$service" ]]; then
            continue
        fi
        
        # Get service status
        local service_status
        service_status=$(docker compose -f "$COMPOSE_FILE" ps "$service" --format "table {{.Status}}" 2>/dev/null | tail -n +2 || echo "unknown")
        
        if [[ "$service_status" == *"healthy"* ]]; then
            add_result "service_${service}" "pass" "Service is healthy" "$service_status"
        elif [[ "$service_status" == *"Up"* ]]; then
            # Service is up but may not have health checks
            add_result "service_${service}" "pass" "Service is running" "$service_status"
        elif [[ "$service_status" == *"unhealthy"* ]]; then
            add_result "service_${service}" "fail" "Service is unhealthy" "$service_status"
            unhealthy_services+=("$service")
        else
            add_result "service_${service}" "warn" "Service status unknown" "$service_status"
        fi
    done
    
    if [[ ${#unhealthy_services[@]} -gt 0 ]]; then
        add_result "overall_service_health" "fail" "Some services are unhealthy" "$(IFS=','; echo "${unhealthy_services[*]}")"
        return 1
    else
        add_result "overall_service_health" "pass" "All services are healthy"
        return 0
    fi
}

# Check database connectivity
check_database_health() {
    if [[ "$CHECK_DATABASE" != "true" ]]; then
        return 0
    fi
    
    log "DEBUG" "Checking database connectivity..."
    
    # Check if database service is running
    if ! docker compose -f "$COMPOSE_FILE" ps db | grep -q "Up"; then
        add_result "database_service" "fail" "Database service is not running"
        return 1
    fi
    
    add_result "database_service" "pass" "Database service is running"
    
    # Check database connectivity
    local db_check_result
    if db_check_result=$(docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" 2>&1); then
        add_result "database_connectivity" "pass" "Database is accepting connections" "$db_check_result"
    else
        add_result "database_connectivity" "fail" "Database connectivity failed" "$db_check_result"
        return 1
    fi
    
    # Check database version and basic info
    local db_version
    if db_version=$(docker compose -f "$COMPOSE_FILE" exec -T db psql -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" -t -c "SELECT version();" 2>/dev/null | head -n1 | xargs); then
        add_result "database_version" "pass" "Database version retrieved" "$db_version"
    else
        add_result "database_version" "warn" "Could not retrieve database version"
    fi
    
    return 0
}

# Check application health
check_application_health() {
    if [[ "$CHECK_APPLICATION" != "true" ]]; then
        return 0
    fi
    
    log "DEBUG" "Checking application health..."
    
    # Check if web service is running
    if ! docker compose -f "$COMPOSE_FILE" ps web | grep -q "Up"; then
        add_result "web_service" "fail" "Web service is not running"
        return 1
    fi
    
    add_result "web_service" "pass" "Web service is running"
    
    # Check Django application health
    local django_health
    if django_health=$(docker compose -f "$COMPOSE_FILE" exec -T web python /app/simple_healthcheck.py 2>&1); then
        add_result "django_health" "pass" "Django application is healthy" "$django_health"
    else
        add_result "django_health" "fail" "Django application health check failed" "$django_health"
        return 1
    fi
    
    # Check HTTP endpoint accessibility
    local http_check
    if http_check=$(curl -s -f -L --max-time 10 "http://localhost/healthz/" 2>&1); then
        add_result "http_endpoint" "pass" "HTTP endpoint is accessible"
    else
        add_result "http_endpoint" "fail" "HTTP endpoint is not accessible" "$http_check"
        return 1
    fi
    
    return 0
}

# Check HTTPS functionality
check_https_health() {
    if [[ "$CHECK_HTTPS" != "true" ]]; then
        return 0
    fi
    
    log "DEBUG" "Checking HTTPS functionality..."
    
    # Check if nginx service is running
    if ! docker compose -f "$COMPOSE_FILE" ps nginx | grep -q "Up"; then
        add_result "nginx_service" "fail" "Nginx service is not running"
        return 1
    fi
    
    add_result "nginx_service" "pass" "Nginx service is running"
    
    # Check nginx configuration
    local nginx_config_check
    if nginx_config_check=$(docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t 2>&1); then
        add_result "nginx_config" "pass" "Nginx configuration is valid"
    else
        add_result "nginx_config" "fail" "Nginx configuration is invalid" "$nginx_config_check"
        return 1
    fi
    
    # Check HTTPS endpoint accessibility (if configured)
    if [[ -n "${DOMAINS:-}" ]]; then
        local domains_array
        IFS=',' read -ra domains_array <<< "$DOMAINS"
        local https_accessible=false
        local https_errors=()
        
        for domain in "${domains_array[@]}"; do
            domain=$(echo "$domain" | xargs)
            
            # Test HTTPS accessibility
            local https_check
            if https_check=$(curl -s -f -L --max-time 10 --insecure "https://$domain/healthz/" 2>&1); then
                add_result "https_${domain}" "pass" "HTTPS accessible for $domain"
                https_accessible=true
            else
                add_result "https_${domain}" "warn" "HTTPS not accessible for $domain" "$https_check"
                https_errors+=("$domain: $https_check")
            fi
            
            # Test HTTP to HTTPS redirect (if SSL is enabled)
            if [[ "${SSL_REDIRECT:-}" == "True" ]]; then
                local redirect_check
                redirect_check=$(curl -s -I -L --max-time 10 "http://$domain/" 2>&1 | head -n1 || echo "")
                
                if echo "$redirect_check" | grep -q "301\|302"; then
                    add_result "https_redirect_${domain}" "pass" "HTTP to HTTPS redirect working for $domain"
                else
                    add_result "https_redirect_${domain}" "warn" "HTTP to HTTPS redirect not working for $domain" "$redirect_check"
                fi
            fi
        done
        
        if [[ "$https_accessible" == "true" ]]; then
            add_result "https_overall" "pass" "HTTPS is accessible for at least one domain"
        else
            add_result "https_overall" "warn" "HTTPS is not accessible for any domain" "$(IFS='; '; echo "${https_errors[*]}")"
        fi
    else
        # Test local HTTPS
        local local_https_check
        if local_https_check=$(curl -s -f -L --max-time 10 --insecure "https://localhost/healthz/" 2>&1); then
            add_result "https_local" "pass" "Local HTTPS endpoint is accessible"
        else
            add_result "https_local" "warn" "Local HTTPS endpoint is not accessible" "$local_https_check"
        fi
    fi
    
    # Check SSL certificate status (if certificates exist)
    if [[ -n "${DOMAINS:-}" ]]; then
        local cert_script="${SCRIPT_DIR}/monitor-certificates.sh"
        if [[ -f "$cert_script" && -x "$cert_script" ]]; then
            local cert_status
            if cert_status=$("$cert_script" --json 2>/dev/null); then
                local alerts_count
                alerts_count=$(echo "$cert_status" | jq -r '.alerts_count // 0')
                
                if [[ "$alerts_count" -eq 0 ]]; then
                    add_result "ssl_certificates" "pass" "SSL certificates are healthy"
                else
                    add_result "ssl_certificates" "warn" "SSL certificates have $alerts_count alerts"
                fi
            else
                add_result "ssl_certificates" "warn" "Could not check SSL certificate status"
            fi
        fi
    fi
    
    return 0
}

# Generate health report
generate_report() {
    local report_data=$(cat << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "overall_status": "$OVERALL_STATUS",
    "total_checks": $TOTAL_CHECKS,
    "failed_checks": $FAILED_CHECKS,
    "success_rate": $(echo "scale=2; ($TOTAL_CHECKS - $FAILED_CHECKS) * 100 / $TOTAL_CHECKS" | bc -l 2>/dev/null || echo "0"),
    "checks": [$(IFS=','; echo "${HEALTH_RESULTS[*]}")]
}
EOF
)
    
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo "$report_data" | jq '.'
    elif [[ "$QUIET_MODE" != "true" ]]; then
        # Human-readable output
        echo
        echo -e "${CYAN}=== Health Check Report ===${NC}"
        echo "Timestamp: $(date)"
        echo "Overall Status: $(if [[ "$OVERALL_STATUS" == "healthy" ]]; then echo -e "${GREEN}HEALTHY${NC}"; else echo -e "${RED}UNHEALTHY${NC}"; fi)"
        echo "Checks: $((TOTAL_CHECKS - FAILED_CHECKS))/$TOTAL_CHECKS passed"
        echo
        
        # Group results by category
        local service_results=()
        local database_results=()
        local application_results=()
        local https_results=()
        local other_results=()
        
        for result in "${HEALTH_RESULTS[@]}"; do
            local check_name
            check_name=$(echo "$result" | jq -r '.check')
            
            case "$check_name" in
                service_*|services_*|overall_service_*)
                    service_results+=("$result")
                    ;;
                database_*)
                    database_results+=("$result")
                    ;;
                *django*|*web*|*http_endpoint*|*application*)
                    application_results+=("$result")
                    ;;
                *https*|*ssl*|*nginx*|*redirect*)
                    https_results+=("$result")
                    ;;
                *)
                    other_results+=("$result")
                    ;;
            esac
        done
        
        # Display results by category
        if [[ ${#service_results[@]} -gt 0 ]]; then
            echo -e "${BLUE}Service Health:${NC}"
            for result in "${service_results[@]}"; do
                display_result "$result"
            done
            echo
        fi
        
        if [[ ${#database_results[@]} -gt 0 ]]; then
            echo -e "${BLUE}Database Health:${NC}"
            for result in "${database_results[@]}"; do
                display_result "$result"
            done
            echo
        fi
        
        if [[ ${#application_results[@]} -gt 0 ]]; then
            echo -e "${BLUE}Application Health:${NC}"
            for result in "${application_results[@]}"; do
                display_result "$result"
            done
            echo
        fi
        
        if [[ ${#https_results[@]} -gt 0 ]]; then
            echo -e "${BLUE}HTTPS Health:${NC}"
            for result in "${https_results[@]}"; do
                display_result "$result"
            done
            echo
        fi
        
        if [[ ${#other_results[@]} -gt 0 ]]; then
            echo -e "${BLUE}System Health:${NC}"
            for result in "${other_results[@]}"; do
                display_result "$result"
            done
            echo
        fi
        
        # Summary
        if [[ "$OVERALL_STATUS" == "healthy" ]]; then
            echo -e "${GREEN}All health checks passed!${NC}"
        else
            echo -e "${RED}$FAILED_CHECKS health check(s) failed.${NC}"
            echo "Check the details above and log file: $LOG_FILE"
        fi
        echo
    fi
}

# Display individual result
display_result() {
    local result="$1"
    local status
    status=$(echo "$result" | jq -r '.status')
    local check
    check=$(echo "$result" | jq -r '.check')
    local message
    message=$(echo "$result" | jq -r '.message')
    
    case "$status" in
        "pass")
            echo -e "  ${GREEN}✓${NC} $check: $message"
            ;;
        "warn")
            echo -e "  ${YELLOW}⚠${NC} $check: $message"
            ;;
        "fail")
            echo -e "  ${RED}✗${NC} $check: $message"
            ;;
    esac
}

# Main function
main() {
    # Parse command line arguments
    parse_args "$@"
    
    if [[ "$QUIET_MODE" != "true" && "$JSON_OUTPUT" != "true" ]]; then
        echo -e "${CYAN}Starting health checks...${NC}"
        log "INFO" "Starting comprehensive health check"
    fi
    
    # Load environment configuration
    load_environment
    
    # Check prerequisites
    if ! check_prerequisites; then
        generate_report
        exit 2
    fi
    
    # Perform health checks
    check_service_health
    check_database_health
    check_application_health
    check_https_health
    
    # Generate and display report
    generate_report
    
    if [[ "$QUIET_MODE" != "true" && "$JSON_OUTPUT" != "true" ]]; then
        log "INFO" "Health check completed: $OVERALL_STATUS"
    fi
    
    # Exit with appropriate code
    if [[ "$OVERALL_STATUS" == "healthy" ]]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function with all arguments
main "$@"
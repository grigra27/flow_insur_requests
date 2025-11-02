#!/bin/bash

# Certificate Monitoring Script for Timeweb Deployment
# 
# This script monitors SSL certificate status, expiry dates, and health
# and provides alerting capabilities for certificate management.
#
# Requirements: 2.2, 4.3
#
# Usage:
#   ./monitor-certificates.sh [--check-expiry] [--check-health] [--alert] [--json]
#
# Options:
#   --check-expiry   Check certificate expiry dates (default)
#   --check-health   Check certificate health and validity
#   --alert          Enable alerting for critical issues
#   --json          Output results in JSON format
#   --help          Show this help message

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/certificate-monitoring.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Alert thresholds (days)
WARNING_THRESHOLD=30
CRITICAL_THRESHOLD=7

# Default options
CHECK_EXPIRY=true
CHECK_HEALTH=false
ENABLE_ALERTS=false
JSON_OUTPUT=false

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
    
    # Log to console with colors (unless JSON output)
    if [[ "$JSON_OUTPUT" != "true" ]]; then
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
Certificate Monitoring Script for Timeweb Deployment

This script monitors SSL certificate status, expiry dates, and health
and provides alerting capabilities for certificate management.

Usage:
    $0 [OPTIONS]

Options:
    --check-expiry   Check certificate expiry dates (default)
    --check-health   Check certificate health and validity
    --alert          Enable alerting for critical issues
    --json          Output results in JSON format
    --help          Show this help message

Alert Thresholds:
    Warning: $WARNING_THRESHOLD days before expiry
    Critical: $CRITICAL_THRESHOLD days before expiry

Examples:
    # Basic expiry check
    $0

    # Full health check with alerts
    $0 --check-health --alert

    # JSON output for monitoring systems
    $0 --json

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check-expiry)
                CHECK_EXPIRY=true
                shift
                ;;
            --check-health)
                CHECK_HEALTH=true
                shift
                ;;
            --alert)
                ENABLE_ALERTS=true
                shift
                ;;
            --json)
                JSON_OUTPUT=true
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
    
    # Source environment file
    set -a
    source "$env_file"
    set +a
    
    # Validate required environment variables
    if [[ -z "${DOMAINS:-}" ]]; then
        error_exit "DOMAINS environment variable is required"
    fi
}

# Check if Docker services are available
check_services() {
    if ! command -v docker &> /dev/null; then
        error_exit "Docker is not installed or not in PATH"
    fi
    
    if ! command -v docker compose &> /dev/null; then
        error_exit "Docker Compose is not installed or not in PATH"
    fi
    
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error_exit "Docker Compose file not found: $COMPOSE_FILE"
    fi
}

# Get certificate information for a domain
get_certificate_info() {
    local domain="$1"
    local cert_info="{}"
    
    # Check if certificate files exist
    if docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "test -f /etc/letsencrypt/live/$domain/fullchain.pem" 2>/dev/null; then
        
        # Get certificate details
        local cert_details
        cert_details=$(docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "openssl x509 -in /etc/letsencrypt/live/$domain/fullchain.pem -noout -text" 2>/dev/null || echo "")
        
        if [[ -n "$cert_details" ]]; then
            # Extract expiry date
            local expiry_date
            expiry_date=$(echo "$cert_details" | grep "Not After" | sed 's/.*Not After : //' || echo "Unknown")
            
            # Extract issuer
            local issuer
            issuer=$(echo "$cert_details" | grep "Issuer:" | sed 's/.*Issuer: //' | head -n1 || echo "Unknown")
            
            # Extract subject
            local subject
            subject=$(echo "$cert_details" | grep "Subject:" | sed 's/.*Subject: //' | head -n1 || echo "Unknown")
            
            # Calculate days until expiry
            local days_until_expiry=0
            if [[ "$expiry_date" != "Unknown" ]]; then
                local expiry_timestamp
                expiry_timestamp=$(date -d "$expiry_date" +%s 2>/dev/null || echo "0")
                local current_timestamp
                current_timestamp=$(date +%s)
                
                if [[ $expiry_timestamp -gt 0 ]]; then
                    days_until_expiry=$(( (expiry_timestamp - current_timestamp) / 86400 ))
                fi
            fi
            
            # Determine status
            local status="valid"
            local alert_level="none"
            
            if [[ $days_until_expiry -le 0 ]]; then
                status="expired"
                alert_level="critical"
            elif [[ $days_until_expiry -le $CRITICAL_THRESHOLD ]]; then
                status="expiring_soon"
                alert_level="critical"
            elif [[ $days_until_expiry -le $WARNING_THRESHOLD ]]; then
                status="expiring_warning"
                alert_level="warning"
            fi
            
            # Build certificate info JSON
            cert_info=$(cat << EOF
{
    "domain": "$domain",
    "exists": true,
    "expiry_date": "$expiry_date",
    "days_until_expiry": $days_until_expiry,
    "issuer": "$issuer",
    "subject": "$subject",
    "status": "$status",
    "alert_level": "$alert_level"
}
EOF
)
        else
            cert_info=$(cat << EOF
{
    "domain": "$domain",
    "exists": true,
    "error": "Could not read certificate details",
    "status": "error",
    "alert_level": "warning"
}
EOF
)
        fi
    else
        cert_info=$(cat << EOF
{
    "domain": "$domain",
    "exists": false,
    "status": "missing",
    "alert_level": "critical"
}
EOF
)
    fi
    
    echo "$cert_info"
}

# Check certificate health via HTTPS connection
check_certificate_health() {
    local domain="$1"
    local health_info="{}"
    
    # Test HTTPS connection
    local ssl_check_result
    ssl_check_result=$(timeout 10 openssl s_client -connect "$domain:443" -servername "$domain" -verify_return_error < /dev/null 2>&1 || echo "connection_failed")
    
    if echo "$ssl_check_result" | grep -q "Verify return code: 0"; then
        # Connection successful
        local cipher
        cipher=$(echo "$ssl_check_result" | grep "Cipher    :" | sed 's/.*Cipher    : //' || echo "Unknown")
        
        local protocol
        protocol=$(echo "$ssl_check_result" | grep "Protocol  :" | sed 's/.*Protocol  : //' || echo "Unknown")
        
        health_info=$(cat << EOF
{
    "domain": "$domain",
    "https_accessible": true,
    "ssl_valid": true,
    "cipher": "$cipher",
    "protocol": "$protocol",
    "status": "healthy"
}
EOF
)
    else
        # Connection failed
        local error_msg
        error_msg=$(echo "$ssl_check_result" | tail -n 5 | tr '\n' ' ' | sed 's/"/\\"/g')
        
        health_info=$(cat << EOF
{
    "domain": "$domain",
    "https_accessible": false,
    "ssl_valid": false,
    "error": "$error_msg",
    "status": "unhealthy"
}
EOF
)
    fi
    
    echo "$health_info"
}

# Send alert for critical issues
send_alert() {
    local alert_data="$1"
    local alert_level="$2"
    local message="$3"
    
    if [[ "$ENABLE_ALERTS" != "true" ]]; then
        return 0
    fi
    
    # Log alert
    log "$alert_level" "ALERT: $message"
    
    # Here you can add integration with external alerting systems:
    # - Email notifications
    # - Slack/Discord webhooks
    # - PagerDuty/Opsgenie
    # - Custom webhook endpoints
    
    # Example webhook call (uncomment and configure as needed):
    # if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    #     curl -X POST "$ALERT_WEBHOOK_URL" \
    #         -H "Content-Type: application/json" \
    #         -d "$alert_data" || true
    # fi
    
    # Example email notification (uncomment and configure as needed):
    # if command -v mail &> /dev/null && [[ -n "${ALERT_EMAIL:-}" ]]; then
    #     echo "$message" | mail -s "Certificate Alert: $alert_level" "$ALERT_EMAIL" || true
    # fi
}

# Monitor certificates
monitor_certificates() {
    local domains_array
    IFS=',' read -ra domains_array <<< "$DOMAINS"
    
    log "INFO" "Starting certificate monitoring for ${#domains_array[@]} domains..."
    
    local results=()
    local alerts=()
    
    for domain in "${domains_array[@]}"; do
        domain=$(echo "$domain" | xargs) # Trim whitespace
        
        log "DEBUG" "Monitoring domain: $domain"
        
        local domain_result="{}"
        
        # Check certificate expiry
        if [[ "$CHECK_EXPIRY" == "true" ]]; then
            local cert_info
            cert_info=$(get_certificate_info "$domain")
            domain_result=$(echo "$domain_result" | jq ". + {\"certificate\": $cert_info}")
            
            # Check for alerts
            local alert_level
            alert_level=$(echo "$cert_info" | jq -r '.alert_level // "none"')
            
            if [[ "$alert_level" != "none" ]]; then
                local alert_message
                alert_message="Certificate alert for $domain: $(echo "$cert_info" | jq -r '.status // "unknown"')"
                
                if [[ "$alert_level" == "critical" ]]; then
                    alert_message="$alert_message ($(echo "$cert_info" | jq -r '.days_until_expiry // "unknown"') days until expiry)"
                fi
                
                alerts+=("$alert_message")
                send_alert "$cert_info" "ERROR" "$alert_message"
            fi
        fi
        
        # Check certificate health
        if [[ "$CHECK_HEALTH" == "true" ]]; then
            local health_info
            health_info=$(check_certificate_health "$domain")
            domain_result=$(echo "$domain_result" | jq ". + {\"health\": $health_info}")
            
            # Check for health alerts
            local health_status
            health_status=$(echo "$health_info" | jq -r '.status // "unknown"')
            
            if [[ "$health_status" == "unhealthy" ]]; then
                local health_alert="HTTPS health check failed for $domain"
                alerts+=("$health_alert")
                send_alert "$health_info" "ERROR" "$health_alert"
            fi
        fi
        
        results+=("$domain_result")
    done
    
    # Generate final report
    local monitoring_report
    monitoring_report=$(cat << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "domains_checked": ${#domains_array[@]},
    "alerts_count": ${#alerts[@]},
    "check_expiry": $CHECK_EXPIRY,
    "check_health": $CHECK_HEALTH,
    "results": [$(IFS=','; echo "${results[*]}")]
}
EOF
)
    
    # Output results
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo "$monitoring_report" | jq '.'
    else
        # Human-readable output
        echo -e "${BLUE}Certificate Monitoring Report${NC}"
        echo "============================="
        echo "Timestamp: $(date)"
        echo "Domains checked: ${#domains_array[@]}"
        echo "Alerts: ${#alerts[@]}"
        echo
        
        for domain in "${domains_array[@]}"; do
            domain=$(echo "$domain" | xargs)
            
            echo -e "${BLUE}Domain: $domain${NC}"
            
            if [[ "$CHECK_EXPIRY" == "true" ]]; then
                local cert_info
                cert_info=$(get_certificate_info "$domain")
                local exists
                exists=$(echo "$cert_info" | jq -r '.exists')
                
                if [[ "$exists" == "true" ]]; then
                    local days_until_expiry
                    days_until_expiry=$(echo "$cert_info" | jq -r '.days_until_expiry // "unknown"')
                    local expiry_date
                    expiry_date=$(echo "$cert_info" | jq -r '.expiry_date // "unknown"')
                    local status
                    status=$(echo "$cert_info" | jq -r '.status // "unknown"')
                    
                    case "$status" in
                        "valid")
                            echo -e "  Certificate: ${GREEN}✓ Valid${NC} (expires in $days_until_expiry days)"
                            ;;
                        "expiring_warning")
                            echo -e "  Certificate: ${YELLOW}⚠ Expiring Soon${NC} (expires in $days_until_expiry days)"
                            ;;
                        "expiring_soon"|"expired")
                            echo -e "  Certificate: ${RED}✗ Critical${NC} (expires in $days_until_expiry days)"
                            ;;
                        *)
                            echo -e "  Certificate: ${RED}✗ Error${NC} ($status)"
                            ;;
                    esac
                    echo "  Expiry Date: $expiry_date"
                else
                    echo -e "  Certificate: ${RED}✗ Not Found${NC}"
                fi
            fi
            
            if [[ "$CHECK_HEALTH" == "true" ]]; then
                local health_info
                health_info=$(check_certificate_health "$domain")
                local https_accessible
                https_accessible=$(echo "$health_info" | jq -r '.https_accessible')
                
                if [[ "$https_accessible" == "true" ]]; then
                    local protocol
                    protocol=$(echo "$health_info" | jq -r '.protocol // "unknown"')
                    local cipher
                    cipher=$(echo "$health_info" | jq -r '.cipher // "unknown"')
                    echo -e "  HTTPS Health: ${GREEN}✓ Accessible${NC} ($protocol, $cipher)"
                else
                    echo -e "  HTTPS Health: ${RED}✗ Not Accessible${NC}"
                fi
            fi
            
            echo
        done
        
        # Show alerts summary
        if [[ ${#alerts[@]} -gt 0 ]]; then
            echo -e "${RED}Alerts:${NC}"
            for alert in "${alerts[@]}"; do
                echo -e "  ${RED}•${NC} $alert"
            done
            echo
        fi
    fi
    
    log "INFO" "Certificate monitoring completed: ${#alerts[@]} alerts generated"
    
    # Return non-zero exit code if there are critical alerts
    if [[ ${#alerts[@]} -gt 0 ]]; then
        return 1
    fi
    
    return 0
}

# Main function
main() {
    # Parse command line arguments
    parse_args "$@"
    
    if [[ "$JSON_OUTPUT" != "true" ]]; then
        log "INFO" "Starting certificate monitoring script..."
    fi
    
    # Load environment configuration
    load_environment
    
    # Check prerequisites
    check_services
    
    # Monitor certificates
    monitor_certificates
    
    if [[ "$JSON_OUTPUT" != "true" ]]; then
        log "INFO" "Certificate monitoring completed successfully"
    fi
}

# Run main function with all arguments
main "$@"
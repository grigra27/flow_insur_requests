#!/bin/bash

# SSL Status Monitoring Script
# This script monitors SSL certificate status and domain availability

set -e

# Configuration
LOG_FILE="/var/log/ssl-monitoring.log"
ALERT_LOG="/var/log/ssl-alerts.log"
STATUS_FILE="/tmp/ssl-status.json"
DOMAINS=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
ALERT_DAYS=7
WARNING_DAYS=30

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

# Alert logging
alert() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ALERT: $1" | tee -a "$ALERT_LOG"
    log "ALERT: $1"
}

# Error handling
error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    log "ERROR: $1"
}

# Success message
success() {
    echo -e "${GREEN}$1${NC}"
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

# Check domain SSL certificate
check_domain_ssl() {
    local domain="$1"
    local result={}
    
    info "Checking SSL for domain: $domain"
    
    # Get certificate information
    local cert_info=$(timeout 10 openssl s_client -connect "$domain:443" -servername "$domain" 2>/dev/null | openssl x509 -noout -dates -subject -issuer 2>/dev/null || echo "")
    
    if [[ -z "$cert_info" ]]; then
        error "Failed to retrieve SSL certificate for $domain"
        echo "{\"domain\":\"$domain\",\"status\":\"error\",\"error\":\"connection_failed\"}"
        return 1
    fi
    
    # Parse certificate dates
    local start_date=$(echo "$cert_info" | grep "notBefore" | cut -d= -f2)
    local end_date=$(echo "$cert_info" | grep "notAfter" | cut -d= -f2)
    local subject=$(echo "$cert_info" | grep "subject" | cut -d= -f2-)
    local issuer=$(echo "$cert_info" | grep "issuer" | cut -d= -f2-)
    
    # Calculate days until expiry
    local end_epoch=$(date -d "$end_date" +%s 2>/dev/null || echo "0")
    local current_epoch=$(date +%s)
    local days_until_expiry=0
    
    if [[ $end_epoch -gt 0 ]]; then
        days_until_expiry=$(( (end_epoch - current_epoch) / 86400 ))
    fi
    
    # Determine status
    local status="valid"
    local alert_level="none"
    
    if [[ $days_until_expiry -lt 0 ]]; then
        status="expired"
        alert_level="critical"
        alert "Certificate for $domain has EXPIRED!"
    elif [[ $days_until_expiry -le $ALERT_DAYS ]]; then
        status="expiring_soon"
        alert_level="critical"
        alert "Certificate for $domain expires in $days_until_expiry days!"
    elif [[ $days_until_expiry -le $WARNING_DAYS ]]; then
        status="expiring_warning"
        alert_level="warning"
        warning "Certificate for $domain expires in $days_until_expiry days"
    else
        success "Certificate for $domain is valid for $days_until_expiry more days"
    fi
    
    # Return JSON status
    echo "{\"domain\":\"$domain\",\"status\":\"$status\",\"days_until_expiry\":$days_until_expiry,\"start_date\":\"$start_date\",\"end_date\":\"$end_date\",\"subject\":\"$subject\",\"issuer\":\"$issuer\",\"alert_level\":\"$alert_level\"}"
}

# Check domain HTTP to HTTPS redirect
check_https_redirect() {
    local domain="$1"
    
    info "Checking HTTPS redirect for $domain"
    
    local response=$(timeout 10 curl -s -I -L "http://$domain" 2>/dev/null || echo "")
    
    if echo "$response" | grep -q "HTTP/.*30[1-8]"; then
        if echo "$response" | grep -q "https://"; then
            success "HTTPS redirect working for $domain"
            return 0
        else
            warning "Redirect found for $domain but not to HTTPS"
            return 1
        fi
    else
        error "No HTTPS redirect found for $domain"
        return 1
    fi
}

# Check domain availability
check_domain_availability() {
    local domain="$1"
    
    info "Checking availability for $domain"
    
    local http_code=$(timeout 10 curl -s -o /dev/null -w "%{http_code}" "https://$domain" 2>/dev/null || echo "000")
    
    if [[ "$http_code" =~ ^[2-3][0-9][0-9]$ ]]; then
        success "Domain $domain is available (HTTP $http_code)"
        return 0
    else
        error "Domain $domain is not available (HTTP $http_code)"
        return 1
    fi
}

# Generate monitoring report
generate_report() {
    local status_data="$1"
    
    echo ""
    echo "=== SSL MONITORING REPORT ==="
    echo "Generated: $(date)"
    echo ""
    
    # Parse JSON data and create summary
    local total_domains=0
    local valid_domains=0
    local warning_domains=0
    local critical_domains=0
    local error_domains=0
    
    while IFS= read -r line; do
        if [[ -n "$line" ]]; then
            total_domains=$((total_domains + 1))
            
            local domain=$(echo "$line" | grep -o '"domain":"[^"]*"' | cut -d'"' -f4)
            local status=$(echo "$line" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            local alert_level=$(echo "$line" | grep -o '"alert_level":"[^"]*"' | cut -d'"' -f4)
            local days=$(echo "$line" | grep -o '"days_until_expiry":[0-9-]*' | cut -d':' -f2)
            
            echo "Domain: $domain"
            echo "  Status: $status"
            echo "  Days until expiry: $days"
            echo ""
            
            case "$alert_level" in
                "none") valid_domains=$((valid_domains + 1)) ;;
                "warning") warning_domains=$((warning_domains + 1)) ;;
                "critical") critical_domains=$((critical_domains + 1)) ;;
                *) error_domains=$((error_domains + 1)) ;;
            esac
        fi
    done <<< "$status_data"
    
    echo "=== SUMMARY ==="
    echo "Total domains: $total_domains"
    echo "Valid: $valid_domains"
    echo "Warnings: $warning_domains"
    echo "Critical: $critical_domains"
    echo "Errors: $error_domains"
    echo ""
    
    # Return appropriate exit code
    if [[ $critical_domains -gt 0 || $error_domains -gt 0 ]]; then
        return 2
    elif [[ $warning_domains -gt 0 ]]; then
        return 1
    else
        return 0
    fi
}

# Save status to file
save_status() {
    local status_data="$1"
    
    cat > "$STATUS_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "domains": [
$(echo "$status_data" | sed 's/^/    /' | sed '$!s/$/,/')
  ]
}
EOF
    
    info "Status saved to $STATUS_FILE"
}

# Main monitoring function
main() {
    log "Starting SSL status monitoring..."
    
    local all_status=""
    local overall_status=0
    
    echo "=== SSL STATUS MONITORING ==="
    echo "Check time: $(date)"
    echo ""
    
    for domain in "${DOMAINS[@]}"; do
        echo "Checking domain: $domain"
        echo "----------------------------------------"
        
        # Check SSL certificate
        local ssl_status=$(check_domain_ssl "$domain")
        all_status="$all_status$ssl_status"$'\n'
        
        # Check HTTPS redirect
        check_https_redirect "$domain"
        
        # Check domain availability
        check_domain_availability "$domain"
        
        echo ""
    done
    
    # Generate report
    generate_report "$all_status"
    local report_status=$?
    
    # Save status to file
    save_status "$all_status"
    
    # Update overall status
    if [[ $report_status -gt $overall_status ]]; then
        overall_status=$report_status
    fi
    
    case $overall_status in
        0) success "All SSL certificates and domains are healthy" ;;
        1) warning "Some SSL certificates need attention" ;;
        2) error "Critical SSL issues found - immediate action required!" ;;
    esac
    
    log "SSL status monitoring completed with status: $overall_status"
    exit $overall_status
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [options]"
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --quiet, -q    Quiet mode (minimal output)"
        echo "  --json         Output only JSON status"
        exit 0
        ;;
    --quiet|-q)
        # Redirect stdout to log file only
        exec 1>>"$LOG_FILE"
        ;;
    --json)
        # JSON output mode - run monitoring and output only the status file
        main > /dev/null 2>&1
        cat "$STATUS_FILE"
        exit 0
        ;;
esac

# Run main function
main "$@"
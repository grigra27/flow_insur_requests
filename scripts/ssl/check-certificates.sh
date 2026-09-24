#!/bin/bash

# SSL Certificate Check Script
# This script checks the validity and expiration dates of SSL certificates

set -e

# Configuration
# Сертификаты лежат в ./letsencrypt проекта (смонтированы в nginx/certbot),
# а не в /etc/letsencrypt хоста. Лог — в logs/ проекта: скрипт запускается
# при деплое от deploy, у которого нет прав на /var/log.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
LETSENCRYPT_DIR="${LETSENCRYPT_DIR:-$PROJECT_DIR/letsencrypt}"
LOG_FILE="${SSL_CHECK_LOG_FILE:-$PROJECT_DIR/logs/ssl-certificates.log}"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:latest}"
ALERT_DAYS=7  # Alert if certificate expires within this many days
WARNING_DAYS=30  # Warning if certificate expires within this many days

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Certificate names to check
CERTIFICATES=("insflow.ru" "insflow.tw1.su")

# Logging function: строка с датой идёт только в лог-файл (в --quiet stdout
# и так направлен в лог). Недоступный на запись лог не роняет проверку.
log() {
    local line="$(date '+%Y-%m-%d %H:%M:%S') - $1"
    if [[ "${QUIET:-0}" == "1" ]]; then
        echo "$line"
    else
        echo "$line" >> "$LOG_FILE" 2>/dev/null || true
    fi
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

# Папка letsencrypt/live принадлежит root с правами 700, deploy её не читает.
# Поэтому публичные части сертификатов (cert.pem, chain.pem — не ключи)
# копируются во временную папку: напрямую, если есть права, иначе через
# одноразовый контейнер certbot (deploy состоит в группе docker).
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
CERT_PATH="$WORK_DIR"

fetch_certificate_files() {
    local cert_name="$1"
    local src="$LETSENCRYPT_DIR/live/$cert_name"
    local dst="$WORK_DIR/$cert_name"
    mkdir -p "$dst"

    if [[ -r "$src/cert.pem" ]]; then
        cp "$src/cert.pem" "$dst/cert.pem"
        [[ -r "$src/chain.pem" ]] && cp "$src/chain.pem" "$dst/chain.pem"
    elif command -v docker > /dev/null 2>&1; then
        docker run --rm -v "$LETSENCRYPT_DIR:/etc/letsencrypt:ro" --entrypoint cat \
            "$CERTBOT_IMAGE" "/etc/letsencrypt/live/$cert_name/cert.pem" > "$dst/cert.pem" 2>/dev/null || rm -f "$dst/cert.pem"
        docker run --rm -v "$LETSENCRYPT_DIR:/etc/letsencrypt:ro" --entrypoint cat \
            "$CERTBOT_IMAGE" "/etc/letsencrypt/live/$cert_name/chain.pem" > "$dst/chain.pem" 2>/dev/null || rm -f "$dst/chain.pem"
    fi
    [[ -s "$dst/cert.pem" ]] || rm -f "$dst/cert.pem"
    [[ -s "$dst/chain.pem" ]] || rm -f "$dst/chain.pem"
}

# Check if certificate file exists
check_certificate_exists() {
    local cert_name="$1"
    fetch_certificate_files "$cert_name"
    local cert_file="$CERT_PATH/$cert_name/cert.pem"
    
    if [[ ! -f "$cert_file" ]]; then
        error "Certificate file not found: $LETSENCRYPT_DIR/live/$cert_name/cert.pem"
        return 1
    fi
    return 0
}

# Get certificate information
get_certificate_info() {
    local cert_name="$1"
    local cert_file="$CERT_PATH/$cert_name/cert.pem"
    
    # Get certificate details
    local subject=$(openssl x509 -in "$cert_file" -noout -subject | sed 's/subject=//')
    local issuer=$(openssl x509 -in "$cert_file" -noout -issuer | sed 's/issuer=//')
    local start_date=$(openssl x509 -in "$cert_file" -noout -startdate | cut -d= -f2)
    local end_date=$(openssl x509 -in "$cert_file" -noout -enddate | cut -d= -f2)
    local san=$(openssl x509 -in "$cert_file" -noout -text | grep -A1 "Subject Alternative Name" | tail -1 | sed 's/^[[:space:]]*//')
    
    echo "Certificate: $cert_name"
    echo "  Subject: $subject"
    echo "  Issuer: $issuer"
    echo "  Valid From: $start_date"
    echo "  Valid Until: $end_date"
    echo "  SAN: $san"
    echo ""
}

# Check certificate expiration
check_certificate_expiration() {
    local cert_name="$1"
    local cert_file="$CERT_PATH/$cert_name/cert.pem"
    
    # Get expiration date
    local end_date=$(openssl x509 -in "$cert_file" -noout -enddate | cut -d= -f2)
    local end_epoch=$(date -d "$end_date" +%s)
    local current_epoch=$(date +%s)
    local days_until_expiry=$(( (end_epoch - current_epoch) / 86400 ))
    
    if [[ $days_until_expiry -lt 0 ]]; then
        error "Certificate $cert_name has EXPIRED!"
        return 2
    elif [[ $days_until_expiry -le $ALERT_DAYS ]]; then
        error "Certificate $cert_name expires in $days_until_expiry days - IMMEDIATE ACTION REQUIRED!"
        return 2
    elif [[ $days_until_expiry -le $WARNING_DAYS ]]; then
        warning "Certificate $cert_name expires in $days_until_expiry days"
        return 1
    else
        success "Certificate $cert_name is valid for $days_until_expiry more days"
        return 0
    fi
}

# Verify certificate chain
verify_certificate_chain() {
    local cert_name="$1"
    local cert_file="$CERT_PATH/$cert_name/cert.pem"
    local chain_file="$CERT_PATH/$cert_name/chain.pem"
    
    if [[ -f "$chain_file" ]]; then
        # chain.pem — промежуточный сертификат; корень берётся из системного хранилища
        if openssl verify -untrusted "$chain_file" "$cert_file" > /dev/null 2>&1; then
            success "Certificate chain verification passed for $cert_name"
            return 0
        else
            error "Certificate chain verification failed for $cert_name"
            return 1
        fi
    else
        warning "Chain file not found for $cert_name"
        return 1
    fi
}

# Check certificate against domain
check_certificate_domain() {
    local cert_name="$1"
    local cert_file="$CERT_PATH/$cert_name/cert.pem"
    
    info "Checking certificate domains for $cert_name..."
    
    # Extract domains from certificate
    local domains=$(openssl x509 -in "$cert_file" -noout -text | grep -A1 "Subject Alternative Name" | tail -1 | sed 's/DNS://g' | sed 's/,/ /g' | sed 's/^[[:space:]]*//')
    
    echo "  Domains in certificate: $domains"
    
    # Test SSL connection for each domain (if accessible)
    for domain in $domains; do
        if timeout 10 openssl s_client -connect "$domain:443" -servername "$domain" < /dev/null > /dev/null 2>&1; then
            success "SSL connection test passed for $domain"
        else
            warning "SSL connection test failed for $domain (may be expected if domain is not yet configured)"
        fi
    done
}

# Generate summary report
generate_summary() {
    local total_certs=$1
    local valid_certs=$2
    local warning_certs=$3
    local critical_certs=$4
    
    echo ""
    echo "=== CERTIFICATE STATUS SUMMARY ==="
    echo "Total certificates checked: $total_certs"
    echo "Valid certificates: $valid_certs"
    echo "Certificates with warnings: $warning_certs"
    echo "Critical certificates: $critical_certs"
    echo ""
    
    if [[ $critical_certs -gt 0 ]]; then
        error "CRITICAL: $critical_certs certificate(s) require immediate attention!"
        return 2
    elif [[ $warning_certs -gt 0 ]]; then
        warning "$warning_certs certificate(s) need attention soon"
        return 1
    else
        success "All certificates are in good condition"
        return 0
    fi
}

# Main execution
main() {
    log "Starting SSL certificate check..."
    
    local total_certs=0
    local valid_certs=0
    local warning_certs=0
    local critical_certs=0
    
    echo "=== SSL CERTIFICATE STATUS CHECK ==="
    echo "Check time: $(date)"
    echo ""
    
    for cert_name in "${CERTIFICATES[@]}"; do
        total_certs=$((total_certs + 1))
        
        echo "Checking certificate: $cert_name"
        echo "----------------------------------------"
        
        if ! check_certificate_exists "$cert_name"; then
            critical_certs=$((critical_certs + 1))
            continue
        fi
        
        # Get certificate information
        get_certificate_info "$cert_name"
        
        # Check expiration (коды 1/2 — статусы, а не ошибки: не даём set -e оборвать скрипт)
        local expiry_status=0
        check_certificate_expiration "$cert_name" || expiry_status=$?
        
        # Verify certificate chain
        verify_certificate_chain "$cert_name" || true
        
        # Check certificate domains
        check_certificate_domain "$cert_name" || true
        
        # Update counters based on status
        case $expiry_status in
            0) valid_certs=$((valid_certs + 1)) ;;
            1) warning_certs=$((warning_certs + 1)) ;;
            2) critical_certs=$((critical_certs + 1)) ;;
        esac
        
        echo ""
    done
    
    # Generate summary
    local summary_status=0
    generate_summary $total_certs $valid_certs $warning_certs $critical_certs || summary_status=$?
    
    log "SSL certificate check completed"
    exit $summary_status
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [options]"
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --quiet, -q    Quiet mode (minimal output)"
        echo "  --verbose, -v  Verbose mode (detailed output)"
        exit 0
        ;;
    --quiet|-q)
        # Redirect stdout to log file only
        QUIET=1
        mkdir -p "$(dirname "$LOG_FILE")"
        exec 1>>"$LOG_FILE"
        ;;
    --verbose|-v)
        # Enable verbose mode (default behavior)
        ;;
esac

# Run main function
main "$@"
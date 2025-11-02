#!/bin/bash

# Certificate Renewal Setup Script for Timeweb Deployment
# 
# This script sets up automatic certificate renewal with cron jobs
# and implements renewal monitoring and alerting.
#
# Requirements: 2.2, 4.3
#
# Usage:
#   ./setup-certificate-renewal.sh [--install] [--uninstall] [--status]
#
# Options:
#   --install    Install automatic renewal (default)
#   --uninstall  Remove automatic renewal
#   --status     Show renewal status and next run times
#   --help       Show this help message

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/certificate-renewal.log"
CRON_LOG_FILE="${PROJECT_DIR}/logs/certificate-renewal-cron.log"
RENEWAL_SCRIPT="${SCRIPT_DIR}/renew-certificates.sh"
MONITOR_SCRIPT="${SCRIPT_DIR}/monitor-certificates.sh"

# Default action
ACTION="install"

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
            echo -e "${BLUE}[DEBUG]${NC} $message"
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
Certificate Renewal Setup Script for Timeweb Deployment

This script sets up automatic certificate renewal with cron jobs
and implements renewal monitoring and alerting.

Usage:
    $0 [OPTIONS]

Options:
    --install    Install automatic renewal (default)
    --uninstall  Remove automatic renewal
    --status     Show renewal status and next run times
    --help       Show this help message

The script will:
1. Create certificate renewal and monitoring scripts
2. Set up cron jobs for automatic renewal (twice daily)
3. Set up monitoring cron job (daily)
4. Configure log rotation for renewal logs

Cron Schedule:
- Certificate renewal: Every 12 hours (02:00 and 14:00)
- Certificate monitoring: Daily at 06:00
- Log cleanup: Weekly on Sunday at 01:00

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --install)
                ACTION="install"
                shift
                ;;
            --uninstall)
                ACTION="uninstall"
                shift
                ;;
            --status)
                ACTION="status"
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

# Create certificate renewal script
create_renewal_script() {
    log "INFO" "Creating certificate renewal script..."
    
    cat > "$RENEWAL_SCRIPT" << 'EOF'
#!/bin/bash

# Certificate Renewal Script
# This script is called by cron to renew certificates automatically

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/certificate-renewal-cron.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Load environment
if [[ -f "${PROJECT_DIR}/.env" ]]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

log "INFO" "Starting certificate renewal check..."

# Change to project directory
cd "$PROJECT_DIR"

# Check if services are running
if ! docker compose -f "$COMPOSE_FILE" ps nginx | grep -q "Up"; then
    log "ERROR" "Nginx service is not running - skipping renewal"
    exit 1
fi

# Run certificate renewal
if docker compose -f "$COMPOSE_FILE" run --rm certbot certbot renew \
    --webroot \
    --webroot-path=/var/www/certbot \
    --quiet \
    --no-random-sleep-on-renew \
    --deploy-hook 'echo "Certificate renewed successfully"'; then
    
    log "INFO" "Certificate renewal check completed successfully"
    
    # Reload nginx if certificates were renewed
    if docker compose -f "$COMPOSE_FILE" exec nginx nginx -t; then
        docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload
        log "INFO" "Nginx configuration reloaded"
    else
        log "ERROR" "Nginx configuration test failed"
    fi
else
    log "ERROR" "Certificate renewal failed"
    exit 1
fi

log "INFO" "Certificate renewal process completed"
EOF

    chmod +x "$RENEWAL_SCRIPT"
    log "INFO" "Certificate renewal script created: $RENEWAL_SCRIPT"
}

# Create certificate monitoring script
create_monitoring_script() {
    log "INFO" "Creating certificate monitoring script..."
    
    cat > "$MONITOR_SCRIPT" << 'EOF'
#!/bin/bash

# Certificate Monitoring Script
# This script monitors certificate expiry and sends alerts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/logs/certificate-monitoring.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Alert thresholds (days)
WARNING_THRESHOLD=30
CRITICAL_THRESHOLD=7

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Load environment
if [[ -f "${PROJECT_DIR}/.env" ]]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

log "INFO" "Starting certificate monitoring check..."

# Change to project directory
cd "$PROJECT_DIR"

# Check if certbot service is available
if ! docker compose -f "$COMPOSE_FILE" config | grep -q "certbot:"; then
    log "WARN" "Certbot service not configured - skipping monitoring"
    exit 0
fi

# Get domains from environment
if [[ -z "${DOMAINS:-}" ]]; then
    log "ERROR" "DOMAINS environment variable not set"
    exit 1
fi

# Parse domains
IFS=',' read -ra domains_array <<< "$DOMAINS"

log "INFO" "Monitoring ${#domains_array[@]} domains for certificate expiry"

# Check each domain
for domain in "${domains_array[@]}"; do
    domain=$(echo "$domain" | xargs) # Trim whitespace
    
    log "INFO" "Checking certificate for domain: $domain"
    
    # Check if certificate exists
    if docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "test -f /etc/letsencrypt/live/$domain/fullchain.pem"; then
        
        # Get certificate expiry date
        expiry_date=$(docker compose -f "$COMPOSE_FILE" run --rm certbot sh -c "openssl x509 -in /etc/letsencrypt/live/$domain/fullchain.pem -noout -enddate" | cut -d= -f2)
        
        if [[ -n "$expiry_date" ]]; then
            # Calculate days until expiry
            expiry_timestamp=$(date -d "$expiry_date" +%s)
            current_timestamp=$(date +%s)
            days_until_expiry=$(( (expiry_timestamp - current_timestamp) / 86400 ))
            
            log "INFO" "Certificate for $domain expires in $days_until_expiry days ($expiry_date)"
            
            # Check thresholds and alert
            if [[ $days_until_expiry -le $CRITICAL_THRESHOLD ]]; then
                log "ERROR" "CRITICAL: Certificate for $domain expires in $days_until_expiry days!"
                # Here you could add email/webhook notifications
            elif [[ $days_until_expiry -le $WARNING_THRESHOLD ]]; then
                log "WARN" "WARNING: Certificate for $domain expires in $days_until_expiry days"
                # Here you could add email/webhook notifications
            fi
        else
            log "ERROR" "Could not determine expiry date for certificate: $domain"
        fi
    else
        log "ERROR" "Certificate not found for domain: $domain"
    fi
done

log "INFO" "Certificate monitoring check completed"
EOF

    chmod +x "$MONITOR_SCRIPT"
    log "INFO" "Certificate monitoring script created: $MONITOR_SCRIPT"
}

# Install cron jobs
install_cron_jobs() {
    log "INFO" "Installing cron jobs for certificate renewal and monitoring..."
    
    # Create temporary cron file
    local temp_cron=$(mktemp)
    
    # Get existing cron jobs (excluding our jobs)
    crontab -l 2>/dev/null | grep -v "# Insflow Certificate" > "$temp_cron" || true
    
    # Add our cron jobs
    cat >> "$temp_cron" << EOF

# Insflow Certificate Management Jobs
# Certificate renewal - twice daily at 02:00 and 14:00
0 2,14 * * * cd "$PROJECT_DIR" && "$RENEWAL_SCRIPT" >> "$CRON_LOG_FILE" 2>&1

# Certificate monitoring - daily at 06:00
0 6 * * * cd "$PROJECT_DIR" && "$MONITOR_SCRIPT" >> "$CRON_LOG_FILE" 2>&1

# Log cleanup - weekly on Sunday at 01:00
0 1 * * 0 find "$PROJECT_DIR/logs" -name "*.log" -type f -mtime +30 -delete 2>/dev/null || true

EOF
    
    # Install new crontab
    if crontab "$temp_cron"; then
        log "INFO" "Cron jobs installed successfully"
    else
        log "ERROR" "Failed to install cron jobs"
        rm -f "$temp_cron"
        return 1
    fi
    
    # Clean up
    rm -f "$temp_cron"
    
    # Show installed jobs
    log "INFO" "Installed cron jobs:"
    crontab -l | grep -A 10 "# Insflow Certificate" || true
}

# Uninstall cron jobs
uninstall_cron_jobs() {
    log "INFO" "Removing cron jobs for certificate renewal and monitoring..."
    
    # Create temporary cron file
    local temp_cron=$(mktemp)
    
    # Get existing cron jobs (excluding our jobs)
    if crontab -l 2>/dev/null | grep -v "# Insflow Certificate" > "$temp_cron"; then
        # Remove any remaining related lines
        sed -i '/certificate.*renewal/d' "$temp_cron" 2>/dev/null || true
        sed -i '/certificate.*monitoring/d' "$temp_cron" 2>/dev/null || true
        sed -i '/renew-certificates\.sh/d' "$temp_cron" 2>/dev/null || true
        sed -i '/monitor-certificates\.sh/d' "$temp_cron" 2>/dev/null || true
        
        # Install cleaned crontab
        if crontab "$temp_cron"; then
            log "INFO" "Cron jobs removed successfully"
        else
            log "ERROR" "Failed to remove cron jobs"
        fi
    else
        # No existing crontab, create empty one
        crontab -r 2>/dev/null || true
        log "INFO" "No existing cron jobs found"
    fi
    
    # Clean up
    rm -f "$temp_cron"
}

# Show renewal status
show_status() {
    log "INFO" "Checking certificate renewal status..."
    
    echo -e "${BLUE}Certificate Renewal Status${NC}"
    echo "=========================="
    echo
    
    # Check if renewal script exists
    if [[ -f "$RENEWAL_SCRIPT" ]]; then
        echo -e "${GREEN}✓${NC} Renewal script: $RENEWAL_SCRIPT"
    else
        echo -e "${RED}✗${NC} Renewal script: Not found"
    fi
    
    # Check if monitoring script exists
    if [[ -f "$MONITOR_SCRIPT" ]]; then
        echo -e "${GREEN}✓${NC} Monitoring script: $MONITOR_SCRIPT"
    else
        echo -e "${RED}✗${NC} Monitoring script: Not found"
    fi
    
    # Check cron jobs
    echo
    echo "Cron Jobs:"
    if crontab -l 2>/dev/null | grep -q "Certificate"; then
        echo -e "${GREEN}✓${NC} Cron jobs installed:"
        crontab -l | grep -A 10 "Certificate" | sed 's/^/  /'
    else
        echo -e "${RED}✗${NC} No certificate cron jobs found"
    fi
    
    # Check recent renewal activity
    echo
    echo "Recent Activity:"
    if [[ -f "$CRON_LOG_FILE" ]]; then
        echo "Last 5 renewal log entries:"
        tail -n 5 "$CRON_LOG_FILE" | sed 's/^/  /' || echo "  No recent activity"
    else
        echo "  No renewal log file found"
    fi
    
    # Check certificate status
    echo
    echo "Certificate Status:"
    if [[ -f "${PROJECT_DIR}/.env" ]]; then
        set -a
        source "${PROJECT_DIR}/.env"
        set +a
        
        if [[ -n "${DOMAINS:-}" ]]; then
            IFS=',' read -ra domains_array <<< "$DOMAINS"
            
            for domain in "${domains_array[@]}"; do
                domain=$(echo "$domain" | xargs)
                
                if docker compose -f "${PROJECT_DIR}/docker-compose.yml" run --rm certbot sh -c "test -f /etc/letsencrypt/live/$domain/fullchain.pem" 2>/dev/null; then
                    expiry_date=$(docker compose -f "${PROJECT_DIR}/docker-compose.yml" run --rm certbot sh -c "openssl x509 -in /etc/letsencrypt/live/$domain/fullchain.pem -noout -enddate" 2>/dev/null | cut -d= -f2 || echo "Unknown")
                    echo -e "  ${GREEN}✓${NC} $domain: Certificate exists (expires: $expiry_date)"
                else
                    echo -e "  ${RED}✗${NC} $domain: No certificate found"
                fi
            done
        else
            echo "  No domains configured"
        fi
    else
        echo "  Environment file not found"
    fi
    
    echo
}

# Install automatic renewal
install_renewal() {
    log "INFO" "Installing automatic certificate renewal..."
    
    # Create renewal and monitoring scripts
    create_renewal_script
    create_monitoring_script
    
    # Install cron jobs
    install_cron_jobs
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    mkdir -p "$(dirname "$CRON_LOG_FILE")"
    
    log "INFO" "Automatic certificate renewal installed successfully!"
    
    echo
    echo -e "${GREEN}Certificate renewal setup completed!${NC}"
    echo
    echo "Configuration:"
    echo "- Renewal script: $RENEWAL_SCRIPT"
    echo "- Monitoring script: $MONITOR_SCRIPT"
    echo "- Renewal log: $CRON_LOG_FILE"
    echo "- Monitoring log: $LOG_FILE"
    echo
    echo "Schedule:"
    echo "- Certificate renewal: Every 12 hours (02:00 and 14:00)"
    echo "- Certificate monitoring: Daily at 06:00"
    echo "- Log cleanup: Weekly on Sunday at 01:00"
    echo
    echo "To check status: $0 --status"
    echo "To uninstall: $0 --uninstall"
}

# Uninstall automatic renewal
uninstall_renewal() {
    log "INFO" "Uninstalling automatic certificate renewal..."
    
    # Remove cron jobs
    uninstall_cron_jobs
    
    # Optionally remove scripts (ask user)
    echo -n "Remove renewal and monitoring scripts? [y/N]: "
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -f "$RENEWAL_SCRIPT" "$MONITOR_SCRIPT"
        log "INFO" "Renewal and monitoring scripts removed"
    else
        log "INFO" "Renewal and monitoring scripts kept"
    fi
    
    log "INFO" "Automatic certificate renewal uninstalled"
    
    echo -e "${GREEN}Certificate renewal uninstalled successfully!${NC}"
}

# Main function
main() {
    log "INFO" "Starting certificate renewal setup script..."
    
    # Parse command line arguments
    parse_args "$@"
    
    case "$ACTION" in
        "install")
            install_renewal
            ;;
        "uninstall")
            uninstall_renewal
            ;;
        "status")
            show_status
            ;;
        *)
            error_exit "Unknown action: $ACTION"
            ;;
    esac
    
    log "INFO" "Certificate renewal setup script completed"
}

# Run main function with all arguments
main "$@"
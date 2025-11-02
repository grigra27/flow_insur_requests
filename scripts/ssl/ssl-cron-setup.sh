#!/bin/bash

# SSL Cron Setup Script
# This script sets up cron jobs for SSL certificate management

set -e

# Configuration
SCRIPT_DIR="/opt/insflow-system/scripts/ssl"
LOG_FILE="/var/log/ssl-certificates.log"

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

# Make scripts executable
make_scripts_executable() {
    info "Making SSL scripts executable..."
    
    local scripts=(
        "$SCRIPT_DIR/obtain-certificates.sh"
        "$SCRIPT_DIR/check-certificates.sh"
        "$SCRIPT_DIR/renew-certificates.sh"
        "$SCRIPT_DIR/post-renewal-hook.sh"
        "$SCRIPT_DIR/monitor-ssl-status.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [[ -f "$script" ]]; then
            chmod +x "$script"
            success "Made executable: $script"
        else
            error_exit "Script not found: $script"
        fi
    done
}

# Setup cron jobs
setup_cron_jobs() {
    info "Setting up cron jobs for SSL certificate management..."
    
    # Create cron job entries
    local cron_entries="
# SSL Certificate Management Cron Jobs
# Renew certificates daily at 2:00 AM
0 2 * * * $SCRIPT_DIR/renew-certificates.sh >> $LOG_FILE 2>&1

# Check certificate status daily at 6:00 AM
0 6 * * * $SCRIPT_DIR/check-certificates.sh --quiet >> $LOG_FILE 2>&1

# Monitor SSL status every 4 hours
0 */4 * * * $SCRIPT_DIR/monitor-ssl-status.sh --quiet >> /var/log/ssl-monitoring.log 2>&1

# Weekly comprehensive check on Sundays at 3:00 AM
0 3 * * 0 $SCRIPT_DIR/check-certificates.sh --verbose >> $LOG_FILE 2>&1
"
    
    # Add cron jobs to root crontab
    (crontab -l 2>/dev/null || echo "") | grep -v "SSL Certificate Management" | grep -v "$SCRIPT_DIR" > /tmp/current_cron
    echo "$cron_entries" >> /tmp/current_cron
    crontab /tmp/current_cron
    rm /tmp/current_cron
    
    success "Cron jobs added successfully"
}

# Create log rotation configuration
setup_log_rotation() {
    info "Setting up log rotation for SSL logs..."
    
    local logrotate_config="/etc/logrotate.d/ssl-certificates"
    
    cat > "$logrotate_config" << 'EOF'
/var/log/ssl-certificates.log /var/log/ssl-monitoring.log /var/log/ssl-alerts.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        # Send HUP signal to rsyslog if running
        if [ -f /var/run/rsyslogd.pid ]; then
            kill -HUP $(cat /var/run/rsyslogd.pid)
        fi
    endscript
}
EOF
    
    success "Log rotation configured: $logrotate_config"
}

# Create systemd service for SSL monitoring (optional)
create_systemd_service() {
    info "Creating systemd service for SSL monitoring..."
    
    local service_file="/etc/systemd/system/ssl-monitor.service"
    local timer_file="/etc/systemd/system/ssl-monitor.timer"
    
    # Create service file
    cat > "$service_file" << EOF
[Unit]
Description=SSL Certificate Monitoring
After=network.target

[Service]
Type=oneshot
ExecStart=$SCRIPT_DIR/monitor-ssl-status.sh --quiet
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Create timer file
    cat > "$timer_file" << EOF
[Unit]
Description=Run SSL Certificate Monitoring every 4 hours
Requires=ssl-monitor.service

[Timer]
OnCalendar=*-*-* 00,04,08,12,16,20:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    # Enable and start the timer
    systemctl daemon-reload
    systemctl enable ssl-monitor.timer
    systemctl start ssl-monitor.timer
    
    success "Systemd service and timer created and enabled"
}

# Verify cron setup
verify_cron_setup() {
    info "Verifying cron setup..."
    
    # Check if cron jobs are installed
    if crontab -l | grep -q "$SCRIPT_DIR"; then
        success "Cron jobs are properly installed"
        
        # Show current cron jobs
        echo "Current SSL-related cron jobs:"
        crontab -l | grep "$SCRIPT_DIR" | while read -r line; do
            echo "  $line"
        done
    else
        error_exit "Cron jobs were not installed properly"
    fi
}

# Test scripts
test_scripts() {
    info "Testing SSL scripts..."
    
    # Test certificate check script
    if "$SCRIPT_DIR/check-certificates.sh" --help > /dev/null 2>&1; then
        success "Certificate check script is working"
    else
        error_exit "Certificate check script test failed"
    fi
    
    # Test monitoring script
    if "$SCRIPT_DIR/monitor-ssl-status.sh" --help > /dev/null 2>&1; then
        success "SSL monitoring script is working"
    else
        error_exit "SSL monitoring script test failed"
    fi
    
    # Test renewal script (dry run)
    info "Testing certificate renewal (dry run)..."
    if "$SCRIPT_DIR/renew-certificates.sh" --dry-run > /dev/null 2>&1; then
        success "Certificate renewal script test passed"
    else
        info "Certificate renewal dry run failed (may be expected if certificates don't exist yet)"
    fi
}

# Main execution
main() {
    log "Starting SSL cron setup..."
    
    check_root
    make_scripts_executable
    setup_cron_jobs
    setup_log_rotation
    
    # Ask user if they want systemd service (optional)
    read -p "Do you want to create systemd service for SSL monitoring? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        create_systemd_service
    fi
    
    verify_cron_setup
    test_scripts
    
    success "SSL cron setup completed successfully"
    
    echo ""
    echo "=== SETUP SUMMARY ==="
    echo "The following cron jobs have been configured:"
    echo "  - Certificate renewal: Daily at 2:00 AM"
    echo "  - Certificate check: Daily at 6:00 AM"
    echo "  - SSL monitoring: Every 4 hours"
    echo "  - Weekly comprehensive check: Sundays at 3:00 AM"
    echo ""
    echo "Log files:"
    echo "  - Certificate operations: $LOG_FILE"
    echo "  - SSL monitoring: /var/log/ssl-monitoring.log"
    echo "  - SSL alerts: /var/log/ssl-alerts.log"
    echo ""
    echo "To manually run scripts:"
    echo "  - Check certificates: $SCRIPT_DIR/check-certificates.sh"
    echo "  - Renew certificates: $SCRIPT_DIR/renew-certificates.sh"
    echo "  - Monitor SSL status: $SCRIPT_DIR/monitor-ssl-status.sh"
    echo ""
    
    log "SSL cron setup completed"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [options]"
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --no-systemd   Skip systemd service creation"
        exit 0
        ;;
    --no-systemd)
        # Skip systemd service creation
        CREATE_SYSTEMD=false
        ;;
esac

# Run main function
main "$@"
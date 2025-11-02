#!/bin/bash

# Setup monitoring cron jobs for HTTPS infrastructure
# This script configures automated monitoring and alerting

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
CRON_LOG="$LOG_DIR/cron_setup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$CRON_LOG"
}

# Error handling
error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    log "ERROR: $1"
    exit 1
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

# Check if running as root or with sudo
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        warning "Running as root. This is not recommended for cron setup."
        warning "Consider running as the application user instead."
    fi
}

# Ensure directories exist
setup_directories() {
    info "Setting up directories..."
    
    mkdir -p "$LOG_DIR"
    mkdir -p "$PROJECT_DIR/scripts"
    
    # Ensure log files exist with proper permissions
    touch "$LOG_DIR/monitoring_dashboard.log"
    touch "$LOG_DIR/https_monitoring.log"
    touch "$LOG_DIR/ssl_events.log"
    touch "$LOG_DIR/certificate_expiry.log"
    touch "$LOG_DIR/security_events.log"
    touch "$LOG_DIR/cron_monitoring.log"
    
    success "Directories and log files created"
}

# Create monitoring wrapper scripts
create_wrapper_scripts() {
    info "Creating monitoring wrapper scripts..."
    
    # Dashboard monitoring wrapper
    cat > "$SCRIPT_DIR/cron-dashboard-monitor.sh" << 'EOF'
#!/bin/bash
# Cron wrapper for dashboard monitoring

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/cron_monitoring.log"

cd "$PROJECT_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting dashboard monitoring" >> "$LOG_FILE"

# Run dashboard monitoring
python3 "$SCRIPT_DIR/monitoring-dashboard.py" --json > "$PROJECT_DIR/logs/latest_dashboard.json" 2>> "$LOG_FILE"
EXIT_CODE=$?

echo "$(date '+%Y-%m-%d %H:%M:%S') - Dashboard monitoring completed with exit code: $EXIT_CODE" >> "$LOG_FILE"

# If critical issues found, you could add alerting here
if [ $EXIT_CODE -eq 2 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - CRITICAL: Dashboard monitoring found critical issues" >> "$LOG_FILE"
    # Add your alerting mechanism here (email, webhook, etc.)
fi

exit $EXIT_CODE
EOF

    # SSL monitoring wrapper
    cat > "$SCRIPT_DIR/cron-ssl-monitor.sh" << 'EOF'
#!/bin/bash
# Cron wrapper for SSL monitoring

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/cron_monitoring.log"

cd "$PROJECT_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting SSL monitoring" >> "$LOG_FILE"

# Run SSL monitoring
python3 "$SCRIPT_DIR/ssl-monitoring-system.py" --json > "$PROJECT_DIR/logs/latest_ssl.json" 2>> "$LOG_FILE"
EXIT_CODE=$?

echo "$(date '+%Y-%m-%d %H:%M:%S') - SSL monitoring completed with exit code: $EXIT_CODE" >> "$LOG_FILE"

# Check for certificate renewal needs
if [ $EXIT_CODE -eq 2 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - CRITICAL: SSL monitoring found critical certificate issues" >> "$LOG_FILE"
    
    # Attempt automatic renewal for critical certificates
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Attempting automatic certificate renewal" >> "$LOG_FILE"
    python3 "$SCRIPT_DIR/ssl-monitoring-system.py" --renew >> "$LOG_FILE" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Certificate renewal completed successfully" >> "$LOG_FILE"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Certificate renewal failed - manual intervention required" >> "$LOG_FILE"
    fi
fi

exit $EXIT_CODE
EOF

    # HTTPS monitoring wrapper
    cat > "$SCRIPT_DIR/cron-https-monitor.sh" << 'EOF'
#!/bin/bash
# Cron wrapper for HTTPS monitoring

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/cron_monitoring.log"

cd "$PROJECT_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting HTTPS monitoring" >> "$LOG_FILE"

# Run HTTPS monitoring
python3 "$SCRIPT_DIR/monitor-domains-https.py" --json > "$PROJECT_DIR/logs/latest_https.json" 2>> "$LOG_FILE"
EXIT_CODE=$?

echo "$(date '+%Y-%m-%d %H:%M:%S') - HTTPS monitoring completed with exit code: $EXIT_CODE" >> "$LOG_FILE"

if [ $EXIT_CODE -eq 1 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: HTTPS monitoring found issues" >> "$LOG_FILE"
elif [ $EXIT_CODE -eq 2 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - CRITICAL: HTTPS monitoring found critical issues" >> "$LOG_FILE"
fi

exit $EXIT_CODE
EOF

    # Make scripts executable
    chmod +x "$SCRIPT_DIR/cron-dashboard-monitor.sh"
    chmod +x "$SCRIPT_DIR/cron-ssl-monitor.sh"
    chmod +x "$SCRIPT_DIR/cron-https-monitor.sh"
    
    success "Monitoring wrapper scripts created"
}

# Setup cron jobs
setup_cron_jobs() {
    info "Setting up cron jobs..."
    
    # Get current user's crontab
    TEMP_CRON=$(mktemp)
    crontab -l > "$TEMP_CRON" 2>/dev/null || true
    
    # Remove existing monitoring cron jobs (if any)
    sed -i '/# INSFLOW MONITORING/d' "$TEMP_CRON" 2>/dev/null || true
    sed -i '/cron-dashboard-monitor.sh/d' "$TEMP_CRON" 2>/dev/null || true
    sed -i '/cron-ssl-monitor.sh/d' "$TEMP_CRON" 2>/dev/null || true
    sed -i '/cron-https-monitor.sh/d' "$TEMP_CRON" 2>/dev/null || true
    
    # Add new monitoring cron jobs
    cat >> "$TEMP_CRON" << EOF

# INSFLOW MONITORING - Auto-generated by setup-monitoring-cron.sh
# Dashboard monitoring every 15 minutes
*/15 * * * * $SCRIPT_DIR/cron-dashboard-monitor.sh

# SSL monitoring every hour
0 * * * * $SCRIPT_DIR/cron-ssl-monitor.sh

# HTTPS monitoring every 30 minutes
*/30 * * * * $SCRIPT_DIR/cron-https-monitor.sh

# Log rotation daily at 2 AM
0 2 * * * find $LOG_DIR -name "*.log" -size +100M -exec truncate -s 50M {} \;

EOF

    # Install the new crontab
    crontab "$TEMP_CRON"
    rm "$TEMP_CRON"
    
    success "Cron jobs installed successfully"
}

# Create log rotation script
setup_log_rotation() {
    info "Setting up log rotation..."
    
    cat > "$SCRIPT_DIR/rotate-monitoring-logs.sh" << 'EOF'
#!/bin/bash
# Log rotation script for monitoring logs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

# Rotate logs larger than 100MB
find "$LOG_DIR" -name "*.log" -size +100M -exec sh -c '
    for file; do
        echo "$(date) - Rotating log file: $file"
        # Keep last 50MB of the file
        tail -c 52428800 "$file" > "$file.tmp" && mv "$file.tmp" "$file"
    done
' sh {} +

# Clean up old JSON files (keep last 7 days)
find "$LOG_DIR" -name "*.json" -mtime +7 -delete

echo "$(date) - Log rotation completed"
EOF

    chmod +x "$SCRIPT_DIR/rotate-monitoring-logs.sh"
    
    success "Log rotation script created"
}

# Create monitoring status script
create_status_script() {
    info "Creating monitoring status script..."
    
    cat > "$SCRIPT_DIR/monitoring-status.sh" << 'EOF'
#!/bin/bash
# Quick monitoring status check

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== INSFLOW MONITORING STATUS ==="
echo "Generated: $(date)"
echo ""

# Check if cron jobs are running
echo "📅 CRON JOBS:"
crontab -l | grep -E "(dashboard-monitor|ssl-monitor|https-monitor)" | while read line; do
    echo "  ✓ $line"
done
echo ""

# Check recent log activity
echo "📋 RECENT ACTIVITY:"
if [ -f "$PROJECT_DIR/logs/cron_monitoring.log" ]; then
    echo "Last 5 monitoring events:"
    tail -5 "$PROJECT_DIR/logs/cron_monitoring.log" | sed 's/^/  /'
else
    echo "  No monitoring log found"
fi
echo ""

# Check latest results
echo "📊 LATEST RESULTS:"
if [ -f "$PROJECT_DIR/logs/latest_dashboard.json" ]; then
    DASHBOARD_STATUS=$(python3 -c "
import json, sys
try:
    with open('$PROJECT_DIR/logs/latest_dashboard.json', 'r') as f:
        data = json.load(f)
    print(f\"Dashboard: {data.get('overall_status', 'unknown')}\")
except:
    print('Dashboard: error reading data')
")
    echo "  $DASHBOARD_STATUS"
else
    echo "  Dashboard: no data available"
fi

if [ -f "$PROJECT_DIR/logs/latest_ssl.json" ]; then
    SSL_STATUS=$(python3 -c "
import json, sys
try:
    with open('$PROJECT_DIR/logs/latest_ssl.json', 'r') as f:
        data = json.load(f)
    print(f\"SSL: {data.get('overall_health', 'unknown')}\")
except:
    print('SSL: error reading data')
")
    echo "  $SSL_STATUS"
else
    echo "  SSL: no data available"
fi

if [ -f "$PROJECT_DIR/logs/latest_https.json" ]; then
    HTTPS_STATUS=$(python3 -c "
import json, sys
try:
    with open('$PROJECT_DIR/logs/latest_https.json', 'r') as f:
        data = json.load(f)
    summary = data.get('summary', {})
    total = summary.get('total_domains', 0)
    healthy = summary.get('healthy_domains', 0)
    print(f\"HTTPS: {healthy}/{total} domains healthy\")
except:
    print('HTTPS: error reading data')
")
    echo "  $HTTPS_STATUS"
else
    echo "  HTTPS: no data available"
fi

echo ""
echo "=== END STATUS ==="
EOF

    chmod +x "$SCRIPT_DIR/monitoring-status.sh"
    
    success "Monitoring status script created"
}

# Display setup summary
display_summary() {
    info "Monitoring cron setup completed successfully!"
    echo ""
    echo "📋 SETUP SUMMARY:"
    echo "  ✓ Monitoring wrapper scripts created"
    echo "  ✓ Cron jobs installed:"
    echo "    - Dashboard monitoring: every 15 minutes"
    echo "    - SSL monitoring: every hour"
    echo "    - HTTPS monitoring: every 30 minutes"
    echo "    - Log rotation: daily at 2 AM"
    echo "  ✓ Log rotation script created"
    echo "  ✓ Status checking script created"
    echo ""
    echo "🔧 MANAGEMENT COMMANDS:"
    echo "  View cron jobs:     crontab -l"
    echo "  Check status:       $SCRIPT_DIR/monitoring-status.sh"
    echo "  Manual dashboard:   $SCRIPT_DIR/monitoring-dashboard.py"
    echo "  Manual SSL check:   $SCRIPT_DIR/ssl-monitoring-system.py"
    echo "  Manual HTTPS check: $SCRIPT_DIR/monitor-domains-https.py"
    echo ""
    echo "📁 LOG LOCATIONS:"
    echo "  Main logs:          $LOG_DIR/"
    echo "  Cron activity:      $LOG_DIR/cron_monitoring.log"
    echo "  Latest results:     $LOG_DIR/latest_*.json"
    echo ""
    echo "⚠️  IMPORTANT NOTES:"
    echo "  - Monitoring will start automatically"
    echo "  - Check logs regularly for issues"
    echo "  - Critical SSL issues trigger automatic renewal attempts"
    echo "  - Customize alerting in wrapper scripts as needed"
}

# Main execution
main() {
    log "Starting monitoring cron setup..."
    
    check_permissions
    setup_directories
    create_wrapper_scripts
    setup_cron_jobs
    setup_log_rotation
    create_status_script
    display_summary
    
    success "Monitoring cron setup completed successfully"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [options]"
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --remove       Remove monitoring cron jobs"
        echo "  --status       Show current monitoring status"
        exit 0
        ;;
    --remove)
        info "Removing monitoring cron jobs..."
        TEMP_CRON=$(mktemp)
        crontab -l > "$TEMP_CRON" 2>/dev/null || true
        sed -i '/# INSFLOW MONITORING/d' "$TEMP_CRON" 2>/dev/null || true
        sed -i '/cron-dashboard-monitor.sh/d' "$TEMP_CRON" 2>/dev/null || true
        sed -i '/cron-ssl-monitor.sh/d' "$TEMP_CRON" 2>/dev/null || true
        sed -i '/cron-https-monitor.sh/d' "$TEMP_CRON" 2>/dev/null || true
        crontab "$TEMP_CRON"
        rm "$TEMP_CRON"
        success "Monitoring cron jobs removed"
        exit 0
        ;;
    --status)
        if [ -f "$SCRIPT_DIR/monitoring-status.sh" ]; then
            "$SCRIPT_DIR/monitoring-status.sh"
        else
            error "Monitoring status script not found. Run setup first."
        fi
        exit 0
        ;;
esac

# Run main function
main "$@"
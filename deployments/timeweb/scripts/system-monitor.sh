#!/bin/bash

# System Monitoring Script for Timeweb Deployment
# 
# This script provides ongoing monitoring of the Timeweb deployment system
# including resource usage, service status, and performance metrics.
#
# Requirements: 4.3, 4.4
#
# Usage:
#   ./system-monitor.sh [OPTIONS]
#
# Options:
#   --continuous     Run continuous monitoring (default: single check)
#   --interval SEC   Monitoring interval in seconds (default: 60)
#   --duration SEC   Total monitoring duration in seconds (0 = infinite)
#   --metrics        Include detailed metrics
#   --alerts         Enable alerting for critical issues
#   --json          Output results in JSON format
#   --log-file FILE  Custom log file path
#   --help          Show this help message

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_LOG_FILE="${PROJECT_DIR}/logs/system-monitoring.log"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Default options
CONTINUOUS_MODE=false
MONITORING_INTERVAL=60
MONITORING_DURATION=0
INCLUDE_METRICS=false
ENABLE_ALERTS=false
JSON_OUTPUT=false
LOG_FILE="$DEFAULT_LOG_FILE"

# Alert thresholds
CPU_THRESHOLD=80
MEMORY_THRESHOLD=80
DISK_THRESHOLD=85
RESPONSE_TIME_THRESHOLD=5000  # milliseconds

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Monitoring state
START_TIME=$(date +%s)
MONITORING_ACTIVE=true

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
    
    # Log to console (unless JSON output)
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
            "ALERT")
                echo -e "${RED}[ALERT]${NC} $message"
                ;;
        esac
    fi
}

# Error handling
error_exit() {
    log "ERROR" "$1"
    exit 1
}

# Cleanup function
cleanup() {
    MONITORING_ACTIVE=false
    log "INFO" "Monitoring stopped"
    exit 0
}

trap cleanup INT TERM

# Show help
show_help() {
    cat << EOF
System Monitoring Script for Timeweb Deployment

This script provides ongoing monitoring of the Timeweb deployment system
including resource usage, service status, and performance metrics.

Usage:
    $0 [OPTIONS]

Options:
    --continuous     Run continuous monitoring (default: single check)
    --interval SEC   Monitoring interval in seconds (default: 60)
    --duration SEC   Total monitoring duration in seconds (0 = infinite)
    --metrics        Include detailed metrics
    --alerts         Enable alerting for critical issues
    --json          Output results in JSON format
    --log-file FILE  Custom log file path
    --help          Show this help message

Alert Thresholds:
    CPU Usage: ${CPU_THRESHOLD}%
    Memory Usage: ${MEMORY_THRESHOLD}%
    Disk Usage: ${DISK_THRESHOLD}%
    Response Time: ${RESPONSE_TIME_THRESHOLD}ms

Examples:
    # Single monitoring check
    $0

    # Continuous monitoring every 30 seconds
    $0 --continuous --interval 30

    # Monitor for 1 hour with metrics
    $0 --continuous --duration 3600 --metrics

    # JSON output for external monitoring
    $0 --json --metrics

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --continuous)
                CONTINUOUS_MODE=true
                shift
                ;;
            --interval)
                MONITORING_INTERVAL="$2"
                shift 2
                ;;
            --duration)
                MONITORING_DURATION="$2"
                shift 2
                ;;
            --metrics)
                INCLUDE_METRICS=true
                shift
                ;;
            --alerts)
                ENABLE_ALERTS=true
                shift
                ;;
            --json)
                JSON_OUTPUT=true
                shift
                ;;
            --log-file)
                LOG_FILE="$2"
                shift 2
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
    
    # Validate numeric arguments
    if ! [[ "$MONITORING_INTERVAL" =~ ^[0-9]+$ ]] || [[ "$MONITORING_INTERVAL" -lt 1 ]]; then
        error_exit "Invalid monitoring interval: $MONITORING_INTERVAL"
    fi
    
    if ! [[ "$MONITORING_DURATION" =~ ^[0-9]+$ ]]; then
        error_exit "Invalid monitoring duration: $MONITORING_DURATION"
    fi
}

# Check prerequisites
check_prerequisites() {
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

# Get system metrics
get_system_metrics() {
    local metrics="{}"
    
    # CPU usage
    local cpu_usage
    if command -v top &> /dev/null; then
        cpu_usage=$(top -l 1 -n 0 | grep "CPU usage" | awk '{print $3}' | sed 's/%//' 2>/dev/null || echo "0")
    else
        cpu_usage="0"
    fi
    
    # Memory usage
    local memory_info
    if command -v vm_stat &> /dev/null; then
        memory_info=$(vm_stat 2>/dev/null || echo "")
        local pages_free pages_active pages_inactive pages_wired page_size
        pages_free=$(echo "$memory_info" | grep "Pages free" | awk '{print $3}' | sed 's/\.//' || echo "0")
        pages_active=$(echo "$memory_info" | grep "Pages active" | awk '{print $3}' | sed 's/\.//' || echo "0")
        pages_inactive=$(echo "$memory_info" | grep "Pages inactive" | awk '{print $3}' | sed 's/\.//' || echo "0")
        pages_wired=$(echo "$memory_info" | grep "Pages wired down" | awk '{print $4}' | sed 's/\.//' || echo "0")
        page_size=4096  # Default page size on macOS
        
        local total_memory used_memory memory_usage_percent
        total_memory=$(((pages_free + pages_active + pages_inactive + pages_wired) * page_size / 1024 / 1024))
        used_memory=$(((pages_active + pages_inactive + pages_wired) * page_size / 1024 / 1024))
        
        if [[ $total_memory -gt 0 ]]; then
            memory_usage_percent=$((used_memory * 100 / total_memory))
        else
            memory_usage_percent=0
        fi
    else
        memory_usage_percent=0
        total_memory=0
        used_memory=0
    fi
    
    # Disk usage
    local disk_usage_percent
    disk_usage_percent=$(df / | tail -1 | awk '{print $5}' | sed 's/%//' 2>/dev/null || echo "0")
    
    # Load average
    local load_average
    load_average=$(uptime | awk -F'load averages:' '{print $2}' | xargs 2>/dev/null || echo "0.00 0.00 0.00")
    
    # Docker stats
    local docker_stats="{}"
    if docker info &> /dev/null; then
        local containers_running containers_total
        containers_running=$(docker ps -q | wc -l | xargs)
        containers_total=$(docker ps -a -q | wc -l | xargs)
        
        docker_stats=$(cat << EOF
{
    "containers_running": $containers_running,
    "containers_total": $containers_total
}
EOF
)
    fi
    
    metrics=$(cat << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "cpu_usage_percent": $cpu_usage,
    "memory": {
        "usage_percent": $memory_usage_percent,
        "total_mb": $total_memory,
        "used_mb": $used_memory
    },
    "disk_usage_percent": $disk_usage_percent,
    "load_average": "$load_average",
    "docker": $docker_stats
}
EOF
)
    
    echo "$metrics"
}

# Get service status
get_service_status() {
    local services_status="{}"
    
    # Get running services
    local running_services
    running_services=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null || echo "")
    
    if [[ -n "$running_services" ]]; then
        local services_array
        readarray -t services_array <<< "$running_services"
        local service_details=()
        
        for service in "${services_array[@]}"; do
            if [[ -z "$service" ]]; then
                continue
            fi
            
            # Get service status and health
            local service_info
            service_info=$(docker compose -f "$COMPOSE_FILE" ps "$service" --format "json" 2>/dev/null || echo "{}")
            
            if [[ -n "$service_info" && "$service_info" != "{}" ]]; then
                # Extract relevant information
                local status health
                status=$(echo "$service_info" | jq -r '.State // "unknown"' 2>/dev/null || echo "unknown")
                health=$(echo "$service_info" | jq -r '.Health // "none"' 2>/dev/null || echo "none")
                
                local service_detail=$(cat << EOF
{
    "name": "$service",
    "status": "$status",
    "health": "$health"
}
EOF
)
                service_details+=("$service_detail")
            fi
        done
        
        services_status=$(cat << EOF
{
    "total_services": ${#services_array[@]},
    "services": [$(IFS=','; echo "${service_details[*]}")]
}
EOF
)
    else
        services_status='{"total_services": 0, "services": []}'
    fi
    
    echo "$services_status"
}

# Get application metrics
get_application_metrics() {
    local app_metrics="{}"
    
    # Test HTTP response time
    local http_response_time=0
    local http_status="unknown"
    
    if command -v curl &> /dev/null; then
        local start_time end_time
        start_time=$(date +%s%3N)
        
        if curl -s -f -L --max-time 10 "http://localhost/healthz/" > /dev/null 2>&1; then
            end_time=$(date +%s%3N)
            http_response_time=$((end_time - start_time))
            http_status="ok"
        else
            http_status="error"
        fi
    fi
    
    # Test HTTPS response time (if available)
    local https_response_time=0
    local https_status="unknown"
    
    if [[ -n "${DOMAINS:-}" ]] && command -v curl &> /dev/null; then
        local domains_array
        IFS=',' read -ra domains_array <<< "$DOMAINS"
        local first_domain
        first_domain=$(echo "${domains_array[0]}" | xargs)
        
        local start_time end_time
        start_time=$(date +%s%3N)
        
        if curl -s -f -L --max-time 10 --insecure "https://$first_domain/healthz/" > /dev/null 2>&1; then
            end_time=$(date +%s%3N)
            https_response_time=$((end_time - start_time))
            https_status="ok"
        else
            https_status="error"
        fi
    fi
    
    app_metrics=$(cat << EOF
{
    "http": {
        "response_time_ms": $http_response_time,
        "status": "$http_status"
    },
    "https": {
        "response_time_ms": $https_response_time,
        "status": "$https_status"
    }
}
EOF
)
    
    echo "$app_metrics"
}

# Check for alerts
check_alerts() {
    local metrics="$1"
    local alerts=()
    
    # CPU usage alert
    local cpu_usage
    cpu_usage=$(echo "$metrics" | jq -r '.system.cpu_usage_percent // 0')
    if (( $(echo "$cpu_usage > $CPU_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        alerts+=("High CPU usage: ${cpu_usage}%")
    fi
    
    # Memory usage alert
    local memory_usage
    memory_usage=$(echo "$metrics" | jq -r '.system.memory.usage_percent // 0')
    if (( $(echo "$memory_usage > $MEMORY_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        alerts+=("High memory usage: ${memory_usage}%")
    fi
    
    # Disk usage alert
    local disk_usage
    disk_usage=$(echo "$metrics" | jq -r '.system.disk_usage_percent // 0')
    if (( $(echo "$disk_usage > $DISK_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        alerts+=("High disk usage: ${disk_usage}%")
    fi
    
    # Response time alert
    local http_response_time
    http_response_time=$(echo "$metrics" | jq -r '.application.http.response_time_ms // 0')
    if (( $(echo "$http_response_time > $RESPONSE_TIME_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        alerts+=("Slow HTTP response: ${http_response_time}ms")
    fi
    
    # Service health alerts
    local unhealthy_services
    unhealthy_services=$(echo "$metrics" | jq -r '.services.services[] | select(.health == "unhealthy" or .status != "running") | .name' 2>/dev/null || echo "")
    
    if [[ -n "$unhealthy_services" ]]; then
        while IFS= read -r service; do
            if [[ -n "$service" ]]; then
                alerts+=("Unhealthy service: $service")
            fi
        done <<< "$unhealthy_services"
    fi
    
    # Send alerts if enabled
    if [[ "$ENABLE_ALERTS" == "true" && ${#alerts[@]} -gt 0 ]]; then
        for alert in "${alerts[@]}"; do
            log "ALERT" "$alert"
            send_alert "$alert"
        done
    fi
    
    # Return alerts as JSON array
    local alerts_json="[]"
    if [[ ${#alerts[@]} -gt 0 ]]; then
        local alerts_quoted=()
        for alert in "${alerts[@]}"; do
            alerts_quoted+=("\"$alert\"")
        done
        alerts_json="[$(IFS=','; echo "${alerts_quoted[*]}")]"
    fi
    
    echo "$alerts_json"
}

# Send alert (placeholder for integration with external systems)
send_alert() {
    local message="$1"
    
    # Here you can add integration with external alerting systems:
    # - Email notifications
    # - Slack/Discord webhooks
    # - PagerDuty/Opsgenie
    # - Custom webhook endpoints
    
    # Example webhook call (uncomment and configure as needed):
    # if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    #     curl -X POST "$ALERT_WEBHOOK_URL" \
    #         -H "Content-Type: application/json" \
    #         -d "{\"message\": \"$message\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" || true
    # fi
    
    log "DEBUG" "Alert sent: $message"
}

# Perform monitoring check
perform_monitoring_check() {
    local system_metrics service_status app_metrics alerts
    
    # Collect metrics
    system_metrics=$(get_system_metrics)
    service_status=$(get_service_status)
    
    if [[ "$INCLUDE_METRICS" == "true" ]]; then
        app_metrics=$(get_application_metrics)
    else
        app_metrics='{"http": {"status": "not_checked"}, "https": {"status": "not_checked"}}'
    fi
    
    # Combine all metrics
    local combined_metrics
    combined_metrics=$(cat << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "system": $system_metrics,
    "services": $service_status,
    "application": $app_metrics
}
EOF
)
    
    # Check for alerts
    alerts=$(check_alerts "$combined_metrics")
    
    # Add alerts to metrics
    combined_metrics=$(echo "$combined_metrics" | jq ". + {\"alerts\": $alerts}")
    
    # Output results
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo "$combined_metrics" | jq '.'
    else
        display_monitoring_results "$combined_metrics"
    fi
    
    # Log summary
    local alerts_count
    alerts_count=$(echo "$alerts" | jq 'length')
    log "INFO" "Monitoring check completed: $alerts_count alerts"
}

# Display monitoring results in human-readable format
display_monitoring_results() {
    local metrics="$1"
    
    echo -e "${CYAN}=== System Monitoring Report ===${NC}"
    echo "Timestamp: $(date)"
    echo
    
    # System metrics
    echo -e "${BLUE}System Resources:${NC}"
    local cpu_usage memory_usage disk_usage
    cpu_usage=$(echo "$metrics" | jq -r '.system.cpu_usage_percent // 0')
    memory_usage=$(echo "$metrics" | jq -r '.system.memory.usage_percent // 0')
    disk_usage=$(echo "$metrics" | jq -r '.system.disk_usage_percent // 0')
    
    echo "  CPU Usage: ${cpu_usage}%"
    echo "  Memory Usage: ${memory_usage}%"
    echo "  Disk Usage: ${disk_usage}%"
    
    local load_average
    load_average=$(echo "$metrics" | jq -r '.system.load_average // "unknown"')
    echo "  Load Average: $load_average"
    echo
    
    # Service status
    echo -e "${BLUE}Services:${NC}"
    local total_services
    total_services=$(echo "$metrics" | jq -r '.services.total_services // 0')
    echo "  Total Services: $total_services"
    
    if [[ $total_services -gt 0 ]]; then
        echo "$metrics" | jq -r '.services.services[] | "  \(.name): \(.status) (\(.health))"' 2>/dev/null || true
    fi
    echo
    
    # Application metrics (if included)
    if [[ "$INCLUDE_METRICS" == "true" ]]; then
        echo -e "${BLUE}Application Performance:${NC}"
        local http_status http_time https_status https_time
        http_status=$(echo "$metrics" | jq -r '.application.http.status // "unknown"')
        http_time=$(echo "$metrics" | jq -r '.application.http.response_time_ms // 0')
        https_status=$(echo "$metrics" | jq -r '.application.https.status // "unknown"')
        https_time=$(echo "$metrics" | jq -r '.application.https.response_time_ms // 0')
        
        echo "  HTTP: $http_status (${http_time}ms)"
        echo "  HTTPS: $https_status (${https_time}ms)"
        echo
    fi
    
    # Alerts
    local alerts_count
    alerts_count=$(echo "$metrics" | jq -r '.alerts | length')
    
    if [[ $alerts_count -gt 0 ]]; then
        echo -e "${RED}Alerts ($alerts_count):${NC}"
        echo "$metrics" | jq -r '.alerts[] | "  • \(.)"' 2>/dev/null || true
        echo
    else
        echo -e "${GREEN}No alerts${NC}"
        echo
    fi
}

# Main monitoring loop
run_monitoring() {
    log "INFO" "Starting system monitoring (continuous: $CONTINUOUS_MODE, interval: ${MONITORING_INTERVAL}s)"
    
    local iteration=0
    
    while [[ "$MONITORING_ACTIVE" == "true" ]]; do
        ((iteration++))
        
        if [[ "$CONTINUOUS_MODE" != "true" && "$JSON_OUTPUT" != "true" ]]; then
            echo -e "${CYAN}Monitoring Check #$iteration${NC}"
        fi
        
        # Perform monitoring check
        perform_monitoring_check
        
        # Check if we should stop (single check mode)
        if [[ "$CONTINUOUS_MODE" != "true" ]]; then
            break
        fi
        
        # Check duration limit
        if [[ $MONITORING_DURATION -gt 0 ]]; then
            local current_time elapsed_time
            current_time=$(date +%s)
            elapsed_time=$((current_time - START_TIME))
            
            if [[ $elapsed_time -ge $MONITORING_DURATION ]]; then
                log "INFO" "Monitoring duration limit reached: ${elapsed_time}s"
                break
            fi
        fi
        
        # Wait for next iteration
        if [[ "$JSON_OUTPUT" != "true" ]]; then
            echo "Next check in ${MONITORING_INTERVAL} seconds..."
            echo
        fi
        
        sleep "$MONITORING_INTERVAL"
    done
    
    log "INFO" "Monitoring completed after $iteration iteration(s)"
}

# Main function
main() {
    # Parse command line arguments
    parse_args "$@"
    
    # Check prerequisites
    check_prerequisites
    
    # Start monitoring
    run_monitoring
}

# Run main function with all arguments
main "$@"
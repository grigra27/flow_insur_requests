#!/bin/sh
# Certbot renewal hook script
# This script runs after successful certificate renewal
# and restarts nginx to load the new certificates

set -e

LOG_FILE="/var/log/letsencrypt/renew-hook.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "Certificate renewal detected, restarting nginx container..."

# Find the nginx container name
NGINX_CONTAINER=$(docker ps --filter "name=nginx" --format "{{.Names}}" | head -1)

if [ -z "$NGINX_CONTAINER" ]; then
    log "ERROR: Could not find nginx container"
    exit 1
fi

log "Found nginx container: $NGINX_CONTAINER"

# Restart nginx container
if docker restart "$NGINX_CONTAINER"; then
    log "SUCCESS: Nginx container restarted successfully"
    
    # Wait a moment for nginx to start
    sleep 3
    
    # Verify nginx is running
    if docker ps --filter "name=nginx" --filter "status=running" | grep -q nginx; then
        log "SUCCESS: Nginx is running and healthy"
    else
        log "WARNING: Nginx restarted but may not be healthy"
    fi
else
    log "ERROR: Failed to restart nginx container"
    exit 1
fi

log "Certificate renewal hook completed successfully"
exit 0

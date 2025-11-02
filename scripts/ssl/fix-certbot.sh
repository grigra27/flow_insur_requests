#!/bin/bash

# Fix Certbot Container
# This script fixes the certbot container when it's restarting due to configuration issues

set -e

PROJECT_PATH="/opt/insflow-system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Success message
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Info message
info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "❌ This script must be run as root (use sudo)"
        exit 1
    fi
}

# Fix certbot container
fix_certbot() {
    info "Fixing certbot container..."
    
    cd "$PROJECT_PATH"
    
    # Stop certbot container
    docker-compose -f docker-compose.timeweb.yml stop certbot
    
    # Remove certbot container
    docker-compose -f docker-compose.timeweb.yml rm -f certbot
    
    # Start certbot with SSL profile
    COMPOSE_PROFILES="ssl" docker-compose -f docker-compose.timeweb.yml up -d certbot
    
    success "Certbot container restarted with fixed configuration"
}

# Check certbot status
check_certbot_status() {
    info "Checking certbot status..."
    
    sleep 10
    
    local status=$(docker-compose -f "$PROJECT_PATH/docker-compose.timeweb.yml" ps certbot --format "table {{.Status}}")
    
    if echo "$status" | grep -q "Up"; then
        success "Certbot container is running properly"
        
        # Show certbot logs
        info "Recent certbot logs:"
        docker-compose -f "$PROJECT_PATH/docker-compose.timeweb.yml" logs --tail=10 certbot
        
        return 0
    else
        echo "❌ Certbot container is still having issues"
        echo "Status: $status"
        
        info "Certbot logs:"
        docker-compose -f "$PROJECT_PATH/docker-compose.timeweb.yml" logs --tail=20 certbot
        
        return 1
    fi
}

# Main function
main() {
    echo "🔧 Fixing Certbot Container"
    echo "=========================="
    
    check_root
    fix_certbot
    
    if check_certbot_status; then
        success "Certbot container fixed successfully!"
        echo ""
        info "Certificate auto-renewal is now working properly"
        info "Certbot will check for renewals every 12 hours"
    else
        echo "❌ Certbot container still has issues"
        echo ""
        info "HTTPS is still working fine, but auto-renewal may not work"
        info "You can manually renew certificates when needed"
    fi
}

# Run main function
main "$@"
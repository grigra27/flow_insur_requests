#!/bin/bash

# Check SSL Certificates Status
# This script checks if SSL certificates exist and shows their status

set -e

PROJECT_PATH="/opt/insflow-system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Success message
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Error message
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Info message
info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check certificate status
check_certificate() {
    local cert_name="$1"
    local cert_dir="$PROJECT_PATH/letsencrypt/live/$cert_name"
    
    echo "Checking certificate: $cert_name"
    echo "----------------------------------------"
    
    if [[ -d "$cert_dir" ]]; then
        success "Certificate directory exists: $cert_dir"
        
        # List files in certificate directory
        echo "Files in certificate directory:"
        ls -la "$cert_dir/" 2>/dev/null || error "Cannot list certificate directory"
        
        # Check specific files
        local files=("cert.pem" "chain.pem" "fullchain.pem" "privkey.pem")
        for file in "${files[@]}"; do
            if [[ -f "$cert_dir/$file" ]]; then
                success "$file exists"
            else
                error "$file missing"
            fi
        done
        
        # Show certificate info using Docker
        if [[ -f "$cert_dir/fullchain.pem" ]]; then
            echo ""
            info "Certificate information:"
            docker run --rm -v "$PROJECT_PATH/letsencrypt:/etc/letsencrypt" \
                certbot/certbot:latest certificates --cert-name "$cert_name" 2>/dev/null || \
                echo "Could not retrieve certificate info"
        fi
        
    else
        error "Certificate directory not found: $cert_dir"
    fi
    
    echo ""
}

# Main function
main() {
    echo "🔍 SSL Certificates Status Check"
    echo "================================="
    echo "Project path: $PROJECT_PATH"
    echo "Timestamp: $(date)"
    echo ""
    
    # Check if letsencrypt directory exists
    if [[ -d "$PROJECT_PATH/letsencrypt" ]]; then
        success "Letsencrypt directory exists"
        
        # Show overall structure
        echo ""
        info "Letsencrypt directory structure:"
        find "$PROJECT_PATH/letsencrypt" -type f -name "*.pem" 2>/dev/null | head -20 || \
            echo "No certificate files found"
        echo ""
        
        # Check specific certificates
        check_certificate "insflow.ru"
        check_certificate "insflow.tw1.su"
        
    else
        error "Letsencrypt directory not found: $PROJECT_PATH/letsencrypt"
        echo ""
        info "This means SSL certificates have not been generated yet."
        echo "Run: bash scripts/ssl/obtain-certificates-docker.sh"
    fi
    
    echo "================================="
    echo "Check completed at $(date)"
}

# Run main function
main "$@"
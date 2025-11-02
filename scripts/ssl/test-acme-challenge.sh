#!/bin/bash

# Test ACME Challenge accessibility
# This script tests if ACME challenge path is working correctly

set -e

# Configuration
DOMAINS="insflow.ru,zs.insflow.ru,insflow.tw1.su,zs.insflow.tw1.su"
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

# Error message
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Test ACME challenge for a domain
test_acme_challenge() {
    local domain="$1"
    echo "Testing ACME challenge for $domain..."
    
    # Create test file
    local test_file="test-$(date +%s).txt"
    local test_content="acme-test-$(date +%s)"
    
    # Ensure webroot directory exists
    mkdir -p "$PROJECT_PATH/certbot_webroot/.well-known/acme-challenge"
    
    # Create test file
    echo "$test_content" > "$PROJECT_PATH/certbot_webroot/.well-known/acme-challenge/$test_file"
    
    # Test HTTP access (this is what Let's Encrypt will do)
    if curl -f -s "http://$domain/.well-known/acme-challenge/$test_file" | grep -q "$test_content"; then
        success "$domain ACME challenge works correctly"
        local result=0
    else
        error "$domain ACME challenge failed"
        echo "  Expected content: $test_content"
        echo "  Actual response:"
        curl -s "http://$domain/.well-known/acme-challenge/$test_file" | head -5
        local result=1
    fi
    
    # Clean up
    rm -f "$PROJECT_PATH/certbot_webroot/.well-known/acme-challenge/$test_file"
    
    return $result
}

# Main function
main() {
    echo "🔍 Testing ACME Challenge for SSL certificate generation"
    echo "======================================================"
    
    local total_tests=0
    local passed_tests=0
    
    # Test each domain
    IFS=',' read -ra DOMAIN_ARRAY <<< "$DOMAINS"
    for domain in "${DOMAIN_ARRAY[@]}"; do
        total_tests=$((total_tests + 1))
        if test_acme_challenge "$domain"; then
            passed_tests=$((passed_tests + 1))
        fi
        echo ""
    done
    
    echo "======================================================"
    echo "📊 Results: $passed_tests/$total_tests domains passed ACME challenge test"
    
    if [[ $passed_tests -eq $total_tests ]]; then
        success "All domains are ready for SSL certificate generation!"
        echo ""
        echo "🚀 You can now run:"
        echo "   bash scripts/ssl/obtain-certificates-docker.sh"
        return 0
    else
        error "Some domains failed ACME challenge test"
        echo ""
        echo "🔧 Fix the nginx configuration and try again"
        return 1
    fi
}

# Run main function
main "$@"
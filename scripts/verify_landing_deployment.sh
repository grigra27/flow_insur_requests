#!/bin/bash

# Landing Page Deployment Verification Script
# This script verifies that the landing page deployment is working correctly

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MAIN_DOMAIN="${MAIN_DOMAIN:-insflow.tw1.su}"
SUBDOMAIN="${SUBDOMAIN:-zs.insflow.tw1.su}"
PROTOCOL="${PROTOCOL:-http}"
TIMEOUT=10

echo "⚠️  Note: This verification is configured for HTTP only (no HTTPS)"

echo -e "${BLUE}=== Landing Page Deployment Verification ===${NC}"
echo "Main domain: $MAIN_DOMAIN"
echo "Subdomain: $SUBDOMAIN"
echo "Protocol: $PROTOCOL"
echo ""

# Function to check HTTP status
check_http_status() {
    local url=$1
    local expected_status=${2:-200}
    local description=$3
    
    echo -n "Checking $description... "
    
    if command -v curl >/dev/null 2>&1; then
        status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TIMEOUT "$url" || echo "000")
    else
        echo -e "${YELLOW}SKIP${NC} (curl not available)"
        return 0
    fi
    
    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}OK${NC} ($status)"
        return 0
    else
        echo -e "${RED}FAIL${NC} ($status, expected $expected_status)"
        return 1
    fi
}

# Function to check if content contains expected text
check_content() {
    local url=$1
    local expected_text=$2
    local description=$3
    
    echo -n "Checking $description... "
    
    if command -v curl >/dev/null 2>&1; then
        content=$(curl -s --connect-timeout $TIMEOUT "$url" || echo "")
        if echo "$content" | grep -q "$expected_text"; then
            echo -e "${GREEN}OK${NC}"
            return 0
        else
            echo -e "${RED}FAIL${NC} (text not found)"
            return 1
        fi
    else
        echo -e "${YELLOW}SKIP${NC} (curl not available)"
        return 0
    fi
}

# Function to check Docker services
check_docker_services() {
    echo -e "${BLUE}=== Docker Services Status ===${NC}"
    
    if command -v docker-compose >/dev/null 2>&1; then
        if [ -f "docker-compose.yml" ]; then
            echo "Docker Compose services:"
            docker-compose -f docker-compose.yml ps
            echo ""
            
            # Check if all services are running
            running_services=$(docker-compose -f docker-compose.yml ps --services --filter "status=running" | wc -l)
            total_services=$(docker-compose -f docker-compose.yml ps --services | wc -l)
            
            if [ "$running_services" -eq "$total_services" ]; then
                echo -e "${GREEN}All Docker services are running${NC}"
            else
                echo -e "${RED}Some Docker services are not running ($running_services/$total_services)${NC}"
                return 1
            fi
        else
            echo -e "${YELLOW}docker-compose.yml not found${NC}"
        fi
    else
        echo -e "${YELLOW}docker-compose not available${NC}"
    fi
    
    echo ""
}

# Function to check static files
check_static_files() {
    echo -e "${BLUE}=== Static Files Check ===${NC}"
    
    # Check landing CSS
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/static/css/landing.css" "200" "Landing CSS file"
    
    # Check main CSS
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/static/css/custom.css" "200" "Main CSS file"
    
    # Check favicon
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/static/favicon.ico" "200" "Favicon"
    
    echo ""
}

# Function to check health endpoints
check_health_endpoints() {
    echo -e "${BLUE}=== Health Endpoints Check ===${NC}"
    
    # Main health check
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/healthz/" "200" "Main health endpoint"
    
    # Landing health check
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/landing/health/" "200" "Landing health endpoint"
    
    # Subdomain health check
    check_http_status "$PROTOCOL://$SUBDOMAIN/healthz/" "200" "Subdomain health endpoint"
    
    echo ""
}

# Function to check domain routing
check_domain_routing() {
    echo -e "${BLUE}=== Domain Routing Check ===${NC}"
    
    # Check main domain serves landing page
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/" "200" "Main domain root"
    check_content "$PROTOCOL://$MAIN_DOMAIN/" "здесь есть флоу" "Landing page content"
    
    # Check subdomain serves application
    check_http_status "$PROTOCOL://$SUBDOMAIN/" "200" "Subdomain root"
    
    # Check that main domain doesn't serve app routes
    check_http_status "$PROTOCOL://$MAIN_DOMAIN/requests/" "404" "Main domain app routes (should be 404)"
    
    echo ""
}

# Function to check logs
check_logs() {
    echo -e "${BLUE}=== Recent Logs Check ===${NC}"
    
    if command -v docker-compose >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
        echo "Recent web service logs:"
        docker-compose -f docker-compose.yml logs --tail=10 web 2>/dev/null || echo "Could not retrieve logs"
        echo ""
        
        echo "Recent nginx service logs:"
        docker-compose -f docker-compose.yml logs --tail=10 nginx 2>/dev/null || echo "Could not retrieve logs"
        echo ""
    else
        echo -e "${YELLOW}Cannot check Docker logs${NC}"
    fi
}

# Function to check environment variables
check_environment() {
    echo -e "${BLUE}=== Environment Configuration Check ===${NC}"
    
    if [ -f ".env" ]; then
        echo -e "${GREEN}.env file exists${NC}"
        
        # Check critical variables
        if grep -q "ALLOWED_HOSTS.*$MAIN_DOMAIN" .env; then
            echo -e "${GREEN}Main domain in ALLOWED_HOSTS${NC}"
        else
            echo -e "${RED}Main domain not found in ALLOWED_HOSTS${NC}"
        fi
        
        if grep -q "ALLOWED_HOSTS.*$SUBDOMAIN" .env; then
            echo -e "${GREEN}Subdomain in ALLOWED_HOSTS${NC}"
        else
            echo -e "${RED}Subdomain not found in ALLOWED_HOSTS${NC}"
        fi
        
        if grep -q "DEBUG=False" .env; then
            echo -e "${GREEN}DEBUG is set to False${NC}"
        else
            echo -e "${YELLOW}DEBUG is not set to False${NC}"
        fi
    else
        echo -e "${RED}.env file not found${NC}"
    fi
    
    echo ""
}

# Function to run performance check
check_performance() {
    echo -e "${BLUE}=== Performance Check ===${NC}"
    
    if command -v curl >/dev/null 2>&1; then
        echo -n "Landing page load time... "
        load_time=$(curl -o /dev/null -s -w "%{time_total}" --connect-timeout $TIMEOUT "$PROTOCOL://$MAIN_DOMAIN/" || echo "0")
        
        if [ "$(echo "$load_time < 2.0" | bc -l 2>/dev/null || echo "1")" = "1" ]; then
            echo -e "${GREEN}OK${NC} (${load_time}s)"
        else
            echo -e "${YELLOW}SLOW${NC} (${load_time}s)"
        fi
        
        echo -n "Subdomain load time... "
        load_time=$(curl -o /dev/null -s -w "%{time_total}" --connect-timeout $TIMEOUT "$PROTOCOL://$SUBDOMAIN/" || echo "0")
        
        if [ "$(echo "$load_time < 3.0" | bc -l 2>/dev/null || echo "1")" = "1" ]; then
            echo -e "${GREEN}OK${NC} (${load_time}s)"
        else
            echo -e "${YELLOW}SLOW${NC} (${load_time}s)"
        fi
    else
        echo -e "${YELLOW}Performance check skipped (curl not available)${NC}"
    fi
    
    echo ""
}

# Main execution
main() {
    local exit_code=0
    
    # Run all checks
    check_environment || exit_code=1
    check_docker_services || exit_code=1
    check_health_endpoints || exit_code=1
    check_domain_routing || exit_code=1
    check_static_files || exit_code=1
    check_performance
    check_logs
    
    # Summary
    echo -e "${BLUE}=== Verification Summary ===${NC}"
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ All critical checks passed!${NC}"
        echo "Landing page deployment appears to be working correctly."
    else
        echo -e "${RED}✗ Some checks failed!${NC}"
        echo "Please review the failed checks and fix any issues."
    fi
    
    echo ""
    echo "Manual verification steps:"
    echo "1. Open $PROTOCOL://$MAIN_DOMAIN in your browser"
    echo "2. Verify the landing page displays correctly"
    echo "3. Open $PROTOCOL://$SUBDOMAIN in your browser"
    echo "4. Verify the main application works"
    echo "5. Test responsive design on mobile devices"
    
    exit $exit_code
}

# Run main function
main "$@"
#!/bin/bash

# Test script for domain routing configuration
# This script tests that domains are properly routed:
# - Main domains (insflow.ru, insflow.tw1.su) should show landing page
# - Subdomains (zs.insflow.ru, zs.insflow.tw1.su) should show Django app

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Domain Routing Test ===${NC}"

# Test function
test_domain() {
    local domain=$1
    local expected_type=$2
    local protocol=${3:-http}
    
    echo -e "\n${BLUE}Testing ${domain} (expecting ${expected_type})...${NC}"
    
    # Test main page
    if curl -s -f -L --connect-timeout 10 --max-time 30 "${protocol}://${domain}/" > /tmp/response_${domain}.html; then
        echo -e "${GREEN}✅ ${domain} is accessible${NC}"
        
        # Check content type
        if [ "$expected_type" = "landing" ]; then
            if grep -q "здесь есть флоу\|InsFlow" /tmp/response_${domain}.html; then
                echo -e "${GREEN}✅ ${domain} shows landing page content${NC}"
            else
                echo -e "${RED}❌ ${domain} does not show landing page content${NC}"
                echo "First 200 chars of response:"
                head -c 200 /tmp/response_${domain}.html
            fi
        elif [ "$expected_type" = "django" ]; then
            if grep -q "login\|Django\|requests" /tmp/response_${domain}.html; then
                echo -e "${GREEN}✅ ${domain} shows Django app content${NC}"
            else
                echo -e "${RED}❌ ${domain} does not show Django app content${NC}"
                echo "First 200 chars of response:"
                head -c 200 /tmp/response_${domain}.html
            fi
        fi
    else
        echo -e "${RED}❌ ${domain} is not accessible${NC}"
    fi
    
    # Test health endpoints
    if [ "$expected_type" = "landing" ]; then
        if curl -s -f --connect-timeout 5 --max-time 10 "${protocol}://${domain}/landing/health/" > /dev/null; then
            echo -e "${GREEN}✅ ${domain}/landing/health/ works${NC}"
        else
            echo -e "${YELLOW}⚠️ ${domain}/landing/health/ not accessible${NC}"
        fi
    elif [ "$expected_type" = "django" ]; then
        if curl -s -f --connect-timeout 5 --max-time 10 "${protocol}://${domain}/healthz/" > /dev/null; then
            echo -e "${GREEN}✅ ${domain}/healthz/ works${NC}"
        else
            echo -e "${YELLOW}⚠️ ${domain}/healthz/ not accessible${NC}"
        fi
    fi
    
    # Clean up
    rm -f /tmp/response_${domain}.html
}

# Determine protocol based on SSL availability
if [ -f "letsencrypt/live/insflow.ru/fullchain.pem" ] && [ -f "letsencrypt/live/insflow.tw1.su/fullchain.pem" ]; then
    PROTOCOL="https"
    echo -e "${GREEN}SSL certificates found, testing with HTTPS${NC}"
else
    PROTOCOL="http"
    echo -e "${YELLOW}SSL certificates not found, testing with HTTP${NC}"
fi

# Test main domains (should show landing page)
echo -e "\n${BLUE}=== Testing Main Domains (Landing Page) ===${NC}"
test_domain "insflow.ru" "landing" "$PROTOCOL"
test_domain "insflow.tw1.su" "landing" "$PROTOCOL"

# Test subdomains (should show Django app)
echo -e "\n${BLUE}=== Testing Subdomains (Django App) ===${NC}"
test_domain "zs.insflow.ru" "django" "$PROTOCOL"
test_domain "zs.insflow.tw1.su" "django" "$PROTOCOL"

echo -e "\n${BLUE}=== Domain Routing Test Complete ===${NC}"
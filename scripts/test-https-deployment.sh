#!/bin/bash

# Test script for HTTPS deployment configuration
# This script validates the deployment configuration without actually deploying

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test functions
test_ssl_scripts() {
    echo -e "${BLUE}Testing SSL scripts...${NC}"
    
    local scripts=(
        "scripts/ssl/obtain-certificates.sh"
        "scripts/ssl/check-certificates.sh"
        "scripts/ssl/renew-certificates.sh"
        "scripts/ssl/ssl-cron-setup.sh"
        "scripts/ssl/monitor-ssl-status.sh"
        "scripts/ssl/post-renewal-hook.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [[ -f "$script" ]]; then
            if [[ -x "$script" ]]; then
                echo -e "${GREEN}✅ $script exists and is executable${NC}"
            else
                echo -e "${YELLOW}⚠️ $script exists but is not executable${NC}"
                chmod +x "$script"
                echo -e "${GREEN}✅ Made $script executable${NC}"
            fi
        else
            echo -e "${RED}❌ $script not found${NC}"
            return 1
        fi
    done
}

test_docker_compose() {
    echo -e "${BLUE}Testing Docker Compose configuration...${NC}"
    
    if [[ -f "docker-compose.timeweb.yml" ]]; then
        echo -e "${GREEN}✅ docker-compose.timeweb.yml exists${NC}"
        
        # Test syntax if docker-compose is available
        if command -v docker-compose > /dev/null 2>&1; then
            if docker-compose -f docker-compose.timeweb.yml config > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Docker Compose syntax is valid${NC}"
            else
                echo -e "${RED}❌ Docker Compose syntax error${NC}"
                return 1
            fi
        else
            echo -e "${YELLOW}⚠️ docker-compose not available, skipping syntax check${NC}"
        fi
    else
        echo -e "${RED}❌ docker-compose.timeweb.yml not found${NC}"
        return 1
    fi
}

test_nginx_config() {
    echo -e "${BLUE}Testing Nginx configuration...${NC}"
    
    if [[ -f "nginx-timeweb/default-https.conf" ]]; then
        echo -e "${GREEN}✅ nginx-timeweb/default-https.conf exists${NC}"
    else
        echo -e "${RED}❌ nginx-timeweb/default-https.conf not found${NC}"
        return 1
    fi
    
    if [[ -f "nginx-timeweb/default.conf" ]]; then
        echo -e "${GREEN}✅ nginx-timeweb/default.conf exists (fallback)${NC}"
    else
        echo -e "${YELLOW}⚠️ nginx-timeweb/default.conf not found (fallback config)${NC}"
    fi
}

test_workflow_syntax() {
    echo -e "${BLUE}Testing GitHub Actions workflow...${NC}"
    
    if [[ -f ".github/workflows/deploy_timeweb.yml" ]]; then
        echo -e "${GREEN}✅ .github/workflows/deploy_timeweb.yml exists${NC}"
        
        # Basic YAML syntax check (if yq is available)
        if command -v yq > /dev/null 2>&1; then
            if yq eval '.jobs.build-and-deploy.steps' .github/workflows/deploy_timeweb.yml > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Workflow YAML syntax is valid${NC}"
            else
                echo -e "${RED}❌ Workflow YAML syntax error${NC}"
                return 1
            fi
        else
            echo -e "${YELLOW}⚠️ yq not available, skipping YAML syntax check${NC}"
        fi
    else
        echo -e "${RED}❌ .github/workflows/deploy_timeweb.yml not found${NC}"
        return 1
    fi
}

test_environment_variables() {
    echo -e "${BLUE}Testing environment variable configuration...${NC}"
    
    # Check if workflow contains required environment variables
    local workflow_file=".github/workflows/deploy_timeweb.yml"
    
    local required_vars=(
        "DOMAINS_PRIMARY"
        "DOMAINS_TECHNICAL"
        "SSL_EMAIL"
    )
    
    for var in "${required_vars[@]}"; do
        if grep -q "$var" "$workflow_file"; then
            echo -e "${GREEN}✅ $var is configured in workflow${NC}"
        else
            echo -e "${RED}❌ $var not found in workflow${NC}"
            return 1
        fi
    done
}

test_documentation() {
    echo -e "${BLUE}Testing documentation...${NC}"
    
    if [[ -f "docs/GITHUB_SECRETS_TIMEWEB_HTTPS.md" ]]; then
        echo -e "${GREEN}✅ HTTPS deployment documentation exists${NC}"
    else
        echo -e "${YELLOW}⚠️ HTTPS deployment documentation not found${NC}"
    fi
}

# Main test execution
main() {
    echo -e "${BLUE}=== HTTPS Deployment Configuration Test ===${NC}"
    echo ""
    
    local tests=(
        "test_ssl_scripts"
        "test_docker_compose"
        "test_nginx_config"
        "test_workflow_syntax"
        "test_environment_variables"
        "test_documentation"
    )
    
    local passed=0
    local total=${#tests[@]}
    
    for test in "${tests[@]}"; do
        echo ""
        if $test; then
            ((passed++))
        fi
    done
    
    echo ""
    echo -e "${BLUE}=== Test Summary ===${NC}"
    echo "Passed: $passed/$total tests"
    
    if [[ $passed -eq $total ]]; then
        echo -e "${GREEN}✅ All tests passed! HTTPS deployment configuration is ready.${NC}"
        return 0
    else
        echo -e "${RED}❌ Some tests failed. Please fix the issues before deploying.${NC}"
        return 1
    fi
}

# Run tests
main "$@"
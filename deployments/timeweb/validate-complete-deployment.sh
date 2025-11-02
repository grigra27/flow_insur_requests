#!/bin/bash

# Complete Timeweb Deployment Validation Script
# This script runs all validation tests for the Timeweb HTTPS deployment
# Requirements: 5.2, 5.3, 5.4 - Complete deployment validation

set -e

echo "=== Complete Timeweb Deployment Validation ==="
echo "Starting comprehensive validation at $(date)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
VERBOSE=${VERBOSE:-false}
RUN_PYTHON_TESTS=${RUN_PYTHON_TESTS:-true}
RUN_SHELL_TESTS=${RUN_SHELL_TESTS:-true}
RUN_END_TO_END_TEST=${RUN_END_TO_END_TEST:-true}
RUN_RENEWAL_TEST=${RUN_RENEWAL_TEST:-true}

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_section() {
    echo -e "${CYAN}=== $1 ===${NC}"
}

# Track test results
total_tests=0
passed_tests=0
failed_tests=0
test_results_file="/tmp/test_results.txt"

# Initialize results file
echo "" > "$test_results_file"

# Function to record test result
record_test() {
    local test_name="$1"
    local result="$2"
    
    echo "$test_name:$result" >> "$test_results_file"
    total_tests=$((total_tests + 1))
    
    if [ "$result" = "PASS" ]; then
        passed_tests=$((passed_tests + 1))
    else
        failed_tests=$((failed_tests + 1))
    fi
}

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: docker-compose.yml not found. Please run this script from deployments/timeweb directory${NC}"
    exit 1
fi

print_section "Prerequisites Check"

# Check required tools
required_tools=("docker" "python3" "curl" "grep" "awk")
for tool in "${required_tools[@]}"; do
    if command -v "$tool" > /dev/null 2>&1; then
        print_status 0 "Tool available: $tool"
        record_test "tool_$tool" "PASS"
    else
        print_status 1 "Tool missing: $tool"
        record_test "tool_$tool" "FAIL"
    fi
done

# Check Python environment
if python3 -c "import unittest, requests, subprocess, pathlib" > /dev/null 2>&1; then
    print_status 0 "Python environment is ready"
    record_test "python_environment" "PASS"
else
    print_status 1 "Python environment missing required modules"
    record_test "python_environment" "FAIL"
fi

echo ""
print_section "Python Unit Tests"

if [ "$RUN_PYTHON_TESTS" = "true" ]; then
    print_info "Running Python deployment validation tests..."
    
    # Run Python unit tests
    if python3 -m unittest tests.test_deployment_validation -v > /tmp/python_tests.log 2>&1; then
        print_status 0 "Python unit tests passed"
        record_test "python_unit_tests" "PASS"
        
        # Count individual test results
        test_count=$(grep -c "test_.*ok" /tmp/python_tests.log || echo "0")
        print_info "Completed $test_count individual Python tests"
        
    else
        print_status 1 "Python unit tests failed"
        record_test "python_unit_tests" "FAIL"
        
        if [ "$VERBOSE" = "true" ]; then
            echo "Python test output:"
            cat /tmp/python_tests.log
        fi
    fi
else
    print_warning "Python tests skipped (RUN_PYTHON_TESTS=false)"
    record_test "python_unit_tests" "SKIP"
fi

echo ""
print_section "Shell Script Tests"

if [ "$RUN_SHELL_TESTS" = "true" ]; then
    print_info "Running shell script validation tests..."
    
    # Test individual scripts
    shell_scripts=(
        "scripts/deploy-timeweb.sh"
        "scripts/obtain-certificates.sh"
        "scripts/health-check.sh"
        "scripts/monitor-certificates.sh"
    )
    
    for script in "${shell_scripts[@]}"; do
        if [ -f "$script" ] && [ -x "$script" ]; then
            # Test script help functionality
            if ./"$script" --help > /dev/null 2>&1; then
                print_status 0 "Script functional: $script"
                record_test "script_$(basename "$script")" "PASS"
            else
                print_warning "Script help not available: $script"
                record_test "script_$(basename "$script")" "WARN"
            fi
        else
            print_status 1 "Script missing or not executable: $script"
            record_test "script_$(basename "$script")" "FAIL"
        fi
    done
else
    print_warning "Shell script tests skipped (RUN_SHELL_TESTS=false)"
fi

echo ""
print_section "End-to-End Deployment Test"

if [ "$RUN_END_TO_END_TEST" = "true" ]; then
    print_info "Running end-to-end deployment test..."
    
    # Set test environment variables
    export TEST_MODE="staging"
    export CLEANUP_AFTER_TEST="true"
    export VERBOSE="$VERBOSE"
    
    if ./test-end-to-end-deployment.sh > /tmp/e2e_test.log 2>&1; then
        print_status 0 "End-to-end deployment test passed"
        record_test "end_to_end_deployment" "PASS"
        
        # Extract key metrics from e2e test
        if grep -q "✓.*deployment test completed successfully" /tmp/e2e_test.log; then
            print_info "All deployment phases completed successfully"
        fi
        
    else
        print_status 1 "End-to-end deployment test failed"
        record_test "end_to_end_deployment" "FAIL"
        
        if [ "$VERBOSE" = "true" ]; then
            echo "E2E test output:"
            tail -50 /tmp/e2e_test.log
        fi
    fi
else
    print_warning "End-to-end test skipped (RUN_END_TO_END_TEST=false)"
    record_test "end_to_end_deployment" "SKIP"
fi

echo ""
print_section "Certificate Renewal Test"

if [ "$RUN_RENEWAL_TEST" = "true" ]; then
    print_info "Running certificate renewal test..."
    
    if ./test-certificate-renewal.sh > /tmp/renewal_test.log 2>&1; then
        print_status 0 "Certificate renewal test passed"
        record_test "certificate_renewal" "PASS"
        
        # Check renewal test phases
        if grep -q "Certificate renewal testing completed" /tmp/renewal_test.log; then
            print_info "All renewal phases completed successfully"
        fi
        
    else
        print_status 1 "Certificate renewal test failed"
        record_test "certificate_renewal" "FAIL"
        
        if [ "$VERBOSE" = "true" ]; then
            echo "Renewal test output:"
            tail -50 /tmp/renewal_test.log
        fi
    fi
else
    print_warning "Certificate renewal test skipped (RUN_RENEWAL_TEST=false)"
    record_test "certificate_renewal" "SKIP"
fi

echo ""
print_section "Configuration Validation"

print_info "Validating deployment configuration files..."

# Check configuration files
config_files=(
    "docker-compose.yml"
    "nginx/default.conf"
    "nginx/default-https.conf"
    ".env.example"
    "README.md"
)

for config in "${config_files[@]}"; do
    if [ -f "$config" ]; then
        print_status 0 "Configuration file exists: $config"
        record_test "config_$(basename "$config")" "PASS"
    else
        print_status 1 "Missing configuration file: $config"
        record_test "config_$(basename "$config")" "FAIL"
    fi
done

# Validate Docker Compose syntax
if command -v docker > /dev/null 2>&1; then
    if docker compose config > /dev/null 2>&1; then
        print_status 0 "Docker Compose configuration is valid"
        record_test "docker_compose_syntax" "PASS"
    else
        print_status 1 "Docker Compose configuration is invalid"
        record_test "docker_compose_syntax" "FAIL"
    fi
else
    print_warning "Docker not available for configuration validation"
    record_test "docker_compose_syntax" "SKIP"
fi

echo ""
print_section "Security Validation"

print_info "Validating security configuration..."

# Check HTTPS configuration
if grep -q "listen 443" nginx/default-https.conf; then
    print_status 0 "HTTPS configuration is present"
    record_test "https_configuration" "PASS"
else
    print_status 1 "HTTPS configuration is missing"
    record_test "https_configuration" "FAIL"
fi

# Check security headers
security_headers=(
    "Strict-Transport-Security"
    "X-Content-Type-Options"
    "X-Frame-Options"
    "X-XSS-Protection"
)

for header in "${security_headers[@]}"; do
    if grep -q "$header" nginx/default-https.conf; then
        print_status 0 "Security header configured: $header"
        record_test "security_header_$header" "PASS"
    else
        print_status 1 "Missing security header: $header"
        record_test "security_header_$header" "FAIL"
    fi
done

# Check SSL configuration
if grep -q "ssl_protocols TLSv1.2 TLSv1.3" nginx/default-https.conf; then
    print_status 0 "Modern SSL protocols configured"
    record_test "ssl_protocols" "PASS"
else
    print_status 1 "SSL protocols not properly configured"
    record_test "ssl_protocols" "FAIL"
fi

echo ""
print_section "Performance Validation"

print_info "Validating performance configuration..."

# Check gzip configuration
if grep -q "gzip on" nginx/default-https.conf; then
    print_status 0 "Gzip compression is enabled"
    record_test "gzip_compression" "PASS"
else
    print_status 1 "Gzip compression is not configured"
    record_test "gzip_compression" "FAIL"
fi

# Check caching configuration
if grep -q "expires" nginx/default-https.conf; then
    print_status 0 "Static file caching is configured"
    record_test "static_caching" "PASS"
else
    print_status 1 "Static file caching is not configured"
    record_test "static_caching" "FAIL"
fi

# Check proxy buffering
if grep -q "proxy_buffering on" nginx/default-https.conf; then
    print_status 0 "Proxy buffering is enabled"
    record_test "proxy_buffering" "PASS"
else
    print_status 1 "Proxy buffering is not configured"
    record_test "proxy_buffering" "FAIL"
fi

echo ""
print_section "Validation Summary"

# Generate comprehensive report
cat > /tmp/complete_validation_report.json << EOF
{
    "validation_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "total_tests": $total_tests,
    "passed_tests": $passed_tests,
    "failed_tests": $failed_tests,
    "success_rate": $(echo "scale=2; $passed_tests * 100 / $total_tests" | bc -l 2>/dev/null || echo "0"),
    "overall_status": "$([ $failed_tests -eq 0 ] && echo "PASS" || echo "FAIL")",
    "test_results": {
EOF

# Add individual test results to JSON
first=true
while IFS=':' read -r test_name result; do
    if [ -n "$test_name" ]; then
        if [ "$first" = "true" ]; then
            first=false
        else
            echo "," >> /tmp/complete_validation_report.json
        fi
        echo "        \"$test_name\": \"$result\"" >> /tmp/complete_validation_report.json
    fi
done < "$test_results_file"

cat >> /tmp/complete_validation_report.json << EOF
    },
    "recommendations": [
EOF

# Add recommendations based on test results
recommendations=""

if grep -q "python_unit_tests:FAIL" "$test_results_file"; then
    recommendations="$recommendations,Fix Python unit test failures before deployment"
fi

if grep -q "end_to_end_deployment:FAIL" "$test_results_file"; then
    recommendations="$recommendations,Resolve end-to-end deployment issues"
fi

if grep -q "certificate_renewal:FAIL" "$test_results_file"; then
    recommendations="$recommendations,Fix certificate renewal configuration"
fi

if grep -q "https_configuration:FAIL" "$test_results_file"; then
    recommendations="$recommendations,Configure HTTPS properly in nginx"
fi

if [ -z "$recommendations" ]; then
    recommendations="Deployment is ready for production"
else
    recommendations="${recommendations#,}"  # Remove leading comma
fi

# Add recommendations to JSON
IFS=',' read -ra rec_array <<< "$recommendations"
for i in "${!rec_array[@]}"; do
    if [ $i -gt 0 ]; then
        echo "," >> /tmp/complete_validation_report.json
    fi
    echo "        \"${rec_array[$i]}\"" >> /tmp/complete_validation_report.json
done

cat >> /tmp/complete_validation_report.json << EOF
    ]
}
EOF

# Display summary
echo -e "${CYAN}=== VALIDATION RESULTS ===${NC}"
echo ""
echo "Total Tests: $total_tests"
echo -e "Passed: ${GREEN}$passed_tests${NC}"
echo -e "Failed: ${RED}$failed_tests${NC}"

if [ $failed_tests -eq 0 ]; then
    echo -e "Overall Status: ${GREEN}PASS${NC}"
    echo ""
    echo -e "${GREEN}✓ All validation tests passed!${NC}"
    echo -e "${GREEN}✓ Timeweb deployment is ready for production use.${NC}"
else
    echo -e "Overall Status: ${RED}FAIL${NC}"
    echo ""
    echo -e "${RED}✗ Some validation tests failed.${NC}"
    echo -e "${YELLOW}⚠ Review failed tests before production deployment.${NC}"
fi

echo ""
echo "Detailed Results:"
while IFS=':' read -r test_name result; do
    if [ -n "$test_name" ]; then
        case "$result" in
            "PASS")
                echo -e "  ${GREEN}✓${NC} $test_name"
                ;;
            "FAIL")
                echo -e "  ${RED}✗${NC} $test_name"
                ;;
            "WARN")
                echo -e "  ${YELLOW}⚠${NC} $test_name"
                ;;
            "SKIP")
                echo -e "  ${BLUE}○${NC} $test_name (skipped)"
                ;;
        esac
    fi
done < "$test_results_file"

echo ""
echo "Recommendations:"
IFS=',' read -ra rec_array <<< "$recommendations"
for recommendation in "${rec_array[@]}"; do
    echo "• $recommendation"
done

echo ""
echo "Validation report saved to: /tmp/complete_validation_report.json"
echo "Individual test logs available in /tmp/"
echo ""
echo "Complete validation finished at $(date)"

# Exit with appropriate code
if [ $failed_tests -eq 0 ]; then
    exit 0
else
    exit 1
fi
#!/bin/bash

# Nginx Configuration Validation Script
# This script performs basic validation of nginx configuration files

set -e

CONFIG_DIR="deployments/timeweb/nginx"

# Function to check basic nginx syntax
check_basic_syntax() {
    local config_file="$1"
    local errors=0
    
    echo "Checking $config_file..."
    
    # Check for basic syntax issues (skip for include files)
    if [[ "$config_file" == *"optimizations.conf" ]]; then
        echo "  ℹ Include file - skipping server block check"
    elif ! grep -q "server {" "$config_file"; then
        echo "  ✗ No server blocks found"
        ((errors++))
    else
        echo "  ✓ Server blocks found"
    fi
    
    # Check for balanced braces
    local open_braces=$(grep -o '{' "$config_file" | wc -l)
    local close_braces=$(grep -o '}' "$config_file" | wc -l)
    
    if [[ $open_braces -eq $close_braces ]]; then
        echo "  ✓ Braces are balanced ($open_braces pairs)"
    else
        echo "  ✗ Braces are not balanced (open: $open_braces, close: $close_braces)"
        ((errors++))
    fi
    
    # Check for semicolons at end of directives
    local missing_semicolons=$(grep -E '^\s*[a-z_]+\s+[^;{]+$' "$config_file" | grep -v '#' | wc -l)
    if [[ $missing_semicolons -eq 0 ]]; then
        echo "  ✓ All directives end with semicolons"
    else
        echo "  ⚠ Potential missing semicolons: $missing_semicolons lines"
    fi
    
    # Check for listen directives (skip for include files)
    if [[ "$config_file" == *"optimizations.conf" ]]; then
        echo "  ℹ Include file - skipping listen/server_name checks"
    else
        if grep -q "listen " "$config_file"; then
            echo "  ✓ Listen directives found"
        else
            echo "  ✗ No listen directives found"
            ((errors++))
        fi
        
        # Check for server_name directives
        if grep -q "server_name " "$config_file"; then
            echo "  ✓ Server name directives found"
        else
            echo "  ✗ No server_name directives found"
            ((errors++))
        fi
    fi
    
    return $errors
}

# Function to check SSL-specific configuration
check_ssl_config() {
    local config_file="$1"
    local errors=0
    
    echo "Checking SSL configuration in $config_file..."
    
    if grep -q "ssl_certificate " "$config_file"; then
        echo "  ✓ SSL certificate directives found"
        
        # Check for matching certificate and key
        local cert_count=$(grep -c "ssl_certificate " "$config_file")
        local key_count=$(grep -c "ssl_certificate_key " "$config_file")
        
        if [[ $cert_count -eq $key_count ]]; then
            echo "  ✓ SSL certificates and keys are balanced"
        else
            echo "  ✗ SSL certificates ($cert_count) and keys ($key_count) are not balanced"
            ((errors++))
        fi
        
        # Check for SSL protocols
        if grep -q "ssl_protocols " "$config_file"; then
            echo "  ✓ SSL protocols configured"
        else
            echo "  ⚠ No SSL protocols specified"
        fi
        
        # Check for SSL ciphers
        if grep -q "ssl_ciphers " "$config_file"; then
            echo "  ✓ SSL ciphers configured"
        else
            echo "  ⚠ No SSL ciphers specified"
        fi
    else
        echo "  ℹ No SSL configuration found (HTTP-only config)"
    fi
    
    return $errors
}

# Function to check include directives
check_includes() {
    local config_file="$1"
    local errors=0
    
    echo "Checking include directives in $config_file..."
    
    # Find all include directives
    local includes=$(grep "include " "$config_file" | grep -v '#' | sed 's/.*include \([^;]*\);.*/\1/')
    
    if [[ -n "$includes" ]]; then
        while IFS= read -r include_path; do
            # Skip built-in nginx includes
            if [[ "$include_path" =~ ^/etc/nginx/ ]]; then
                echo "  ℹ External include: $include_path (will be checked at runtime)"
            else
                echo "  ⚠ Include directive found: $include_path"
            fi
        done <<< "$includes"
    else
        echo "  ℹ No include directives found"
    fi
    
    return $errors
}

# Function to validate all configurations
validate_all() {
    local total_errors=0
    
    echo "=== Nginx Configuration Validation ==="
    echo "Validating configurations in $CONFIG_DIR"
    echo ""
    
    # Check main configuration files
    for config in "default.conf" "default-ssl.conf" "default-acme.conf"; do
        if [[ -f "$CONFIG_DIR/$config" ]]; then
            echo "--- Validating $config ---"
            check_basic_syntax "$CONFIG_DIR/$config"
            local basic_errors=$?
            
            if [[ "$config" == *"ssl"* ]]; then
                check_ssl_config "$CONFIG_DIR/$config"
                local ssl_errors=$?
                ((basic_errors += ssl_errors))
            fi
            
            check_includes "$CONFIG_DIR/$config"
            local include_errors=$?
            ((basic_errors += include_errors))
            
            if [[ $basic_errors -eq 0 ]]; then
                echo "  ✅ $config validation passed"
            else
                echo "  ❌ $config validation failed with $basic_errors errors"
            fi
            
            ((total_errors += basic_errors))
            echo ""
        else
            echo "⚠ Configuration file $config not found"
            echo ""
        fi
    done
    
    # Check optimization files
    for opt_config in "ssl-optimizations.conf" "static-optimizations.conf"; do
        if [[ -f "$CONFIG_DIR/$opt_config" ]]; then
            echo "--- Validating $opt_config ---"
            check_basic_syntax "$CONFIG_DIR/$opt_config"
            local opt_errors=$?
            
            if [[ $opt_errors -eq 0 ]]; then
                echo "  ✅ $opt_config validation passed"
            else
                echo "  ❌ $opt_config validation failed with $opt_errors errors"
            fi
            
            ((total_errors += opt_errors))
            echo ""
        fi
    done
    
    echo "=== Validation Summary ==="
    if [[ $total_errors -eq 0 ]]; then
        echo "✅ All configurations passed validation"
        return 0
    else
        echo "❌ Validation failed with $total_errors total errors"
        return 1
    fi
}

# Main execution
main() {
    local action="${1:-validate}"
    
    case "$action" in
        "validate"|"check")
            validate_all
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [validate|check|help]"
            echo ""
            echo "Commands:"
            echo "  validate  - Validate all nginx configuration files (default)"
            echo "  check     - Alias for validate"
            echo "  help      - Show this help message"
            ;;
        *)
            echo "Unknown command: $action"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
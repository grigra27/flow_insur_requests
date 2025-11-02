#!/bin/bash

# SSL Security Setup Script
# This script sets up additional SSL security features

set -e

# Configuration
DH_PARAM_FILE="/etc/ssl/certs/dhparam.pem"
DH_PARAM_SIZE=2048

# Function to generate Diffie-Hellman parameters
generate_dh_params() {
    echo "Generating Diffie-Hellman parameters..."
    
    if [[ -f "$DH_PARAM_FILE" ]]; then
        echo "Diffie-Hellman parameters already exist at $DH_PARAM_FILE"
        
        # Check if the file is valid
        if openssl dhparam -in "$DH_PARAM_FILE" -check -noout >/dev/null 2>&1; then
            echo "Existing DH parameters are valid"
            return 0
        else
            echo "Existing DH parameters are invalid, regenerating..."
            rm -f "$DH_PARAM_FILE"
        fi
    fi
    
    # Create directory if it doesn't exist
    mkdir -p "$(dirname "$DH_PARAM_FILE")"
    
    # Generate new DH parameters
    echo "Generating new DH parameters (this may take several minutes)..."
    openssl dhparam -out "$DH_PARAM_FILE" "$DH_PARAM_SIZE"
    
    # Set proper permissions
    chmod 644 "$DH_PARAM_FILE"
    
    echo "Diffie-Hellman parameters generated successfully"
}

# Function to setup SSL security configurations
setup_ssl_configs() {
    echo "Setting up SSL security configurations..."
    
    local nginx_conf_dir="/etc/nginx/conf.d"
    local source_dir="/app/deployments/timeweb/nginx"
    
    # Copy SSL optimization configuration
    if [[ -f "${source_dir}/ssl-optimizations.conf" ]]; then
        cp "${source_dir}/ssl-optimizations.conf" "${nginx_conf_dir}/"
        echo "SSL optimizations configuration copied"
    fi
    
    # Copy static file optimization configuration
    if [[ -f "${source_dir}/static-optimizations.conf" ]]; then
        cp "${source_dir}/static-optimizations.conf" "${nginx_conf_dir}/"
        echo "Static file optimizations configuration copied"
    fi
}

# Function to test SSL configuration
test_ssl_config() {
    echo "Testing SSL configuration..."
    
    # Test nginx configuration
    if nginx -t; then
        echo "Nginx configuration test passed"
    else
        echo "Nginx configuration test failed"
        return 1
    fi
    
    # Test DH parameters if they exist
    if [[ -f "$DH_PARAM_FILE" ]]; then
        if openssl dhparam -in "$DH_PARAM_FILE" -check -noout >/dev/null 2>&1; then
            echo "DH parameters are valid"
        else
            echo "DH parameters are invalid"
            return 1
        fi
    fi
}

# Function to show SSL security status
show_ssl_status() {
    echo "=== SSL Security Status ==="
    
    # Check DH parameters
    if [[ -f "$DH_PARAM_FILE" ]]; then
        echo "✓ Diffie-Hellman parameters: Present"
        local dh_size
        dh_size=$(openssl dhparam -in "$DH_PARAM_FILE" -text -noout 2>/dev/null | grep "DH Parameters" | grep -o '[0-9]\+' || echo "unknown")
        echo "  Size: ${dh_size} bits"
    else
        echo "✗ Diffie-Hellman parameters: Missing"
    fi
    
    # Check SSL configurations
    local nginx_conf_dir="/etc/nginx/conf.d"
    
    if [[ -f "${nginx_conf_dir}/ssl-optimizations.conf" ]]; then
        echo "✓ SSL optimizations: Configured"
    else
        echo "✗ SSL optimizations: Not configured"
    fi
    
    if [[ -f "${nginx_conf_dir}/static-optimizations.conf" ]]; then
        echo "✓ Static file optimizations: Configured"
    else
        echo "✗ Static file optimizations: Not configured"
    fi
    
    # Check nginx configuration
    if nginx -t >/dev/null 2>&1; then
        echo "✓ Nginx configuration: Valid"
    else
        echo "✗ Nginx configuration: Invalid"
    fi
}

# Main function
main() {
    local action="${1:-setup}"
    
    echo "=== SSL Security Setup ==="
    echo "Current time: $(date)"
    
    case "$action" in
        "setup")
            echo "Setting up SSL security features..."
            generate_dh_params
            setup_ssl_configs
            test_ssl_config
            echo "SSL security setup completed successfully"
            ;;
        "dh")
            echo "Generating Diffie-Hellman parameters only..."
            generate_dh_params
            ;;
        "configs")
            echo "Setting up SSL configurations only..."
            setup_ssl_configs
            test_ssl_config
            ;;
        "test")
            echo "Testing SSL configuration..."
            test_ssl_config
            ;;
        "status")
            show_ssl_status
            ;;
        *)
            echo "Usage: $0 [setup|dh|configs|test|status]"
            echo ""
            echo "Commands:"
            echo "  setup   - Full SSL security setup (default)"
            echo "  dh      - Generate Diffie-Hellman parameters only"
            echo "  configs - Setup SSL configuration files only"
            echo "  test    - Test current SSL configuration"
            echo "  status  - Show SSL security status"
            exit 1
            ;;
    esac
}

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
    echo "Warning: This script may need root privileges for some operations"
    echo "Consider running with sudo if you encounter permission errors"
fi

# Run main function with all arguments
main "$@"
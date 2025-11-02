#!/bin/bash

# Nginx Configuration Management Script
# This script detects SSL certificate availability and configures nginx accordingly

set -e

# Configuration paths
NGINX_DIR="/etc/nginx/conf.d"
CONFIG_DIR="/app/deployments/timeweb/nginx"
SSL_DIR="/etc/letsencrypt/live"

# Domain configurations
DOMAINS=("insflow.ru" "insflow.tw1.su")

# Function to check if SSL certificates exist for a domain
check_ssl_cert() {
    local domain=$1
    local cert_path="${SSL_DIR}/${domain}/fullchain.pem"
    local key_path="${SSL_DIR}/${domain}/privkey.pem"
    
    if [[ -f "$cert_path" && -f "$key_path" ]]; then
        # Verify certificate is valid and not expired
        if openssl x509 -in "$cert_path" -noout -checkend 86400 >/dev/null 2>&1; then
            echo "Valid SSL certificate found for $domain"
            return 0
        else
            echo "SSL certificate for $domain is expired or invalid"
            return 1
        fi
    else
        echo "SSL certificate files not found for $domain"
        return 1
    fi
}

# Function to check if all required SSL certificates are available
check_all_ssl_certs() {
    local all_valid=true
    
    for domain in "${DOMAINS[@]}"; do
        if ! check_ssl_cert "$domain"; then
            all_valid=false
        fi
    done
    
    if $all_valid; then
        echo "All SSL certificates are valid and available"
        return 0
    else
        echo "Some SSL certificates are missing or invalid"
        return 1
    fi
}

# Function to configure nginx for HTTP-only mode
configure_http_mode() {
    echo "Configuring nginx for HTTP-only mode..."
    
    # Copy HTTP-only configuration
    cp "${CONFIG_DIR}/default.conf" "${NGINX_DIR}/default.conf"
    
    # Remove any existing SSL configuration
    rm -f "${NGINX_DIR}/default-ssl.conf"
    
    echo "Nginx configured for HTTP-only mode"
}

# Function to configure nginx for HTTPS mode
configure_https_mode() {
    echo "Configuring nginx for HTTPS mode..."
    
    # Copy HTTPS configuration
    cp "${CONFIG_DIR}/default-ssl.conf" "${NGINX_DIR}/default.conf"
    
    echo "Nginx configured for HTTPS mode with SSL redirects"
}

# Function to test nginx configuration
test_nginx_config() {
    echo "Testing nginx configuration..."
    
    if nginx -t; then
        echo "Nginx configuration test passed"
        return 0
    else
        echo "Nginx configuration test failed"
        return 1
    fi
}

# Function to reload nginx
reload_nginx() {
    echo "Reloading nginx..."
    
    if command -v systemctl >/dev/null 2>&1; then
        systemctl reload nginx
    elif command -v service >/dev/null 2>&1; then
        service nginx reload
    else
        nginx -s reload
    fi
    
    echo "Nginx reloaded successfully"
}

# Function to get current SSL mode
get_ssl_mode() {
    if [[ -f "${NGINX_DIR}/default.conf" ]]; then
        if grep -q "listen 443 ssl" "${NGINX_DIR}/default.conf"; then
            echo "https"
        else
            echo "http"
        fi
    else
        echo "unknown"
    fi
}

# Main function
main() {
    local action="${1:-auto}"
    local current_mode
    
    echo "=== Nginx SSL Configuration Manager ==="
    echo "Current time: $(date)"
    
    # Get current mode
    current_mode=$(get_ssl_mode)
    echo "Current nginx mode: $current_mode"
    
    case "$action" in
        "auto")
            echo "Auto-detecting SSL certificate availability..."
            
            if check_all_ssl_certs; then
                if [[ "$current_mode" != "https" ]]; then
                    configure_https_mode
                    if test_nginx_config; then
                        reload_nginx
                        echo "Successfully switched to HTTPS mode"
                    else
                        echo "Failed to configure HTTPS mode, reverting to HTTP"
                        configure_http_mode
                        test_nginx_config && reload_nginx
                    fi
                else
                    echo "Already in HTTPS mode and certificates are valid"
                fi
            else
                if [[ "$current_mode" != "http" ]]; then
                    configure_http_mode
                    if test_nginx_config; then
                        reload_nginx
                        echo "Successfully switched to HTTP-only mode"
                    else
                        echo "Failed to configure HTTP mode"
                        exit 1
                    fi
                else
                    echo "Already in HTTP-only mode"
                fi
            fi
            ;;
        "http")
            echo "Forcing HTTP-only mode..."
            configure_http_mode
            test_nginx_config && reload_nginx
            ;;
        "https")
            echo "Forcing HTTPS mode..."
            if check_all_ssl_certs; then
                configure_https_mode
                test_nginx_config && reload_nginx
            else
                echo "Cannot enable HTTPS mode: SSL certificates not available"
                exit 1
            fi
            ;;
        "status")
            echo "SSL Certificate Status:"
            for domain in "${DOMAINS[@]}"; do
                if check_ssl_cert "$domain"; then
                    echo "  ✓ $domain: Valid"
                else
                    echo "  ✗ $domain: Invalid/Missing"
                fi
            done
            echo "Current nginx mode: $current_mode"
            ;;
        "test")
            echo "Testing current nginx configuration..."
            test_nginx_config
            ;;
        *)
            echo "Usage: $0 [auto|http|https|status|test]"
            echo ""
            echo "Commands:"
            echo "  auto   - Automatically detect SSL and configure nginx (default)"
            echo "  http   - Force HTTP-only mode"
            echo "  https  - Force HTTPS mode (requires valid certificates)"
            echo "  status - Show SSL certificate and nginx status"
            echo "  test   - Test current nginx configuration"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
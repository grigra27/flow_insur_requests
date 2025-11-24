#!/usr/bin/env python3
"""
Timeweb Configuration Integrity Verification Script
This script verifies that all Timeweb configuration components are present and valid.
"""

import os
import sys
from pathlib import Path

# ANSI color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    """Print a formatted header"""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text.center(80)}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")

def print_success(text):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")

def print_error(text):
    """Print error message"""
    print(f"{RED}✗ {text}{RESET}")

def print_warning(text):
    """Print warning message"""
    print(f"{YELLOW}⚠ {text}{RESET}")

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if Path(filepath).exists():
        print_success(f"{description}: {filepath}")
        return True
    else:
        print_error(f"{description} NOT FOUND: {filepath}")
        return False

def check_docker_compose():
    """Verify docker-compose.yml configuration"""
    print_header("1. Docker Compose Configuration")
    
    filepath = "docker-compose.yml"
    if not check_file_exists(filepath, "Docker Compose file"):
        return False
    
    # Read and verify content
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check for required services
    required_services = ['db', 'web', 'nginx', 'certbot']
    all_services_present = True
    
    for service in required_services:
        if f"  {service}:" in content or f"  {service}:\n" in content:
            print_success(f"Service '{service}' is defined")
        else:
            print_error(f"Service '{service}' is NOT defined")
            all_services_present = False
    
    # Check for Timeweb-specific volumes
    if 'postgres_data_timeweb' in content:
        print_success("Timeweb PostgreSQL volume is configured")
    else:
        print_warning("Timeweb PostgreSQL volume not found")
    
    # Check for HTTPS environment variables
    https_vars = ['ENABLE_HTTPS', 'SSL_REDIRECT', 'SECURE_COOKIES', 'HSTS_SECONDS']
    for var in https_vars:
        if var in content:
            print_success(f"HTTPS variable '{var}' is configured")
        else:
            print_warning(f"HTTPS variable '{var}' not found")
    
    # Check for Timeweb domains
    timeweb_domains = ['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su']
    domains_found = sum(1 for domain in timeweb_domains if domain in content)
    print_success(f"Found {domains_found}/{len(timeweb_domains)} Timeweb domains in configuration")
    
    return all_services_present

def check_env_example():
    """Verify .env.example file"""
    print_header("2. Environment Variables Configuration")
    
    filepath = ".env.example"
    if not check_file_exists(filepath, "Environment example file"):
        return False
    
    # Read and verify content
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check for required variables
    required_vars = [
        'SECRET_KEY',
        'DEBUG',
        'DB_NAME',
        'DB_USER',
        'DB_PASSWORD',
        'ALLOWED_HOSTS',
        'ENABLE_HTTPS',
        'SSL_REDIRECT',
        'SECURE_COOKIES',
        'HSTS_SECONDS',
        'MAIN_DOMAINS',
        'SUBDOMAINS',
        'DOMAINS',
        'SSL_EMAIL'
    ]
    
    missing_vars = []
    for var in required_vars:
        if f"{var}=" in content:
            print_success(f"Variable '{var}' is defined")
        else:
            print_error(f"Variable '{var}' is NOT defined")
            missing_vars.append(var)
    
    # Check for Timeweb domains
    timeweb_domains = ['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su']
    domains_found = sum(1 for domain in timeweb_domains if domain in content)
    print_success(f"Found {domains_found}/{len(timeweb_domains)} Timeweb domains in .env.example")
    
    # Check for HTTPS configuration section
    if 'HTTPS SECURITY CONFIGURATION' in content:
        print_success("HTTPS security configuration section is present")
    else:
        print_warning("HTTPS security configuration section not found")
    
    return len(missing_vars) == 0

def check_nginx_config():
    """Verify nginx-timeweb configuration files"""
    print_header("3. Nginx Configuration Files")
    
    nginx_dir = "nginx-timeweb"
    if not Path(nginx_dir).is_dir():
        print_error(f"Nginx configuration directory NOT FOUND: {nginx_dir}")
        return False
    
    print_success(f"Nginx configuration directory exists: {nginx_dir}")
    
    # Check for required configuration files
    required_files = [
        'default.conf',
        'default-https.conf',
        'default-acme.conf'
    ]
    
    all_files_present = True
    for filename in required_files:
        filepath = Path(nginx_dir) / filename
        if not check_file_exists(str(filepath), f"Nginx config '{filename}'"):
            all_files_present = False
        else:
            # Verify content
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Check for Timeweb domains
            timeweb_domains = ['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su']
            domains_found = sum(1 for domain in timeweb_domains if domain in content)
            
            if domains_found > 0:
                print_success(f"  → Found {domains_found} Timeweb domains in {filename}")
            else:
                print_warning(f"  → No Timeweb domains found in {filename}")
            
            # Check for SSL configuration in HTTPS file
            if filename == 'default-https.conf':
                if 'ssl_certificate' in content and 'ssl_certificate_key' in content:
                    print_success(f"  → SSL certificate configuration is present")
                else:
                    print_error(f"  → SSL certificate configuration is MISSING")
                
                if 'Strict-Transport-Security' in content:
                    print_success(f"  → HSTS header is configured")
                else:
                    print_warning(f"  → HSTS header not found")
    
    return all_files_present

def check_django_settings():
    """Verify Django HTTPS settings"""
    print_header("4. Django HTTPS Settings")
    
    filepath = "onlineservice/settings.py"
    if not check_file_exists(filepath, "Django settings file"):
        return False
    
    # Read and verify content
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check for HTTPS-related settings
    https_settings = [
        'ENABLE_HTTPS',
        'SECURE_SSL_REDIRECT',
        'SECURE_HSTS_SECONDS',
        'SECURE_HSTS_INCLUDE_SUBDOMAINS',
        'SECURE_HSTS_PRELOAD',
        'SESSION_COOKIE_SECURE',
        'CSRF_COOKIE_SECURE',
        'SECURE_PROXY_SSL_HEADER',
        'CSRF_TRUSTED_ORIGINS'
    ]
    
    missing_settings = []
    for setting in https_settings:
        if setting in content:
            print_success(f"Setting '{setting}' is configured")
        else:
            print_error(f"Setting '{setting}' is NOT configured")
            missing_settings.append(setting)
    
    # Check for Timeweb domains
    timeweb_domains = ['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su']
    domains_found = sum(1 for domain in timeweb_domains if domain in content)
    
    if domains_found > 0:
        print_success(f"Found {domains_found} Timeweb domains in settings")
    else:
        print_warning("No Timeweb domains found in settings (may be configured via environment)")
    
    # Check for HTTPS middleware
    if 'HTTPSSecurityMiddleware' in content:
        print_success("HTTPS security middleware is configured")
    else:
        print_warning("HTTPS security middleware not found")
    
    # Check for domain routing middleware
    if 'DomainRoutingMiddleware' in content:
        print_success("Domain routing middleware is configured")
    else:
        print_warning("Domain routing middleware not found")
    
    return len(missing_settings) == 0

def check_domain_configuration():
    """Verify domain configuration"""
    print_header("5. Domain Configuration")
    
    # Check all configuration files for Timeweb domains
    timeweb_domains = ['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su']
    
    files_to_check = [
        'docker-compose.yml',
        '.env.example',
        'onlineservice/settings.py'
    ]
    
    for filepath in files_to_check:
        if Path(filepath).exists():
            with open(filepath, 'r') as f:
                content = f.read()
            
            domains_found = [domain for domain in timeweb_domains if domain in content]
            
            if domains_found:
                print_success(f"{filepath}: Found domains {', '.join(domains_found)}")
            else:
                print_warning(f"{filepath}: No Timeweb domains found")
    
    return True

def main():
    """Main verification function"""
    print_header("Timeweb Configuration Integrity Verification")
    print("This script verifies all components of the Timeweb deployment configuration.\n")
    
    results = {
        'docker_compose': check_docker_compose(),
        'env_example': check_env_example(),
        'nginx_config': check_nginx_config(),
        'django_settings': check_django_settings(),
        'domain_config': check_domain_configuration()
    }
    
    # Print summary
    print_header("Verification Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for check_name, result in results.items():
        status = f"{GREEN}PASSED{RESET}" if result else f"{RED}FAILED{RESET}"
        print(f"{check_name.replace('_', ' ').title()}: {status}")
    
    print(f"\n{BLUE}Overall Result: {passed}/{total} checks passed{RESET}\n")
    
    if passed == total:
        print_success("All Timeweb configuration checks passed!")
        print_success("The configuration is ready for deployment.")
        return 0
    else:
        print_error(f"{total - passed} check(s) failed.")
        print_error("Please review the errors above and fix the configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

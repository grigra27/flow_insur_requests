#!/usr/bin/env python3
"""
Enhanced healthcheck script for Django application with HTTPS and domain support
"""
import sys
import urllib.request
import urllib.error
import ssl
import socket
import os
import json
import logging
from datetime import datetime, timedelta

# Configure logging for SSL-related events
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/healthcheck.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def check_endpoint(url, description, timeout=10):
    """Check a specific endpoint and return success status"""
    try:
        # Create request with proper headers
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'HealthCheck/1.0')
        
        response = urllib.request.urlopen(request, timeout=timeout)
        if response.status == 200:
            print(f"✓ {description} - OK")
            logger.info(f"Health check passed: {description} ({url})")
            return True
        else:
            print(f"✗ {description} - Failed with status: {response.status}")
            logger.warning(f"Health check failed: {description} ({url}) - Status: {response.status}")
            return False
    except urllib.error.HTTPError as e:
        print(f"✗ {description} - HTTP Error {e.code}: {e.reason}")
        logger.error(f"Health check HTTP error: {description} ({url}) - {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"✗ {description} - Failed: {e}")
        logger.error(f"Health check URL error: {description} ({url}) - {e}")
        return False
    except Exception as e:
        print(f"✗ {description} - Error: {e}")
        logger.error(f"Health check error: {description} ({url}) - {e}")
        return False

def check_ssl_certificate(hostname, port=443):
    """Check SSL certificate validity and expiration"""
    try:
        # Create SSL context
        context = ssl.create_default_context()
        
        # Connect and get certificate
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                
                # Parse expiration date
                not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                days_until_expiry = (not_after - datetime.now()).days
                
                # Check certificate status
                if days_until_expiry < 0:
                    print(f"✗ SSL Certificate for {hostname} - EXPIRED {abs(days_until_expiry)} days ago")
                    logger.error(f"SSL certificate expired for {hostname}: {abs(days_until_expiry)} days ago")
                    return False
                elif days_until_expiry <= 7:
                    print(f"⚠ SSL Certificate for {hostname} - Expires in {days_until_expiry} days (CRITICAL)")
                    logger.warning(f"SSL certificate for {hostname} expires in {days_until_expiry} days (CRITICAL)")
                    return False
                elif days_until_expiry <= 30:
                    print(f"⚠ SSL Certificate for {hostname} - Expires in {days_until_expiry} days (WARNING)")
                    logger.warning(f"SSL certificate for {hostname} expires in {days_until_expiry} days")
                    return True
                else:
                    print(f"✓ SSL Certificate for {hostname} - Valid for {days_until_expiry} more days")
                    logger.info(f"SSL certificate for {hostname} is valid for {days_until_expiry} more days")
                    return True
                    
    except socket.timeout:
        print(f"✗ SSL Certificate for {hostname} - Connection timeout")
        logger.error(f"SSL certificate check timeout for {hostname}")
        return False
    except ssl.SSLError as e:
        print(f"✗ SSL Certificate for {hostname} - SSL Error: {e}")
        logger.error(f"SSL certificate error for {hostname}: {e}")
        return False
    except Exception as e:
        print(f"✗ SSL Certificate for {hostname} - Error: {e}")
        logger.error(f"SSL certificate check error for {hostname}: {e}")
        return False

def check_https_redirect(domain):
    """Check if HTTP to HTTPS redirect is working"""
    try:
        http_url = f"http://{domain}/"
        
        # Create request that doesn't follow redirects automatically
        request = urllib.request.Request(http_url)
        request.add_header('User-Agent', 'HealthCheck/1.0')
        
        try:
            response = urllib.request.urlopen(request, timeout=10)
            # If we get here, there's no redirect
            print(f"✗ HTTPS Redirect for {domain} - No redirect found")
            logger.warning(f"No HTTPS redirect found for {domain}")
            return False
        except urllib.error.HTTPError as e:
            if e.code in [301, 302, 303, 307, 308]:
                # Check if redirect location is HTTPS
                location = e.headers.get('Location', '')
                if location.startswith('https://'):
                    print(f"✓ HTTPS Redirect for {domain} - Working ({e.code})")
                    logger.info(f"HTTPS redirect working for {domain} ({e.code})")
                    return True
                else:
                    print(f"✗ HTTPS Redirect for {domain} - Redirects to non-HTTPS: {location}")
                    logger.warning(f"HTTPS redirect for {domain} redirects to non-HTTPS: {location}")
                    return False
            else:
                print(f"✗ HTTPS Redirect for {domain} - HTTP Error {e.code}")
                logger.error(f"HTTPS redirect check failed for {domain}: HTTP {e.code}")
                return False
                
    except Exception as e:
        print(f"✗ HTTPS Redirect for {domain} - Error: {e}")
        logger.error(f"HTTPS redirect check error for {domain}: {e}")
        return False

def get_configured_domains():
    """Get configured domains from environment variables"""
    # Get domains from environment
    main_domains = os.getenv('MAIN_DOMAINS', 'insflow.tw1.su').split(',')
    subdomains = os.getenv('SUBDOMAINS', 'zs.insflow.tw1.su').split(',')
    
    # Clean up domains (remove whitespace)
    main_domains = [domain.strip() for domain in main_domains if domain.strip()]
    subdomains = [domain.strip() for domain in subdomains if domain.strip()]
    
    return main_domains, subdomains

def check_domain_health(domain, is_subdomain=False):
    """Check health of a specific domain"""
    results = []
    
    print(f"\n--- Checking domain: {domain} ---")
    
    # Determine protocol based on environment
    is_https_enabled = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() == 'true'
    protocol = 'https' if is_https_enabled else 'http'
    
    if is_https_enabled:
        # Check SSL certificate
        ssl_ok = check_ssl_certificate(domain)
        results.append(ssl_ok)
        
        # Check HTTPS redirect
        redirect_ok = check_https_redirect(domain)
        results.append(redirect_ok)
    
    # Check main endpoints
    if is_subdomain:
        # For subdomains, check Django application endpoints
        health_ok = check_endpoint(f'{protocol}://{domain}/healthz/', f'{domain} - Health endpoint')
        login_ok = check_endpoint(f'{protocol}://{domain}/login/', f'{domain} - Login page')
        results.extend([health_ok, login_ok])
    else:
        # For main domains, check landing page
        landing_ok = check_endpoint(f'{protocol}://{domain}/', f'{domain} - Landing page')
        results.append(landing_ok)
    
    # Check static files
    static_ok = check_endpoint(f'{protocol}://{domain}/static/favicon.ico', f'{domain} - Static files')
    results.append(static_ok)
    
    return all(results)

def save_health_status(results):
    """Save health check results to JSON file"""
    try:
        os.makedirs('logs', exist_ok=True)
        
        status_data = {
            'timestamp': datetime.now().isoformat(),
            'results': results,
            'overall_status': 'healthy' if all(r['status'] for r in results) else 'unhealthy'
        }
        
        with open('logs/healthcheck_status.json', 'w') as f:
            json.dump(status_data, f, indent=2)
            
        logger.info(f"Health check status saved: {status_data['overall_status']}")
        
    except Exception as e:
        logger.error(f"Failed to save health check status: {e}")

def main():
    """Main health check function"""
    print("Starting enhanced health check with HTTPS support...")
    logger.info("Starting health check")
    
    # Check if we're in production environment
    is_production = os.getenv('DEBUG', 'True').lower() == 'false'
    is_https_enabled = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() == 'true'
    
    print(f"Environment: {'Production' if is_production else 'Development'}")
    print(f"HTTPS Mode: {'Enabled' if is_https_enabled else 'Disabled'}")
    
    results = []
    all_checks_passed = True
    
    if is_production:
        print("\nProduction environment detected - checking all configured domains")
        
        # Get configured domains
        main_domains, subdomains = get_configured_domains()
        
        print(f"Main domains: {', '.join(main_domains)}")
        print(f"Subdomains: {', '.join(subdomains)}")
        
        # Check main domains (landing pages)
        for domain in main_domains:
            domain_ok = check_domain_health(domain, is_subdomain=False)
            results.append({
                'domain': domain,
                'type': 'main',
                'status': domain_ok,
                'timestamp': datetime.now().isoformat()
            })
            if not domain_ok:
                all_checks_passed = False
        
        # Check subdomains (Django application)
        for domain in subdomains:
            domain_ok = check_domain_health(domain, is_subdomain=True)
            results.append({
                'domain': domain,
                'type': 'subdomain',
                'status': domain_ok,
                'timestamp': datetime.now().isoformat()
            })
            if not domain_ok:
                all_checks_passed = False
                
    else:
        print("\nDevelopment environment - checking local endpoints")
        
        # Basic health check endpoint
        health_ok = check_endpoint('http://localhost:8000/healthz/', 'Local health endpoint')
        results.append({
            'domain': 'localhost:8000',
            'type': 'local',
            'endpoint': 'healthz',
            'status': health_ok,
            'timestamp': datetime.now().isoformat()
        })
        
        # Check landing page
        landing_ok = check_endpoint('http://localhost:8000/landing/', 'Local landing page')
        results.append({
            'domain': 'localhost:8000',
            'type': 'local',
            'endpoint': 'landing',
            'status': landing_ok,
            'timestamp': datetime.now().isoformat()
        })
        
        all_checks_passed = health_ok and landing_ok
    
    # Save results
    save_health_status(results)
    
    # Print summary
    print(f"\n--- Health Check Summary ---")
    passed_count = sum(1 for r in results if r['status'])
    total_count = len(results)
    
    print(f"Checks passed: {passed_count}/{total_count}")
    
    if all_checks_passed:
        print("✓ All health checks passed")
        logger.info("All health checks passed")
        sys.exit(0)
    else:
        print("✗ Some health checks failed")
        logger.error("Some health checks failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
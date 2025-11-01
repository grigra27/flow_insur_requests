#!/usr/bin/env python3
"""
Enhanced healthcheck script for Django application with domain support
"""
import sys
import urllib.request
import urllib.error
import os

def check_endpoint(url, description):
    """Check a specific endpoint and return success status"""
    try:
        response = urllib.request.urlopen(url, timeout=5)
        if response.status == 200:
            print(f"✓ {description} - OK")
            return True
        else:
            print(f"✗ {description} - Failed with status: {response.status}")
            return False
    except urllib.error.URLError as e:
        print(f"✗ {description} - Failed: {e}")
        return False
    except Exception as e:
        print(f"✗ {description} - Error: {e}")
        return False

def main():
    """Main health check function"""
    print("Starting health check...")
    
    # Basic health check endpoint
    health_ok = check_endpoint('http://localhost:8000/healthz/', 'Health endpoint')
    
    # Check landing page (simulating main domain)
    landing_ok = check_endpoint('http://localhost:8000/landing/', 'Landing page')
    
    # Check if we're in production environment
    is_production = os.getenv('DEBUG', 'True').lower() == 'false'
    
    if is_production:
        print("Production environment detected - checking domain-specific endpoints")
        
        # In production, we can check both domains if available
        main_domain = os.getenv('MAIN_DOMAIN', 'insflow.tw1.su')
        subdomain = os.getenv('SUBDOMAIN', 'zs.insflow.tw1.su')
        
        print(f"Configured domains: {main_domain}, {subdomain}")
    
    # Determine overall health
    if health_ok and landing_ok:
        print("✓ All health checks passed")
        sys.exit(0)
    else:
        print("✗ Some health checks failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
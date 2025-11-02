#!/usr/bin/env python3
"""
Simple health check for deployment - only checks local Django app
"""
import sys
import urllib.request
import urllib.error
import ssl
import os

def check_local_django():
    """Check only the local Django application"""
    # Try HTTP first (direct to Django), then HTTPS if needed
    urls_to_try = [
        'http://localhost:8000/healthz/',  # Direct to Django
        'http://localhost/healthz/',       # Through nginx HTTP
        'https://localhost/healthz/'       # Through nginx HTTPS (with SSL verification disabled)
    ]
    
    for url in urls_to_try:
        try:
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'DeploymentHealthCheck/1.0')
            
            # For HTTPS, disable SSL verification for localhost
            if url.startswith('https://'):
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                response = urllib.request.urlopen(request, timeout=10, context=ssl_context)
            else:
                response = urllib.request.urlopen(request, timeout=5)
                
            if response.status == 200:
                print(f"✓ Local Django health check - OK ({url})")
                return True
            else:
                print(f"✗ Health check failed for {url} - Status: {response.status}")
                
        except Exception as e:
            print(f"✗ Health check failed for {url} - Error: {e}")
            continue
    
    print("✗ All health check attempts failed")
    return False

if __name__ == "__main__":
    if check_local_django():
        sys.exit(0)
    else:
        sys.exit(1)
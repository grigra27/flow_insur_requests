#!/usr/bin/env python3
"""
Simple health check for deployment - only checks local Django app
"""
import sys
import urllib.request
import urllib.error

def check_local_django():
    """Check only the local Django application"""
    try:
        request = urllib.request.Request('http://localhost:8000/healthz/')
        request.add_header('User-Agent', 'DeploymentHealthCheck/1.0')
        
        response = urllib.request.urlopen(request, timeout=5)
        if response.status == 200:
            print("✓ Local Django health check - OK")
            return True
        else:
            print(f"✗ Local Django health check - Failed with status: {response.status}")
            return False
    except Exception as e:
        print(f"✗ Local Django health check - Failed: {e}")
        return False

if __name__ == "__main__":
    if check_local_django():
        sys.exit(0)
    else:
        sys.exit(1)
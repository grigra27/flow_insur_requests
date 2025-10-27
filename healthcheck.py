#!/usr/bin/env python3
"""
Simple healthcheck script for Django application
"""
import sys
import urllib.request
import urllib.error

def main():
    try:
        response = urllib.request.urlopen('http://localhost:8000/healthz/', timeout=5)
        if response.status == 200:
            print("Health check passed")
            sys.exit(0)
        else:
            print(f"Health check failed with status: {response.status}")
            sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Health check failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Health check error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Domain monitoring script for insflow.tw1.su infrastructure
Monitors both main domain and subdomain availability
"""
import sys
import urllib.request
import urllib.error
import json
import time
import logging
from datetime import datetime
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/domain_monitoring.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class DomainMonitor:
    """Monitor domain availability and performance"""
    
    def __init__(self):
        self.main_domain = os.getenv('MAIN_DOMAIN', 'insflow.tw1.su')
        self.subdomain = os.getenv('SUBDOMAIN', 'zs.insflow.tw1.su')
        self.timeout = 10
        
    def check_domain(self, domain, path='/', expected_status=200):
        """Check if a domain is accessible"""
        url = f"https://{domain}{path}"
        start_time = time.time()
        
        try:
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'DomainMonitor/1.0')
            
            response = urllib.request.urlopen(request, timeout=self.timeout)
            response_time = time.time() - start_time
            
            result = {
                'domain': domain,
                'path': path,
                'status': 'success',
                'status_code': response.status,
                'response_time': round(response_time, 3),
                'timestamp': datetime.now().isoformat()
            }
            
            if response.status == expected_status:
                logger.info(f"✓ {domain}{path} - OK ({response.status}) - {response_time:.3f}s")
            else:
                logger.warning(f"⚠ {domain}{path} - Unexpected status {response.status} - {response_time:.3f}s")
                result['status'] = 'warning'
                
            return result
            
        except urllib.error.HTTPError as e:
            response_time = time.time() - start_time
            result = {
                'domain': domain,
                'path': path,
                'status': 'error',
                'status_code': e.code,
                'error': str(e),
                'response_time': round(response_time, 3),
                'timestamp': datetime.now().isoformat()
            }
            logger.error(f"✗ {domain}{path} - HTTP Error {e.code} - {response_time:.3f}s")
            return result
            
        except urllib.error.URLError as e:
            response_time = time.time() - start_time
            result = {
                'domain': domain,
                'path': path,
                'status': 'error',
                'error': str(e),
                'response_time': round(response_time, 3),
                'timestamp': datetime.now().isoformat()
            }
            logger.error(f"✗ {domain}{path} - URL Error: {e}")
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            result = {
                'domain': domain,
                'path': path,
                'status': 'error',
                'error': str(e),
                'response_time': round(response_time, 3),
                'timestamp': datetime.now().isoformat()
            }
            logger.error(f"✗ {domain}{path} - Error: {e}")
            return result
    
    def check_landing_page(self):
        """Check landing page on main domain"""
        return self.check_domain(self.main_domain, '/')
    
    def check_subdomain_app(self):
        """Check main application on subdomain"""
        return self.check_domain(self.subdomain, '/login/')
    
    def check_static_files(self):
        """Check static file serving on both domains"""
        results = []
        
        # Check CSS file on main domain
        css_result = self.check_domain(self.main_domain, '/static/css/landing.css')
        results.append(css_result)
        
        # Check CSS file on subdomain
        css_result_sub = self.check_domain(self.subdomain, '/static/css/custom.css')
        results.append(css_result_sub)
        
        return results
    
    def run_full_check(self):
        """Run complete domain monitoring check"""
        logger.info("Starting full domain monitoring check...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'checks': []
        }
        
        # Check landing page
        landing_result = self.check_landing_page()
        results['checks'].append(landing_result)
        
        # Check subdomain application
        app_result = self.check_subdomain_app()
        results['checks'].append(app_result)
        
        # Check static files
        static_results = self.check_static_files()
        results['checks'].extend(static_results)
        
        # Calculate overall status
        error_count = sum(1 for check in results['checks'] if check['status'] == 'error')
        warning_count = sum(1 for check in results['checks'] if check['status'] == 'warning')
        
        if error_count > 0:
            results['overall_status'] = 'error'
            logger.error(f"Domain monitoring completed with {error_count} errors, {warning_count} warnings")
        elif warning_count > 0:
            results['overall_status'] = 'warning'
            logger.warning(f"Domain monitoring completed with {warning_count} warnings")
        else:
            results['overall_status'] = 'success'
            logger.info("Domain monitoring completed successfully")
        
        # Save results to file
        self.save_results(results)
        
        return results
    
    def save_results(self, results):
        """Save monitoring results to JSON file"""
        try:
            os.makedirs('logs', exist_ok=True)
            with open('logs/domain_monitoring_results.json', 'w') as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save monitoring results: {e}")

def main():
    """Main function"""
    monitor = DomainMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        # Continuous monitoring mode
        logger.info("Starting continuous domain monitoring...")
        interval = int(os.getenv('MONITOR_INTERVAL', '300'))  # 5 minutes default
        
        while True:
            try:
                monitor.run_full_check()
                logger.info(f"Sleeping for {interval} seconds...")
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    else:
        # Single check mode
        results = monitor.run_full_check()
        
        # Exit with appropriate code
        if results['overall_status'] == 'error':
            sys.exit(1)
        elif results['overall_status'] == 'warning':
            sys.exit(2)
        else:
            sys.exit(0)

if __name__ == "__main__":
    main()
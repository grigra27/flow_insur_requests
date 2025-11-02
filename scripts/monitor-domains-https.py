#!/usr/bin/env python3
"""
Comprehensive HTTPS domain monitoring script for insflow infrastructure
Monitors all domains with SSL certificate checks and HTTPS functionality
"""
import sys
import urllib.request
import urllib.error
import ssl
import socket
import json
import time
import logging
import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/https_monitoring.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class HTTPSMonitor:
    """Comprehensive HTTPS monitoring for all domains"""
    
    def __init__(self):
        # Get domains from environment or use defaults
        self.main_domains = self._get_env_list('MAIN_DOMAINS', ['insflow.ru', 'insflow.tw1.su'])
        self.subdomains = self._get_env_list('SUBDOMAINS', ['zs.insflow.ru', 'zs.insflow.tw1.su'])
        self.all_domains = self.main_domains + self.subdomains
        
        # Configuration
        self.timeout = 10
        self.ssl_warning_days = 30
        self.ssl_critical_days = 7
        
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
    def _get_env_list(self, env_var: str, default: List[str]) -> List[str]:
        """Get list from environment variable or return default"""
        env_value = os.getenv(env_var)
        if env_value:
            return [domain.strip() for domain in env_value.split(',') if domain.strip()]
        return default
    
    def check_ssl_certificate(self, hostname: str, port: int = 443) -> Dict:
        """Check SSL certificate validity and return detailed information"""
        result = {
            'hostname': hostname,
            'port': port,
            'status': 'unknown',
            'valid': False,
            'days_until_expiry': 0,
            'issuer': '',
            'subject': '',
            'not_before': '',
            'not_after': '',
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            
            # Connect and get certificate
            with socket.create_connection((hostname, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    
                    # Parse certificate information
                    not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    days_until_expiry = (not_after - datetime.now()).days
                    
                    # Update result
                    result.update({
                        'valid': True,
                        'days_until_expiry': days_until_expiry,
                        'issuer': cert.get('issuer', [{}])[0].get('organizationName', 'Unknown'),
                        'subject': cert.get('subject', [{}])[0].get('commonName', hostname),
                        'not_before': not_before.isoformat(),
                        'not_after': not_after.isoformat()
                    })
                    
                    # Determine status
                    if days_until_expiry < 0:
                        result['status'] = 'expired'
                        logger.error(f"SSL certificate for {hostname} has EXPIRED {abs(days_until_expiry)} days ago")
                    elif days_until_expiry <= self.ssl_critical_days:
                        result['status'] = 'critical'
                        logger.error(f"SSL certificate for {hostname} expires in {days_until_expiry} days (CRITICAL)")
                    elif days_until_expiry <= self.ssl_warning_days:
                        result['status'] = 'warning'
                        logger.warning(f"SSL certificate for {hostname} expires in {days_until_expiry} days")
                    else:
                        result['status'] = 'valid'
                        logger.info(f"SSL certificate for {hostname} is valid for {days_until_expiry} more days")
                        
        except socket.timeout:
            result['error'] = 'Connection timeout'
            result['status'] = 'error'
            logger.error(f"SSL certificate check timeout for {hostname}")
        except ssl.SSLError as e:
            result['error'] = f'SSL Error: {str(e)}'
            result['status'] = 'error'
            logger.error(f"SSL certificate error for {hostname}: {e}")
        except Exception as e:
            result['error'] = str(e)
            result['status'] = 'error'
            logger.error(f"SSL certificate check error for {hostname}: {e}")
            
        return result
    
    def check_https_redirect(self, domain: str) -> Dict:
        """Check if HTTP to HTTPS redirect is working properly"""
        result = {
            'domain': domain,
            'redirect_working': False,
            'redirect_code': None,
            'redirect_location': '',
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            http_url = f"http://{domain}/"
            
            # Create request that doesn't follow redirects
            request = urllib.request.Request(http_url)
            request.add_header('User-Agent', 'HTTPSMonitor/1.0')
            
            try:
                response = urllib.request.urlopen(request, timeout=self.timeout)
                # If we get here, there's no redirect
                result['error'] = 'No redirect found'
                logger.warning(f"No HTTPS redirect found for {domain}")
            except urllib.error.HTTPError as e:
                if e.code in [301, 302, 303, 307, 308]:
                    location = e.headers.get('Location', '')
                    result['redirect_code'] = e.code
                    result['redirect_location'] = location
                    
                    if location.startswith('https://'):
                        result['redirect_working'] = True
                        logger.info(f"HTTPS redirect working for {domain} ({e.code} -> {location})")
                    else:
                        result['error'] = f'Redirects to non-HTTPS: {location}'
                        logger.warning(f"HTTPS redirect for {domain} redirects to non-HTTPS: {location}")
                else:
                    result['error'] = f'HTTP Error {e.code}'
                    logger.error(f"HTTPS redirect check failed for {domain}: HTTP {e.code}")
                    
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"HTTPS redirect check error for {domain}: {e}")
            
        return result
    
    def check_domain_availability(self, domain: str, paths: List[str] = None) -> Dict:
        """Check domain availability for multiple paths"""
        if paths is None:
            # Default paths based on domain type
            if domain in self.main_domains:
                paths = ['/']  # Landing page
            else:
                paths = ['/login/', '/healthz/']  # Django app endpoints
        
        result = {
            'domain': domain,
            'paths': {},
            'overall_available': True,
            'timestamp': datetime.now().isoformat()
        }
        
        for path in paths:
            path_result = self._check_single_path(domain, path)
            result['paths'][path] = path_result
            
            if not path_result['available']:
                result['overall_available'] = False
        
        return result
    
    def _check_single_path(self, domain: str, path: str) -> Dict:
        """Check availability of a single path on a domain"""
        url = f"https://{domain}{path}"
        start_time = time.time()
        
        path_result = {
            'path': path,
            'available': False,
            'status_code': None,
            'response_time': 0,
            'error': None
        }
        
        try:
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'HTTPSMonitor/1.0')
            
            response = urllib.request.urlopen(request, timeout=self.timeout)
            response_time = time.time() - start_time
            
            path_result.update({
                'available': True,
                'status_code': response.status,
                'response_time': round(response_time, 3)
            })
            
            logger.info(f"✓ {domain}{path} - Available ({response.status}) - {response_time:.3f}s")
            
        except urllib.error.HTTPError as e:
            response_time = time.time() - start_time
            path_result.update({
                'status_code': e.code,
                'response_time': round(response_time, 3),
                'error': f'HTTP {e.code}: {e.reason}'
            })
            logger.error(f"✗ {domain}{path} - HTTP Error {e.code} - {response_time:.3f}s")
            
        except Exception as e:
            response_time = time.time() - start_time
            path_result.update({
                'response_time': round(response_time, 3),
                'error': str(e)
            })
            logger.error(f"✗ {domain}{path} - Error: {e}")
            
        return path_result
    
    def check_security_headers(self, domain: str) -> Dict:
        """Check for important security headers"""
        result = {
            'domain': domain,
            'headers': {},
            'security_score': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        security_headers = [
            'Strict-Transport-Security',
            'X-Frame-Options',
            'X-Content-Type-Options',
            'Referrer-Policy',
            'X-XSS-Protection'
        ]
        
        try:
            url = f"https://{domain}/"
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'HTTPSMonitor/1.0')
            
            response = urllib.request.urlopen(request, timeout=self.timeout)
            
            for header in security_headers:
                header_value = response.headers.get(header)
                result['headers'][header] = {
                    'present': header_value is not None,
                    'value': header_value
                }
                
                if header_value:
                    result['security_score'] += 1
            
            # Calculate percentage
            result['security_score'] = round((result['security_score'] / len(security_headers)) * 100)
            
            logger.info(f"Security headers check for {domain}: {result['security_score']}% ({result['security_score']}/{len(security_headers)})")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Security headers check error for {domain}: {e}")
            
        return result
    
    def run_comprehensive_check(self) -> Dict:
        """Run comprehensive monitoring check for all domains"""
        logger.info("Starting comprehensive HTTPS monitoring check...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'domains': {},
            'summary': {
                'total_domains': len(self.all_domains),
                'healthy_domains': 0,
                'ssl_issues': 0,
                'availability_issues': 0,
                'redirect_issues': 0
            }
        }
        
        for domain in self.all_domains:
            logger.info(f"Checking domain: {domain}")
            
            domain_result = {
                'domain': domain,
                'type': 'main' if domain in self.main_domains else 'subdomain',
                'ssl_certificate': self.check_ssl_certificate(domain),
                'https_redirect': self.check_https_redirect(domain),
                'availability': self.check_domain_availability(domain),
                'security_headers': self.check_security_headers(domain),
                'overall_healthy': True
            }
            
            # Determine overall health
            if (domain_result['ssl_certificate']['status'] in ['expired', 'critical', 'error'] or
                not domain_result['https_redirect']['redirect_working'] or
                not domain_result['availability']['overall_available']):
                domain_result['overall_healthy'] = False
            
            # Update summary
            if domain_result['overall_healthy']:
                results['summary']['healthy_domains'] += 1
            
            if domain_result['ssl_certificate']['status'] in ['expired', 'critical', 'error']:
                results['summary']['ssl_issues'] += 1
                
            if not domain_result['https_redirect']['redirect_working']:
                results['summary']['redirect_issues'] += 1
                
            if not domain_result['availability']['overall_available']:
                results['summary']['availability_issues'] += 1
            
            results['domains'][domain] = domain_result
        
        # Save results
        self._save_results(results)
        
        # Log summary
        summary = results['summary']
        logger.info(f"Monitoring completed: {summary['healthy_domains']}/{summary['total_domains']} domains healthy")
        
        if summary['ssl_issues'] > 0:
            logger.error(f"SSL issues found on {summary['ssl_issues']} domains")
        if summary['redirect_issues'] > 0:
            logger.error(f"HTTPS redirect issues found on {summary['redirect_issues']} domains")
        if summary['availability_issues'] > 0:
            logger.error(f"Availability issues found on {summary['availability_issues']} domains")
        
        return results
    
    def _save_results(self, results: Dict):
        """Save monitoring results to JSON file"""
        try:
            with open('logs/https_monitoring_results.json', 'w') as f:
                json.dump(results, f, indent=2)
            logger.info("Monitoring results saved to logs/https_monitoring_results.json")
        except Exception as e:
            logger.error(f"Failed to save monitoring results: {e}")
    
    def generate_report(self, results: Dict = None) -> str:
        """Generate a human-readable monitoring report"""
        if results is None:
            # Load latest results
            try:
                with open('logs/https_monitoring_results.json', 'r') as f:
                    results = json.load(f)
            except Exception as e:
                return f"Error loading results: {e}"
        
        report = []
        report.append("=== HTTPS MONITORING REPORT ===")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Data from: {results['timestamp']}")
        report.append("")
        
        # Summary
        summary = results['summary']
        report.append("=== SUMMARY ===")
        report.append(f"Total domains: {summary['total_domains']}")
        report.append(f"Healthy domains: {summary['healthy_domains']}")
        report.append(f"SSL issues: {summary['ssl_issues']}")
        report.append(f"Redirect issues: {summary['redirect_issues']}")
        report.append(f"Availability issues: {summary['availability_issues']}")
        report.append("")
        
        # Domain details
        report.append("=== DOMAIN DETAILS ===")
        for domain, data in results['domains'].items():
            status_icon = "✓" if data['overall_healthy'] else "✗"
            report.append(f"{status_icon} {domain} ({data['type']})")
            
            # SSL status
            ssl = data['ssl_certificate']
            if ssl['valid']:
                report.append(f"  SSL: {ssl['status']} - expires in {ssl['days_until_expiry']} days")
            else:
                report.append(f"  SSL: {ssl['status']} - {ssl.get('error', 'Unknown error')}")
            
            # HTTPS redirect
            redirect = data['https_redirect']
            if redirect['redirect_working']:
                report.append(f"  Redirect: Working ({redirect['redirect_code']})")
            else:
                report.append(f"  Redirect: Failed - {redirect.get('error', 'Unknown error')}")
            
            # Availability
            avail = data['availability']
            if avail['overall_available']:
                report.append(f"  Availability: All paths accessible")
            else:
                failed_paths = [path for path, info in avail['paths'].items() if not info['available']]
                report.append(f"  Availability: Issues with paths: {', '.join(failed_paths)}")
            
            # Security headers
            security = data['security_headers']
            report.append(f"  Security headers: {security.get('security_score', 0)}%")
            
            report.append("")
        
        return "\n".join(report)

def main():
    """Main function"""
    monitor = HTTPSMonitor()
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--continuous':
            # Continuous monitoring mode
            logger.info("Starting continuous HTTPS monitoring...")
            interval = int(os.getenv('MONITOR_INTERVAL', '300'))  # 5 minutes default
            
            while True:
                try:
                    results = monitor.run_comprehensive_check()
                    
                    # Check if we should exit with error status
                    summary = results['summary']
                    if summary['ssl_issues'] > 0 or summary['availability_issues'] > 0:
                        logger.error("Critical issues found during monitoring")
                    
                    logger.info(f"Sleeping for {interval} seconds...")
                    time.sleep(interval)
                except KeyboardInterrupt:
                    logger.info("Monitoring stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")
                    time.sleep(60)  # Wait 1 minute before retrying
                    
        elif sys.argv[1] == '--report':
            # Generate report from latest results
            print(monitor.generate_report())
            
        elif sys.argv[1] == '--json':
            # Output JSON results
            results = monitor.run_comprehensive_check()
            print(json.dumps(results, indent=2))
            
        else:
            print("Usage: monitor-domains-https.py [--continuous|--report|--json]")
            sys.exit(1)
    else:
        # Single check mode
        results = monitor.run_comprehensive_check()
        
        # Print report
        print(monitor.generate_report(results))
        
        # Exit with appropriate code
        summary = results['summary']
        if summary['ssl_issues'] > 0 or summary['availability_issues'] > 0:
            sys.exit(1)  # Critical issues
        elif summary['redirect_issues'] > 0:
            sys.exit(2)  # Warning issues
        else:
            sys.exit(0)  # All good

if __name__ == "__main__":
    main()
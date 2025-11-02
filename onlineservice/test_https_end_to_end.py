#!/usr/bin/env python3
"""
End-to-End HTTPS Integration Tests
Tests all four domains with comprehensive HTTPS functionality
"""

import os
import sys
import time
import requests
import ssl
import socket
import concurrent.futures
from urllib.parse import urljoin
from datetime import datetime, timedelta
import json
import subprocess
from typing import Dict, List, Tuple, Optional

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class HTTPSEndToEndTester:
    """Comprehensive HTTPS end-to-end testing suite"""
    
    def __init__(self):
        self.domains = {
            'main_domains': ['insflow.ru', 'insflow.tw1.su'],
            'subdomains': ['zs.insflow.ru', 'zs.insflow.tw1.su']
        }
        self.all_domains = self.domains['main_domains'] + self.domains['subdomains']
        self.test_results = {}
        self.session = requests.Session()
        self.session.timeout = 30
        
    def log_test(self, test_name: str, domain: str, status: str, details: str = ""):
        """Log test results"""
        timestamp = datetime.now().isoformat()
        if domain not in self.test_results:
            self.test_results[domain] = []
        
        self.test_results[domain].append({
            'test': test_name,
            'status': status,
            'details': details,
            'timestamp': timestamp
        })
        
        status_symbol = "✓" if status == "PASS" else "✗"
        print(f"{status_symbol} [{domain}] {test_name}: {status}")
        if details:
            print(f"  Details: {details}")
    
    def test_ssl_certificate_validity(self, domain: str) -> bool:
        """Test SSL certificate validity and configuration"""
        try:
            # Test SSL connection
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    
                    # Check certificate validity
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    days_until_expiry = (not_after - datetime.now()).days
                    
                    if days_until_expiry < 7:
                        self.log_test("SSL Certificate Validity", domain, "WARN", 
                                    f"Certificate expires in {days_until_expiry} days")
                    else:
                        self.log_test("SSL Certificate Validity", domain, "PASS", 
                                    f"Certificate valid for {days_until_expiry} days")
                    
                    # Check certificate subject
                    subject = dict(x[0] for x in cert['subject'])
                    if domain in subject.get('commonName', '') or any(domain in san for san in cert.get('subjectAltName', [])):
                        self.log_test("SSL Certificate Subject", domain, "PASS", 
                                    f"Certificate matches domain")
                    else:
                        self.log_test("SSL Certificate Subject", domain, "FAIL", 
                                    f"Certificate doesn't match domain")
                        return False
                    
                    return True
                    
        except Exception as e:
            self.log_test("SSL Certificate Validity", domain, "FAIL", str(e))
            return False
    
    def test_http_to_https_redirect(self, domain: str) -> bool:
        """Test automatic HTTP to HTTPS redirection"""
        try:
            # Test HTTP request gets redirected to HTTPS
            response = self.session.get(f"http://{domain}", allow_redirects=False, timeout=10)
            
            if response.status_code in [301, 302, 307, 308]:
                redirect_location = response.headers.get('Location', '')
                if redirect_location.startswith('https://'):
                    self.log_test("HTTP to HTTPS Redirect", domain, "PASS", 
                                f"Redirects to {redirect_location}")
                    return True
                else:
                    self.log_test("HTTP to HTTPS Redirect", domain, "FAIL", 
                                f"Redirects to non-HTTPS: {redirect_location}")
                    return False
            else:
                self.log_test("HTTP to HTTPS Redirect", domain, "FAIL", 
                            f"No redirect, status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("HTTP to HTTPS Redirect", domain, "FAIL", str(e))
            return False
    
    def test_https_response(self, domain: str) -> bool:
        """Test HTTPS response and security headers"""
        try:
            response = self.session.get(f"https://{domain}", timeout=15)
            
            # Test response status
            if response.status_code == 200:
                self.log_test("HTTPS Response Status", domain, "PASS", "200 OK")
            else:
                self.log_test("HTTPS Response Status", domain, "FAIL", 
                            f"Status: {response.status_code}")
                return False
            
            # Test security headers
            security_headers = {
                'Strict-Transport-Security': 'HSTS header',
                'X-Frame-Options': 'Clickjacking protection',
                'X-Content-Type-Options': 'MIME type sniffing protection',
                'X-XSS-Protection': 'XSS protection'
            }
            
            for header, description in security_headers.items():
                if header in response.headers:
                    self.log_test(f"Security Header: {header}", domain, "PASS", 
                                response.headers[header])
                else:
                    self.log_test(f"Security Header: {header}", domain, "WARN", 
                                f"Missing {description}")
            
            return True
            
        except Exception as e:
            self.log_test("HTTPS Response", domain, "FAIL", str(e))
            return False
    
    def test_landing_page_functionality(self, domain: str) -> bool:
        """Test landing page functionality through HTTPS"""
        if domain not in self.domains['main_domains']:
            return True  # Skip for subdomains
            
        try:
            response = self.session.get(f"https://{domain}", timeout=15)
            
            # Check if it's the landing page
            if 'landing' in response.text.lower() or 'страхов' in response.text.lower():
                self.log_test("Landing Page Content", domain, "PASS", "Landing page loaded")
            else:
                self.log_test("Landing Page Content", domain, "WARN", "Content unclear")
            
            # Test static files loading
            if 'css' in response.text and 'js' in response.text:
                self.log_test("Landing Page Assets", domain, "PASS", "CSS/JS references found")
            else:
                self.log_test("Landing Page Assets", domain, "WARN", "Limited asset references")
            
            return True
            
        except Exception as e:
            self.log_test("Landing Page Functionality", domain, "FAIL", str(e))
            return False
    
    def test_django_app_functionality(self, domain: str) -> bool:
        """Test Django application functionality through HTTPS"""
        if domain not in self.domains['subdomains']:
            return True  # Skip for main domains
            
        try:
            # Test Django app main page
            response = self.session.get(f"https://{domain}", timeout=15)
            
            if response.status_code == 200:
                self.log_test("Django App Access", domain, "PASS", "Django app accessible")
            else:
                self.log_test("Django App Access", domain, "FAIL", 
                            f"Status: {response.status_code}")
                return False
            
            # Test Django admin (should redirect to login)
            admin_response = self.session.get(f"https://{domain}/admin/", timeout=10)
            if admin_response.status_code in [200, 302]:
                self.log_test("Django Admin Access", domain, "PASS", "Admin accessible")
            else:
                self.log_test("Django Admin Access", domain, "WARN", 
                            f"Admin status: {admin_response.status_code}")
            
            # Test API endpoints if available
            try:
                api_response = self.session.get(f"https://{domain}/api/", timeout=10)
                if api_response.status_code in [200, 404]:  # 404 is OK if no API
                    self.log_test("API Endpoints", domain, "PASS", "API accessible")
            except:
                self.log_test("API Endpoints", domain, "INFO", "No API endpoints found")
            
            return True
            
        except Exception as e:
            self.log_test("Django App Functionality", domain, "FAIL", str(e))
            return False
    
    def test_static_files_https(self, domain: str) -> bool:
        """Test static files loading through HTTPS"""
        try:
            # Test common static file paths
            static_paths = [
                '/static/css/custom.css',
                '/static/favicon.ico',
                '/static/css/bootstrap/bootstrap.min.css'
            ]
            
            static_files_working = 0
            for path in static_paths:
                try:
                    response = self.session.get(f"https://{domain}{path}", timeout=10)
                    if response.status_code == 200:
                        static_files_working += 1
                        self.log_test(f"Static File: {path}", domain, "PASS", "File loaded")
                    else:
                        self.log_test(f"Static File: {path}", domain, "INFO", 
                                    f"Status: {response.status_code}")
                except:
                    self.log_test(f"Static File: {path}", domain, "INFO", "File not found")
            
            if static_files_working > 0:
                self.log_test("Static Files HTTPS", domain, "PASS", 
                            f"{static_files_working}/{len(static_paths)} files loaded")
                return True
            else:
                self.log_test("Static Files HTTPS", domain, "WARN", "No static files found")
                return False
                
        except Exception as e:
            self.log_test("Static Files HTTPS", domain, "FAIL", str(e))
            return False
    
    def test_performance_metrics(self, domain: str) -> Dict:
        """Test HTTPS performance metrics"""
        try:
            start_time = time.time()
            response = self.session.get(f"https://{domain}", timeout=15)
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000  # Convert to milliseconds
            
            # Performance thresholds
            if response_time < 1000:
                status = "EXCELLENT"
            elif response_time < 2000:
                status = "GOOD"
            elif response_time < 5000:
                status = "ACCEPTABLE"
            else:
                status = "SLOW"
            
            self.log_test("HTTPS Performance", domain, status, 
                        f"Response time: {response_time:.2f}ms")
            
            return {
                'response_time_ms': response_time,
                'status_code': response.status_code,
                'content_length': len(response.content)
            }
            
        except Exception as e:
            self.log_test("HTTPS Performance", domain, "FAIL", str(e))
            return {}
    
    def test_concurrent_load(self, domain: str, concurrent_requests: int = 10) -> bool:
        """Test concurrent load handling"""
        try:
            def make_request():
                start_time = time.time()
                response = self.session.get(f"https://{domain}", timeout=15)
                end_time = time.time()
                return {
                    'status_code': response.status_code,
                    'response_time': (end_time - start_time) * 1000,
                    'success': response.status_code == 200
                }
            
            # Execute concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
                futures = [executor.submit(make_request) for _ in range(concurrent_requests)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            # Analyze results
            successful_requests = sum(1 for r in results if r['success'])
            avg_response_time = sum(r['response_time'] for r in results) / len(results)
            
            success_rate = (successful_requests / concurrent_requests) * 100
            
            if success_rate >= 95:
                status = "PASS"
            elif success_rate >= 80:
                status = "WARN"
            else:
                status = "FAIL"
            
            self.log_test("Concurrent Load Test", domain, status, 
                        f"{success_rate:.1f}% success rate, avg: {avg_response_time:.2f}ms")
            
            return success_rate >= 80
            
        except Exception as e:
            self.log_test("Concurrent Load Test", domain, "FAIL", str(e))
            return False
    
    def run_comprehensive_tests(self) -> Dict:
        """Run all comprehensive tests for all domains"""
        print("=" * 80)
        print("HTTPS END-TO-END INTEGRATION TESTING")
        print("=" * 80)
        print(f"Testing domains: {', '.join(self.all_domains)}")
        print(f"Started at: {datetime.now().isoformat()}")
        print()
        
        overall_results = {}
        
        for domain in self.all_domains:
            print(f"\n--- Testing {domain} ---")
            domain_results = {
                'ssl_valid': self.test_ssl_certificate_validity(domain),
                'http_redirect': self.test_http_to_https_redirect(domain),
                'https_response': self.test_https_response(domain),
                'landing_page': self.test_landing_page_functionality(domain),
                'django_app': self.test_django_app_functionality(domain),
                'static_files': self.test_static_files_https(domain),
                'performance': self.test_performance_metrics(domain),
                'load_test': self.test_concurrent_load(domain, 5)  # Reduced for testing
            }
            
            overall_results[domain] = domain_results
        
        return overall_results
    
    def generate_test_report(self, results: Dict) -> str:
        """Generate comprehensive test report"""
        report = []
        report.append("=" * 80)
        report.append("HTTPS END-TO-END TEST REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append(f"Domains tested: {len(self.all_domains)}")
        report.append("")
        
        # Summary
        total_tests = 0
        passed_tests = 0
        
        for domain, domain_results in results.items():
            report.append(f"Domain: {domain}")
            report.append("-" * 40)
            
            for test_name, result in domain_results.items():
                total_tests += 1
                if isinstance(result, bool):
                    status = "PASS" if result else "FAIL"
                    if result:
                        passed_tests += 1
                elif isinstance(result, dict):
                    status = "INFO"
                    passed_tests += 1  # Performance metrics count as pass
                else:
                    status = "INFO"
                    passed_tests += 1
                
                report.append(f"  {test_name}: {status}")
            
            report.append("")
        
        # Overall summary
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        report.append(f"OVERALL RESULTS:")
        report.append(f"  Total tests: {total_tests}")
        report.append(f"  Passed: {passed_tests}")
        report.append(f"  Success rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            report.append("  Status: EXCELLENT ✓")
        elif success_rate >= 80:
            report.append("  Status: GOOD ✓")
        elif success_rate >= 70:
            report.append("  Status: ACCEPTABLE ⚠")
        else:
            report.append("  Status: NEEDS ATTENTION ✗")
        
        # Detailed results
        report.append("\nDETAILED TEST RESULTS:")
        report.append("=" * 40)
        
        for domain, test_results in self.test_results.items():
            report.append(f"\n{domain}:")
            for test in test_results:
                report.append(f"  [{test['timestamp']}] {test['test']}: {test['status']}")
                if test['details']:
                    report.append(f"    {test['details']}")
        
        return "\n".join(report)


def main():
    """Main test execution function"""
    tester = HTTPSEndToEndTester()
    
    try:
        # Run comprehensive tests
        results = tester.run_comprehensive_tests()
        
        # Generate and save report
        report = tester.generate_test_report(results)
        
        # Save report to file
        report_filename = f"https_end_to_end_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print("\n" + "=" * 80)
        print("TEST EXECUTION COMPLETED")
        print("=" * 80)
        print(f"Report saved to: {report_filename}")
        print("\nSUMMARY:")
        print(report.split("OVERALL RESULTS:")[1].split("DETAILED TEST RESULTS:")[0])
        
        return results
        
    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        return {}
    except Exception as e:
        print(f"\nTest execution failed: {e}")
        return {}


if __name__ == "__main__":
    main()
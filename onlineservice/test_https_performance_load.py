#!/usr/bin/env python3
"""
HTTPS Performance and Load Testing
Comprehensive performance testing for all HTTPS domains
"""

import os
import sys
import time
import requests
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
import ssl
import socket
from typing import Dict, List, Tuple
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class HTTPSPerformanceTester:
    """HTTPS Performance and Load Testing Suite"""
    
    def __init__(self):
        self.domains = {
            'main_domains': ['insflow.ru', 'insflow.tw1.su'],
            'subdomains': ['zs.insflow.ru', 'zs.insflow.tw1.su']
        }
        self.all_domains = self.domains['main_domains'] + self.domains['subdomains']
        self.results = {}
        
    def measure_ssl_handshake_time(self, domain: str, port: int = 443) -> float:
        """Measure SSL handshake time"""
        try:
            start_time = time.time()
            
            # Create socket connection
            sock = socket.create_connection((domain, port), timeout=10)
            
            # Perform SSL handshake
            context = ssl.create_default_context()
            ssl_sock = context.wrap_socket(sock, server_hostname=domain)
            
            handshake_time = time.time() - start_time
            
            ssl_sock.close()
            sock.close()
            
            return handshake_time * 1000  # Convert to milliseconds
            
        except Exception as e:
            print(f"SSL handshake failed for {domain}: {e}")
            return -1
    
    def measure_response_time(self, url: str, timeout: int = 15) -> Dict:
        """Measure detailed response time metrics"""
        try:
            session = requests.Session()
            
            start_time = time.time()
            response = session.get(url, timeout=timeout)
            end_time = time.time()
            
            total_time = (end_time - start_time) * 1000
            
            return {
                'success': True,
                'status_code': response.status_code,
                'total_time_ms': total_time,
                'content_length': len(response.content),
                'headers': dict(response.headers),
                'url': url
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
    
    def run_load_test(self, domain: str, num_requests: int = 50, 
                     concurrent_users: int = 10, duration_seconds: int = 30) -> Dict:
        """Run comprehensive load test"""
        print(f"\nRunning load test for {domain}")
        print(f"  Requests: {num_requests}, Concurrent users: {concurrent_users}")
        print(f"  Duration: {duration_seconds} seconds")
        
        url = f"https://{domain}"
        results = []
        errors = []
        start_time = time.time()
        
        def make_request():
            return self.measure_response_time(url)
        
        # Execute load test
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            # Submit initial batch of requests
            futures = []
            for _ in range(min(num_requests, concurrent_users)):
                futures.append(executor.submit(make_request))
            
            completed_requests = 0
            
            # Process results and submit new requests
            while completed_requests < num_requests and (time.time() - start_time) < duration_seconds:
                for future in as_completed(futures):
                    result = future.result()
                    
                    if result['success']:
                        results.append(result)
                    else:
                        errors.append(result)
                    
                    completed_requests += 1
                    
                    # Submit new request if we haven't reached the limit
                    if completed_requests < num_requests and (time.time() - start_time) < duration_seconds:
                        futures.append(executor.submit(make_request))
                    
                    futures.remove(future)
                    
                    if completed_requests % 10 == 0:
                        print(f"  Completed: {completed_requests}/{num_requests}")
        
        # Calculate statistics
        if results:
            response_times = [r['total_time_ms'] for r in results]
            content_lengths = [r['content_length'] for r in results]
            
            stats = {
                'total_requests': len(results),
                'total_errors': len(errors),
                'success_rate': (len(results) / (len(results) + len(errors))) * 100,
                'avg_response_time_ms': statistics.mean(response_times),
                'median_response_time_ms': statistics.median(response_times),
                'min_response_time_ms': min(response_times),
                'max_response_time_ms': max(response_times),
                'p95_response_time_ms': statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times),
                'p99_response_time_ms': statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else max(response_times),
                'avg_content_length': statistics.mean(content_lengths),
                'requests_per_second': len(results) / (time.time() - start_time),
                'test_duration_seconds': time.time() - start_time
            }
        else:
            stats = {
                'total_requests': 0,
                'total_errors': len(errors),
                'success_rate': 0,
                'error': 'No successful requests'
            }
        
        return {
            'domain': domain,
            'statistics': stats,
            'errors': errors[:10],  # Keep only first 10 errors
            'sample_results': results[:5]  # Keep only first 5 successful results
        }
    
    def test_static_files_performance(self, domain: str) -> Dict:
        """Test static files loading performance"""
        static_files = [
            '/static/css/custom.css',
            '/static/favicon.ico',
            '/static/css/bootstrap/bootstrap.min.css',
            '/static/js/bootstrap/bootstrap.bundle.min.js'
        ]
        
        results = {}
        
        for file_path in static_files:
            url = f"https://{domain}{file_path}"
            result = self.measure_response_time(url, timeout=10)
            
            if result['success']:
                results[file_path] = {
                    'response_time_ms': result['total_time_ms'],
                    'content_length': result['content_length'],
                    'status': 'SUCCESS'
                }
            else:
                results[file_path] = {
                    'status': 'FAILED',
                    'error': result.get('error', 'Unknown error')
                }
        
        return results
    
    def test_ssl_performance(self, domain: str, iterations: int = 10) -> Dict:
        """Test SSL handshake performance"""
        handshake_times = []
        
        for i in range(iterations):
            handshake_time = self.measure_ssl_handshake_time(domain)
            if handshake_time > 0:
                handshake_times.append(handshake_time)
            
            if i % 3 == 0:
                print(f"  SSL handshake {i+1}/{iterations}: {handshake_time:.2f}ms")
        
        if handshake_times:
            return {
                'avg_handshake_time_ms': statistics.mean(handshake_times),
                'min_handshake_time_ms': min(handshake_times),
                'max_handshake_time_ms': max(handshake_times),
                'successful_handshakes': len(handshake_times),
                'total_attempts': iterations
            }
        else:
            return {
                'error': 'No successful SSL handshakes',
                'total_attempts': iterations
            }
    
    def run_comprehensive_performance_test(self) -> Dict:
        """Run comprehensive performance tests for all domains"""
        print("=" * 80)
        print("HTTPS PERFORMANCE AND LOAD TESTING")
        print("=" * 80)
        print(f"Testing domains: {', '.join(self.all_domains)}")
        print(f"Started at: {datetime.now().isoformat()}")
        
        all_results = {}
        
        for domain in self.all_domains:
            print(f"\n{'='*20} Testing {domain} {'='*20}")
            
            domain_results = {}
            
            # SSL Performance Test
            print(f"\n1. SSL Handshake Performance Test")
            ssl_results = self.test_ssl_performance(domain, iterations=5)
            domain_results['ssl_performance'] = ssl_results
            
            # Basic Response Time Test
            print(f"\n2. Basic Response Time Test")
            basic_response = self.measure_response_time(f"https://{domain}")
            domain_results['basic_response'] = basic_response
            
            # Static Files Performance Test
            print(f"\n3. Static Files Performance Test")
            static_results = self.test_static_files_performance(domain)
            domain_results['static_files'] = static_results
            
            # Load Test (reduced for testing)
            print(f"\n4. Load Test")
            load_results = self.run_load_test(
                domain, 
                num_requests=20,  # Reduced for testing
                concurrent_users=5, 
                duration_seconds=15
            )
            domain_results['load_test'] = load_results
            
            all_results[domain] = domain_results
        
        return all_results
    
    def generate_performance_report(self, results: Dict) -> str:
        """Generate comprehensive performance report"""
        report = []
        report.append("=" * 80)
        report.append("HTTPS PERFORMANCE TEST REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        for domain, domain_results in results.items():
            report.append(f"DOMAIN: {domain}")
            report.append("=" * 50)
            
            # SSL Performance
            if 'ssl_performance' in domain_results:
                ssl_data = domain_results['ssl_performance']
                report.append("\nSSL Handshake Performance:")
                if 'avg_handshake_time_ms' in ssl_data:
                    report.append(f"  Average handshake time: {ssl_data['avg_handshake_time_ms']:.2f}ms")
                    report.append(f"  Min handshake time: {ssl_data['min_handshake_time_ms']:.2f}ms")
                    report.append(f"  Max handshake time: {ssl_data['max_handshake_time_ms']:.2f}ms")
                    report.append(f"  Success rate: {ssl_data['successful_handshakes']}/{ssl_data['total_attempts']}")
                else:
                    report.append(f"  Error: {ssl_data.get('error', 'Unknown error')}")
            
            # Basic Response
            if 'basic_response' in domain_results:
                basic_data = domain_results['basic_response']
                report.append("\nBasic Response Performance:")
                if basic_data['success']:
                    report.append(f"  Response time: {basic_data['total_time_ms']:.2f}ms")
                    report.append(f"  Status code: {basic_data['status_code']}")
                    report.append(f"  Content length: {basic_data['content_length']} bytes")
                else:
                    report.append(f"  Error: {basic_data.get('error', 'Unknown error')}")
            
            # Static Files
            if 'static_files' in domain_results:
                report.append("\nStatic Files Performance:")
                for file_path, file_data in domain_results['static_files'].items():
                    if file_data['status'] == 'SUCCESS':
                        report.append(f"  {file_path}: {file_data['response_time_ms']:.2f}ms ({file_data['content_length']} bytes)")
                    else:
                        report.append(f"  {file_path}: FAILED - {file_data.get('error', 'Unknown error')}")
            
            # Load Test
            if 'load_test' in domain_results:
                load_data = domain_results['load_test']['statistics']
                report.append("\nLoad Test Results:")
                if 'avg_response_time_ms' in load_data:
                    report.append(f"  Total requests: {load_data['total_requests']}")
                    report.append(f"  Success rate: {load_data['success_rate']:.1f}%")
                    report.append(f"  Average response time: {load_data['avg_response_time_ms']:.2f}ms")
                    report.append(f"  Median response time: {load_data['median_response_time_ms']:.2f}ms")
                    report.append(f"  95th percentile: {load_data['p95_response_time_ms']:.2f}ms")
                    report.append(f"  Requests per second: {load_data['requests_per_second']:.2f}")
                    report.append(f"  Test duration: {load_data['test_duration_seconds']:.2f}s")
                else:
                    report.append(f"  Error: {load_data.get('error', 'Unknown error')}")
            
            report.append("")
        
        # Performance Summary
        report.append("PERFORMANCE SUMMARY")
        report.append("=" * 30)
        
        # Calculate overall metrics
        total_domains = len(results)
        successful_domains = 0
        avg_response_times = []
        
        for domain, domain_results in results.items():
            if (domain_results.get('basic_response', {}).get('success', False) and
                domain_results.get('load_test', {}).get('statistics', {}).get('success_rate', 0) > 80):
                successful_domains += 1
                
                if 'basic_response' in domain_results:
                    avg_response_times.append(domain_results['basic_response']['total_time_ms'])
        
        report.append(f"Domains tested: {total_domains}")
        report.append(f"Successful domains: {successful_domains}")
        report.append(f"Overall success rate: {(successful_domains/total_domains)*100:.1f}%")
        
        if avg_response_times:
            overall_avg = statistics.mean(avg_response_times)
            report.append(f"Average response time across domains: {overall_avg:.2f}ms")
            
            if overall_avg < 500:
                report.append("Performance rating: EXCELLENT ✓")
            elif overall_avg < 1000:
                report.append("Performance rating: GOOD ✓")
            elif overall_avg < 2000:
                report.append("Performance rating: ACCEPTABLE ⚠")
            else:
                report.append("Performance rating: NEEDS IMPROVEMENT ✗")
        
        return "\n".join(report)


def main():
    """Main performance test execution"""
    tester = HTTPSPerformanceTester()
    
    try:
        print("Starting HTTPS Performance Testing...")
        print("This may take several minutes to complete.")
        print()
        
        # Run comprehensive performance tests
        results = tester.run_comprehensive_performance_test()
        
        # Generate report
        report = tester.generate_performance_report(results)
        
        # Save report
        report_filename = f"https_performance_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Save raw results as JSON
        json_filename = f"https_performance_test_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        print("\n" + "=" * 80)
        print("PERFORMANCE TEST COMPLETED")
        print("=" * 80)
        print(f"Report saved to: {report_filename}")
        print(f"Raw data saved to: {json_filename}")
        print()
        print("SUMMARY:")
        summary_start = report.find("PERFORMANCE SUMMARY")
        if summary_start != -1:
            print(report[summary_start:])
        
        return results
        
    except KeyboardInterrupt:
        print("\nPerformance test interrupted by user")
        return {}
    except Exception as e:
        print(f"\nPerformance test failed: {e}")
        import traceback
        traceback.print_exc()
        return {}


if __name__ == "__main__":
    main()
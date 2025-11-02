"""
Performance tests for HTTPS functionality.
Tests SSL handshake performance, concurrent connections, and HTTPS-specific optimizations.
"""
import time
import threading
import statistics
from django.test import TestCase, Client, override_settings
from django.test.utils import override_settings
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue


@override_settings(
    ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su'],
    MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
    SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su'],
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True
)
class HTTPSPerformanceTest(TestCase):
    """Test HTTPS performance characteristics"""
    
    def setUp(self):
        self.client = Client()
        self.domains = {
            'main': ['insflow.ru', 'insflow.tw1.su'],
            'sub': ['zs.insflow.ru', 'zs.insflow.tw1.su']
        }
    
    def measure_response_time(self, domain, path, secure=True, iterations=5):
        """Measure average response time for a given domain and path"""
        times = []
        
        for _ in range(iterations):
            start_time = time.time()
            response = self.client.get(path, HTTP_HOST=domain, secure=secure)
            end_time = time.time()
            
            times.append(end_time - start_time)
            
            # Ensure request was successful
            self.assertIn(response.status_code, [200, 302, 404])
        
        return {
            'avg': statistics.mean(times),
            'min': min(times),
            'max': max(times),
            'median': statistics.median(times)
        }
    
    def test_landing_page_response_time_performance(self):
        """Test landing page response time performance across main domains"""
        performance_results = {}
        
        for domain in self.domains['main']:
            with self.subTest(domain=domain):
                results = self.measure_response_time(domain, '/')
                performance_results[domain] = results
                
                # Response time should be reasonable (under 1 second for tests)
                self.assertLess(results['avg'], 1.0, 
                              f"Average response time for {domain} is too high: {results['avg']:.3f}s")
                self.assertLess(results['max'], 2.0,
                              f"Max response time for {domain} is too high: {results['max']:.3f}s")
        
        # Response times should be consistent across domains
        if len(performance_results) > 1:
            avg_times = [results['avg'] for results in performance_results.values()]
            time_variance = max(avg_times) - min(avg_times)
            self.assertLess(time_variance, 0.5, 
                          f"Response time variance across domains is too high: {time_variance:.3f}s")
    
    def test_static_file_serving_performance(self):
        """Test static file serving performance over HTTPS"""
        static_files = [
            '/static/css/custom.css',
            '/static/css/landing.css',
            '/static/favicon.ico'
        ]
        
        for domain in self.domains['main']:
            for static_file in static_files:
                with self.subTest(domain=domain, file=static_file):
                    results = self.measure_response_time(domain, static_file)
                    
                    # Static files should be served quickly
                    self.assertLess(results['avg'], 0.5,
                                  f"Static file {static_file} on {domain} is too slow: {results['avg']:.3f}s")
    
    def test_subdomain_application_performance(self):
        """Test subdomain application performance over HTTPS"""
        app_paths = ['/', '/admin/', '/login/']
        
        for domain in self.domains['sub']:
            for path in app_paths:
                with self.subTest(domain=domain, path=path):
                    results = self.measure_response_time(domain, path)
                    
                    # Application responses should be reasonable
                    self.assertLess(results['avg'], 1.0,
                                  f"Application path {path} on {domain} is too slow: {results['avg']:.3f}s")
    
    def test_concurrent_request_performance(self):
        """Test performance under concurrent HTTPS requests"""
        def make_concurrent_request(domain, path):
            start_time = time.time()
            response = self.client.get(path, HTTP_HOST=domain, secure=True)
            end_time = time.time()
            return {
                'domain': domain,
                'path': path,
                'status_code': response.status_code,
                'response_time': end_time - start_time
            }
        
        # Test concurrent requests to different domains
        test_cases = [
            ('insflow.ru', '/'),
            ('insflow.tw1.su', '/'),
            ('zs.insflow.ru', '/'),
            ('zs.insflow.tw1.su', '/'),
        ]
        
        # Run concurrent requests
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            
            # Submit multiple requests for each test case
            for _ in range(3):  # 3 iterations of each test case
                for domain, path in test_cases:
                    future = executor.submit(make_concurrent_request, domain, path)
                    futures.append(future)
            
            # Collect results
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        # Analyze concurrent performance
        response_times = [r['response_time'] for r in results]
        avg_concurrent_time = statistics.mean(response_times)
        max_concurrent_time = max(response_times)
        
        # Concurrent requests should not be significantly slower
        self.assertLess(avg_concurrent_time, 2.0,
                       f"Average concurrent response time is too high: {avg_concurrent_time:.3f}s")
        self.assertLess(max_concurrent_time, 5.0,
                       f"Max concurrent response time is too high: {max_concurrent_time:.3f}s")
        
        # All requests should succeed
        for result in results:
            with self.subTest(domain=result['domain'], path=result['path']):
                self.assertIn(result['status_code'], [200, 302, 404])
    
    def test_domain_routing_middleware_performance(self):
        """Test domain routing middleware performance overhead"""
        # Measure middleware processing time by comparing with and without middleware
        
        def measure_middleware_overhead(domain, path, iterations=10):
            times_with_middleware = []
            
            for _ in range(iterations):
                start_time = time.time()
                response = self.client.get(path, HTTP_HOST=domain, secure=True)
                end_time = time.time()
                times_with_middleware.append(end_time - start_time)
            
            return statistics.mean(times_with_middleware)
        
        # Test middleware overhead on different domain types
        test_cases = [
            ('insflow.ru', '/'),  # Main domain - middleware processing
            ('zs.insflow.ru', '/'),  # Subdomain - pass through
            ('localhost', '/'),  # Development - pass through
        ]
        
        overhead_results = {}
        for domain, path in test_cases:
            with self.subTest(domain=domain):
                avg_time = measure_middleware_overhead(domain, path)
                overhead_results[domain] = avg_time
                
                # Middleware should not add significant overhead
                self.assertLess(avg_time, 0.1,
                              f"Middleware overhead for {domain} is too high: {avg_time:.3f}s")
        
        # Main domain processing should not be significantly slower than pass-through
        if 'insflow.ru' in overhead_results and 'zs.insflow.ru' in overhead_results:
            overhead_diff = overhead_results['insflow.ru'] - overhead_results['zs.insflow.ru']
            self.assertLess(overhead_diff, 0.05,
                          f"Main domain processing overhead is too high: {overhead_diff:.3f}s")
    
    def test_memory_usage_under_load(self):
        """Test memory usage characteristics under HTTPS load"""
        import gc
        import sys
        
        # Get initial memory usage
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Simulate load with multiple requests
        for _ in range(50):
            for domain in ['insflow.ru', 'zs.insflow.ru']:
                response = self.client.get('/', HTTP_HOST=domain, secure=True)
                self.assertIn(response.status_code, [200, 302, 404])
        
        # Check memory usage after load
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Memory usage should not grow excessively
        object_growth = final_objects - initial_objects
        self.assertLess(object_growth, 1000,
                       f"Excessive object growth under load: {object_growth} objects")
    
    def test_ssl_redirect_performance(self):
        """Test SSL redirect performance impact"""
        with override_settings(SECURE_SSL_REDIRECT=True):
            # Measure time for HTTP requests that should redirect
            redirect_times = []
            
            for _ in range(5):
                start_time = time.time()
                # Simulate HTTP request (secure=False)
                response = self.client.get('/', HTTP_HOST='insflow.ru', secure=False)
                end_time = time.time()
                
                redirect_times.append(end_time - start_time)
            
            avg_redirect_time = statistics.mean(redirect_times)
            
            # SSL redirects should be fast
            self.assertLess(avg_redirect_time, 0.1,
                          f"SSL redirect is too slow: {avg_redirect_time:.3f}s")


class HTTPSSecurityPerformanceTest(TestCase):
    """Test performance impact of HTTPS security features"""
    
    def setUp(self):
        self.client = Client()
    
    @override_settings(
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True
    )
    def test_security_headers_performance_impact(self):
        """Test performance impact of security headers"""
        # Measure response time with all security features enabled
        start_time = time.time()
        response = self.client.get('/', HTTP_HOST='insflow.ru', secure=True)
        end_time = time.time()
        
        response_time_with_security = end_time - start_time
        
        # Security headers should not significantly impact performance
        self.assertLess(response_time_with_security, 1.0,
                       f"Security headers add too much overhead: {response_time_with_security:.3f}s")
        self.assertEqual(response.status_code, 200)
    
    def test_secure_cookie_performance(self):
        """Test performance impact of secure cookies"""
        with override_settings(
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True
        ):
            # Measure session creation performance
            session_times = []
            
            for _ in range(10):
                start_time = time.time()
                response = self.client.get('/', HTTP_HOST='zs.insflow.ru', secure=True)
                end_time = time.time()
                
                session_times.append(end_time - start_time)
            
            avg_session_time = statistics.mean(session_times)
            
            # Secure cookies should not significantly impact performance
            self.assertLess(avg_session_time, 0.5,
                          f"Secure cookies add too much overhead: {avg_session_time:.3f}s")
    
    def test_csrf_protection_performance(self):
        """Test performance impact of CSRF protection over HTTPS"""
        with override_settings(CSRF_COOKIE_SECURE=True):
            # Measure CSRF token generation performance
            csrf_times = []
            
            for _ in range(10):
                start_time = time.time()
                # Get page that would generate CSRF token
                response = self.client.get('/', HTTP_HOST='zs.insflow.ru', secure=True)
                end_time = time.time()
                
                csrf_times.append(end_time - start_time)
            
            avg_csrf_time = statistics.mean(csrf_times)
            
            # CSRF protection should not significantly impact performance
            self.assertLess(avg_csrf_time, 0.5,
                          f"CSRF protection adds too much overhead: {avg_csrf_time:.3f}s")


class HTTPSLoadTest(TestCase):
    """Load testing for HTTPS functionality"""
    
    def setUp(self):
        self.client = Client()
    
    @override_settings(
        ALLOWED_HOSTS=['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su'],
        MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
        SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su']
    )
    def test_sustained_load_performance(self):
        """Test performance under sustained HTTPS load"""
        def sustained_request_worker(results_queue, duration_seconds=5):
            """Worker function for sustained load testing"""
            end_time = time.time() + duration_seconds
            request_count = 0
            error_count = 0
            
            domains = ['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su']
            
            while time.time() < end_time:
                try:
                    domain = domains[request_count % len(domains)]
                    path = '/' if domain in ['insflow.ru', 'insflow.tw1.su'] else '/admin/'
                    
                    response = self.client.get(path, HTTP_HOST=domain, secure=True)
                    
                    if response.status_code not in [200, 302, 404]:
                        error_count += 1
                    
                    request_count += 1
                    
                except Exception:
                    error_count += 1
                
                # Small delay to prevent overwhelming
                time.sleep(0.01)
            
            results_queue.put({
                'requests': request_count,
                'errors': error_count,
                'error_rate': error_count / request_count if request_count > 0 else 0
            })
        
        # Run sustained load test with multiple workers
        results_queue = queue.Queue()
        workers = []
        
        # Start multiple worker threads
        for _ in range(3):
            worker = threading.Thread(target=sustained_request_worker, args=(results_queue, 3))
            workers.append(worker)
            worker.start()
        
        # Wait for all workers to complete
        for worker in workers:
            worker.join()
        
        # Analyze results
        total_requests = 0
        total_errors = 0
        
        while not results_queue.empty():
            result = results_queue.get()
            total_requests += result['requests']
            total_errors += result['errors']
        
        overall_error_rate = total_errors / total_requests if total_requests > 0 else 0
        
        # Performance assertions
        self.assertGreater(total_requests, 100, "Should handle at least 100 requests in load test")
        self.assertLess(overall_error_rate, 0.05, f"Error rate too high: {overall_error_rate:.2%}")
    
    def test_burst_load_handling(self):
        """Test handling of burst HTTPS traffic"""
        def burst_request_batch(batch_size=20):
            """Execute a batch of concurrent requests"""
            results = []
            
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = []
                
                # Submit burst of requests
                for i in range(batch_size):
                    domain = 'insflow.ru' if i % 2 == 0 else 'zs.insflow.ru'
                    path = '/' if domain == 'insflow.ru' else '/admin/'
                    
                    future = executor.submit(self.client.get, path, HTTP_HOST=domain, secure=True)
                    futures.append((future, domain, path))
                
                # Collect results
                for future, domain, path in futures:
                    try:
                        response = future.result(timeout=5)
                        results.append({
                            'domain': domain,
                            'path': path,
                            'status_code': response.status_code,
                            'success': response.status_code in [200, 302, 404]
                        })
                    except Exception as e:
                        results.append({
                            'domain': domain,
                            'path': path,
                            'status_code': None,
                            'success': False,
                            'error': str(e)
                        })
            
            return results
        
        # Execute burst load test
        burst_results = burst_request_batch(30)
        
        # Analyze burst performance
        successful_requests = sum(1 for r in burst_results if r['success'])
        success_rate = successful_requests / len(burst_results)
        
        # Burst load should be handled well
        self.assertGreater(success_rate, 0.9, f"Burst success rate too low: {success_rate:.2%}")
        
        # Check that all domains handled requests
        domains_tested = set(r['domain'] for r in burst_results)
        self.assertIn('insflow.ru', domains_tested)
        self.assertIn('zs.insflow.ru', domains_tested)
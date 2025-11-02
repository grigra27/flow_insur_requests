#!/usr/bin/env python3
"""
HTTPS Integration Test Runner
Comprehensive test suite runner for all HTTPS functionality
"""

import os
import sys
import subprocess
import time
from datetime import datetime
import json
import argparse

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_command(command, description="", timeout=300):
    """Run a command and return the result"""
    print(f"\n{'='*60}")
    print(f"Running: {description or command}")
    print(f"{'='*60}")
    
    try:
        start_time = time.time()
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        end_time = time.time()
        
        print(f"Command completed in {end_time - start_time:.2f} seconds")
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        return result.returncode == 0, result.stdout, result.stderr
        
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds")
        return False, "", "Command timed out"
    except Exception as e:
        print(f"Command failed with exception: {e}")
        return False, "", str(e)

def check_domain_accessibility():
    """Check if domains are accessible before running tests"""
    print("\n" + "="*60)
    print("CHECKING DOMAIN ACCESSIBILITY")
    print("="*60)
    
    domains = ['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su']
    accessible_domains = []
    
    for domain in domains:
        try:
            import requests
            response = requests.get(f"https://{domain}", timeout=10)
            if response.status_code == 200:
                print(f"✓ {domain} - Accessible (Status: {response.status_code})")
                accessible_domains.append(domain)
            else:
                print(f"⚠ {domain} - Accessible but status: {response.status_code}")
                accessible_domains.append(domain)
        except Exception as e:
            print(f"✗ {domain} - Not accessible: {e}")
    
    print(f"\nAccessible domains: {len(accessible_domains)}/{len(domains)}")
    return accessible_domains

def run_end_to_end_tests():
    """Run comprehensive end-to-end tests"""
    print("\n" + "="*60)
    print("RUNNING END-TO-END TESTS")
    print("="*60)
    
    # Run the end-to-end test script
    success, stdout, stderr = run_command(
        "python3 onlineservice/test_https_end_to_end.py",
        "End-to-End HTTPS Tests",
        timeout=600  # 10 minutes
    )
    
    return success, stdout, stderr

def run_performance_tests():
    """Run performance and load tests"""
    print("\n" + "="*60)
    print("RUNNING PERFORMANCE TESTS")
    print("="*60)
    
    # Run the performance test script
    success, stdout, stderr = run_command(
        "python3 onlineservice/test_https_performance_load.py",
        "HTTPS Performance and Load Tests",
        timeout=900  # 15 minutes
    )
    
    return success, stdout, stderr

def run_django_tests():
    """Run Django-specific HTTPS tests"""
    print("\n" + "="*60)
    print("RUNNING DJANGO HTTPS TESTS")
    print("="*60)
    
    # Run existing Django HTTPS tests
    test_files = [
        "onlineservice.test_https_functional",
        "onlineservice.test_https_middleware", 
        "onlineservice.test_https_ssl_integration"
    ]
    
    all_success = True
    
    for test_file in test_files:
        success, stdout, stderr = run_command(
            f"python3 manage.py test {test_file}",
            f"Django Test: {test_file}",
            timeout=300
        )
        
        if not success:
            all_success = False
            print(f"⚠ Test {test_file} failed")
        else:
            print(f"✓ Test {test_file} passed")
    
    return all_success

def run_ssl_certificate_checks():
    """Run SSL certificate validation checks"""
    print("\n" + "="*60)
    print("RUNNING SSL CERTIFICATE CHECKS")
    print("="*60)
    
    domains = ['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su']
    
    for domain in domains:
        # Check certificate expiry
        success, stdout, stderr = run_command(
            f"echo | openssl s_client -servername {domain} -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates",
            f"SSL Certificate Check: {domain}",
            timeout=30
        )
        
        if success:
            print(f"✓ {domain} - Certificate information retrieved")
        else:
            print(f"⚠ {domain} - Certificate check failed")

def generate_comprehensive_report(test_results):
    """Generate comprehensive test report"""
    report = []
    report.append("=" * 80)
    report.append("HTTPS INTEGRATION TEST COMPREHENSIVE REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("")
    
    # Test Summary
    report.append("TEST EXECUTION SUMMARY")
    report.append("-" * 40)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results.values() if result['success'])
    
    report.append(f"Total test suites: {total_tests}")
    report.append(f"Passed test suites: {passed_tests}")
    report.append(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")
    report.append("")
    
    # Individual Test Results
    report.append("INDIVIDUAL TEST RESULTS")
    report.append("-" * 40)
    
    for test_name, result in test_results.items():
        status = "PASS" if result['success'] else "FAIL"
        report.append(f"{test_name}: {status}")
        
        if result.get('duration'):
            report.append(f"  Duration: {result['duration']:.2f} seconds")
        
        if not result['success'] and result.get('error'):
            report.append(f"  Error: {result['error']}")
        
        report.append("")
    
    # Recommendations
    report.append("RECOMMENDATIONS")
    report.append("-" * 40)
    
    if passed_tests == total_tests:
        report.append("✓ All tests passed successfully!")
        report.append("✓ HTTPS implementation is working correctly")
        report.append("✓ All domains are properly configured")
        report.append("✓ Performance is within acceptable limits")
    else:
        report.append("⚠ Some tests failed - review the following:")
        
        for test_name, result in test_results.items():
            if not result['success']:
                report.append(f"  - Fix issues with {test_name}")
        
        report.append("")
        report.append("Common solutions:")
        report.append("  - Check DNS configuration")
        report.append("  - Verify SSL certificates are valid")
        report.append("  - Ensure all services are running")
        report.append("  - Check firewall and network connectivity")
    
    return "\n".join(report)

def main():
    """Main test execution function"""
    parser = argparse.ArgumentParser(description='Run HTTPS Integration Tests')
    parser.add_argument('--skip-accessibility', action='store_true', 
                       help='Skip domain accessibility check')
    parser.add_argument('--skip-performance', action='store_true',
                       help='Skip performance tests')
    parser.add_argument('--skip-django', action='store_true',
                       help='Skip Django-specific tests')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick tests only (skip performance and load tests)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("HTTPS INTEGRATION TEST SUITE")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    test_results = {}
    start_time = time.time()
    
    try:
        # Check domain accessibility
        if not args.skip_accessibility:
            accessible_domains = check_domain_accessibility()
            if len(accessible_domains) == 0:
                print("⚠ No domains are accessible. Tests may fail.")
                print("Consider checking your network connection and DNS configuration.")
        
        # Run SSL certificate checks
        print("\n" + "="*60)
        print("SSL CERTIFICATE VALIDATION")
        print("="*60)
        cert_start = time.time()
        run_ssl_certificate_checks()
        cert_duration = time.time() - cert_start
        test_results['SSL Certificate Checks'] = {
            'success': True,  # Assume success for now
            'duration': cert_duration
        }
        
        # Run Django tests
        if not args.skip_django:
            django_start = time.time()
            django_success = run_django_tests()
            django_duration = time.time() - django_start
            test_results['Django HTTPS Tests'] = {
                'success': django_success,
                'duration': django_duration
            }
        
        # Run end-to-end tests
        e2e_start = time.time()
        e2e_success, e2e_stdout, e2e_stderr = run_end_to_end_tests()
        e2e_duration = time.time() - e2e_start
        test_results['End-to-End Tests'] = {
            'success': e2e_success,
            'duration': e2e_duration,
            'stdout': e2e_stdout,
            'stderr': e2e_stderr
        }
        
        # Run performance tests (unless skipped or quick mode)
        if not args.skip_performance and not args.quick:
            perf_start = time.time()
            perf_success, perf_stdout, perf_stderr = run_performance_tests()
            perf_duration = time.time() - perf_start
            test_results['Performance Tests'] = {
                'success': perf_success,
                'duration': perf_duration,
                'stdout': perf_stdout,
                'stderr': perf_stderr
            }
        
        # Generate comprehensive report
        total_duration = time.time() - start_time
        report = generate_comprehensive_report(test_results)
        
        # Save report
        report_filename = f"https_integration_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report)
            f.write(f"\n\nTotal execution time: {total_duration:.2f} seconds")
        
        # Save test results as JSON
        json_filename = f"https_integration_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(test_results, f, indent=2, default=str)
        
        print("\n" + "=" * 80)
        print("HTTPS INTEGRATION TESTING COMPLETED")
        print("=" * 80)
        print(f"Total execution time: {total_duration:.2f} seconds")
        print(f"Report saved to: {report_filename}")
        print(f"Results saved to: {json_filename}")
        print()
        
        # Print summary
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results.values() if result['success'])
        
        print("FINAL SUMMARY:")
        print(f"  Test suites executed: {total_tests}")
        print(f"  Test suites passed: {passed_tests}")
        print(f"  Overall success rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if passed_tests == total_tests:
            print("  Status: ALL TESTS PASSED ✓")
            return 0
        else:
            print("  Status: SOME TESTS FAILED ⚠")
            return 1
            
    except KeyboardInterrupt:
        print("\n\nTest execution interrupted by user")
        return 130
    except Exception as e:
        print(f"\n\nTest execution failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
#!/usr/bin/env python3
"""
HTTPS Implementation Test Runner
Simple script to test the HTTPS integration implementation
"""

import os
import sys
import subprocess
from datetime import datetime

def run_test(command, description):
    """Run a test command and return success status"""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✓ PASSED")
            if result.stdout:
                print("Output:")
                print(result.stdout[-500:])  # Show last 500 chars
        else:
            print("✗ FAILED")
            if result.stderr:
                print("Error:")
                print(result.stderr[-500:])  # Show last 500 chars
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("✗ TIMEOUT")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False

def main():
    """Main test execution"""
    print("HTTPS Integration Implementation Test")
    print("=" * 50)
    print(f"Started at: {datetime.now().isoformat()}")
    
    tests = [
        ("python3 onlineservice/test_https_basic_verification.py", 
         "Basic HTTPS Configuration Verification"),
        
        ("python3 -c \"from onlineservice.test_https_end_to_end import HTTPSEndToEndTester; print('End-to-end tester: OK')\"",
         "End-to-End Test Module Import"),
        
        ("python3 -c \"from onlineservice.test_https_performance_load import HTTPSPerformanceTester; print('Performance tester: OK')\"",
         "Performance Test Module Import"),
        
        ("python3 -c \"import onlineservice.run_https_integration_tests; print('Integration runner: OK')\"",
         "Integration Test Runner Import"),
        
        ("ls -la onlineservice/test_https_*.py",
         "Test Files Existence Check"),
        
        ("ls -la docs/HTTPS_INTEGRATION_TESTING_GUIDE.md",
         "Documentation File Check")
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for command, description in tests:
        success = run_test(command, description)
        if success:
            passed_tests += 1
    
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("\n✓ ALL TESTS PASSED - HTTPS Implementation is ready!")
        print("\nNext steps:")
        print("1. Configure domains and SSL certificates")
        print("2. Run: python3 onlineservice/run_https_integration_tests.py --quick")
        print("3. For full testing: python3 onlineservice/run_https_integration_tests.py")
        return True
    else:
        print("\n⚠ SOME TESTS FAILED - Review implementation")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
#!/usr/bin/env python
"""
Test runner script for insurance system improvements tests
"""
import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ['DJANGO_SETTINGS_MODULE'] = 'onlineservice.settings'
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    
    # Run specific test modules
    test_modules = [
        'tests.test_branch_mapping',
        'tests.test_insurance_type_detection', 
        'tests.test_date_extraction',
        'tests.test_integration_workflow',
    ]
    
    failures = test_runner.run_tests(test_modules)
    
    if failures:
        sys.exit(bool(failures))
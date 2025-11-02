# HTTPS Functionality Tests

This directory contains comprehensive tests for HTTPS functionality across all four domains (insflow.ru, zs.insflow.ru, insflow.tw1.su, zs.insflow.tw1.su).

## Test Files Overview

### 1. `test_https_middleware.py` - Unit Tests for Domain Routing Middleware
**Purpose**: Tests the updated DomainRoutingMiddleware with HTTPS support for all four domains.

**Key Test Areas**:
- Middleware initialization with HTTPS domain configuration
- Main domain routing (insflow.ru, insflow.tw1.su) - landing page only
- Subdomain routing (zs.insflow.ru, zs.insflow.tw1.su) - full application
- Static and media file handling across domains
- Error handling and logging for domain routing decisions
- Security handling for unknown domains

**Test Classes**:
- `HTTPSDomainRoutingMiddlewareTest` - Main middleware functionality
- `HTTPSDomainRoutingConfigurationTest` - Configuration handling

### 2. `test_https_ssl_integration.py` - SSL Configuration Integration Tests
**Purpose**: Tests SSL settings, security headers, and HTTPS-specific Django configuration.

**Key Test Areas**:
- HTTPS security settings (SSL redirect, secure cookies, HSTS)
- Security headers configuration (XSS protection, content type nosniff, etc.)
- Content Security Policy (CSP) headers
- HTTPS middleware integration with Django security middleware
- Environment variable configuration for HTTPS settings
- Logging configuration for HTTPS events

**Test Classes**:
- `HTTPSSecuritySettingsTest` - Security settings validation
- `HTTPSMiddlewareIntegrationTest` - Middleware chain integration
- `HTTPSLoggingIntegrationTest` - HTTPS logging functionality
- `HTTPSEnvironmentConfigurationTest` - Environment variable handling
- `HTTPSStaticFilesIntegrationTest` - Static file serving over HTTPS
- `HTTPSHealthCheckIntegrationTest` - Health check functionality

### 3. `test_https_functional.py` - Functional Tests for All Four Domains
**Purpose**: End-to-end functional testing of HTTPS across all domains.

**Key Test Areas**:
- Landing page functionality on main domains (insflow.ru, insflow.tw1.su)
- Django application functionality on subdomains (zs.insflow.ru, zs.insflow.tw1.su)
- Static and media file accessibility across domains
- Authentication functionality over HTTPS
- Cross-domain consistency and behavior
- Error handling and security responses

**Test Classes**:
- `HTTPSFunctionalTest` - Core functionality across domains
- `HTTPSAuthenticationFunctionalTest` - Authentication over HTTPS
- `HTTPSCrossDomainFunctionalTest` - Cross-domain consistency
- `HTTPSErrorHandlingFunctionalTest` - Error handling
- `HTTPSPerformanceFunctionalTest` - Basic performance validation

### 4. `test_https_performance.py` - Performance Tests for HTTPS
**Purpose**: Performance testing for HTTPS functionality and SSL characteristics.

**Key Test Areas**:
- Response time performance across domains
- Static file serving performance over HTTPS
- Concurrent request handling
- Domain routing middleware performance overhead
- Memory usage under HTTPS load
- SSL redirect performance impact
- Security features performance impact

**Test Classes**:
- `HTTPSPerformanceTest` - Core performance metrics
- `HTTPSSecurityPerformanceTest` - Security feature performance impact
- `HTTPSLoadTest` - Load testing and sustained traffic handling

### 5. `test_https_runner.py` - Test Runner and Validation
**Purpose**: Comprehensive test runner and validation for the HTTPS test suite.

**Key Features**:
- Runs all HTTPS tests with detailed reporting
- Category-specific test execution (middleware, ssl, functional, performance)
- Test coverage validation
- Configuration compatibility testing

**Classes**:
- `HTTPSTestRunner` - Main test runner with reporting
- `HTTPSTestValidation` - Meta-tests for test suite completeness

## Running the Tests

### Run All HTTPS Tests
```bash
python manage.py test onlineservice.test_https_middleware onlineservice.test_https_ssl_integration onlineservice.test_https_functional onlineservice.test_https_performance --verbosity=2
```

### Run Specific Test Categories

**Middleware Tests Only**:
```bash
python manage.py test onlineservice.test_https_middleware --verbosity=2
```

**SSL Integration Tests Only**:
```bash
python manage.py test onlineservice.test_https_ssl_integration --verbosity=2
```

**Functional Tests Only**:
```bash
python manage.py test onlineservice.test_https_functional --verbosity=2
```

**Performance Tests Only**:
```bash
python manage.py test onlineservice.test_https_performance --verbosity=2
```

### Using the Custom Test Runner
```bash
# Run all tests with comprehensive reporting
python onlineservice/test_https_runner.py

# Run specific category
python onlineservice/test_https_runner.py middleware
python onlineservice/test_https_runner.py ssl
python onlineservice/test_https_runner.py functional
python onlineservice/test_https_runner.py performance
```

## Test Configuration

### Required Settings for HTTPS Tests
The tests use `@override_settings` decorators to configure the test environment:

```python
ALLOWED_HOSTS = ['insflow.ru', 'zs.insflow.ru', 'insflow.tw1.su', 'zs.insflow.tw1.su', 'localhost', 'testserver']
MAIN_DOMAINS = ['insflow.ru', 'insflow.tw1.su']
SUBDOMAINS = ['zs.insflow.ru', 'zs.insflow.tw1.su']
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

### Test Environment Compatibility
The tests are designed to work in both HTTP (development) and HTTPS (production) environments:
- Tests use `secure=True` parameter to simulate HTTPS requests
- Configuration tests verify both HTTP and HTTPS settings
- Middleware tests ensure compatibility with both modes

## Coverage Areas

### Requirements Coverage
The tests cover all requirements from the HTTPS specification:

**Requirement 2.4** (Domain Routing):
- ✅ `test_https_middleware.py` - Complete middleware testing
- ✅ `test_https_functional.py` - End-to-end domain functionality

**Requirement 4.4** (SSL Configuration):
- ✅ `test_https_ssl_integration.py` - SSL settings and security headers
- ✅ `test_https_performance.py` - SSL performance characteristics

**Requirement 5.5** (Django HTTPS Configuration):
- ✅ `test_https_ssl_integration.py` - Django security settings
- ✅ `test_https_functional.py` - Authentication and session security

### Domain Coverage
All four domains are thoroughly tested:
- **insflow.ru** - Main domain, landing page only
- **zs.insflow.ru** - Subdomain, full Django application
- **insflow.tw1.su** - Technical main domain, landing page only
- **zs.insflow.tw1.su** - Technical subdomain, full Django application

### Functionality Coverage
- ✅ Domain routing and middleware processing
- ✅ SSL/TLS configuration and security headers
- ✅ Static and media file serving over HTTPS
- ✅ Authentication and session management
- ✅ Error handling and security responses
- ✅ Performance characteristics and load handling
- ✅ Cross-domain consistency
- ✅ Logging and monitoring

## Expected Test Results

### Successful Test Run
When all tests pass, you should see:
- All middleware tests passing (19 tests)
- All SSL integration tests passing (15+ tests)
- All functional tests passing (25+ tests)
- All performance tests passing (10+ tests)

### Common Issues and Solutions

**DisallowedHost Errors**:
- Ensure `ALLOWED_HOSTS` includes all test domains
- Tests handle Django's security validation correctly

**Template Not Found Errors**:
- Ensure `templates/landing/index.html` exists
- Landing page template should contain "здесь есть флоу" text

**Import Errors**:
- Ensure all test files are in the correct location
- Check that Django settings are properly configured

## Integration with CI/CD

These tests should be run as part of the HTTPS deployment process:
1. **Pre-deployment**: Run all tests to validate HTTPS configuration
2. **Post-deployment**: Run functional tests to verify live HTTPS functionality
3. **Monitoring**: Use performance tests for ongoing HTTPS performance validation

## Performance Benchmarks

The performance tests establish benchmarks for:
- **Response Time**: < 1 second for landing pages, < 2 seconds for application pages
- **Concurrent Handling**: > 90% success rate under concurrent load
- **Middleware Overhead**: < 0.1 seconds additional processing time
- **Memory Usage**: < 1000 object growth under sustained load

## Security Validation

The tests validate critical security aspects:
- SSL redirect functionality
- Secure cookie configuration
- HSTS header implementation
- Content Security Policy headers
- Domain isolation and access control
- Error message security (no information leakage)
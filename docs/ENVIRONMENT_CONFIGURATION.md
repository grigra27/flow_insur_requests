# Environment Configuration for HTTPS Production

This document describes the environment configuration setup for HTTPS production deployment of the insurance request system.

## Overview

The environment configuration has been updated to properly support HTTPS in production with comprehensive security settings, proper cookie configuration, and optimized performance settings.

## Configuration Files

### .env File Structure

The `.env` file contains all environment-specific configuration:

```bash
# Django настройки
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-server-ip,your-domain.com,www.your-domain.com

# HTTPS настройки - Enable only in production with valid SSL certificate
CSRF_COOKIE_SECURE=True
SESSION_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com,https://your-server-ip

# Additional security settings for HTTPS
SECURE_CONTENT_SECURITY_POLICY=default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none';
SECURE_REFERRER_POLICY=strict-origin-when-cross-origin
SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin

# Database, Email, Redis, Docker settings...
```

## Key Configuration Changes

### 1. HTTPS Security Settings

#### SSL Redirect
- `SECURE_SSL_REDIRECT=True`: Forces all HTTP requests to redirect to HTTPS
- Only enabled in production to avoid issues during development

#### Cookie Security
- `CSRF_COOKIE_SECURE=True`: CSRF cookies only sent over HTTPS
- `SESSION_COOKIE_SECURE=True`: Session cookies only sent over HTTPS
- Both settings prevent cookie interception over insecure connections

#### HSTS (HTTP Strict Transport Security)
- `SECURE_HSTS_SECONDS=31536000`: 1 year HSTS policy
- `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`: Apply HSTS to all subdomains
- `SECURE_HSTS_PRELOAD=True`: Enable HSTS preload list inclusion

### 2. CSRF Protection

#### Trusted Origins
- `CSRF_TRUSTED_ORIGINS`: List of HTTPS origins allowed for CSRF-protected requests
- Must include all domains where the application will be accessed
- All origins must use HTTPS protocol

Example:
```bash
CSRF_TRUSTED_ORIGINS=https://onbr.site,https://www.onbr.site,https://64.227.75.233
```

### 3. Additional Security Headers

#### Content Security Policy (CSP)
- `SECURE_CONTENT_SECURITY_POLICY`: Defines allowed content sources
- Helps prevent XSS attacks by controlling resource loading
- Current policy allows self-hosted resources and necessary inline scripts/styles

#### Referrer Policy
- `SECURE_REFERRER_POLICY=strict-origin-when-cross-origin`: Controls referrer information
- Provides privacy protection while maintaining functionality

#### Cross-Origin Opener Policy
- `SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin`: Prevents cross-origin access to window objects
- Enhances security for popup windows and cross-origin interactions

### 4. Production Settings

#### Debug Mode
- `DEBUG=False`: Disables debug mode in production
- Prevents sensitive information exposure in error pages

#### Allowed Hosts
- `ALLOWED_HOSTS`: List of allowed hostnames/IPs
- Must include all domains and IP addresses where the application will be accessed
- Prevents HTTP Host header attacks

## Django Settings Integration

The Django settings file (`onlineservice/settings.py`) properly integrates all environment variables:

```python
# HTTPS settings for production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Cookie security
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)

# HSTS settings
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# Additional security headers
SECURE_CONTENT_SECURITY_POLICY = config('SECURE_CONTENT_SECURITY_POLICY', default="...", cast=str)
SECURE_REFERRER_POLICY = config('SECURE_REFERRER_POLICY', default='strict-origin-when-cross-origin', cast=str)
SECURE_CROSS_ORIGIN_OPENER_POLICY = config('SECURE_CROSS_ORIGIN_OPENER_POLICY', default='same-origin', cast=str)

# CSRF settings
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=lambda v: [s.strip() for s in v.split(',')])
```

## Validation and Testing

### Environment Validation Script

Use the `validate_env_config.py` script to validate your environment configuration:

```bash
python validate_env_config.py
```

This script checks:
- ✅ All required environment variables are set
- ✅ HTTPS security settings are properly configured
- ✅ CSRF trusted origins are HTTPS-only
- ✅ Database and email configuration
- ⚠️ Warnings for potential security issues

### Automated Tests

Run the environment configuration tests:

```bash
python -c "
import os, sys, django
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onlineservice.settings')
django.setup()
from tests.test_env_configuration import *
import unittest
unittest.main()
"
```

## Deployment Checklist

Before deploying to production:

1. **Update .env file**:
   - [ ] Set `DEBUG=False`
   - [ ] Configure proper `ALLOWED_HOSTS`
   - [ ] Set secure `SECRET_KEY`
   - [ ] Enable all HTTPS security settings
   - [ ] Configure `CSRF_TRUSTED_ORIGINS` with HTTPS URLs

2. **Validate configuration**:
   - [ ] Run `python validate_env_config.py`
   - [ ] Run environment configuration tests
   - [ ] Verify all security settings are enabled

3. **SSL Certificate**:
   - [ ] Ensure valid SSL certificate is installed
   - [ ] Verify certificate covers all domains in `ALLOWED_HOSTS`
   - [ ] Test HTTPS access to all configured domains

4. **Security Headers**:
   - [ ] Test CSP policy doesn't break functionality
   - [ ] Verify HSTS headers are sent
   - [ ] Check security headers with online tools

## Security Considerations

### Production-Only Settings

These settings should only be enabled in production with valid SSL certificates:
- `SECURE_SSL_REDIRECT=True`
- `CSRF_COOKIE_SECURE=True`
- `SESSION_COOKIE_SECURE=True`
- `SECURE_HSTS_SECONDS > 0`

### Development vs Production

For development:
```bash
DEBUG=True
SECURE_SSL_REDIRECT=False
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0
```

For production:
```bash
DEBUG=False
SECURE_SSL_REDIRECT=True
CSRF_COOKIE_SECURE=True
SESSION_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
```

## Troubleshooting

### Common Issues

1. **CSRF Token Errors**:
   - Verify `CSRF_TRUSTED_ORIGINS` includes all domains
   - Ensure all origins use HTTPS protocol
   - Check that `CSRF_COOKIE_SECURE=True` only in HTTPS environment

2. **SSL Redirect Loops**:
   - Verify nginx is properly configured for SSL termination
   - Check `SECURE_PROXY_SSL_HEADER` setting
   - Ensure `HTTP_X_FORWARDED_PROTO` header is set by proxy

3. **Cookie Issues**:
   - Verify cookies are only secure in HTTPS environment
   - Check browser developer tools for cookie attributes
   - Ensure session cookies are properly configured

### Validation Commands

```bash
# Validate environment configuration
python validate_env_config.py

# Test Django settings loading
python manage.py check --deploy

# Run configuration tests
python -m pytest tests/test_env_configuration.py -v
```

## References

- [Django Security Settings](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Security Headers](https://owasp.org/www-project-secure-headers/)
- [Mozilla Security Guidelines](https://infosec.mozilla.org/guidelines/web_security)
- [HSTS Preload List](https://hstspreload.org/)
# Security Headers and CSP Implementation Guide

This document describes the comprehensive security headers and Content Security Policy (CSP) implementation for the insurance request system.

## Overview

The security implementation includes:
- Content Security Policy (CSP) with nonce support
- HTTP Strict Transport Security (HSTS) with preload
- Comprehensive security headers (X-Frame-Options, X-Content-Type-Options, etc.)
- CORS configuration
- Permissions Policy
- Clear-Site-Data headers for logout

## Features Implemented

### 1. Content Security Policy (CSP)

#### Base CSP Policy
```
default-src 'self'; 
script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; 
style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; 
img-src 'self' data: https: blob:; 
font-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; 
connect-src 'self' https:; 
media-src 'self' data: blob:; 
object-src 'none'; 
base-uri 'self'; 
form-action 'self'; 
frame-ancestors 'none'; 
upgrade-insecure-requests; 
block-all-mixed-content;
```

#### Admin CSP Policy
More permissive policy for Django admin interface:
```
default-src 'self'; 
script-src 'self' 'unsafe-inline' 'unsafe-eval'; 
style-src 'self' 'unsafe-inline'; 
img-src 'self' data: https:; 
font-src 'self' data:; 
connect-src 'self'; 
frame-ancestors 'self'; 
upgrade-insecure-requests;
```

#### CSP Nonce Support
- Automatic nonce generation for each request
- Template tags for easy nonce usage
- Nonce-based inline script/style protection

### 2. HTTP Strict Transport Security (HSTS)

- **Max-Age**: 31536000 seconds (1 year)
- **includeSubDomains**: Enabled
- **preload**: Enabled for HSTS preload list

### 3. Security Headers

| Header | Value | Purpose |
|--------|-------|---------|
| X-Frame-Options | DENY | Prevents clickjacking |
| X-Content-Type-Options | nosniff | Prevents MIME sniffing |
| X-XSS-Protection | 1; mode=block | XSS protection (legacy) |
| Referrer-Policy | strict-origin-when-cross-origin | Controls referrer information |
| Cross-Origin-Opener-Policy | same-origin | Controls cross-origin window access |
| Cross-Origin-Embedder-Policy | (configurable) | Controls cross-origin embedding |
| Cross-Origin-Resource-Policy | (configurable) | Controls cross-origin resource access |

### 4. Permissions Policy

Restricts access to browser features:
```
geolocation=(), microphone=(), camera=(), payment=(), usb=(), 
magnetometer=(), gyroscope=(), accelerometer=(), 
ambient-light-sensor=(), autoplay=(self), encrypted-media=(self), 
fullscreen=(self), picture-in-picture=(), screen-wake-lock=(), 
web-share=(self), clipboard-read=(), clipboard-write=(self)
```

### 5. CORS Configuration

Configurable CORS support with:
- Allowed origins whitelist
- Credential support control
- Method and header restrictions
- Preflight caching

### 6. Clear-Site-Data

Automatically clears browser data on logout pages:
- Cache
- Cookies
- Storage

## Configuration

### Environment Variables

```bash
# HSTS Configuration
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True

# CSP Configuration
SECURE_CONTENT_SECURITY_POLICY="default-src 'self'; ..."
SECURE_CONTENT_SECURITY_POLICY_ADMIN="default-src 'self'; ..."
SECURE_CONTENT_SECURITY_POLICY_REPORT_ONLY=""

# Security Headers
X_FRAME_OPTIONS=DENY
SECURE_REFERRER_POLICY=strict-origin-when-cross-origin
SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin
SECURE_SERVER_HEADER=""

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
CORS_ALLOW_CREDENTIALS=False
CORS_ALLOWED_METHODS=GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS
CORS_ALLOWED_HEADERS=Accept,Content-Type,Authorization,X-CSRFToken
```

### Django Settings

Key settings in `settings.py`:
- `SECURE_SSL_REDIRECT`: Enable HTTPS redirect
- `SECURE_PROXY_SSL_HEADER`: Trust proxy headers
- `CSRF_COOKIE_SECURE`: Secure CSRF cookies
- `SESSION_COOKIE_SECURE`: Secure session cookies

## Template Usage

### Security Meta Tags
```html
{% load security_tags %}
{% security_meta_tags %}
```

### CSP Nonce Usage
```html
{% load security_tags %}

<!-- Inline script with nonce -->
<script nonce="{% csp_nonce %}">
    console.log('Secure inline script');
</script>

<!-- Using template tag -->
{% csp_script_tag "console.log('Hello World');" %}

<!-- Inline style with nonce -->
{% csp_style_tag "body { margin: 0; }" %}
```

### Resource Preloading
```html
{% load security_tags %}
{% preload_resource "/static/js/app.js" "script" %}
```

## Middleware

### HTTPSSecurityMiddleware
- Adds comprehensive security headers
- Handles CSP with nonce support
- Manages CORS headers
- Implements Clear-Site-Data

### CSPNonceMiddleware
- Generates cryptographically secure nonces
- Makes nonces available to templates
- Logs nonce generation in debug mode

## Validation and Testing

### Management Command
```bash
python manage.py validate_security_headers --verbose
```

### Test Suite
```bash
python manage.py test insurance_requests.test_security_headers
```

### Validation Features
- CSP syntax validation
- Security header testing
- HSTS configuration validation
- CORS configuration checking

## Security Considerations

### CSP Warnings
- `'unsafe-inline'` and `'unsafe-eval'` are used for compatibility
- Consider migrating to nonce-based CSP for better security
- Monitor CSP violations using report-only mode

### HSTS Preload
- Requires HTTPS to be fully functional
- Cannot be easily reverted once submitted to preload list
- Test thoroughly before enabling in production

### CORS Security
- Restrict allowed origins to trusted domains
- Avoid `allow_all_origins=True` in production
- Be cautious with credential support

## Nginx Integration

The nginx configuration complements Django security headers:
- HSTS header at nginx level for immediate protection
- Static file security headers
- Server token removal
- SSL/TLS optimization

## Monitoring

### Security Logs
- Security events logged to `logs/security.log`
- CSP violations can be monitored
- Failed authentication attempts tracked

### Performance Impact
- Minimal overhead from security headers
- CSP nonce generation is lightweight
- Headers cached by browsers

## Best Practices

1. **Regular Updates**: Keep CSP policies updated as requirements change
2. **Testing**: Use CSP report-only mode to test new policies
3. **Monitoring**: Monitor security logs for violations
4. **Documentation**: Keep security configuration documented
5. **Validation**: Regularly run security validation commands

## Troubleshooting

### Common Issues

1. **CSP Violations**: Check browser console for CSP errors
2. **Mixed Content**: Ensure all resources use HTTPS
3. **CORS Errors**: Verify allowed origins configuration
4. **HSTS Issues**: Clear browser HSTS cache if needed

### Debug Mode
- Set `DEBUG=True` for detailed CSP nonce logging
- Use `FORCE_SECURITY_HEADERS=True` to test headers in development
- Monitor `logs/security.log` for security events

## External Resources

- [MDN CSP Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [OWASP Security Headers](https://owasp.org/www-project-secure-headers/)
- [HSTS Preload List](https://hstspreload.org/)
- [CSP Evaluator](https://csp-evaluator.withgoogle.com/)
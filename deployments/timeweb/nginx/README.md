# Unified Nginx Configuration for Timeweb Deployment

This directory contains the unified nginx configuration system that automatically detects SSL certificate availability and configures the server accordingly.

## Configuration Files

### Main Configuration Files

- **`default.conf`** - HTTP-only configuration used when SSL certificates are not available
- **`default-ssl.conf`** - HTTPS-enabled configuration used when SSL certificates are available
- **`default-acme.conf`** - ACME-only configuration used during certificate generation

### Optimization Files

- **`ssl-optimizations.conf`** - Enhanced SSL/TLS security settings and headers
- **`static-optimizations.conf`** - Optimized static file serving with caching and compression

### Legacy Files (for reference)

- **`default-https.conf`** - Original HTTPS configuration (replaced by default-ssl.conf)

## Features

### SSL Detection and Auto-Configuration

The system automatically detects SSL certificate availability and switches between HTTP and HTTPS modes:

- **HTTP Mode**: Used when SSL certificates are not available or invalid
- **HTTPS Mode**: Used when valid SSL certificates are detected
- **ACME Mode**: Special mode for Let's Encrypt certificate generation

### Security Features

#### SSL/TLS Security
- Modern TLS 1.2 and 1.3 protocols only
- Strong cipher suites with perfect forward secrecy
- OCSP stapling for improved performance
- Diffie-Hellman parameters for enhanced security
- Session optimization and security

#### Security Headers
- **HSTS**: HTTP Strict Transport Security with preload
- **CSP**: Content Security Policy for XSS protection
- **X-Frame-Options**: Clickjacking protection
- **X-Content-Type-Options**: MIME type sniffing protection
- **Referrer-Policy**: Referrer information control
- **Permissions-Policy**: Feature policy restrictions
- **Cross-Origin Policies**: CORP, COEP, COOP headers

### Performance Optimizations

#### Static File Serving
- Long-term caching for immutable assets (CSS, JS, images, fonts)
- Proper MIME types and character encoding
- Gzip compression with static pre-compression support
- Vary headers for proper caching behavior
- CORS support for font files

#### Proxy Optimizations
- Enhanced proxy buffering for better performance
- Optimized timeouts and buffer sizes
- HTTP/2 support for HTTPS connections
- Connection keep-alive optimization

## Usage

### Automatic Configuration

Use the configuration management script to automatically detect and configure SSL:

```bash
# Auto-detect SSL and configure nginx
./scripts/configure-nginx.sh auto

# Check SSL certificate status
./scripts/configure-nginx.sh status

# Test current configuration
./scripts/configure-nginx.sh test
```

### Manual Configuration

Force specific modes when needed:

```bash
# Force HTTP-only mode
./scripts/configure-nginx.sh http

# Force HTTPS mode (requires valid certificates)
./scripts/configure-nginx.sh https
```

### SSL Security Setup

Set up additional SSL security features:

```bash
# Full SSL security setup
./scripts/setup-ssl-security.sh setup

# Generate Diffie-Hellman parameters only
./scripts/setup-ssl-security.sh dh

# Check SSL security status
./scripts/setup-ssl-security.sh status
```

## Configuration Details

### Domains Supported

- `insflow.ru` (main domain)
- `zs.insflow.ru` (subdomain)
- `insflow.tw1.su` (technical domain)
- `zs.insflow.tw1.su` (technical subdomain)
- `80.90.189.37` (IP address fallback)

### SSL Certificate Paths

- **insflow.ru**: `/etc/letsencrypt/live/insflow.ru/`
- **insflow.tw1.su**: `/etc/letsencrypt/live/insflow.tw1.su/`

### Health Check Endpoints

- **`/health`**: Basic health check (available on both HTTP and HTTPS)
- **`/.well-known/acme-challenge/`**: Let's Encrypt ACME challenges (HTTP only)

## File Structure

```
deployments/timeweb/nginx/
├── README.md                    # This documentation
├── default.conf                 # HTTP-only configuration
├── default-ssl.conf            # HTTPS-enabled configuration
├── default-acme.conf           # ACME challenge configuration
├── ssl-optimizations.conf      # SSL security settings
├── static-optimizations.conf   # Static file optimizations
└── default-https.conf          # Legacy HTTPS configuration
```

## Deployment Integration

The nginx configuration integrates with the Docker Compose deployment:

1. **Certificate Detection**: Scripts check for valid SSL certificates
2. **Configuration Selection**: Appropriate nginx config is selected
3. **Service Restart**: Nginx is reloaded with new configuration
4. **Health Monitoring**: Endpoints provide status information

## Troubleshooting

### Common Issues

1. **SSL Certificate Not Found**
   - Check certificate paths in `/etc/letsencrypt/live/`
   - Verify certificate validity with `openssl x509 -in cert.pem -noout -dates`
   - Run certificate acquisition process

2. **Nginx Configuration Errors**
   - Test configuration with `nginx -t`
   - Check include file paths are correct
   - Verify SSL optimization files are present

3. **Performance Issues**
   - Check gzip compression is working
   - Verify static file caching headers
   - Monitor proxy buffer usage

### Debug Commands

```bash
# Test nginx configuration
nginx -t

# Check SSL certificate validity
openssl x509 -in /etc/letsencrypt/live/domain/fullchain.pem -noout -dates

# Test SSL configuration
openssl s_client -connect domain:443 -servername domain

# Check nginx status
systemctl status nginx

# View nginx error logs
tail -f /var/log/nginx/error.log
```

## Security Considerations

- All security headers are applied consistently
- SSL/TLS configuration follows current best practices
- Static files are served with appropriate security headers
- ACME challenges are isolated and secure
- Health checks don't expose sensitive information

## Performance Considerations

- Static files use aggressive caching for immutable assets
- Gzip compression reduces bandwidth usage
- HTTP/2 is enabled for HTTPS connections
- Proxy buffering optimizes dynamic content delivery
- OCSP stapling reduces SSL handshake time
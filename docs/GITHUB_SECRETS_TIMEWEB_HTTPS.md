# GitHub Secrets Configuration for Timeweb HTTPS Deployment

This document describes the GitHub Secrets that need to be configured for the Timeweb HTTPS deployment workflow.

## Required Secrets

### Existing Secrets (Updated)

These secrets were already configured but may need updates for HTTPS support:

#### `TIMEWEB_ALLOWED_HOSTS`
**Description**: Comma-separated list of allowed hosts for Django
**New Value**: `insflow.ru,zs.insflow.ru,insflow.tw1.su,zs.insflow.tw1.su,localhost,127.0.0.1`
**Example**: `insflow.ru,zs.insflow.ru,insflow.tw1.su,zs.insflow.tw1.su,localhost,127.0.0.1`

### New Secrets (Required for HTTPS)

#### `TIMEWEB_MAIN_DOMAINS`
**Description**: Comma-separated list of main domains (primary business domains)
**Value**: `insflow.ru,insflow.tw1.su`
**Purpose**: Used for landing page routing and SSL certificate management

#### `TIMEWEB_SUBDOMAINS`
**Description**: Comma-separated list of subdomains (Django application domains)
**Value**: `zs.insflow.ru,zs.insflow.tw1.su`
**Purpose**: Used for Django application routing and SSL certificate management

### Existing Secrets (No Changes Required)

These secrets remain unchanged:

- `TIMEWEB_HOST` - Server IP address
- `TIMEWEB_USERNAME` - SSH username
- `TIMEWEB_SSH_KEY` - SSH private key
- `TIMEWEB_PORT` - SSH port (usually 22)
- `TIMEWEB_SECRET_KEY` - Django secret key
- `TIMEWEB_DB_NAME` - Database name
- `TIMEWEB_DB_USER` - Database username
- `TIMEWEB_DB_PASSWORD` - Database password
- `GITHUB_TOKEN` - Automatically provided by GitHub
- `DOCKERHUB_USERNAME` - Docker Hub username (optional)
- `DOCKERHUB_TOKEN` - Docker Hub token (optional)

## DNS Configuration Requirements

Before the HTTPS deployment can work, the following DNS records must be configured:

### A Records
```
insflow.ru        A    <TIMEWEB_SERVER_IP>
zs.insflow.ru     A    <TIMEWEB_SERVER_IP>
```

### Existing Records (Should Already Exist)
```
insflow.tw1.su    A    <TIMEWEB_SERVER_IP>
zs.insflow.tw1.su A    <TIMEWEB_SERVER_IP>
```

## Deployment Behavior

### HTTPS Mode (Default)
When DNS is properly configured and SSL certificates can be obtained:
- All HTTP traffic is redirected to HTTPS
- SSL certificates are automatically obtained from Let's Encrypt
- Automatic certificate renewal is configured
- All security headers are enabled

### Fallback Mode (HTTP-only)
When DNS is not configured or SSL certificates cannot be obtained:
- System falls back to HTTP-only mode
- No SSL redirects are enforced
- Security headers are disabled for HTTP compatibility
- Deployment continues successfully

## Monitoring and Alerts

The deployment workflow includes:
- SSL certificate status checks
- Automatic fallback to HTTP-only mode if HTTPS fails
- Comprehensive deployment reporting
- Post-deployment verification of all endpoints

## Troubleshooting

### Common Issues

1. **DNS Not Configured**
   - Symptom: Deployment falls back to HTTP-only mode
   - Solution: Configure DNS A records for insflow.ru and zs.insflow.ru

2. **SSL Certificate Generation Fails**
   - Symptom: Deployment continues in fallback mode
   - Solution: Check DNS propagation and Let's Encrypt rate limits

3. **Domain Routing Issues**
   - Symptom: 404 errors on new domains
   - Solution: Verify TIMEWEB_MAIN_DOMAINS and TIMEWEB_SUBDOMAINS secrets

### Manual SSL Certificate Generation

If automatic certificate generation fails, you can manually generate certificates:

```bash
# SSH to the server
ssh -p <TIMEWEB_PORT> <TIMEWEB_USERNAME>@<TIMEWEB_HOST>

# Navigate to project directory
cd /opt/insflow-system

# Run certificate generation script
sudo scripts/ssl/obtain-certificates.sh

# Check certificate status
sudo scripts/ssl/check-certificates.sh

# Restart deployment
docker-compose -f docker-compose.timeweb.yml restart nginx
```

## Security Considerations

### HTTPS Security Headers
When HTTPS is enabled, the following security headers are automatically configured:
- `Strict-Transport-Security` (HSTS)
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`
- `X-XSS-Protection`

### Certificate Management
- Certificates are automatically renewed 30 days before expiration
- Renewal attempts are made daily at 2:00 AM
- Certificate status is checked daily at 6:00 AM
- Comprehensive checks are performed weekly

### Fallback Security
In HTTP-only fallback mode:
- Secure cookie flags are disabled
- HSTS headers are not sent
- SSL redirect is disabled
- System remains functional but less secure

## Migration Path

### Phase 1: DNS Configuration
1. Configure DNS A records for insflow.ru and zs.insflow.ru
2. Wait for DNS propagation (up to 48 hours)
3. Verify DNS resolution from multiple locations

### Phase 2: Secrets Update
1. Update `TIMEWEB_ALLOWED_HOSTS` secret
2. Add `TIMEWEB_MAIN_DOMAINS` secret
3. Add `TIMEWEB_SUBDOMAINS` secret

### Phase 3: Deployment
1. Push changes to main branch
2. Monitor deployment workflow
3. Verify HTTPS functionality
4. Test all domain endpoints

### Phase 4: Verification
1. Test automatic HTTP to HTTPS redirects
2. Verify SSL certificate validity
3. Check security headers
4. Test certificate renewal process

## Support

For issues with the HTTPS deployment:
1. Check the deployment workflow logs in GitHub Actions
2. Review the deployment report generated during deployment
3. Check SSL certificate status using the provided scripts
4. Verify DNS configuration and propagation
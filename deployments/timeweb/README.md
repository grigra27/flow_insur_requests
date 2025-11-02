# Timeweb HTTPS Deployment Guide

This guide provides comprehensive instructions for deploying the Insurance System on Timeweb hosting with HTTPS support using Let's Encrypt SSL certificates.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Detailed Deployment Steps](#detailed-deployment-steps)
5. [Configuration](#configuration)
6. [SSL Certificate Management](#ssl-certificate-management)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)
8. [Troubleshooting](#troubleshooting)
9. [Common Issues](#common-issues)
10. [Advanced Configuration](#advanced-configuration)

## Overview

The Timeweb deployment provides:
- **HTTPS-first deployment** with automatic SSL certificate management
- **Automatic fallback to HTTP** when certificates are not available
- **Multi-domain support** for both main domains and subdomains
- **Automated certificate renewal** via Let's Encrypt
- **Health monitoring** and service validation
- **Clean deployment structure** separated from Digital Ocean configuration

### Supported Domains

- **Main domains**: `insflow.ru`, `insflow.tw1.su`
- **Subdomains**: `zs.insflow.ru`, `zs.insflow.tw1.su`

### Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Nginx       │    │   Django App    │    │   PostgreSQL    │
│   (SSL Proxy)   │────│   (Gunicorn)    │────│   (Database)    │
│   Port 80/443   │    │   Port 8000     │    │   Port 5432     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│    Certbot      │
│ (SSL Renewal)   │
└─────────────────┘
```

## Prerequisites

### Server Requirements

- **OS**: Ubuntu 20.04+ or CentOS 8+
- **RAM**: Minimum 2GB, recommended 4GB+
- **Storage**: Minimum 20GB free space
- **Network**: Public IP address with ports 80 and 443 accessible

### Software Requirements

- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+
- **Git**: For code deployment
- **Curl**: For health checks

### Domain Requirements

- Domains must be pointed to your server's IP address
- DNS propagation must be complete before SSL certificate acquisition
- Firewall must allow HTTP (80) and HTTPS (443) traffic

### Installation Commands

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install Git and Curl
sudo apt install -y git curl

# Logout and login again to apply Docker group membership
```

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system

# Navigate to Timeweb deployment directory
cd deployments/timeweb

# Copy and configure environment
cp .env.example .env
nano .env  # Edit configuration (see Configuration section)
```

### 2. Deploy with Automatic SSL

```bash
# Make deployment script executable
chmod +x scripts/deploy-timeweb.sh

# Deploy with automatic SSL detection
./scripts/deploy-timeweb.sh

# Or deploy with verbose output
./scripts/deploy-timeweb.sh --verbose
```

### 3. Verify Deployment

```bash
# Check service status
docker compose ps

# Check health
./scripts/health-check.sh

# View logs
docker compose logs -f
```

## Detailed Deployment Steps

### Step 1: Environment Configuration

Create and configure the `.env` file:

```bash
cp .env.example .env
```

**Required Configuration:**

```env
# Application Settings
SECRET_KEY=your-very-secure-secret-key-change-this
DEBUG=False
DOCKER_IMAGE=your-registry/insurance-system:latest

# Database Configuration
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure_database_password

# Domain Configuration
DOMAINS=insflow.ru,insflow.tw1.su,zs.insflow.ru,zs.insflow.tw1.su
ALLOWED_HOSTS=insflow.ru,insflow.tw1.su,zs.insflow.ru,zs.insflow.tw1.su

# SSL Configuration
SSL_EMAIL=admin@insflow.ru
CERTBOT_STAGING=false

# HTTPS Security Settings
ENABLE_HTTPS=True
SSL_REDIRECT=True
SECURE_COOKIES=True
HSTS_SECONDS=31536000
```

### Step 2: DNS Configuration

Ensure all domains point to your server:

```bash
# Check DNS resolution
nslookup insflow.ru
nslookup insflow.tw1.su
nslookup zs.insflow.ru
nslookup zs.insflow.tw1.su

# Test connectivity
curl -I http://insflow.ru
curl -I http://insflow.tw1.su
```

### Step 3: Initial Deployment

```bash
# Deploy in HTTP mode first (for certificate acquisition)
./scripts/deploy-timeweb.sh --http-only

# Wait for services to be ready
sleep 30

# Check HTTP accessibility
curl -f http://insflow.ru/healthz/
curl -f http://insflow.tw1.su/healthz/
```

### Step 4: SSL Certificate Acquisition

```bash
# Obtain SSL certificates for all domains
./scripts/obtain-certificates.sh

# Verify certificate acquisition
./scripts/monitor-certificates.sh --check-all

# Deploy with HTTPS enabled
./scripts/deploy-timeweb.sh --force-ssl
```

### Step 5: Final Verification

```bash
# Test HTTPS access
curl -f https://insflow.ru/healthz/
curl -f https://insflow.tw1.su/healthz/

# Test HTTP to HTTPS redirect
curl -I http://insflow.ru/

# Check SSL certificate validity
./scripts/monitor-certificates.sh --verbose
```

## Configuration

### Environment Variables Reference

#### Core Application Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | Django secret key | - | ✅ |
| `DEBUG` | Debug mode | `False` | ✅ |
| `DOCKER_IMAGE` | Docker image to deploy | - | ✅ |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | - | ✅ |

#### Database Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DB_NAME` | Database name | - | ✅ |
| `DB_USER` | Database user | - | ✅ |
| `DB_PASSWORD` | Database password | - | ✅ |

#### SSL/HTTPS Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DOMAINS` | Comma-separated domains for SSL | - | ✅ |
| `SSL_EMAIL` | Email for Let's Encrypt | - | ✅ |
| `CERTBOT_STAGING` | Use staging certificates | `false` | ❌ |
| `ENABLE_HTTPS` | Enable HTTPS features | `True` | ❌ |
| `SSL_REDIRECT` | Redirect HTTP to HTTPS | `True` | ❌ |
| `SECURE_COOKIES` | Use secure cookies | `True` | ❌ |
| `HSTS_SECONDS` | HSTS max age | `31536000` | ❌ |

#### Volume Configuration (Advanced)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SSL_VOLUME_TYPE` | SSL volume type (volume/bind) | `volume` | ❌ |
| `SSL_CERTIFICATES_PATH` | SSL certificates path (for bind) | - | ❌ |
| `ACME_VOLUME_TYPE` | ACME volume type (volume/bind) | `volume` | ❌ |
| `ACME_CHALLENGE_PATH` | ACME challenge path (for bind) | - | ❌ |

### Docker Compose Configuration

The deployment uses a single `docker-compose.yml` file with the following services:

#### Services Overview

- **db**: PostgreSQL database with health checks
- **web**: Django application with Gunicorn
- **nginx**: Reverse proxy with SSL termination
- **certbot**: SSL certificate management (profile: ssl)

#### Volume Management

The system supports both Docker volumes and bind mounts:

**Docker Volumes (Default):**
```yaml
volumes:
  ssl_certificates:
    driver: local
  acme_challenge:
    driver: local
```

**Bind Mounts (Production):**
```env
SSL_VOLUME_TYPE=bind
SSL_CERTIFICATES_PATH=/opt/letsencrypt
ACME_VOLUME_TYPE=bind
ACME_CHALLENGE_PATH=/opt/acme-challenge
```

## SSL Certificate Management

### Automatic Certificate Acquisition

The deployment script automatically handles SSL certificates:

```bash
# Automatic mode (recommended)
./scripts/deploy-timeweb.sh

# Force SSL mode (fail if no certificates)
./scripts/deploy-timeweb.sh --force-ssl

# HTTP only mode (skip SSL)
./scripts/deploy-timeweb.sh --http-only
```

### Manual Certificate Management

#### Obtain Certificates

```bash
# Obtain certificates for all configured domains
./scripts/obtain-certificates.sh

# Obtain certificates with staging (for testing)
./scripts/obtain-certificates.sh --staging

# Force certificate renewal
./scripts/obtain-certificates.sh --force-renewal

# Verbose output
./scripts/obtain-certificates.sh --verbose
```

#### Monitor Certificates

```bash
# Check all certificates
./scripts/monitor-certificates.sh

# Check specific domain
./scripts/monitor-certificates.sh --domain insflow.ru

# Verbose output with expiry details
./scripts/monitor-certificates.sh --verbose

# Check and send alerts
./scripts/monitor-certificates.sh --alert
```

### Certificate Renewal

Automatic renewal is handled by the certbot service:

```bash
# Setup automatic renewal (run once)
./scripts/setup-certificate-renewal.sh

# Manual renewal check
docker compose exec certbot certbot renew --dry-run

# Force renewal
docker compose exec certbot certbot renew --force-renewal
```

### Certificate Troubleshooting

#### Check Certificate Status

```bash
# List all certificates
docker compose exec certbot certbot certificates

# Check certificate details
openssl x509 -in /path/to/cert.pem -text -noout

# Test certificate with OpenSSL
openssl s_client -connect insflow.ru:443 -servername insflow.ru
```

#### Common Certificate Issues

1. **Domain validation failed**
   ```bash
   # Check DNS resolution
   nslookup insflow.ru
   
   # Check HTTP accessibility
   curl -I http://insflow.ru/.well-known/acme-challenge/test
   ```

2. **Rate limiting**
   ```bash
   # Use staging environment for testing
   ./scripts/obtain-certificates.sh --staging
   ```

3. **Certificate expired**
   ```bash
   # Force renewal
   ./scripts/obtain-certificates.sh --force-renewal
   ```

## Monitoring and Maintenance

### Health Monitoring

#### Automated Health Checks

```bash
# Run comprehensive health check
./scripts/health-check.sh

# Health check with detailed output
./scripts/health-check.sh --verbose

# Health check for specific service
./scripts/health-check.sh --service web
```

#### Manual Health Verification

```bash
# Check service status
docker compose ps

# Check service health
docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"

# Test HTTP endpoints
curl -f http://insflow.ru/healthz/
curl -f https://insflow.ru/healthz/

# Check database connectivity
docker compose exec web python manage.py dbshell -c "SELECT 1;"
```

### System Monitoring

#### Resource Monitoring

```bash
# Monitor system resources
./scripts/system-monitor.sh

# Monitor Docker resources
docker stats

# Monitor disk usage
df -h
docker system df
```

#### Log Management

```bash
# View application logs
docker compose logs -f web

# View nginx logs
docker compose logs -f nginx

# View certificate logs
docker compose logs -f certbot

# View all logs
docker compose logs -f

# View logs with timestamps
docker compose logs -f -t
```

### Maintenance Tasks

#### Regular Maintenance

```bash
# Update Docker images
docker compose pull
docker compose up -d

# Clean up unused Docker resources
docker system prune -f

# Backup database
docker compose exec web python manage.py dumpdata > backup_$(date +%Y%m%d).json

# Update application code
git pull origin main
docker compose up -d --build
```

#### Database Maintenance

```bash
# Run database migrations
docker compose exec web python manage.py migrate

# Collect static files
docker compose exec web python manage.py collectstatic --noinput

# Create superuser
docker compose exec web python manage.py createsuperuser

# Database shell access
docker compose exec web python manage.py dbshell
```

## Troubleshooting

### Common Deployment Issues

#### 1. Services Won't Start

**Symptoms:**
- Services exit immediately
- Health checks fail
- Cannot connect to application

**Diagnosis:**
```bash
# Check service status
docker compose ps

# Check service logs
docker compose logs web
docker compose logs nginx
docker compose logs db

# Check configuration
docker compose config
```

**Solutions:**
```bash
# Restart services
docker compose restart

# Rebuild and restart
docker compose up -d --build

# Check environment variables
docker compose exec web env | grep -E "(SECRET_KEY|DB_|ALLOWED_HOSTS)"
```

#### 2. SSL Certificate Issues

**Symptoms:**
- HTTPS not working
- Certificate errors in browser
- Certificate acquisition fails

**Diagnosis:**
```bash
# Check certificate status
./scripts/monitor-certificates.sh --verbose

# Check DNS resolution
nslookup insflow.ru

# Check HTTP accessibility for ACME challenge
curl -I http://insflow.ru/.well-known/acme-challenge/
```

**Solutions:**
```bash
# Retry certificate acquisition
./scripts/obtain-certificates.sh --force-renewal

# Use staging certificates for testing
./scripts/obtain-certificates.sh --staging

# Check domain configuration
echo $DOMAINS
```

#### 3. Database Connection Issues

**Symptoms:**
- Application cannot connect to database
- Database health checks fail
- Migration errors

**Diagnosis:**
```bash
# Check database service
docker compose logs db

# Test database connection
docker compose exec web python manage.py dbshell

# Check database configuration
docker compose exec web env | grep DB_
```

**Solutions:**
```bash
# Restart database service
docker compose restart db

# Check database credentials
docker compose exec db psql -U $DB_USER -d $DB_NAME -c "SELECT 1;"

# Reset database (WARNING: destroys data)
docker compose down -v
docker compose up -d
```

#### 4. Nginx Configuration Issues

**Symptoms:**
- 502 Bad Gateway errors
- Static files not loading
- SSL configuration errors

**Diagnosis:**
```bash
# Check nginx configuration
docker compose exec nginx nginx -t

# Check nginx logs
docker compose logs nginx

# Test upstream connection
docker compose exec nginx curl -I http://web:8000/healthz/
```

**Solutions:**
```bash
# Reload nginx configuration
docker compose exec nginx nginx -s reload

# Restart nginx service
docker compose restart nginx

# Check SSL certificate paths
docker compose exec nginx ls -la /etc/letsencrypt/live/
```

### Performance Issues

#### High Resource Usage

**Diagnosis:**
```bash
# Monitor resource usage
docker stats

# Check system resources
./scripts/system-monitor.sh

# Check application performance
docker compose exec web python manage.py check --deploy
```

**Solutions:**
```bash
# Optimize Docker resources
docker system prune -f

# Restart services to clear memory
docker compose restart

# Scale services if needed (advanced)
docker compose up -d --scale web=2
```

#### Slow Response Times

**Diagnosis:**
```bash
# Test response times
curl -w "@curl-format.txt" -o /dev/null -s https://insflow.ru/

# Check database performance
docker compose exec web python manage.py dbshell -c "EXPLAIN ANALYZE SELECT * FROM insurance_requests_insurancerequest LIMIT 10;"
```

**Solutions:**
```bash
# Optimize database
docker compose exec web python manage.py migrate

# Clear application cache
docker compose exec web python manage.py shell -c "from django.core.cache import cache; cache.clear()"

# Restart services
docker compose restart
```

## Common Issues

### Issue 1: Certificate Acquisition Fails

**Problem:** Let's Encrypt certificate acquisition fails with domain validation error.

**Cause:** Domain not properly configured or not accessible via HTTP.

**Solution:**
```bash
# 1. Verify DNS configuration
nslookup insflow.ru

# 2. Test HTTP accessibility
curl -I http://insflow.ru/

# 3. Check nginx configuration
docker compose exec nginx nginx -t

# 4. Retry with staging certificates
./scripts/obtain-certificates.sh --staging

# 5. Check ACME challenge directory
docker compose exec nginx ls -la /var/www/certbot/
```

### Issue 2: HTTP to HTTPS Redirect Loop

**Problem:** Infinite redirect loop between HTTP and HTTPS.

**Cause:** Incorrect nginx configuration or missing SSL certificates.

**Solution:**
```bash
# 1. Check SSL certificate availability
./scripts/monitor-certificates.sh

# 2. Verify nginx configuration
docker compose exec nginx nginx -t

# 3. Check SSL redirect settings
docker compose exec web env | grep SSL_REDIRECT

# 4. Restart nginx
docker compose restart nginx
```

### Issue 3: Database Connection Refused

**Problem:** Django application cannot connect to PostgreSQL database.

**Cause:** Database service not ready or incorrect credentials.

**Solution:**
```bash
# 1. Check database service status
docker compose ps db

# 2. Wait for database to be ready
docker compose exec db pg_isready -U $DB_USER -d $DB_NAME

# 3. Verify database credentials
docker compose exec web env | grep DB_

# 4. Test connection manually
docker compose exec web python manage.py dbshell

# 5. Restart services in order
docker compose restart db
sleep 10
docker compose restart web
```

### Issue 4: Static Files Not Loading

**Problem:** CSS, JavaScript, and images not loading properly.

**Cause:** Incorrect static file configuration or nginx setup.

**Solution:**
```bash
# 1. Collect static files
docker compose exec web python manage.py collectstatic --noinput

# 2. Check static file permissions
docker compose exec web ls -la /app/staticfiles/

# 3. Verify nginx static file configuration
docker compose exec nginx cat /etc/nginx/conf.d/default.conf | grep static

# 4. Test static file access
curl -I https://insflow.ru/static/css/custom.css

# 5. Restart nginx
docker compose restart nginx
```

### Issue 5: High Memory Usage

**Problem:** Services consuming excessive memory.

**Cause:** Memory leaks or insufficient resource limits.

**Solution:**
```bash
# 1. Monitor resource usage
docker stats

# 2. Check for memory leaks
docker compose logs web | grep -i memory

# 3. Restart services to clear memory
docker compose restart

# 4. Optimize Docker resources
docker system prune -f

# 5. Set resource limits (if needed)
# Add to docker-compose.yml:
# deploy:
#   resources:
#     limits:
#       memory: 1G
```

## Advanced Configuration

### Custom SSL Configuration

For advanced SSL setups, you can customize the nginx configuration:

```bash
# Edit nginx configuration
nano nginx/default.conf

# Add custom SSL settings
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

### Production Bind Mounts

For production deployments, use bind mounts for persistent storage:

```env
# .env configuration
SSL_VOLUME_TYPE=bind
SSL_CERTIFICATES_PATH=/opt/letsencrypt
ACME_VOLUME_TYPE=bind
ACME_CHALLENGE_PATH=/opt/acme-challenge
```

```bash
# Create directories
sudo mkdir -p /opt/letsencrypt /opt/acme-challenge
sudo chown -R 1000:1000 /opt/letsencrypt /opt/acme-challenge
```

### Multi-Environment Setup

For staging and production environments:

```bash
# Staging environment
cp .env.example .env.staging
# Configure with staging domains and settings

# Production environment
cp .env.example .env.production
# Configure with production domains and settings

# Deploy to specific environment
docker compose --env-file .env.staging up -d
```

### Monitoring Integration

Integrate with external monitoring systems:

```bash
# Add monitoring endpoints to nginx configuration
location /nginx-status {
    stub_status on;
    access_log off;
    allow 127.0.0.1;
    deny all;
}

# Add health check endpoint
location /health {
    access_log off;
    return 200 "healthy\n";
    add_header Content-Type text/plain;
}
```

## Support and Maintenance

### Regular Maintenance Schedule

- **Daily**: Monitor service health and certificate status
- **Weekly**: Review logs and system resources
- **Monthly**: Update Docker images and security patches
- **Quarterly**: Review and update SSL certificates

### Backup Strategy

```bash
# Database backup
docker compose exec web python manage.py dumpdata > backup_$(date +%Y%m%d).json

# Media files backup
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/

# SSL certificates backup
tar -czf ssl_backup_$(date +%Y%m%d).tar.gz /opt/letsencrypt/
```

### Update Procedure

```bash
# 1. Backup current state
./scripts/backup.sh

# 2. Update code
git pull origin main

# 3. Update images
docker compose pull

# 4. Deploy updates
docker compose up -d --build

# 5. Run migrations
docker compose exec web python manage.py migrate

# 6. Verify deployment
./scripts/health-check.sh
```

---

For additional support or questions, please refer to the main project documentation or contact the development team.
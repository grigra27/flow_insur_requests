# Digital Ocean HTTP Deployment Guide

This guide provides instructions for deploying the Insurance System on Digital Ocean with HTTP configuration.

## Overview

The Digital Ocean deployment provides:
- **Simple HTTP deployment** without SSL complexity
- **Lightweight configuration** for development and testing
- **Fast deployment** with minimal setup requirements
- **Cost-effective solution** for non-production environments

### Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Nginx       │    │   Django App    │    │   PostgreSQL    │
│   (HTTP Proxy)  │────│   (Gunicorn)    │────│   (Database)    │
│   Port 80       │    │   Port 8000     │    │   Port 5432     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-repo/insurance-system.git
cd insurance-system/deployments/digital-ocean

# Copy and configure environment
cp .env.example .env
nano .env  # Edit configuration
```

### 2. Deploy

```bash
# Start services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### 3. Verify

```bash
# Test HTTP access
curl -f http://your-domain.com/healthz/

# Check service health
docker compose ps --format "table {{.Service}}\t{{.Status}}"
```

## Configuration

### Environment Variables

Create `.env` file with the following configuration:

```env
# Application Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
DOCKER_IMAGE=your-registry/insurance-system:latest

# Database Configuration
DB_NAME=insurance_db
DB_USER=insurance_user
DB_PASSWORD=secure_password

# Domain Configuration
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# HTTP Settings (no SSL)
ENABLE_HTTPS=False
SSL_REDIRECT=False
SECURE_COOKIES=False
```

## Services

### Docker Compose Services

- **db**: PostgreSQL database
- **web**: Django application with Gunicorn
- **nginx**: HTTP reverse proxy

### Service Management

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart web

# View service logs
docker compose logs -f web

# Execute commands in service
docker compose exec web python manage.py migrate
```

## Maintenance

### Updates

```bash
# Update images
docker compose pull

# Restart with new images
docker compose up -d

# Apply database migrations
docker compose exec web python manage.py migrate
```

### Monitoring

```bash
# Check service status
docker compose ps

# Monitor resource usage
docker stats

# View logs
docker compose logs -f
```

### Backup

```bash
# Database backup
docker compose exec web python manage.py dumpdata > backup.json

# Media files backup
tar -czf media_backup.tar.gz media/
```

## Troubleshooting

### Common Issues

1. **Service won't start**
   ```bash
   docker compose logs service-name
   ```

2. **Database connection issues**
   ```bash
   docker compose exec web python manage.py dbshell
   ```

3. **Static files not loading**
   ```bash
   docker compose exec web python manage.py collectstatic --noinput
   ```

## Migration to HTTPS

To migrate to HTTPS deployment (Timeweb configuration):

1. **Backup current deployment**
   ```bash
   docker compose exec web python manage.py dumpdata > backup.json
   ```

2. **Switch to Timeweb configuration**
   ```bash
   cd ../timeweb
   cp .env.example .env
   # Configure domains and SSL settings
   ```

3. **Deploy with HTTPS**
   ```bash
   ./scripts/deploy-timeweb.sh
   ```

4. **Restore data**
   ```bash
   docker compose exec web python manage.py loaddata backup.json
   ```

For detailed HTTPS deployment instructions, see [../timeweb/README.md](../timeweb/README.md).

---

For additional support, refer to the main project documentation or the Timeweb deployment guide for HTTPS setup.
# Docker Configuration Optimization Guide

This guide explains the Docker optimizations implemented for the insurance request system to improve performance, security, and reliability.

## Overview

The optimized Docker configuration includes:
- Resource allocation limits for all services
- Health checks for service monitoring
- Secure internal networking
- Performance tuning for database and cache
- SSL certificate management
- Comprehensive logging and monitoring

## Services Configuration

### Database (PostgreSQL)

**Optimizations:**
- Memory allocation: 1GB limit, 512MB reservation
- Performance tuning with shared buffers and cache settings
- Health checks with pg_isready
- Optimized connection settings

**Environment Variables:**
```bash
POSTGRES_SHARED_BUFFERS=256MB
POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
POSTGRES_WORK_MEM=4MB
POSTGRES_MAINTENANCE_WORK_MEM=64MB
```

### Redis Cache

**Optimizations:**
- Memory limit: 512MB with LRU eviction policy
- Persistence configuration for data safety
- Health checks with ping command
- Optimized for session and cache storage

**Configuration:**
```bash
redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru --save 60 1000
```

### Django Web Application

**Optimizations:**
- Resource limits: 1GB memory, 1 CPU core
- Health checks using Django management command
- Optimized Python settings (unbuffered, no bytecode)
- Proper dependency management with health check conditions

**Environment Variables:**
```bash
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

### Nginx Reverse Proxy

**Optimizations:**
- Resource allocation: 512MB memory limit
- SSL certificate volume mounts for multiple sources
- Nginx cache and temp directories
- Health check endpoint configuration
- Static file optimization

**Volume Mounts:**
- SSL certificates: `/etc/letsencrypt`, `/etc/ssl/certs`, `/etc/ssl/private`
- Cache directories: `nginx_cache`, `nginx_temp`
- Static files: Read-only mounts for better security

### Celery Worker (Optional)

**Optimizations:**
- Dedicated worker process with concurrency control
- Resource limits: 512MB memory, 0.5 CPU
- Health checks with Celery inspect
- Optimized for background task processing

## Health Checks

All services include comprehensive health checks:

### Database Health Check
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Redis Health Check
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

### Django Health Check
```yaml
healthcheck:
  test: ["CMD", "python", "manage.py", "check", "--deploy"]
  interval: 60s
  timeout: 30s
  retries: 3
  start_period: 60s
```

### Nginx Health Check
```yaml
healthcheck:
  test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost/health/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

## Security Features

### Network Security
- Custom bridge network with isolated subnet (172.20.0.0/16)
- Internal service communication only
- No direct external access to database or cache

### SSL Certificate Management
- Multiple certificate source support
- Read-only certificate mounts
- Automatic certificate renewal support

### Resource Security
- Memory and CPU limits prevent resource exhaustion
- Read-only mounts where possible
- Proper file permissions and ownership

## Performance Monitoring

### Resource Monitoring
```bash
# Monitor container resource usage
docker stats

# Check container health status
docker-compose ps

# View service logs
docker-compose logs -f [service_name]
```

### Performance Metrics
- Container CPU and memory usage
- Database connection pooling
- Redis cache hit rates
- Nginx request processing times

## Deployment Commands

### Initial Deployment
```bash
# Validate configuration
python validate_docker_config.py

# Start services with health checks
docker-compose up -d

# Check service health
docker-compose ps
```

### Updates and Maintenance
```bash
# Update services
docker-compose pull
docker-compose up -d

# View logs
docker-compose logs -f

# Restart specific service
docker-compose restart [service_name]
```

### Backup and Recovery
```bash
# Backup database
docker-compose exec db pg_dump -U ${DB_USER} ${DB_NAME} > backup.sql

# Backup volumes
docker run --rm -v postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

## Troubleshooting

### Common Issues

1. **Service Won't Start**
   - Check health check logs: `docker-compose logs [service]`
   - Verify environment variables
   - Check resource availability

2. **SSL Certificate Issues**
   - Verify certificate paths in volumes
   - Check certificate permissions
   - Ensure certificate renewal process

3. **Performance Issues**
   - Monitor resource usage: `docker stats`
   - Check database query performance
   - Review nginx access logs

4. **Network Connectivity**
   - Verify internal network configuration
   - Check service dependencies
   - Test health check endpoints

### Log Locations
- Nginx logs: `/var/log/nginx/`
- Django logs: `/app/logs/`
- Database logs: Container logs via `docker-compose logs db`
- Redis logs: Container logs via `docker-compose logs redis`

## Optimization Validation

Use the provided validation script to check configuration:

```bash
python validate_docker_config.py
```

This script checks:
- Docker and Docker Compose installation
- Service configuration completeness
- Environment variable setup
- SSL certificate availability
- Nginx configuration validity

## Best Practices

1. **Resource Management**
   - Set appropriate memory and CPU limits
   - Monitor resource usage regularly
   - Scale services based on load

2. **Security**
   - Use secrets for sensitive data
   - Regularly update base images
   - Monitor security logs

3. **Maintenance**
   - Implement log rotation
   - Regular backup procedures
   - Monitor certificate expiration

4. **Performance**
   - Optimize database queries
   - Use appropriate caching strategies
   - Monitor response times

## Environment Variables Reference

See `.env.example` for complete list of configuration variables including:
- Database performance settings
- Container resource limits
- Health check intervals
- Nginx optimization parameters
- Celery worker configuration
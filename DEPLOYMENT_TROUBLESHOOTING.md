# Digital Ocean Deployment Troubleshooting Guide

## Common Issues and Solutions

### 1. Nginx Container Unhealthy Error

**Error:** `ERROR: for nginx Container "xxx" is unhealthy.`

**Causes:**
- Web service not ready when nginx starts
- Health check timeout too aggressive
- Network connectivity issues between containers

**Solutions:**

#### Quick Fix - Use Conservative Configuration
```bash
# On the server, use the conservative docker-compose file
cd /opt/insurance-system
cp docker-compose.conservative.yml docker-compose.yml
docker-compose down --remove-orphans
docker-compose up -d
```

#### Manual Step-by-Step Deployment
```bash
# 1. Start services one by one
docker-compose down --remove-orphans

# 2. Start database first
docker-compose up -d db

# 3. Wait for database
sleep 30
docker-compose exec db pg_isready -U insurance_user -d insurance_db

# 4. Start web service
docker-compose up -d web

# 5. Wait for web service and run migrations
sleep 60
docker-compose exec web python manage.py migrate --noinput
docker-compose exec web python manage.py collectstatic --noinput

# 6. Test web service directly
curl -f http://localhost:8000/healthz/

# 7. Start nginx
docker-compose up -d nginx

# 8. Test complete application
curl -f http://localhost/healthz/
```

### 2. Database Connection Issues

**Error:** Database connection refused or timeout

**Solutions:**
```bash
# Check database status
docker-compose logs db

# Restart database service
docker-compose restart db

# Check database connectivity
docker-compose exec web python manage.py dbshell
```

### 3. Static Files Not Loading

**Error:** 404 errors for CSS/JS files

**Solutions:**
```bash
# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Check nginx volume mounts
docker-compose exec nginx ls -la /app/staticfiles/

# Restart nginx
docker-compose restart nginx
```

### 4. Health Check Failures

**Error:** Health check endpoints returning errors

**Solutions:**
```bash
# Test health check directly
docker-compose exec web python /app/healthcheck.py

# Check web service logs
docker-compose logs web

# Test individual endpoints
curl -v http://localhost:8000/healthz/
curl -v http://localhost/healthz/
```

## Monitoring Commands

### Check Service Status
```bash
docker-compose ps
docker-compose ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f nginx
docker-compose logs -f db
```

### Resource Usage
```bash
docker stats
docker system df
```

### Network Connectivity
```bash
# Test internal connectivity
docker-compose exec nginx wget -qO- http://web:8000/healthz/
docker-compose exec web curl -f http://localhost:8000/healthz/
```

## Emergency Recovery

### Complete Reset
```bash
cd /opt/insurance-system

# Stop everything
docker-compose down --remove-orphans

# Remove volumes (WARNING: This will delete data!)
docker-compose down -v

# Pull latest code
git fetch origin main
git reset --hard origin/main

# Rebuild and restart
docker-compose build --no-cache
docker-compose up -d
```

### Rollback to Previous Version
```bash
# Check git history
git log --oneline -10

# Rollback to previous commit
git reset --hard HEAD~1

# Restart services
docker-compose down --remove-orphans
docker-compose up -d
```

## Performance Optimization

### Increase Health Check Timeouts
Edit `docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:8000/healthz/"]
  interval: 60s      # Increased from 30s
  timeout: 30s       # Increased from 15s
  retries: 10        # Increased from 5
  start_period: 300s # Increased from 120s
```

### Optimize Resource Limits
```yaml
services:
  web:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'
```

## Contact Information

If issues persist:
1. Check GitHub Actions logs for deployment details
2. Review server logs: `journalctl -u docker`
3. Monitor disk space: `df -h`
4. Check memory usage: `free -h`
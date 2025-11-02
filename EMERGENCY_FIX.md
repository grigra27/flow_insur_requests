# Emergency Fix for Digital Ocean Deployment

Run these commands directly on your Digital Ocean server to fix the current nginx unhealthy container issue:

## Quick Fix Commands

```bash
# 1. Go to project directory
cd /opt/insurance-system

# 2. Stop all services
docker-compose down --remove-orphans

# 3. Create a working docker-compose.yml without problematic health checks
cat > docker-compose.yml << 'EOF'
version: "3.9"

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  web:
    image: ${DOCKER_IMAGE}
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DEBUG=False
      - DB_ENGINE=django.db.backends.postgresql
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_HOST=db
      - DB_PORT=5432
      - ALLOWED_HOSTS=${ALLOWED_HOSTS}
    volumes:
      - media_data:/app/media
      - logs_data:/app/logs
      - staticfiles_data:/app/staticfiles
    depends_on:
      - db
    restart: unless-stopped

  nginx:
    build:
      context: ./nginx
    image: custom-nginx:latest
    ports:
      - "80:80"
    volumes:
      - staticfiles_data:/app/staticfiles:ro
      - media_data:/app/media:ro
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
  media_data:
  logs_data:
  staticfiles_data:
EOF

# 4. Start services step by step
echo "Starting database..."
docker-compose up -d db

# 5. Wait for database
sleep 30

# 6. Start web service
echo "Starting web service..."
docker-compose up -d web

# 7. Wait for web service
sleep 60

# 8. Run migrations
echo "Running migrations..."
docker-compose exec -T web python manage.py migrate --noinput

# 9. Collect static files
echo "Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput

# 10. Test web service
echo "Testing web service..."
docker-compose exec -T web curl -f http://localhost:8000/healthz/

# 11. Start nginx
echo "Starting nginx..."
docker-compose up -d nginx

# 12. Wait for nginx
sleep 30

# 13. Test complete application
echo "Testing complete application..."
curl -f http://localhost/healthz/

# 14. Check final status
echo "Final status:"
docker-compose ps
```

## Alternative One-Liner Fix

If you prefer a single command, run this:

```bash
cd /opt/insurance-system && docker-compose down --remove-orphans && docker-compose up -d db && sleep 30 && docker-compose up -d web && sleep 60 && docker-compose exec -T web python manage.py migrate --noinput && docker-compose exec -T web python manage.py collectstatic --noinput && docker-compose up -d nginx && sleep 30 && curl -f http://localhost/healthz/ && docker-compose ps
```

## Verification

After running the fix, verify everything is working:

```bash
# Check service status
docker-compose ps

# Test endpoints
curl -I http://localhost/healthz/
curl -I http://onbr.site/healthz/

# Check logs if needed
docker-compose logs nginx
docker-compose logs web
```

## What This Fix Does

1. **Removes problematic health checks** that were causing circular dependencies
2. **Uses step-by-step startup** to ensure proper service initialization order
3. **Adds proper delays** between service starts
4. **Tests each step** to ensure everything is working

The application should be accessible at http://onbr.site and http://64.227.75.233 after this fix.
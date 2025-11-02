# Deployment Dependencies Analysis

## Overview

This document analyzes the dependencies between different deployment components to ensure safe cleanup and modification of Timeweb deployment files without breaking existing functionality.

## Dependency Categories

### 1. Critical Dependencies (DO NOT MODIFY)

These components are essential for Digital Ocean deployment and shared application functionality:

#### Digital Ocean Deployment Chain
```
GitHub Actions (deploy_do.yml)
    ↓
docker-compose.yml
    ↓
├── PostgreSQL (postgres:15 image)
├── Django Web App (custom image)
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── requirements.txt
│   └── Django application code
└── Nginx Reverse Proxy
    ├── nginx/Dockerfile
    └── nginx/default.conf
```

#### Shared Django Application
```
Django Core:
├── manage.py
├── onlineservice/ (settings, urls, wsgi)
├── insurance_requests/ (main app)
├── summaries/ (summaries app)
├── core/ (utilities)
├── templates/
├── static/
└── media/
```

### 2. Timeweb-Specific Dependencies (CAN MODIFY)

These components are specific to Timeweb deployment and can be safely modified:

#### Timeweb Deployment Chain
```
GitHub Actions (deploy_timeweb.yml)
    ↓
docker-compose.timeweb.yml
    ↓
├── PostgreSQL (same as DO, different volumes)
├── Django Web App (same image, different env vars)
├── Nginx with SSL (nginx:alpine + mounted configs)
│   ├── nginx-timeweb/default.conf (HTTP fallback)
│   ├── nginx-timeweb/default-https.conf (HTTPS config)
│   └── nginx-timeweb/default-acme.conf (ACME challenges)
└── Certbot (certbot/certbot image, SSL profile)
    └── scripts/ssl/obtain-certificates-docker.sh
```

#### SSL Certificate Management
```
Certificate Acquisition:
scripts/ssl/obtain-certificates-docker.sh
    ↓
Let's Encrypt via Certbot Docker
    ↓
Certificate Storage (bind mounts):
├── ./letsencrypt/live/insflow.ru/
├── ./letsencrypt/live/insflow.tw1.su/
└── ./certbot_webroot/

Certificate Renewal:
scripts/ssl/renew-certificates.sh
    ↓
Cron Job or Certbot Container
    ↓
Automatic Renewal Every 12 Hours
```

### 3. Obsolete Dependencies (SAFE TO REMOVE)

These components have no active dependencies and can be safely removed:

#### Obsolete Docker Configurations
- `docker-compose.conservative.yml` - No references in workflows or scripts
- `nginx-timeweb/Dockerfile` - Not used in docker-compose.timeweb.yml

#### Obsolete SSL Scripts
- `scripts/ssl/fix-*.sh` - Temporary fix scripts, no longer referenced
- `scripts/ssl/activate-https-manual.sh` - Replaced by Docker-based approach

#### Obsolete Documentation
- All `*_SUMMARY.md`, `*_FIX.md` files - Historical records only

## Dependency Analysis by Component

### Docker Compose Files

#### docker-compose.yml (Digital Ocean)
**Dependencies:**
- ✅ Referenced by: `.github/workflows/deploy_do.yml`
- ✅ Uses: `nginx/default.conf`, `nginx/Dockerfile`
- ✅ Volumes: `postgres_data`, `media_data`, `logs_data`, `staticfiles_data`
- ⚠️ **CRITICAL**: Do not modify

#### docker-compose.timeweb.yml (Timeweb)
**Dependencies:**
- ✅ Referenced by: `.github/workflows/deploy_timeweb.yml`
- ✅ Uses: `nginx-timeweb/default.conf` (mounted)
- ✅ Volumes: `postgres_data_timeweb`, `media_data_timeweb`, etc.
- ✅ Bind mounts: `./letsencrypt`, `./certbot_webroot`
- ✅ **MODIFIABLE**: Can be simplified

#### docker-compose.conservative.yml (Obsolete)
**Dependencies:**
- ❌ No references in workflows
- ❌ No references in scripts
- ❌ Uses same volume names as main DO config (potential conflict)
- ✅ **SAFE TO REMOVE**

### Nginx Configurations

#### nginx/default.conf (Digital Ocean)
**Dependencies:**
- ✅ Referenced by: `docker-compose.yml`
- ✅ Mounted in: nginx service container
- ⚠️ **CRITICAL**: Do not modify

#### nginx-timeweb/default.conf (Timeweb HTTP)
**Dependencies:**
- ✅ Referenced by: `docker-compose.timeweb.yml`
- ✅ Used as: HTTP fallback configuration
- ✅ **MODIFIABLE**: Can be updated

#### nginx-timeweb/default-https.conf (Timeweb HTTPS)
**Dependencies:**
- ⚠️ Not directly referenced in docker-compose
- ✅ Used by: deployment scripts for HTTPS mode
- ✅ **MODIFIABLE**: Can be simplified

#### nginx-timeweb/default-http.conf (Duplicate)
**Dependencies:**
- ❌ No references found
- ❌ Duplicate of default.conf
- ✅ **SAFE TO REMOVE**

### SSL Scripts

#### Essential SSL Scripts
**obtain-certificates-docker.sh:**
- ✅ Referenced by: `.github/workflows/deploy_timeweb.yml`
- ✅ Uses: `docker-compose.timeweb.yml`, nginx configs
- ⚠️ **CRITICAL**: Core certificate acquisition

**renew-certificates.sh:**
- ✅ Used by: cron jobs, certbot container
- ✅ **ESSENTIAL**: Certificate renewal

**check-certificates.sh:**
- ✅ Used by: monitoring scripts
- ✅ **USEFUL**: Certificate validation

#### Obsolete SSL Scripts
**fix-*.sh scripts:**
- ❌ No references in active workflows
- ❌ Temporary solutions, replaced by Docker approach
- ✅ **SAFE TO REMOVE**

### Environment Configuration

#### .env.example (Digital Ocean)
**Dependencies:**
- ✅ Referenced by: documentation
- ✅ Template for: Digital Ocean deployment
- ⚠️ **PRESERVE**: Reference template

#### .env.timeweb.example (Timeweb)
**Dependencies:**
- ✅ Referenced by: documentation, workflows
- ✅ Template for: Timeweb deployment
- ✅ **MODIFIABLE**: Can be simplified (remove excessive CSP vars)

## Cross-Platform Dependencies

### Shared Components
These components are used by both deployments:

1. **Django Application Code**
   - All Python files in app directories
   - Templates and static files
   - Database models and migrations

2. **Docker Image**
   - Same base image used by both platforms
   - Built from same Dockerfile
   - Different environment variables only

3. **Health Check Endpoints**
   - `/healthz/` endpoint used by both nginx configs
   - Health check logic in Django application

### Platform-Specific Components

#### Digital Ocean Only
- `docker-compose.yml`
- `nginx/` directory
- Volume names without `_timeweb` suffix

#### Timeweb Only
- `docker-compose.timeweb.yml`
- `nginx-timeweb/` directory
- `scripts/ssl/` directory
- Volume names with `_timeweb` suffix
- SSL certificate management

## Risk Assessment Matrix

### No Risk (Safe to Modify/Remove)
- Obsolete documentation files
- Fix scripts in `scripts/ssl/`
- `docker-compose.conservative.yml`
- `nginx-timeweb/default-http.conf`
- `nginx-timeweb/Dockerfile`

### Low Risk (Can Modify with Testing)
- `docker-compose.timeweb.yml` (simplification)
- `nginx-timeweb/default-https.conf` (simplification)
- `.env.timeweb.example` (variable reduction)
- SSL monitoring scripts (consolidation)

### Medium Risk (Modify with Caution)
- `nginx-timeweb/default.conf` (active HTTP config)
- Essential SSL scripts (obtain, renew, check)
- GitHub Actions workflows

### High Risk (Do Not Modify)
- `docker-compose.yml` (Digital Ocean)
- `nginx/` directory (Digital Ocean)
- Django application code
- Shared Docker image configuration

## Modification Guidelines

### Safe Modifications
1. Remove files with no dependencies
2. Simplify overly complex configurations
3. Consolidate redundant scripts
4. Update documentation

### Required Testing After Modifications
1. **Digital Ocean deployment** must continue working
2. **Timeweb HTTP fallback** must work
3. **Timeweb HTTPS** must work with certificates
4. **Certificate renewal** must function
5. **All domains** must be accessible

### Rollback Plan
1. Keep backup of modified files
2. Test changes in staging environment first
3. Have working configuration ready for quick rollback
4. Monitor deployments after changes

## Conclusion

The dependency analysis shows that approximately 40% of Timeweb-related files can be safely removed or modified without affecting the Digital Ocean deployment or core application functionality. The key is to preserve the working Digital Ocean configuration while simplifying the Timeweb-specific components.

The most critical dependencies to preserve are:
1. Digital Ocean deployment chain
2. Shared Django application code
3. Essential SSL certificate management scripts
4. Active nginx configurations for both platforms
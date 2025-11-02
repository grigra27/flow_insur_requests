# Timeweb Deployment Files Inventory

## Docker Compose Configurations

### Active Configurations
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `docker-compose.yml` | Digital Ocean HTTP deployment | ✅ Working | Preserve |
| `docker-compose.timeweb.yml` | Timeweb HTTPS deployment | ⚠️ Complex | Simplify |

### Obsolete Configurations
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `docker-compose.conservative.yml` | Fallback without health checks | ❌ Obsolete | Remove |

## Nginx Configurations

### Digital Ocean (nginx/)
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `nginx/default.conf` | HTTP config for onbr.site | ✅ Working | Preserve |
| `nginx/Dockerfile` | Custom nginx build | ✅ Working | Preserve |

### Timeweb (nginx-timeweb/)
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `nginx-timeweb/default.conf` | HTTP fallback config | ✅ Active | Keep |
| `nginx-timeweb/default-https.conf` | HTTPS config (400+ lines) | ⚠️ Complex | Simplify |
| `nginx-timeweb/default-http.conf` | Duplicate HTTP config | ❌ Redundant | Remove |
| `nginx-timeweb/default-acme.conf` | ACME challenge config | ✅ Useful | Keep |
| `nginx-timeweb/Dockerfile` | Unused nginx build | ❌ Unused | Remove |
| `nginx-timeweb/HTTPS_CONFIG_SUMMARY.md` | Config documentation | ✅ Useful | Keep |

## SSL Scripts (scripts/ssl/)

### Essential Scripts
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `scripts/ssl/obtain-certificates-docker.sh` | Docker-based cert acquisition | ✅ Essential | Keep |
| `scripts/ssl/renew-certificates.sh` | Certificate renewal | ✅ Essential | Keep |
| `scripts/ssl/check-certificates.sh` | Certificate validation | ✅ Essential | Keep |
| `scripts/ssl/README.md` | SSL documentation | ✅ Essential | Keep |

### Fix Scripts (Obsolete)
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `scripts/ssl/fix-certbot.sh` | Certbot fix script | ❌ Obsolete | Remove |
| `scripts/ssl/fix-deployment-https.sh` | Deployment fix | ❌ Obsolete | Remove |
| `scripts/ssl/fix-redirect-loops.sh` | Redirect fix | ❌ Obsolete | Remove |
| `scripts/ssl/activate-https-manual.sh` | Manual activation | ❌ Obsolete | Remove |
| `scripts/ssl/quick-https-enable.sh` | Quick fix | ❌ Obsolete | Remove |

### Monitoring Scripts
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `scripts/ssl/monitor-ssl-status.sh` | SSL monitoring | ⚠️ Redundant | Consolidate |
| `scripts/ssl/check-certificates-status.sh` | Cert status check | ⚠️ Redundant | Consolidate |
| `scripts/ssl/verify-https-working.sh` | HTTPS verification | ⚠️ Redundant | Consolidate |

### Setup Scripts
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `scripts/ssl/ssl-cron-setup.sh` | Cron job setup | ✅ Useful | Keep |
| `scripts/ssl/post-renewal-hook.sh` | Post-renewal actions | ✅ Useful | Keep |
| `scripts/ssl/test-acme-challenge.sh` | ACME testing | ✅ Useful | Keep |

## General Scripts

### Deployment Scripts
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `scripts/deploy_do_improved.sh` | Digital Ocean deployment | ✅ Working | Preserve |
| `scripts/fix_deployment_now.sh` | Emergency fix script | ❌ Obsolete | Remove |
| `scripts/test-https-deployment.sh` | HTTPS deployment test | ✅ Useful | Keep |
| `scripts/verify_landing_deployment.sh` | Landing page verification | ✅ Useful | Keep |

### Monitoring Scripts
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `scripts/monitor-domains-https.py` | Domain monitoring | ✅ Useful | Keep |
| `scripts/monitoring-dashboard.py` | Monitoring dashboard | ✅ Useful | Keep |
| `scripts/ssl-monitoring-system.py` | SSL monitoring system | ✅ Useful | Keep |
| `scripts/setup-monitoring.sh` | Monitoring setup | ✅ Useful | Keep |
| `scripts/setup-monitoring-cron.sh` | Cron setup | ✅ Useful | Keep |
| `scripts/domain-monitor.service` | Systemd service | ✅ Useful | Keep |

## Environment Configuration

### Active Configuration Files
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `.env.example` | Digital Ocean env template | ✅ Clean | Preserve |
| `.env.timeweb.example` | Timeweb env template (25+ vars) | ⚠️ Complex | Simplify |

## Documentation Files

### Active Documentation
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `DEPLOYMENT_GUIDE.md` | General deployment guide | ✅ Useful | Keep |
| `DEPLOYMENT_GUIDE_TIMEWEB.md` | Timeweb HTTPS guide | ✅ Comprehensive | Keep |
| `SSL_SETUP_GUIDE.md` | SSL configuration guide | ✅ Useful | Keep |

### Status/Fix Documentation (Obsolete)
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `DEPLOYMENT_FIXES_SUMMARY.md` | Historical fixes | ❌ Obsolete | Remove |
| `EMERGENCY_FIX.md` | Emergency procedures | ❌ Obsolete | Remove |
| `QUICK_FIX_CURRENT_DEPLOYMENT.md` | Quick fixes | ❌ Obsolete | Remove |
| `DEPLOYMENT_TROUBLESHOOTING.md` | Troubleshooting guide | ⚠️ Review | Consolidate |
| `DIGITAL_OCEAN_COMPATIBILITY_REPORT.md` | Compatibility report | ❌ Obsolete | Remove |
| `FINAL_HTTPS_SOLUTION.md` | HTTPS solution doc | ❌ Obsolete | Remove |
| `HTTPS_DEPLOYMENT_IMPLEMENTATION_SUMMARY.md` | Implementation summary | ❌ Obsolete | Remove |
| `HTTPS_DEPLOYMENT_SUCCESS.md` | Success report | ❌ Obsolete | Remove |
| `HTTPS_DOMAIN_IMPLEMENTATION_SUMMARY.md` | Domain implementation | ❌ Obsolete | Remove |
| `HTTPS_INTEGRATION_TESTING_IMPLEMENTATION_SUMMARY.md` | Testing summary | ❌ Obsolete | Remove |
| `HTTPS_NEXT_STEPS.md` | Next steps doc | ❌ Obsolete | Remove |
| `SSL_FIX_INSTRUCTIONS.md` | SSL fix instructions | ❌ Obsolete | Remove |
| `SSL_SUCCESS_BUT_FILES_MISSING.md` | SSL status doc | ❌ Obsolete | Remove |

## Summary Statistics

### Files by Category
- **Docker Compose**: 3 files (1 obsolete)
- **Nginx Configs**: 6 files (2 redundant, 1 unused)
- **SSL Scripts**: 14 files (5 obsolete, 3 redundant)
- **General Scripts**: 9 files (1 obsolete)
- **Environment**: 2 files (1 needs simplification)
- **Documentation**: 19 files (13 obsolete)

### Action Summary
- **Remove**: 23 files (43%)
- **Keep**: 21 files (40%)
- **Simplify/Consolidate**: 9 files (17%)

### Cleanup Impact
- **Immediate cleanup**: Remove 23 obsolete files
- **Consolidation**: Merge 6 redundant configurations
- **Simplification**: Reduce complexity in 3 key files
- **Organization**: Restructure remaining 30 files

## Dependencies Map

### Critical Dependencies (DO NOT MODIFY)
```
Digital Ocean Deployment:
├── docker-compose.yml
├── nginx/default.conf
├── nginx/Dockerfile
└── .env.example

Django Application (Shared):
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
└── manage.py
```

### Timeweb Dependencies (CAN MODIFY)
```
Timeweb Deployment:
├── docker-compose.timeweb.yml (simplify)
├── nginx-timeweb/default.conf (keep)
├── nginx-timeweb/default-https.conf (simplify)
├── scripts/ssl/obtain-certificates-docker.sh (keep)
├── scripts/ssl/renew-certificates.sh (keep)
└── .env.timeweb.example (simplify)
```

### Obsolete Files (SAFE TO REMOVE)
```
Obsolete Files:
├── docker-compose.conservative.yml
├── nginx-timeweb/default-http.conf
├── nginx-timeweb/Dockerfile
├── scripts/ssl/fix-*.sh (5 files)
├── scripts/fix_deployment_now.sh
└── *_SUMMARY.md, *_FIX.md files (13 files)
```
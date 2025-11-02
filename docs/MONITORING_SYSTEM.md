# HTTPS Monitoring System Documentation

## Overview

The HTTPS monitoring system provides comprehensive monitoring for the insflow infrastructure, including health checks, SSL certificate monitoring, and HTTPS functionality verification across all domains.

## Components

### 1. Enhanced Health Check (`healthcheck.py`)

**Purpose**: Monitors Django application health with HTTPS support

**Features**:
- HTTPS endpoint checking
- SSL certificate validation
- Domain-specific health checks
- Development and production mode support
- Comprehensive logging

**Usage**:
```bash
# Run health check
python3 healthcheck.py

# Check logs
tail -f logs/healthcheck.log
```

**Environment Variables**:
- `DEBUG`: Set to `false` for production mode
- `SECURE_SSL_REDIRECT`: Set to `true` to enable HTTPS checks
- `MAIN_DOMAINS`: Comma-separated list of main domains
- `SUBDOMAINS`: Comma-separated list of subdomains

### 2. HTTPS Domain Monitor (`scripts/monitor-domains-https.py`)

**Purpose**: Comprehensive HTTPS monitoring for all domains

**Features**:
- SSL certificate expiry checking
- HTTPS redirect verification
- Domain availability testing
- Security headers validation
- Performance monitoring

**Usage**:
```bash
# Single monitoring run
python3 scripts/monitor-domains-https.py

# JSON output
python3 scripts/monitor-domains-https.py --json

# Generate report from latest data
python3 scripts/monitor-domains-https.py --report

# Continuous monitoring
python3 scripts/monitor-domains-https.py --continuous
```

**Output Files**:
- `logs/https_monitoring.log`: Detailed monitoring logs
- `logs/https_monitoring_results.json`: Latest monitoring results

### 3. SSL Monitoring System (`scripts/ssl-monitoring-system.py`)

**Purpose**: SSL certificate lifecycle management and monitoring

**Features**:
- Certificate expiry tracking
- Automatic renewal triggering
- SSL event logging
- Certificate validation
- Renewal status reporting

**Usage**:
```bash
# Run SSL monitoring
python3 scripts/ssl-monitoring-system.py

# JSON output
python3 scripts/ssl-monitoring-system.py --json

# Generate report
python3 scripts/ssl-monitoring-system.py --report

# Trigger certificate renewal
python3 scripts/ssl-monitoring-system.py --renew

# Continuous monitoring
python3 scripts/ssl-monitoring-system.py --continuous
```

**Output Files**:
- `logs/ssl_events.log`: SSL-related events
- `logs/certificate_expiry.log`: Certificate expiry events
- `logs/security_events.log`: Security-related events
- `logs/ssl_monitoring_comprehensive.json`: Latest SSL monitoring results

### 4. Monitoring Dashboard (`scripts/monitoring-dashboard.py`)

**Purpose**: Unified monitoring dashboard integrating all components

**Features**:
- Comprehensive system overview
- Integrated health, HTTPS, and SSL monitoring
- Status aggregation and reporting
- JSON API for external integration
- Overall system health assessment

**Usage**:
```bash
# Run comprehensive monitoring
python3 scripts/monitoring-dashboard.py

# JSON output for API
python3 scripts/monitoring-dashboard.py --json

# Generate report from latest data
python3 scripts/monitoring-dashboard.py --report

# Individual component checks
python3 scripts/monitoring-dashboard.py --health-only
python3 scripts/monitoring-dashboard.py --https-only
python3 scripts/monitoring-dashboard.py --ssl-only
```

**Output Files**:
- `logs/monitoring_dashboard.log`: Dashboard operation logs
- `logs/monitoring_dashboard.json`: Latest comprehensive results

## Automated Monitoring Setup

### Cron Job Installation

```bash
# Install monitoring cron jobs
./scripts/setup-monitoring-cron.sh

# Check monitoring status
./scripts/setup-monitoring-cron.sh --status

# Remove monitoring cron jobs
./scripts/setup-monitoring-cron.sh --remove
```

### Cron Schedule

- **Dashboard monitoring**: Every 15 minutes
- **SSL monitoring**: Every hour
- **HTTPS monitoring**: Every 30 minutes
- **Log rotation**: Daily at 2 AM

### Wrapper Scripts

The cron setup creates wrapper scripts that handle:
- Proper environment setup
- Error logging
- Automatic certificate renewal for critical issues
- Result archiving

## Monitoring Configuration

### Environment Variables

```bash
# Domain configuration
MAIN_DOMAINS=insflow.ru,insflow.tw1.su
SUBDOMAINS=zs.insflow.ru,zs.insflow.tw1.su

# SSL monitoring
SSL_CHECK_INTERVAL=3600        # 1 hour
SSL_ALERT_DAYS=7              # Critical alert threshold
SSL_WARNING_DAYS=30           # Warning threshold

# General monitoring
MONITOR_INTERVAL=300          # 5 minutes for continuous mode
```

### Log Files

All monitoring components write to structured log files:

```
logs/
├── healthcheck.log                    # Health check events
├── healthcheck_status.json           # Latest health check results
├── https_monitoring.log               # HTTPS monitoring events
├── https_monitoring_results.json     # Latest HTTPS results
├── ssl_events.log                     # SSL-related events
├── certificate_expiry.log             # Certificate expiry events
├── security_events.log                # Security-related events
├── ssl_monitoring_comprehensive.json # Latest SSL results
├── monitoring_dashboard.log           # Dashboard operation logs
├── monitoring_dashboard.json          # Latest comprehensive results
├── cron_monitoring.log               # Cron job execution logs
├── latest_dashboard.json             # Latest dashboard results (cron)
├── latest_ssl.json                   # Latest SSL results (cron)
└── latest_https.json                 # Latest HTTPS results (cron)
```

## Monitoring Workflow

### 1. Health Checks

1. **Local Development**: Checks `localhost:8000` endpoints
2. **Production**: Checks all configured domains with HTTPS
3. **SSL Validation**: Verifies certificate validity and expiry
4. **Redirect Testing**: Confirms HTTP to HTTPS redirects

### 2. SSL Certificate Monitoring

1. **Certificate Discovery**: Finds certificates in `/etc/letsencrypt/live/`
2. **Expiry Checking**: Calculates days until expiry
3. **Status Classification**: 
   - Valid: >30 days
   - Warning: 8-30 days
   - Critical: ≤7 days
   - Expired: <0 days
4. **Automatic Renewal**: Triggers renewal for critical certificates

### 3. HTTPS Domain Monitoring

1. **SSL Certificate Check**: Validates certificates for all domains
2. **Redirect Verification**: Tests HTTP to HTTPS redirects
3. **Availability Testing**: Checks domain accessibility
4. **Security Headers**: Validates security header presence
5. **Performance Monitoring**: Measures response times

### 4. Dashboard Integration

1. **Component Aggregation**: Combines all monitoring results
2. **Status Calculation**: Determines overall system health
3. **Report Generation**: Creates human-readable reports
4. **API Output**: Provides JSON for external systems

## Alert Levels

### Health Status

- **Healthy**: All checks passing
- **Warning**: Some non-critical issues
- **Critical**: Service-affecting problems

### SSL Status

- **Valid**: Certificate valid for >30 days
- **Warning**: Certificate expires in 8-30 days
- **Critical**: Certificate expires in ≤7 days
- **Expired**: Certificate has expired

### Exit Codes

- **0**: All systems healthy
- **1**: Warnings present
- **2**: Critical issues found

## Integration Examples

### GitHub Actions Integration

```yaml
- name: Run Monitoring Check
  run: |
    python3 scripts/monitoring-dashboard.py --json > monitoring_results.json
    if [ $? -eq 2 ]; then
      echo "Critical monitoring issues found"
      exit 1
    fi
```

### External Monitoring Integration

```bash
# Get monitoring status via API
curl -s http://your-domain/api/monitoring | jq '.overall_status'

# Or run locally
python3 scripts/monitoring-dashboard.py --json | jq '.overall_status'
```

### Alerting Integration

Add alerting to cron wrapper scripts:

```bash
# In cron-dashboard-monitor.sh
if [ $EXIT_CODE -eq 2 ]; then
    # Send alert (email, webhook, etc.)
    curl -X POST "https://hooks.slack.com/..." \
         -d '{"text":"Critical monitoring issues detected"}'
fi
```

## Troubleshooting

### Common Issues

1. **Permission Errors**:
   ```bash
   # Ensure proper permissions
   chmod +x scripts/*.py
   chmod +x scripts/*.sh
   ```

2. **Missing Dependencies**:
   ```bash
   # Install required packages
   pip3 install -r requirements.txt
   ```

3. **SSL Certificate Access**:
   ```bash
   # Ensure access to certificate files
   sudo chown -R $USER:$USER /etc/letsencrypt/
   ```

4. **Log Directory Issues**:
   ```bash
   # Create logs directory
   mkdir -p logs
   chmod 755 logs
   ```

### Debugging

1. **Enable Verbose Logging**:
   ```bash
   export PYTHONPATH=.
   python3 -v scripts/monitoring-dashboard.py
   ```

2. **Check Individual Components**:
   ```bash
   # Test health checks
   python3 healthcheck.py
   
   # Test HTTPS monitoring
   python3 scripts/monitor-domains-https.py --json
   
   # Test SSL monitoring
   python3 scripts/ssl-monitoring-system.py --json
   ```

3. **Review Logs**:
   ```bash
   # Check recent monitoring activity
   tail -f logs/monitoring_dashboard.log
   
   # Check SSL events
   tail -f logs/ssl_events.log
   
   # Check cron execution
   tail -f logs/cron_monitoring.log
   ```

## Maintenance

### Log Rotation

Logs are automatically rotated by the cron setup:
- Files larger than 100MB are truncated to 50MB
- JSON result files older than 7 days are deleted

### Manual Maintenance

```bash
# Clean old logs
find logs/ -name "*.log" -size +100M -exec truncate -s 50M {} \;

# Clean old results
find logs/ -name "*.json" -mtime +7 -delete

# Check monitoring status
./scripts/monitoring-status.sh
```

### Updates and Changes

When updating monitoring configuration:

1. Update environment variables
2. Restart cron jobs if needed:
   ```bash
   ./scripts/setup-monitoring-cron.sh --remove
   ./scripts/setup-monitoring-cron.sh
   ```
3. Test new configuration:
   ```bash
   python3 scripts/monitoring-dashboard.py --json
   ```

## Security Considerations

1. **Log File Permissions**: Ensure monitoring logs are not world-readable
2. **Certificate Access**: Limit access to SSL certificate files
3. **Cron Security**: Run monitoring as non-root user when possible
4. **Network Security**: Monitor for SSL/TLS vulnerabilities
5. **Alert Security**: Secure alerting endpoints and credentials

## Performance Impact

The monitoring system is designed to be lightweight:
- Health checks: ~1-2 seconds per run
- HTTPS monitoring: ~5-10 seconds per domain
- SSL monitoring: ~2-5 seconds per certificate
- Dashboard aggregation: ~10-20 seconds total

Cron scheduling ensures minimal system impact while providing comprehensive coverage.
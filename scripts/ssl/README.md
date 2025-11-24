# SSL Certificate Management Scripts

This directory contains essential scripts for managing SSL certificates for the Timeweb deployment of the insurance system.

## Overview

The SSL certificate management system provides automated certificate obtainment, renewal, and monitoring for all domains:
- `insflow.ru` (main domain)
- `zs.insflow.ru` (Django application subdomain)
- `insflow.tw1.su` (technical domain mirror)
- `zs.insflow.tw1.su` (technical subdomain mirror)

## Scripts

### 1. `obtain-certificates.sh`
**Purpose**: Initial obtainment of Let's Encrypt certificates for all domains.

**Usage**:
```bash
sudo ./obtain-certificates.sh
```

**Features**:
- Obtains certificates for both primary and technical domains
- Uses standalone mode (stops nginx temporarily)
- Verifies DNS resolution before attempting certificate generation
- Validates certificates after obtainment
- Comprehensive logging and error handling

**Requirements**:
- Must run as root
- Certbot must be installed
- DNS records must be properly configured
- Docker compose file must be available

### 2. `renew-certificates.sh`
**Purpose**: Automatic renewal of Let's Encrypt certificates.

**Usage**:
```bash
sudo ./renew-certificates.sh [options]
```

**Options**:
- `--dry-run`: Test renewal without actually renewing
- `--force-restart`: Force nginx restart even if no renewal occurred
- `--help, -h`: Show help message

**Features**:
- Automatic certificate renewal using certbot
- Stops/starts nginx container during renewal
- Runs post-renewal hooks
- Verifies certificates after renewal
- Handles renewal status detection
- Comprehensive error handling and logging

### 3. `check-certificates.sh`
**Purpose**: Check the validity and expiration status of SSL certificates.

**Usage**:
```bash
./check-certificates.sh [options]
```

**Options**:
- `--quiet, -q`: Minimal output (logs only)
- `--verbose, -v`: Detailed output (default)
- `--help, -h`: Show help message

**Features**:
- Checks certificate expiration dates
- Verifies certificate chains
- Tests SSL connections to domains
- Provides detailed certificate information
- Color-coded status output
- Configurable warning thresholds (7 days critical, 30 days warning)

**Exit Codes**:
- `0`: All certificates are valid
- `1`: Some certificates have warnings
- `2`: Critical issues found

### 4. `post-renewal-hook.sh`
**Purpose**: Post-renewal actions (runs automatically after successful renewal).

**Features**:
- Updates certificate file permissions
- Reloads nginx configuration
- Tests SSL endpoints
- Ensures proper certificate deployment

### 5. `ssl-cron-setup.sh`
**Purpose**: Setup automated cron jobs for SSL certificate management.

**Usage**:
```bash
sudo ./ssl-cron-setup.sh [options]
```

**Options**:
- `--no-systemd`: Skip systemd service creation
- `--help, -h`: Show help message

**Features**:
- Makes all SSL scripts executable
- Sets up cron jobs for automated operations
- Configures log rotation
- Optional systemd service creation
- Verifies setup and tests scripts

**Cron Schedule**:
- **Certificate renewal**: Daily at 2:00 AM
- **Certificate check**: Daily at 6:00 AM  
- **SSL monitoring**: Every 4 hours
- **Weekly comprehensive check**: Sundays at 3:00 AM

### 6. `monitor-ssl-status.sh`
**Purpose**: Comprehensive SSL status monitoring and alerting.

**Usage**:
```bash
./monitor-ssl-status.sh [options]
```

**Options**:
- `--quiet, -q`: Minimal output (logs only)
- `--json`: Output only JSON status
- `--help, -h`: Show help message

**Features**:
- Monitors all domain SSL certificates
- Checks HTTPS redirects
- Verifies domain availability
- Generates JSON status reports
- Configurable alert thresholds
- Comprehensive logging and alerting

**Output**:
- Console report with color-coded status
- JSON status file (`/tmp/ssl-status.json`)
- Detailed logs in `/var/log/ssl-monitoring.log`
- Alert logs in `/var/log/ssl-alerts.log`



## Installation and Setup

### 1. Initial Setup
```bash
# Make setup script executable
chmod +x scripts/ssl/ssl-cron-setup.sh

# Run setup (as root)
sudo scripts/ssl/ssl-cron-setup.sh
```

### 2. Obtain Initial Certificates
```bash
# Ensure DNS is configured first, then:
sudo scripts/ssl/obtain-certificates.sh
```

### 3. Verify Setup
```bash
# Check certificate status
scripts/ssl/check-certificates.sh

# Monitor SSL status
scripts/ssl/monitor-ssl-status.sh

# Test renewal (dry run)
sudo scripts/ssl/renew-certificates.sh --dry-run
```

## Configuration

### Environment Variables
The scripts use the following configuration (can be modified in each script):

```bash
# Email for Let's Encrypt registration
EMAIL="admin@insflow.ru"

# Domain groups
DOMAINS_PRIMARY="insflow.ru,zs.insflow.ru"
DOMAINS_TECHNICAL="insflow.tw1.su,zs.insflow.tw1.su"

# Alert thresholds
ALERT_DAYS=7        # Critical alert threshold
WARNING_DAYS=30     # Warning threshold

# Paths
CERT_PATH="/etc/letsencrypt/live"
LOG_FILE="/var/log/ssl-certificates.log"
DOCKER_COMPOSE_FILE="/opt/insflow-system/docker-compose.yml"
```

### Log Files
- **Certificate operations**: `/var/log/ssl-certificates.log`
- **SSL monitoring**: `/var/log/ssl-monitoring.log`
- **SSL alerts**: `/var/log/ssl-alerts.log`

### Log Rotation
Automatic log rotation is configured for all SSL logs:
- **Rotation**: Daily
- **Retention**: 30 days
- **Compression**: Enabled (delayed)

## Troubleshooting

### Common Issues

1. **Certificate obtainment fails**:
   - Check DNS resolution: `nslookup domain.com`
   - Verify port 80/443 accessibility
   - Check nginx container status
   - Review logs in `/var/log/ssl-certificates.log`

2. **Renewal fails**:
   - Run dry-run test: `sudo scripts/ssl/renew-certificates.sh --dry-run`
   - Check certificate expiration: `scripts/ssl/check-certificates.sh`
   - Verify docker-compose file path

3. **Monitoring alerts**:
   - Check certificate status: `scripts/ssl/check-certificates.sh`
   - Verify domain accessibility
   - Review alert logs: `/var/log/ssl-alerts.log`

### Manual Operations

```bash
# Force certificate renewal
sudo scripts/ssl/renew-certificates.sh --force-restart

# Check specific certificate
openssl x509 -in /etc/letsencrypt/live/insflow.ru/cert.pem -noout -dates

# Test SSL connection
openssl s_client -connect insflow.ru:443 -servername insflow.ru

# View cron jobs
crontab -l | grep ssl

# Check systemd timer status
systemctl status ssl-monitor.timer
```

## Security Considerations

1. **File Permissions**: Scripts automatically set appropriate permissions for certificate files
2. **Root Access**: Certificate operations require root privileges
3. **Log Security**: Logs may contain sensitive information - ensure proper access controls
4. **Network Security**: Scripts perform network operations - ensure firewall allows HTTPS traffic

## Integration with Docker

The scripts are designed to work with the Docker-based deployment:
- Automatically stops/starts nginx container during certificate operations
- Uses docker-compose commands for container management
- Handles certificate volume mounting
- Supports both development and production environments

## Monitoring and Alerting

The monitoring system provides multiple levels of alerting:

- **INFO**: Normal operations and successful checks
- **WARNING**: Certificates expiring within 30 days
- **CRITICAL**: Certificates expiring within 7 days or already expired
- **ERROR**: System errors, connection failures, or missing certificates

Future enhancements can include:
- Email notifications
- Slack/webhook integrations
- Prometheus metrics export
- Dashboard integration

## Maintenance

### Regular Tasks
- Review logs weekly for any issues
- Verify cron jobs are running: `systemctl status cron`
- Check disk space for log files
- Update scripts as needed for new requirements

### Updates
When updating scripts:
1. Test in development environment first
2. Backup existing scripts
3. Update and test individual scripts
4. Verify cron jobs still work
5. Monitor logs after deployment

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review log files for detailed error information
3. Test individual components manually
4. Verify system requirements and dependencies
# Timeweb Deployment Scripts

This directory contains scripts for managing the Timeweb HTTPS deployment.

## Available Scripts

### Deployment and Management

- `deploy-timeweb.sh` - **Main deployment script** with certificate detection and automatic configuration selection
- `health-check.sh` - Comprehensive health checks for services, database, application, and HTTPS functionality
- `system-monitor.sh` - System monitoring with resource usage, performance metrics, and alerting

### Certificate Management

- `obtain-certificates.sh` - Obtain Let's Encrypt certificates for all configured domains
- `setup-certificate-renewal.sh` - Set up automatic certificate renewal via cron
- `monitor-certificates.sh` - Monitor SSL certificate status and expiry dates

### Configuration Management

- `configure-nginx.sh` - Configure nginx with SSL detection and security settings
- `validate-nginx-config.sh` - Validate nginx configuration before applying changes
- `setup-ssl-security.sh` - Configure SSL security settings and headers

## Usage Examples

### Initial Deployment
```bash
# Full automatic deployment (recommended)
./deploy-timeweb.sh

# Force HTTP-only deployment
./deploy-timeweb.sh --http-only

# Deploy with staging certificates for testing
./deploy-timeweb.sh --staging

# Force SSL deployment (fail if no certificates)
./deploy-timeweb.sh --force-ssl
```

### Health Monitoring
```bash
# Basic service health check
./health-check.sh

# Comprehensive health check
./health-check.sh --all

# HTTPS-specific health checks
./health-check.sh --https

# JSON output for monitoring systems
./health-check.sh --all --json

# Quiet mode for scripts (exit codes only)
./health-check.sh --all --quiet
```

### System Monitoring
```bash
# Single monitoring check
./system-monitor.sh

# Continuous monitoring every 30 seconds
./system-monitor.sh --continuous --interval 30

# Monitor for 1 hour with detailed metrics
./system-monitor.sh --continuous --duration 3600 --metrics

# Enable alerting for critical issues
./system-monitor.sh --continuous --alerts

# JSON output for external monitoring systems
./system-monitor.sh --json --metrics
```

### Certificate Management
```bash
# Obtain certificates for all domains
./obtain-certificates.sh

# Check certificate status
./monitor-certificates.sh

# Check certificate expiry with alerts
./monitor-certificates.sh --check-expiry --alert

# Force certificate renewal
./obtain-certificates.sh --force-renewal

# Set up automatic renewal
./setup-certificate-renewal.sh
```

### Configuration Management
```bash
# Configure nginx with SSL
./configure-nginx.sh

# Validate nginx configuration
./validate-nginx-config.sh

# Set up SSL security settings
./setup-ssl-security.sh
```

## Script Features

### deploy-timeweb.sh
- **Automatic SSL detection** - Detects available certificates and chooses appropriate configuration
- **Fallback mechanisms** - Automatically falls back to HTTP if SSL is not available
- **Health validation** - Performs comprehensive health checks after deployment
- **Configuration selection** - Automatically configures environment based on SSL availability
- **Comprehensive logging** - Detailed logging of all deployment steps

### health-check.sh
- **Multi-layer checks** - Services, database, application, and HTTPS functionality
- **Flexible options** - Check specific components or everything
- **Multiple output formats** - Human-readable, JSON, or quiet mode
- **Exit codes** - Proper exit codes for integration with monitoring systems
- **Detailed reporting** - Comprehensive health reports with actionable information

### system-monitor.sh
- **Resource monitoring** - CPU, memory, disk usage tracking
- **Performance metrics** - Response time monitoring for HTTP/HTTPS endpoints
- **Service monitoring** - Docker container and service health tracking
- **Alerting system** - Configurable thresholds with alert notifications
- **Continuous monitoring** - Support for ongoing monitoring with configurable intervals

### monitor-certificates.sh
- **Expiry monitoring** - Tracks certificate expiration dates
- **Health validation** - Tests HTTPS connectivity and SSL validity
- **Alert thresholds** - Configurable warning and critical thresholds
- **Multiple output formats** - Human-readable or JSON output
- **Integration ready** - Designed for integration with external monitoring systems

## Environment Variables

All scripts use the following environment variables from the `.env` file:

### Required Variables
- `DOCKER_IMAGE` - Docker image to deploy
- `DB_NAME` - Database name
- `DB_USER` - Database user
- `DB_PASSWORD` - Database password

### SSL Configuration
- `DOMAINS` - Comma-separated list of domains for SSL certificates
- `SSL_EMAIL` - Email address for Let's Encrypt registration
- `CERTBOT_STAGING` - Set to 'true' for testing with staging certificates

### HTTPS Settings
- `ENABLE_HTTPS` - Enable HTTPS functionality (True/False)
- `SSL_REDIRECT` - Enable HTTP to HTTPS redirects (True/False)
- `SECURE_COOKIES` - Enable secure cookie settings (True/False)
- `HSTS_SECONDS` - HSTS header duration in seconds

### Optional Configuration
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts
- `SSL_VOLUME_TYPE` - Volume type for SSL certificates (volume/bind)
- `SSL_CERTIFICATES_PATH` - Path for SSL certificates (when using bind mounts)

## Logging

All scripts log their activities to the `../logs/` directory:

### Deployment Logs
- `deployment.log` - Main deployment script activities
- `health-check.log` - Health check results and issues
- `system-monitoring.log` - System monitoring data and alerts

### Certificate Logs
- `certificate-acquisition.log` - Certificate obtaining and renewal activities
- `certificate-monitoring.log` - Certificate status monitoring

### Configuration Logs
- `nginx-configuration.log` - Nginx configuration changes

## Monitoring Integration

### Health Check Integration
The health check script provides multiple output formats for integration:
- **Exit codes**: 0 (healthy), 1 (unhealthy), 2 (critical failure)
- **JSON output**: Structured data for monitoring systems
- **Quiet mode**: Minimal output for automated scripts

### System Monitor Integration
The system monitor supports:
- **Webhook alerts**: Configure `ALERT_WEBHOOK_URL` for external notifications
- **Email alerts**: Configure `ALERT_EMAIL` for email notifications
- **JSON metrics**: Structured output for metrics collection systems
- **Configurable thresholds**: Adjust alert thresholds via script variables

### Certificate Monitor Integration
Certificate monitoring provides:
- **Expiry alerts**: Configurable warning and critical thresholds
- **JSON status**: Machine-readable certificate status information
- **Health validation**: HTTPS connectivity testing

## Error Handling

Scripts implement comprehensive error handling and will:
1. **Validate prerequisites** - Check for required tools and configurations
2. **Log all activities** - Comprehensive logging to appropriate log files
3. **Provide clear messages** - User-friendly error messages and guidance
4. **Use proper exit codes** - Standard exit codes for script integration
5. **Implement fallbacks** - Graceful degradation when possible
6. **Clean up resources** - Automatic cleanup of temporary files and processes

## Security Considerations

- **Input validation** - All scripts validate input parameters and environment variables
- **Secure handling** - Certificate private keys and sensitive data are handled securely
- **Minimal permissions** - Scripts run with minimal required permissions
- **Temporary cleanup** - Automatic cleanup of temporary files and sensitive data
- **Logging security** - Sensitive information is not logged in plain text
- **Network security** - HTTPS validation and secure communication protocols

## Troubleshooting

### Common Issues

1. **Certificate acquisition fails**
   - Check domain DNS configuration
   - Verify nginx is accessible on port 80
   - Check firewall settings
   - Review certificate acquisition logs

2. **Health checks fail**
   - Verify all services are running: `docker compose ps`
   - Check service logs: `docker compose logs [service]`
   - Validate environment configuration
   - Review health check logs

3. **HTTPS not working**
   - Verify certificates exist and are valid
   - Check nginx configuration: `./validate-nginx-config.sh`
   - Test certificate renewal: `./obtain-certificates.sh --force-renewal`
   - Review SSL configuration logs

4. **Performance issues**
   - Monitor system resources: `./system-monitor.sh --metrics`
   - Check application logs for errors
   - Verify database connectivity
   - Review performance metrics in monitoring logs

## Requirements Compliance

This deployment and monitoring system fulfills the following requirements:

- **Requirement 4.1**: Comprehensive deployment documentation and scripts
- **Requirement 4.2**: Certificate detection and automatic configuration selection
- **Requirement 4.3**: Monitoring and health check scripts that work with HTTPS
- **Requirement 4.4**: Clear error messages and debugging steps
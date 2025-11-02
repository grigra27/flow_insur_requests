#!/usr/bin/env python3
"""
SSL Monitoring and Logging System
Integrates with existing SSL scripts and provides comprehensive logging
"""
import sys
import os
import json
import logging
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

# Configure logging for SSL events
class SSLEventLogger:
    """Specialized logger for SSL-related events"""
    
    def __init__(self):
        self.setup_logging()
        
    def setup_logging(self):
        """Setup specialized SSL logging"""
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        # SSL-specific logger
        self.ssl_logger = logging.getLogger('ssl_events')
        self.ssl_logger.setLevel(logging.INFO)
        
        # SSL log file handler
        ssl_handler = logging.FileHandler('logs/ssl_events.log')
        ssl_formatter = logging.Formatter(
            '%(asctime)s - SSL - %(levelname)s - %(message)s'
        )
        ssl_handler.setFormatter(ssl_formatter)
        self.ssl_logger.addHandler(ssl_handler)
        
        # Certificate expiry logger
        self.cert_logger = logging.getLogger('certificate_expiry')
        self.cert_logger.setLevel(logging.INFO)
        
        cert_handler = logging.FileHandler('logs/certificate_expiry.log')
        cert_formatter = logging.Formatter(
            '%(asctime)s - CERT - %(levelname)s - %(message)s'
        )
        cert_handler.setFormatter(cert_formatter)
        self.cert_logger.addHandler(cert_handler)
        
        # Security events logger
        self.security_logger = logging.getLogger('security_events')
        self.security_logger.setLevel(logging.INFO)
        
        security_handler = logging.FileHandler('logs/security_events.log')
        security_formatter = logging.Formatter(
            '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
        )
        security_handler.setFormatter(security_formatter)
        self.security_logger.addHandler(security_handler)
    
    def log_ssl_event(self, event_type: str, domain: str, message: str, level: str = 'info'):
        """Log SSL-related events"""
        log_message = f"[{event_type}] {domain}: {message}"
        
        if level == 'error':
            self.ssl_logger.error(log_message)
        elif level == 'warning':
            self.ssl_logger.warning(log_message)
        else:
            self.ssl_logger.info(log_message)
    
    def log_certificate_event(self, domain: str, days_until_expiry: int, status: str):
        """Log certificate expiry events"""
        if status == 'expired':
            self.cert_logger.error(f"{domain}: Certificate EXPIRED {abs(days_until_expiry)} days ago")
        elif status == 'critical':
            self.cert_logger.error(f"{domain}: Certificate expires in {days_until_expiry} days (CRITICAL)")
        elif status == 'warning':
            self.cert_logger.warning(f"{domain}: Certificate expires in {days_until_expiry} days")
        else:
            self.cert_logger.info(f"{domain}: Certificate valid for {days_until_expiry} more days")
    
    def log_security_event(self, domain: str, event: str, details: str = ""):
        """Log security-related events"""
        message = f"{domain}: {event}"
        if details:
            message += f" - {details}"
        self.security_logger.info(message)

class SSLMonitoringSystem:
    """Comprehensive SSL monitoring system"""
    
    def __init__(self):
        self.logger = SSLEventLogger()
        self.domains = self._get_domains()
        self.scripts_dir = Path('scripts/ssl')
        
        # Monitoring configuration
        self.check_interval = int(os.getenv('SSL_CHECK_INTERVAL', '3600'))  # 1 hour default
        self.alert_days = int(os.getenv('SSL_ALERT_DAYS', '7'))
        self.warning_days = int(os.getenv('SSL_WARNING_DAYS', '30'))
        
    def _get_domains(self) -> List[str]:
        """Get list of domains to monitor"""
        main_domains = os.getenv('MAIN_DOMAINS', 'insflow.ru,insflow.tw1.su').split(',')
        subdomains = os.getenv('SUBDOMAINS', 'zs.insflow.ru,zs.insflow.tw1.su').split(',')
        
        all_domains = []
        for domain in main_domains + subdomains:
            domain = domain.strip()
            if domain:
                all_domains.append(domain)
        
        return all_domains
    
    def run_ssl_status_check(self) -> Dict:
        """Run the existing SSL status monitoring script"""
        try:
            script_path = self.scripts_dir / 'monitor-ssl-status.sh'
            
            if not script_path.exists():
                self.logger.log_ssl_event('SCRIPT_ERROR', 'system', 
                                        f'SSL monitoring script not found: {script_path}', 'error')
                return {'error': 'SSL monitoring script not found'}
            
            # Run the script in JSON mode
            result = subprocess.run(
                [str(script_path), '--json'],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode == 0:
                try:
                    status_data = json.loads(result.stdout)
                    self.logger.log_ssl_event('SCRIPT_SUCCESS', 'system', 
                                            'SSL status check completed successfully')
                    return status_data
                except json.JSONDecodeError as e:
                    self.logger.log_ssl_event('SCRIPT_ERROR', 'system', 
                                            f'Failed to parse SSL script output: {e}', 'error')
                    return {'error': f'Failed to parse script output: {e}'}
            else:
                error_msg = result.stderr or 'Unknown error'
                self.logger.log_ssl_event('SCRIPT_ERROR', 'system', 
                                        f'SSL script failed with code {result.returncode}: {error_msg}', 'error')
                return {'error': f'Script failed: {error_msg}'}
                
        except subprocess.TimeoutExpired:
            self.logger.log_ssl_event('SCRIPT_ERROR', 'system', 
                                    'SSL monitoring script timed out', 'error')
            return {'error': 'Script execution timed out'}
        except Exception as e:
            self.logger.log_ssl_event('SCRIPT_ERROR', 'system', 
                                    f'Failed to run SSL script: {e}', 'error')
            return {'error': f'Failed to run script: {e}'}
    
    def check_certificate_renewal_status(self) -> Dict:
        """Check if certificates need renewal"""
        renewal_status = {
            'timestamp': datetime.now().isoformat(),
            'domains': {},
            'renewal_needed': [],
            'renewal_critical': []
        }
        
        for domain in self.domains:
            try:
                # Check certificate expiry using openssl
                cert_path = f'/etc/letsencrypt/live/{domain}/cert.pem'
                
                if os.path.exists(cert_path):
                    result = subprocess.run(
                        ['openssl', 'x509', '-in', cert_path, '-noout', '-enddate'],
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        # Parse expiry date
                        end_date_str = result.stdout.strip().split('=')[1]
                        end_date = datetime.strptime(end_date_str, '%b %d %H:%M:%S %Y %Z')
                        days_until_expiry = (end_date - datetime.now()).days
                        
                        domain_status = {
                            'cert_path': cert_path,
                            'end_date': end_date.isoformat(),
                            'days_until_expiry': days_until_expiry,
                            'status': 'valid'
                        }
                        
                        # Determine renewal status
                        if days_until_expiry <= self.alert_days:
                            domain_status['status'] = 'critical'
                            renewal_status['renewal_critical'].append(domain)
                            self.logger.log_certificate_event(domain, days_until_expiry, 'critical')
                        elif days_until_expiry <= self.warning_days:
                            domain_status['status'] = 'warning'
                            renewal_status['renewal_needed'].append(domain)
                            self.logger.log_certificate_event(domain, days_until_expiry, 'warning')
                        else:
                            self.logger.log_certificate_event(domain, days_until_expiry, 'valid')
                        
                        renewal_status['domains'][domain] = domain_status
                    else:
                        error_msg = f'Failed to read certificate: {result.stderr}'
                        renewal_status['domains'][domain] = {
                            'error': error_msg,
                            'status': 'error'
                        }
                        self.logger.log_ssl_event('CERT_READ_ERROR', domain, error_msg, 'error')
                else:
                    error_msg = f'Certificate file not found: {cert_path}'
                    renewal_status['domains'][domain] = {
                        'error': error_msg,
                        'status': 'missing'
                    }
                    self.logger.log_ssl_event('CERT_MISSING', domain, error_msg, 'error')
                    
            except Exception as e:
                error_msg = f'Certificate check failed: {e}'
                renewal_status['domains'][domain] = {
                    'error': error_msg,
                    'status': 'error'
                }
                self.logger.log_ssl_event('CERT_CHECK_ERROR', domain, error_msg, 'error')
        
        return renewal_status
    
    def trigger_certificate_renewal(self, domains: List[str] = None) -> Dict:
        """Trigger certificate renewal for specified domains"""
        if domains is None:
            domains = self.domains
        
        renewal_results = {
            'timestamp': datetime.now().isoformat(),
            'domains': {},
            'overall_success': True
        }
        
        for domain in domains:
            try:
                self.logger.log_ssl_event('RENEWAL_START', domain, 'Starting certificate renewal')
                
                # Run certbot renewal for specific domain
                result = subprocess.run(
                    ['certbot', 'renew', '--cert-name', domain, '--quiet'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode == 0:
                    renewal_results['domains'][domain] = {
                        'status': 'success',
                        'message': 'Certificate renewed successfully'
                    }
                    self.logger.log_ssl_event('RENEWAL_SUCCESS', domain, 'Certificate renewed successfully')
                else:
                    error_msg = result.stderr or 'Unknown renewal error'
                    renewal_results['domains'][domain] = {
                        'status': 'failed',
                        'error': error_msg
                    }
                    renewal_results['overall_success'] = False
                    self.logger.log_ssl_event('RENEWAL_FAILED', domain, f'Renewal failed: {error_msg}', 'error')
                    
            except subprocess.TimeoutExpired:
                error_msg = 'Certificate renewal timed out'
                renewal_results['domains'][domain] = {
                    'status': 'failed',
                    'error': error_msg
                }
                renewal_results['overall_success'] = False
                self.logger.log_ssl_event('RENEWAL_TIMEOUT', domain, error_msg, 'error')
            except Exception as e:
                error_msg = f'Renewal process failed: {e}'
                renewal_results['domains'][domain] = {
                    'status': 'failed',
                    'error': error_msg
                }
                renewal_results['overall_success'] = False
                self.logger.log_ssl_event('RENEWAL_ERROR', domain, error_msg, 'error')
        
        return renewal_results
    
    def run_comprehensive_monitoring(self) -> Dict:
        """Run comprehensive SSL monitoring"""
        self.logger.log_ssl_event('MONITORING_START', 'system', 'Starting comprehensive SSL monitoring')
        
        monitoring_results = {
            'timestamp': datetime.now().isoformat(),
            'ssl_status': {},
            'renewal_status': {},
            'overall_health': 'unknown'
        }
        
        # Run SSL status check
        ssl_status = self.run_ssl_status_check()
        monitoring_results['ssl_status'] = ssl_status
        
        # Check certificate renewal status
        renewal_status = self.check_certificate_renewal_status()
        monitoring_results['renewal_status'] = renewal_status
        
        # Determine overall health
        critical_issues = len(renewal_status.get('renewal_critical', []))
        ssl_errors = 'error' in ssl_status
        
        if critical_issues > 0 or ssl_errors:
            monitoring_results['overall_health'] = 'critical'
            self.logger.log_ssl_event('HEALTH_CRITICAL', 'system', 
                                    f'Critical SSL issues detected: {critical_issues} critical certificates, SSL errors: {ssl_errors}', 'error')
        elif len(renewal_status.get('renewal_needed', [])) > 0:
            monitoring_results['overall_health'] = 'warning'
            self.logger.log_ssl_event('HEALTH_WARNING', 'system', 
                                    f'SSL warnings detected: {len(renewal_status.get("renewal_needed", []))} certificates need attention', 'warning')
        else:
            monitoring_results['overall_health'] = 'healthy'
            self.logger.log_ssl_event('HEALTH_OK', 'system', 'All SSL certificates are healthy')
        
        # Save results
        self._save_monitoring_results(monitoring_results)
        
        self.logger.log_ssl_event('MONITORING_COMPLETE', 'system', 
                                f'SSL monitoring completed with status: {monitoring_results["overall_health"]}')
        
        return monitoring_results
    
    def _save_monitoring_results(self, results: Dict):
        """Save monitoring results to file"""
        try:
            os.makedirs('logs', exist_ok=True)
            with open('logs/ssl_monitoring_comprehensive.json', 'w') as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            self.logger.log_ssl_event('SAVE_ERROR', 'system', f'Failed to save monitoring results: {e}', 'error')
    
    def generate_monitoring_report(self, results: Dict = None) -> str:
        """Generate human-readable monitoring report"""
        if results is None:
            try:
                with open('logs/ssl_monitoring_comprehensive.json', 'r') as f:
                    results = json.load(f)
            except Exception as e:
                return f"Error loading monitoring results: {e}"
        
        report = []
        report.append("=== SSL MONITORING SYSTEM REPORT ===")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Data from: {results['timestamp']}")
        report.append(f"Overall Health: {results['overall_health'].upper()}")
        report.append("")
        
        # Certificate renewal status
        renewal = results.get('renewal_status', {})
        if renewal:
            report.append("=== CERTIFICATE STATUS ===")
            
            critical = renewal.get('renewal_critical', [])
            needed = renewal.get('renewal_needed', [])
            
            if critical:
                report.append(f"🚨 CRITICAL - Certificates expiring soon: {', '.join(critical)}")
            
            if needed:
                report.append(f"⚠️  WARNING - Certificates need attention: {', '.join(needed)}")
            
            if not critical and not needed:
                report.append("✅ All certificates are healthy")
            
            report.append("")
            
            # Domain details
            for domain, info in renewal.get('domains', {}).items():
                status_icon = "✅" if info.get('status') == 'valid' else "❌"
                report.append(f"{status_icon} {domain}")
                
                if 'days_until_expiry' in info:
                    report.append(f"   Expires in: {info['days_until_expiry']} days")
                if 'error' in info:
                    report.append(f"   Error: {info['error']}")
                    
            report.append("")
        
        # SSL status
        ssl_status = results.get('ssl_status', {})
        if ssl_status and 'error' not in ssl_status:
            report.append("=== SSL STATUS ===")
            
            if 'domains' in ssl_status:
                for domain_info in ssl_status['domains']:
                    domain = domain_info.get('domain', 'Unknown')
                    status = domain_info.get('status', 'unknown')
                    
                    status_icon = "✅" if status == 'valid' else "❌"
                    report.append(f"{status_icon} {domain}: {status}")
            
            report.append("")
        
        return "\n".join(report)

def main():
    """Main function"""
    monitoring_system = SSLMonitoringSystem()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--continuous':
            # Continuous monitoring mode
            print("Starting continuous SSL monitoring...")
            
            while True:
                try:
                    results = monitoring_system.run_comprehensive_monitoring()
                    
                    # Check if we need to trigger renewal
                    renewal_critical = results.get('renewal_status', {}).get('renewal_critical', [])
                    if renewal_critical:
                        print(f"Triggering renewal for critical certificates: {', '.join(renewal_critical)}")
                        renewal_results = monitoring_system.trigger_certificate_renewal(renewal_critical)
                        
                        if renewal_results['overall_success']:
                            print("Certificate renewal completed successfully")
                        else:
                            print("Certificate renewal had some failures")
                    
                    print(f"Sleeping for {monitoring_system.check_interval} seconds...")
                    time.sleep(monitoring_system.check_interval)
                    
                except KeyboardInterrupt:
                    print("Monitoring stopped by user")
                    break
                except Exception as e:
                    print(f"Monitoring error: {e}")
                    time.sleep(60)  # Wait 1 minute before retrying
                    
        elif sys.argv[1] == '--report':
            # Generate and print report
            results = monitoring_system.run_comprehensive_monitoring()
            print(monitoring_system.generate_monitoring_report(results))
            
        elif sys.argv[1] == '--renew':
            # Trigger certificate renewal
            if len(sys.argv) > 2:
                domains = sys.argv[2].split(',')
            else:
                domains = None
            
            results = monitoring_system.trigger_certificate_renewal(domains)
            print(json.dumps(results, indent=2))
            
        elif sys.argv[1] == '--json':
            # Output JSON results
            results = monitoring_system.run_comprehensive_monitoring()
            print(json.dumps(results, indent=2))
            
        else:
            print("Usage: ssl-monitoring-system.py [--continuous|--report|--renew [domains]|--json]")
            sys.exit(1)
    else:
        # Single monitoring run
        results = monitoring_system.run_comprehensive_monitoring()
        print(monitoring_system.generate_monitoring_report(results))
        
        # Exit with appropriate code based on health
        if results['overall_health'] == 'critical':
            sys.exit(2)
        elif results['overall_health'] == 'warning':
            sys.exit(1)
        else:
            sys.exit(0)

if __name__ == "__main__":
    main()
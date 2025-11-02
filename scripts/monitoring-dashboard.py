#!/usr/bin/env python3
"""
Unified Monitoring Dashboard for HTTPS Infrastructure
Integrates health checks, SSL monitoring, and domain monitoring
"""
import sys
import os
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/monitoring_dashboard.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class MonitoringDashboard:
    """Unified monitoring dashboard for all system components"""
    
    def __init__(self):
        self.ensure_logs_directory()
        self.scripts_dir = Path('scripts')
        
    def ensure_logs_directory(self):
        """Ensure logs directory exists"""
        os.makedirs('logs', exist_ok=True)
    
    def run_health_checks(self) -> Dict:
        """Run Django application health checks"""
        try:
            logger.info("Running health checks...")
            
            result = subprocess.run(
                [sys.executable, 'healthcheck.py'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Try to load health check status from JSON file
            status_file = Path('logs/healthcheck_status.json')
            if status_file.exists():
                with open(status_file, 'r') as f:
                    health_data = json.load(f)
            else:
                # Fallback to basic status
                health_data = {
                    'timestamp': datetime.now().isoformat(),
                    'overall_status': 'healthy' if result.returncode == 0 else 'unhealthy',
                    'exit_code': result.returncode,
                    'output': result.stdout,
                    'error': result.stderr
                }
            
            logger.info(f"Health checks completed with status: {health_data.get('overall_status', 'unknown')}")
            return health_data
            
        except subprocess.TimeoutExpired:
            logger.error("Health check timed out")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'error',
                'error': 'Health check timed out'
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'error',
                'error': str(e)
            }
    
    def run_https_monitoring(self) -> Dict:
        """Run HTTPS domain monitoring"""
        try:
            logger.info("Running HTTPS monitoring...")
            
            script_path = self.scripts_dir / 'monitor-domains-https.py'
            
            if not script_path.exists():
                logger.error(f"HTTPS monitoring script not found: {script_path}")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'error': 'HTTPS monitoring script not found'
                }
            
            result = subprocess.run(
                [sys.executable, str(script_path), '--json'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode in [0, 1, 2]:  # 0=success, 1=warnings, 2=critical
                try:
                    https_data = json.loads(result.stdout)
                    logger.info("HTTPS monitoring completed successfully")
                    return https_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse HTTPS monitoring output: {e}")
                    return {
                        'timestamp': datetime.now().isoformat(),
                        'error': f'Failed to parse output: {e}',
                        'raw_output': result.stdout
                    }
            else:
                logger.error(f"HTTPS monitoring failed with exit code {result.returncode}")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'error': f'HTTPS monitoring failed: {result.stderr}',
                    'exit_code': result.returncode
                }
                
        except subprocess.TimeoutExpired:
            logger.error("HTTPS monitoring timed out")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': 'HTTPS monitoring timed out'
            }
        except Exception as e:
            logger.error(f"HTTPS monitoring failed: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def run_ssl_monitoring(self) -> Dict:
        """Run SSL certificate monitoring"""
        try:
            logger.info("Running SSL monitoring...")
            
            script_path = self.scripts_dir / 'ssl-monitoring-system.py'
            
            if not script_path.exists():
                logger.error(f"SSL monitoring script not found: {script_path}")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'error': 'SSL monitoring script not found'
                }
            
            result = subprocess.run(
                [sys.executable, str(script_path), '--json'],
                capture_output=True,
                text=True,
                timeout=180
            )
            
            if result.returncode in [0, 1, 2]:  # 0=healthy, 1=warning, 2=critical
                try:
                    ssl_data = json.loads(result.stdout)
                    logger.info("SSL monitoring completed successfully")
                    return ssl_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse SSL monitoring output: {e}")
                    return {
                        'timestamp': datetime.now().isoformat(),
                        'error': f'Failed to parse output: {e}',
                        'raw_output': result.stdout
                    }
            else:
                logger.error(f"SSL monitoring failed with exit code {result.returncode}")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'error': f'SSL monitoring failed: {result.stderr}',
                    'exit_code': result.returncode
                }
                
        except subprocess.TimeoutExpired:
            logger.error("SSL monitoring timed out")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': 'SSL monitoring timed out'
            }
        except Exception as e:
            logger.error(f"SSL monitoring failed: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def run_comprehensive_monitoring(self) -> Dict:
        """Run all monitoring components and generate comprehensive report"""
        logger.info("Starting comprehensive monitoring...")
        
        dashboard_data = {
            'timestamp': datetime.now().isoformat(),
            'health_checks': {},
            'https_monitoring': {},
            'ssl_monitoring': {},
            'overall_status': 'unknown',
            'summary': {
                'total_checks': 0,
                'passed_checks': 0,
                'warning_checks': 0,
                'failed_checks': 0
            }
        }
        
        # Run health checks
        dashboard_data['health_checks'] = self.run_health_checks()
        
        # Run HTTPS monitoring
        dashboard_data['https_monitoring'] = self.run_https_monitoring()
        
        # Run SSL monitoring
        dashboard_data['ssl_monitoring'] = self.run_ssl_monitoring()
        
        # Calculate overall status
        self._calculate_overall_status(dashboard_data)
        
        # Save dashboard data
        self._save_dashboard_data(dashboard_data)
        
        logger.info(f"Comprehensive monitoring completed with status: {dashboard_data['overall_status']}")
        
        return dashboard_data
    
    def _calculate_overall_status(self, dashboard_data: Dict):
        """Calculate overall system status based on all monitoring components"""
        summary = dashboard_data['summary']
        
        # Health checks
        health_status = dashboard_data['health_checks'].get('overall_status', 'error')
        if health_status == 'healthy':
            summary['passed_checks'] += 1
        elif health_status == 'warning':
            summary['warning_checks'] += 1
        else:
            summary['failed_checks'] += 1
        summary['total_checks'] += 1
        
        # HTTPS monitoring
        https_data = dashboard_data['https_monitoring']
        if 'error' not in https_data and 'summary' in https_data:
            https_summary = https_data['summary']
            total_domains = https_summary.get('total_domains', 0)
            healthy_domains = https_summary.get('healthy_domains', 0)
            
            if total_domains > 0:
                if healthy_domains == total_domains:
                    summary['passed_checks'] += 1
                elif healthy_domains > 0:
                    summary['warning_checks'] += 1
                else:
                    summary['failed_checks'] += 1
            else:
                summary['failed_checks'] += 1
        else:
            summary['failed_checks'] += 1
        summary['total_checks'] += 1
        
        # SSL monitoring
        ssl_data = dashboard_data['ssl_monitoring']
        if 'error' not in ssl_data and 'overall_health' in ssl_data:
            ssl_health = ssl_data['overall_health']
            if ssl_health == 'healthy':
                summary['passed_checks'] += 1
            elif ssl_health == 'warning':
                summary['warning_checks'] += 1
            else:
                summary['failed_checks'] += 1
        else:
            summary['failed_checks'] += 1
        summary['total_checks'] += 1
        
        # Determine overall status
        if summary['failed_checks'] > 0:
            dashboard_data['overall_status'] = 'critical'
        elif summary['warning_checks'] > 0:
            dashboard_data['overall_status'] = 'warning'
        else:
            dashboard_data['overall_status'] = 'healthy'
    
    def _save_dashboard_data(self, dashboard_data: Dict):
        """Save dashboard data to JSON file"""
        try:
            with open('logs/monitoring_dashboard.json', 'w') as f:
                json.dump(dashboard_data, f, indent=2)
            logger.info("Dashboard data saved successfully")
        except Exception as e:
            logger.error(f"Failed to save dashboard data: {e}")
    
    def generate_dashboard_report(self, dashboard_data: Dict = None) -> str:
        """Generate human-readable dashboard report"""
        if dashboard_data is None:
            try:
                with open('logs/monitoring_dashboard.json', 'r') as f:
                    dashboard_data = json.load(f)
            except Exception as e:
                return f"Error loading dashboard data: {e}"
        
        report = []
        report.append("=" * 60)
        report.append("🔍 INSFLOW INFRASTRUCTURE MONITORING DASHBOARD")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Data from: {dashboard_data['timestamp']}")
        report.append("")
        
        # Overall status
        status = dashboard_data['overall_status']
        status_icon = {
            'healthy': '✅',
            'warning': '⚠️',
            'critical': '🚨',
            'unknown': '❓'
        }.get(status, '❓')
        
        report.append(f"🎯 OVERALL STATUS: {status_icon} {status.upper()}")
        report.append("")
        
        # Summary
        summary = dashboard_data['summary']
        report.append("📊 SUMMARY")
        report.append("-" * 20)
        report.append(f"Total checks: {summary['total_checks']}")
        report.append(f"✅ Passed: {summary['passed_checks']}")
        report.append(f"⚠️  Warnings: {summary['warning_checks']}")
        report.append(f"❌ Failed: {summary['failed_checks']}")
        report.append("")
        
        # Health checks
        report.append("🏥 HEALTH CHECKS")
        report.append("-" * 20)
        health_data = dashboard_data['health_checks']
        
        if 'error' in health_data:
            report.append(f"❌ Error: {health_data['error']}")
        else:
            health_status = health_data.get('overall_status', 'unknown')
            health_icon = '✅' if health_status == 'healthy' else '❌'
            report.append(f"{health_icon} Status: {health_status}")
            
            if 'results' in health_data:
                for result in health_data['results']:
                    domain = result.get('domain', 'unknown')
                    status = result.get('status', False)
                    result_icon = '✅' if status else '❌'
                    report.append(f"  {result_icon} {domain}")
        
        report.append("")
        
        # HTTPS monitoring
        report.append("🔒 HTTPS MONITORING")
        report.append("-" * 20)
        https_data = dashboard_data['https_monitoring']
        
        if 'error' in https_data:
            report.append(f"❌ Error: {https_data['error']}")
        elif 'summary' in https_data:
            https_summary = https_data['summary']
            total = https_summary.get('total_domains', 0)
            healthy = https_summary.get('healthy_domains', 0)
            ssl_issues = https_summary.get('ssl_issues', 0)
            
            report.append(f"📈 Domains: {healthy}/{total} healthy")
            
            if ssl_issues > 0:
                report.append(f"🚨 SSL issues: {ssl_issues}")
            
            # Domain details
            if 'domains' in https_data:
                for domain, data in https_data['domains'].items():
                    domain_icon = '✅' if data.get('overall_healthy', False) else '❌'
                    report.append(f"  {domain_icon} {domain}")
        
        report.append("")
        
        # SSL monitoring
        report.append("🔐 SSL CERTIFICATE MONITORING")
        report.append("-" * 20)
        ssl_data = dashboard_data['ssl_monitoring']
        
        if 'error' in ssl_data:
            report.append(f"❌ Error: {ssl_data['error']}")
        else:
            ssl_health = ssl_data.get('overall_health', 'unknown')
            ssl_icon = {
                'healthy': '✅',
                'warning': '⚠️',
                'critical': '🚨'
            }.get(ssl_health, '❓')
            
            report.append(f"{ssl_icon} Overall health: {ssl_health}")
            
            # Certificate details
            renewal_status = ssl_data.get('renewal_status', {})
            if renewal_status:
                critical = renewal_status.get('renewal_critical', [])
                needed = renewal_status.get('renewal_needed', [])
                
                if critical:
                    report.append(f"🚨 Critical renewals needed: {', '.join(critical)}")
                if needed:
                    report.append(f"⚠️  Renewals needed: {', '.join(needed)}")
                if not critical and not needed:
                    report.append("✅ All certificates healthy")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def generate_json_report(self, dashboard_data: Dict = None) -> str:
        """Generate JSON report for API consumption"""
        if dashboard_data is None:
            try:
                with open('logs/monitoring_dashboard.json', 'r') as f:
                    dashboard_data = json.load(f)
            except Exception as e:
                return json.dumps({'error': f'Failed to load dashboard data: {e}'})
        
        return json.dumps(dashboard_data, indent=2)

def main():
    """Main function"""
    dashboard = MonitoringDashboard()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--json':
            # JSON output mode
            dashboard_data = dashboard.run_comprehensive_monitoring()
            print(dashboard.generate_json_report(dashboard_data))
            
        elif sys.argv[1] == '--report':
            # Generate report from latest data
            print(dashboard.generate_dashboard_report())
            
        elif sys.argv[1] == '--health-only':
            # Run only health checks
            health_data = dashboard.run_health_checks()
            print(json.dumps(health_data, indent=2))
            
        elif sys.argv[1] == '--https-only':
            # Run only HTTPS monitoring
            https_data = dashboard.run_https_monitoring()
            print(json.dumps(https_data, indent=2))
            
        elif sys.argv[1] == '--ssl-only':
            # Run only SSL monitoring
            ssl_data = dashboard.run_ssl_monitoring()
            print(json.dumps(ssl_data, indent=2))
            
        else:
            print("Usage: monitoring-dashboard.py [--json|--report|--health-only|--https-only|--ssl-only]")
            sys.exit(1)
    else:
        # Default: run comprehensive monitoring and show report
        dashboard_data = dashboard.run_comprehensive_monitoring()
        print(dashboard.generate_dashboard_report(dashboard_data))
        
        # Exit with appropriate code
        status = dashboard_data['overall_status']
        if status == 'critical':
            sys.exit(2)
        elif status == 'warning':
            sys.exit(1)
        else:
            sys.exit(0)

if __name__ == "__main__":
    main()
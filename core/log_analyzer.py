"""
Log analysis and monitoring utilities
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


class LogAnalyzer:
    """Analyze application logs for performance and security insights"""
    
    def __init__(self, log_dir=None):
        self.log_dir = Path(log_dir or settings.BASE_DIR / 'logs')
        self.patterns = {
            'slow_request': re.compile(r'Slow request.*duration: ([\d.]+)s.*path: ([^\s]+)'),
            'file_upload': re.compile(r'File upload.*content_length: (\d+).*duration: ([\d.]+)'),
            'security_event': re.compile(r'\[SECURITY\].*?(Suspicious|Failed|Error).*?ip: ([^\s]+)'),
            'error': re.compile(r'ERROR.*?(\w+Error|Exception).*?line (\d+)'),
            'performance': re.compile(r'\[PERFORMANCE\].*?duration: ([\d.]+)s.*?path: ([^\s]+)')
        }
    
    def analyze_performance_logs(self, hours=24):
        """Analyze performance logs for the last N hours"""
        log_file = self.log_dir / 'performance.log'
        if not log_file.exists():
            return {}
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        slow_requests = []
        request_times = defaultdict(list)
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    # Parse timestamp
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match:
                        continue
                    
                    try:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if log_time < cutoff_time:
                            continue
                    except ValueError:
                        continue
                    
                    # Analyze slow requests
                    slow_match = self.patterns['slow_request'].search(line)
                    if slow_match:
                        duration = float(slow_match.group(1))
                        path = slow_match.group(2)
                        slow_requests.append({
                            'timestamp': log_time,
                            'duration': duration,
                            'path': path
                        })
                        request_times[path].append(duration)
        
        except Exception as e:
            logger.error(f"Error analyzing performance logs: {e}")
            return {}
        
        # Calculate statistics
        analysis = {
            'slow_requests_count': len(slow_requests),
            'slowest_requests': sorted(slow_requests, key=lambda x: x['duration'], reverse=True)[:10],
            'slow_endpoints': {},
            'average_response_times': {}
        }
        
        # Analyze by endpoint
        for path, times in request_times.items():
            if times:
                analysis['slow_endpoints'][path] = {
                    'count': len(times),
                    'avg_time': sum(times) / len(times),
                    'max_time': max(times),
                    'min_time': min(times)
                }
                analysis['average_response_times'][path] = sum(times) / len(times)
        
        return analysis
    
    def analyze_security_logs(self, hours=24):
        """Analyze security logs for threats and suspicious activity"""
        log_file = self.log_dir / 'security.log'
        if not log_file.exists():
            return {}
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        security_events = []
        ip_addresses = Counter()
        event_types = Counter()
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    # Parse timestamp
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match:
                        continue
                    
                    try:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if log_time < cutoff_time:
                            continue
                    except ValueError:
                        continue
                    
                    # Analyze security events
                    security_match = self.patterns['security_event'].search(line)
                    if security_match:
                        event_type = security_match.group(1)
                        ip_address = security_match.group(2)
                        
                        security_events.append({
                            'timestamp': log_time,
                            'event_type': event_type,
                            'ip_address': ip_address,
                            'raw_line': line.strip()
                        })
                        
                        ip_addresses[ip_address] += 1
                        event_types[event_type] += 1
        
        except Exception as e:
            logger.error(f"Error analyzing security logs: {e}")
            return {}
        
        return {
            'total_security_events': len(security_events),
            'recent_events': security_events[-20:],  # Last 20 events
            'top_suspicious_ips': ip_addresses.most_common(10),
            'event_type_distribution': dict(event_types),
            'high_risk_ips': [ip for ip, count in ip_addresses.items() if count > 10]
        }
    
    def analyze_file_upload_logs(self, hours=24):
        """Analyze file upload performance and issues"""
        log_file = self.log_dir / 'file_uploads.log'
        if not log_file.exists():
            return {}
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        uploads = []
        upload_sizes = []
        upload_durations = []
        failed_uploads = []
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    # Parse timestamp
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match:
                        continue
                    
                    try:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if log_time < cutoff_time:
                            continue
                    except ValueError:
                        continue
                    
                    # Analyze file uploads
                    upload_match = self.patterns['file_upload'].search(line)
                    if upload_match:
                        size = int(upload_match.group(1))
                        duration = float(upload_match.group(2))
                        
                        upload_info = {
                            'timestamp': log_time,
                            'size': size,
                            'duration': duration,
                            'speed': size / duration if duration > 0 else 0
                        }
                        
                        uploads.append(upload_info)
                        upload_sizes.append(size)
                        upload_durations.append(duration)
                        
                        # Check for failed uploads (indicated by error in line)
                        if 'ERROR' in line or 'Failed' in line:
                            failed_uploads.append(upload_info)
        
        except Exception as e:
            logger.error(f"Error analyzing file upload logs: {e}")
            return {}
        
        if not uploads:
            return {'message': 'No file uploads found in the specified time period'}
        
        return {
            'total_uploads': len(uploads),
            'failed_uploads': len(failed_uploads),
            'success_rate': (len(uploads) - len(failed_uploads)) / len(uploads) * 100,
            'average_upload_size': sum(upload_sizes) / len(upload_sizes),
            'average_upload_duration': sum(upload_durations) / len(upload_durations),
            'largest_upload': max(upload_sizes),
            'slowest_upload': max(upload_durations),
            'recent_failed_uploads': failed_uploads[-10:],
            'upload_speed_stats': {
                'avg_speed': sum(u['speed'] for u in uploads) / len(uploads),
                'min_speed': min(u['speed'] for u in uploads),
                'max_speed': max(u['speed'] for u in uploads)
            }
        }
    
    def analyze_error_logs(self, hours=24):
        """Analyze error logs for common issues"""
        log_file = self.log_dir / 'errors.log'
        if not log_file.exists():
            return {}
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        errors = []
        error_types = Counter()
        error_locations = Counter()
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    # Parse timestamp
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match:
                        continue
                    
                    try:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if log_time < cutoff_time:
                            continue
                    except ValueError:
                        continue
                    
                    # Analyze errors
                    error_match = self.patterns['error'].search(line)
                    if error_match:
                        error_type = error_match.group(1)
                        line_number = error_match.group(2)
                        
                        errors.append({
                            'timestamp': log_time,
                            'error_type': error_type,
                            'line_number': line_number,
                            'raw_line': line.strip()
                        })
                        
                        error_types[error_type] += 1
                        error_locations[f"line {line_number}"] += 1
        
        except Exception as e:
            logger.error(f"Error analyzing error logs: {e}")
            return {}
        
        return {
            'total_errors': len(errors),
            'recent_errors': errors[-20:],
            'most_common_errors': error_types.most_common(10),
            'error_hotspots': error_locations.most_common(10),
            'error_rate': len(errors) / hours if hours > 0 else 0
        }
    
    def generate_monitoring_report(self, hours=24):
        """Generate a comprehensive monitoring report"""
        report = {
            'report_generated': datetime.now().isoformat(),
            'analysis_period_hours': hours,
            'performance': self.analyze_performance_logs(hours),
            'security': self.analyze_security_logs(hours),
            'file_uploads': self.analyze_file_upload_logs(hours),
            'errors': self.analyze_error_logs(hours)
        }
        
        # Add summary
        report['summary'] = {
            'total_slow_requests': report['performance'].get('slow_requests_count', 0),
            'total_security_events': report['security'].get('total_security_events', 0),
            'total_file_uploads': report['file_uploads'].get('total_uploads', 0),
            'file_upload_success_rate': report['file_uploads'].get('success_rate', 0),
            'total_errors': report['errors'].get('total_errors', 0),
            'error_rate_per_hour': report['errors'].get('error_rate', 0)
        }
        
        return report
    
    def save_report(self, report, filename=None):
        """Save monitoring report to file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"monitoring_report_{timestamp}.json"
        
        report_path = self.log_dir / filename
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            
            logger.info(f"Monitoring report saved to {report_path}")
            return str(report_path)
        
        except Exception as e:
            logger.error(f"Error saving monitoring report: {e}")
            return None


def get_log_analyzer():
    """Get a configured log analyzer instance"""
    return LogAnalyzer()


def generate_daily_report():
    """Generate and save a daily monitoring report"""
    analyzer = get_log_analyzer()
    report = analyzer.generate_monitoring_report(hours=24)
    return analyzer.save_report(report)


def generate_weekly_report():
    """Generate and save a weekly monitoring report"""
    analyzer = get_log_analyzer()
    report = analyzer.generate_monitoring_report(hours=168)  # 7 days
    return analyzer.save_report(report, f"weekly_report_{datetime.now().strftime('%Y%m%d')}.json")
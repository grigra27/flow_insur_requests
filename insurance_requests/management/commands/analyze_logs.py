"""
Management command for analyzing application logs
"""
import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from core.log_analyzer import LogAnalyzer


class Command(BaseCommand):
    help = 'Analyze application logs for performance, security, and operational insights'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Number of hours to analyze (default: 24)'
        )
        
        parser.add_argument(
            '--type',
            choices=['performance', 'security', 'uploads', 'errors', 'all'],
            default='all',
            help='Type of analysis to perform (default: all)'
        )
        
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path for the report (JSON format)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )
        
        parser.add_argument(
            '--summary-only',
            action='store_true',
            help='Show only summary information'
        )
    
    def handle(self, *args, **options):
        hours = options['hours']
        analysis_type = options['type']
        output_file = options['output']
        verbose = options['verbose']
        summary_only = options['summary_only']
        
        self.stdout.write(
            self.style.SUCCESS(f'Analyzing logs for the last {hours} hours...')
        )
        
        try:
            analyzer = LogAnalyzer()
            
            if analysis_type == 'all':
                report = analyzer.generate_monitoring_report(hours)
                self.display_full_report(report, verbose, summary_only)
            elif analysis_type == 'performance':
                report = analyzer.analyze_performance_logs(hours)
                self.display_performance_report(report, verbose)
            elif analysis_type == 'security':
                report = analyzer.analyze_security_logs(hours)
                self.display_security_report(report, verbose)
            elif analysis_type == 'uploads':
                report = analyzer.analyze_file_upload_logs(hours)
                self.display_upload_report(report, verbose)
            elif analysis_type == 'errors':
                report = analyzer.analyze_error_logs(hours)
                self.display_error_report(report, verbose)
            
            # Save to file if requested
            if output_file:
                if analysis_type == 'all':
                    analyzer.save_report(report, output_file)
                else:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(report, f, indent=2, default=str)
                
                self.stdout.write(
                    self.style.SUCCESS(f'Report saved to {output_file}')
                )
        
        except Exception as e:
            raise CommandError(f'Error analyzing logs: {e}')
    
    def display_full_report(self, report, verbose, summary_only):
        """Display the full monitoring report"""
        self.stdout.write(self.style.SUCCESS('\n=== MONITORING REPORT ==='))
        self.stdout.write(f"Report generated: {report['report_generated']}")
        self.stdout.write(f"Analysis period: {report['analysis_period_hours']} hours\n")
        
        # Display summary
        summary = report.get('summary', {})
        self.stdout.write(self.style.WARNING('SUMMARY:'))
        self.stdout.write(f"  Slow requests: {summary.get('total_slow_requests', 0)}")
        self.stdout.write(f"  Security events: {summary.get('total_security_events', 0)}")
        self.stdout.write(f"  File uploads: {summary.get('total_file_uploads', 0)}")
        self.stdout.write(f"  Upload success rate: {summary.get('file_upload_success_rate', 0):.1f}%")
        self.stdout.write(f"  Total errors: {summary.get('total_errors', 0)}")
        self.stdout.write(f"  Error rate/hour: {summary.get('error_rate_per_hour', 0):.2f}\n")
        
        if not summary_only:
            # Display detailed reports
            self.display_performance_report(report.get('performance', {}), verbose)
            self.display_security_report(report.get('security', {}), verbose)
            self.display_upload_report(report.get('file_uploads', {}), verbose)
            self.display_error_report(report.get('errors', {}), verbose)
    
    def display_performance_report(self, report, verbose):
        """Display performance analysis report"""
        if not report:
            return
        
        self.stdout.write(self.style.WARNING('\nPERFORMANCE ANALYSIS:'))
        self.stdout.write(f"  Slow requests: {report.get('slow_requests_count', 0)}")
        
        # Show slowest endpoints
        slow_endpoints = report.get('slow_endpoints', {})
        if slow_endpoints:
            self.stdout.write("  Slowest endpoints:")
            for path, stats in list(slow_endpoints.items())[:5]:
                self.stdout.write(f"    {path}: avg {stats['avg_time']:.3f}s (max: {stats['max_time']:.3f}s)")
        
        if verbose and report.get('slowest_requests'):
            self.stdout.write("  Recent slow requests:")
            for req in report['slowest_requests'][:5]:
                self.stdout.write(f"    {req['path']}: {req['duration']:.3f}s at {req['timestamp']}")
    
    def display_security_report(self, report, verbose):
        """Display security analysis report"""
        if not report:
            return
        
        self.stdout.write(self.style.WARNING('\nSECURITY ANALYSIS:'))
        self.stdout.write(f"  Total security events: {report.get('total_security_events', 0)}")
        
        # Show top suspicious IPs
        suspicious_ips = report.get('top_suspicious_ips', [])
        if suspicious_ips:
            self.stdout.write("  Top suspicious IPs:")
            for ip, count in suspicious_ips[:5]:
                self.stdout.write(f"    {ip}: {count} events")
        
        # Show event types
        event_types = report.get('event_type_distribution', {})
        if event_types:
            self.stdout.write("  Event types:")
            for event_type, count in event_types.items():
                self.stdout.write(f"    {event_type}: {count}")
        
        # Show high-risk IPs
        high_risk_ips = report.get('high_risk_ips', [])
        if high_risk_ips:
            self.stdout.write(self.style.ERROR(f"  HIGH RISK IPs: {', '.join(high_risk_ips)}"))
        
        if verbose and report.get('recent_events'):
            self.stdout.write("  Recent security events:")
            for event in report['recent_events'][-3:]:
                self.stdout.write(f"    {event['timestamp']}: {event['event_type']} from {event['ip_address']}")
    
    def display_upload_report(self, report, verbose):
        """Display file upload analysis report"""
        if not report:
            return
        
        if 'message' in report:
            self.stdout.write(self.style.WARNING(f"\nFILE UPLOADS: {report['message']}"))
            return
        
        self.stdout.write(self.style.WARNING('\nFILE UPLOAD ANALYSIS:'))
        self.stdout.write(f"  Total uploads: {report.get('total_uploads', 0)}")
        self.stdout.write(f"  Failed uploads: {report.get('failed_uploads', 0)}")
        self.stdout.write(f"  Success rate: {report.get('success_rate', 0):.1f}%")
        self.stdout.write(f"  Average size: {report.get('average_upload_size', 0) / 1024 / 1024:.1f} MB")
        self.stdout.write(f"  Average duration: {report.get('average_upload_duration', 0):.2f}s")
        
        speed_stats = report.get('upload_speed_stats', {})
        if speed_stats:
            avg_speed_mbps = speed_stats.get('avg_speed', 0) / 1024 / 1024
            self.stdout.write(f"  Average speed: {avg_speed_mbps:.2f} MB/s")
        
        if verbose and report.get('recent_failed_uploads'):
            self.stdout.write("  Recent failed uploads:")
            for upload in report['recent_failed_uploads'][-3:]:
                size_mb = upload['size'] / 1024 / 1024
                self.stdout.write(f"    {upload['timestamp']}: {size_mb:.1f}MB in {upload['duration']:.2f}s")
    
    def display_error_report(self, report, verbose):
        """Display error analysis report"""
        if not report:
            return
        
        self.stdout.write(self.style.WARNING('\nERROR ANALYSIS:'))
        self.stdout.write(f"  Total errors: {report.get('total_errors', 0)}")
        self.stdout.write(f"  Error rate: {report.get('error_rate', 0):.2f} errors/hour")
        
        # Show most common errors
        common_errors = report.get('most_common_errors', [])
        if common_errors:
            self.stdout.write("  Most common errors:")
            for error_type, count in common_errors[:5]:
                self.stdout.write(f"    {error_type}: {count}")
        
        # Show error hotspots
        hotspots = report.get('error_hotspots', [])
        if hotspots:
            self.stdout.write("  Error hotspots:")
            for location, count in hotspots[:5]:
                self.stdout.write(f"    {location}: {count}")
        
        if verbose and report.get('recent_errors'):
            self.stdout.write("  Recent errors:")
            for error in report['recent_errors'][-3:]:
                self.stdout.write(f"    {error['timestamp']}: {error['error_type']} at {error['line_number']}")
"""
Monitoring dashboard views for administrators
"""
import json
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from core.log_analyzer import LogAnalyzer
from core.log_management import LogManager


@staff_member_required
def monitoring_dashboard(request):
    """Main monitoring dashboard"""
    context = {
        'title': 'System Monitoring Dashboard',
        'current_time': datetime.now(),
    }
    return render(request, 'insurance_requests/monitoring_dashboard.html', context)


@staff_member_required
@cache_page(300)  # Cache for 5 minutes
def monitoring_api_summary(request):
    """API endpoint for monitoring summary data"""
    try:
        analyzer = LogAnalyzer()
        hours = int(request.GET.get('hours', 24))
        
        # Generate monitoring report
        report = analyzer.generate_monitoring_report(hours)
        
        # Prepare summary data for frontend
        summary_data = {
            'period_hours': hours,
            'generated_at': datetime.now().isoformat(),
            'metrics': {
                'slow_requests': report['performance'].get('slow_requests_count', 0),
                'security_events': report['security'].get('total_security_events', 0),
                'file_uploads': report['file_uploads'].get('total_uploads', 0),
                'upload_success_rate': report['file_uploads'].get('success_rate', 0),
                'total_errors': report['errors'].get('total_errors', 0),
                'error_rate': report['errors'].get('error_rate', 0)
            },
            'alerts': []
        }
        
        # Generate alerts based on thresholds
        if summary_data['metrics']['slow_requests'] > 10:
            summary_data['alerts'].append({
                'type': 'warning',
                'message': f"High number of slow requests: {summary_data['metrics']['slow_requests']}"
            })
        
        if summary_data['metrics']['security_events'] > 5:
            summary_data['alerts'].append({
                'type': 'danger',
                'message': f"Security events detected: {summary_data['metrics']['security_events']}"
            })
        
        if summary_data['metrics']['upload_success_rate'] < 95 and summary_data['metrics']['file_uploads'] > 0:
            summary_data['alerts'].append({
                'type': 'warning',
                'message': f"Low upload success rate: {summary_data['metrics']['upload_success_rate']:.1f}%"
            })
        
        if summary_data['metrics']['error_rate'] > 1:
            summary_data['alerts'].append({
                'type': 'danger',
                'message': f"High error rate: {summary_data['metrics']['error_rate']:.2f} errors/hour"
            })
        
        return JsonResponse(summary_data)
    
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating monitoring summary: {str(e)}'
        }, status=500)


@staff_member_required
@cache_page(300)
def monitoring_api_performance(request):
    """API endpoint for performance metrics"""
    try:
        analyzer = LogAnalyzer()
        hours = int(request.GET.get('hours', 24))
        
        performance_data = analyzer.analyze_performance_logs(hours)
        
        # Format data for charts
        chart_data = {
            'slow_endpoints': [],
            'response_times': []
        }
        
        # Top 10 slowest endpoints
        slow_endpoints = performance_data.get('slow_endpoints', {})
        for path, stats in list(slow_endpoints.items())[:10]:
            chart_data['slow_endpoints'].append({
                'endpoint': path,
                'avg_time': round(stats['avg_time'], 3),
                'max_time': round(stats['max_time'], 3),
                'count': stats['count']
            })
        
        # Recent slow requests for timeline
        slowest_requests = performance_data.get('slowest_requests', [])
        for req in slowest_requests[:20]:
            chart_data['response_times'].append({
                'timestamp': req['timestamp'].isoformat() if hasattr(req['timestamp'], 'isoformat') else str(req['timestamp']),
                'duration': req['duration'],
                'path': req['path']
            })
        
        return JsonResponse({
            'period_hours': hours,
            'total_slow_requests': performance_data.get('slow_requests_count', 0),
            'chart_data': chart_data
        })
    
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating performance data: {str(e)}'
        }, status=500)


@staff_member_required
@cache_page(300)
def monitoring_api_security(request):
    """API endpoint for security metrics"""
    try:
        analyzer = LogAnalyzer()
        hours = int(request.GET.get('hours', 24))
        
        security_data = analyzer.analyze_security_logs(hours)
        
        # Format data for charts
        chart_data = {
            'suspicious_ips': [],
            'event_types': [],
            'recent_events': []
        }
        
        # Top suspicious IPs
        for ip, count in security_data.get('top_suspicious_ips', [])[:10]:
            chart_data['suspicious_ips'].append({
                'ip': ip,
                'count': count
            })
        
        # Event type distribution
        event_types = security_data.get('event_type_distribution', {})
        for event_type, count in event_types.items():
            chart_data['event_types'].append({
                'type': event_type,
                'count': count
            })
        
        # Recent events
        for event in security_data.get('recent_events', [])[-10:]:
            chart_data['recent_events'].append({
                'timestamp': event['timestamp'].isoformat() if hasattr(event['timestamp'], 'isoformat') else str(event['timestamp']),
                'event_type': event['event_type'],
                'ip_address': event['ip_address']
            })
        
        return JsonResponse({
            'period_hours': hours,
            'total_events': security_data.get('total_security_events', 0),
            'high_risk_ips': security_data.get('high_risk_ips', []),
            'chart_data': chart_data
        })
    
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating security data: {str(e)}'
        }, status=500)


@staff_member_required
@cache_page(300)
def monitoring_api_uploads(request):
    """API endpoint for file upload metrics"""
    try:
        analyzer = LogAnalyzer()
        hours = int(request.GET.get('hours', 24))
        
        upload_data = analyzer.analyze_file_upload_logs(hours)
        
        if 'message' in upload_data:
            return JsonResponse({
                'period_hours': hours,
                'message': upload_data['message'],
                'chart_data': {}
            })
        
        # Format data for charts
        chart_data = {
            'upload_stats': {
                'total': upload_data.get('total_uploads', 0),
                'failed': upload_data.get('failed_uploads', 0),
                'success_rate': upload_data.get('success_rate', 0)
            },
            'size_stats': {
                'average_mb': round(upload_data.get('average_upload_size', 0) / 1024 / 1024, 2),
                'largest_mb': round(upload_data.get('largest_upload', 0) / 1024 / 1024, 2)
            },
            'performance_stats': {
                'avg_duration': round(upload_data.get('average_upload_duration', 0), 2),
                'slowest_duration': round(upload_data.get('slowest_upload', 0), 2),
                'avg_speed_mbps': round(upload_data.get('upload_speed_stats', {}).get('avg_speed', 0) / 1024 / 1024, 2)
            }
        }
        
        return JsonResponse({
            'period_hours': hours,
            'chart_data': chart_data
        })
    
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating upload data: {str(e)}'
        }, status=500)


@staff_member_required
@cache_page(300)
def monitoring_api_logs(request):
    """API endpoint for log file statistics"""
    try:
        manager = LogManager()
        stats = manager.get_log_file_stats()
        
        # Format data for frontend
        log_data = {
            'total_files': stats['total_files'],
            'total_size_mb': round(stats['total_size'] / 1024 / 1024, 2),
            'compressed_files': stats['compressed_files'],
            'uncompressed_files': stats['uncompressed_files'],
            'files_by_type': []
        }
        
        # Format files by type
        for log_type, type_stats in stats.get('files_by_type', {}).items():
            log_data['files_by_type'].append({
                'type': log_type,
                'count': type_stats['count'],
                'size_mb': round(type_stats['size'] / 1024 / 1024, 2)
            })
        
        # Add file age information
        if stats.get('oldest_file'):
            log_data['oldest_file'] = {
                'name': stats['oldest_file']['name'],
                'date': stats['oldest_file']['date'].isoformat() if hasattr(stats['oldest_file']['date'], 'isoformat') else str(stats['oldest_file']['date'])
            }
        
        if stats.get('largest_file'):
            log_data['largest_file'] = {
                'name': stats['largest_file']['name'],
                'size_mb': round(stats['largest_file']['size'] / 1024 / 1024, 2)
            }
        
        return JsonResponse(log_data)
    
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating log statistics: {str(e)}'
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def monitoring_api_maintenance(request):
    """API endpoint to trigger log maintenance"""
    try:
        manager = LogManager()
        stats = manager.perform_maintenance()
        
        return JsonResponse({
            'success': True,
            'message': 'Log maintenance completed successfully',
            'stats': stats
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error performing log maintenance: {str(e)}'
        }, status=500)
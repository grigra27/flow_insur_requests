"""
Enhanced logging middleware for comprehensive monitoring
"""
import time
import logging
import json
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponseServerError
import traceback

# Get specialized loggers
performance_logger = logging.getLogger('performance')
security_logger = logging.getLogger('security')
file_upload_logger = logging.getLogger('file_upload')


class SecurityLoggingMiddleware(MiddlewareMixin):
    """Middleware for logging security-related events"""
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.suspicious_patterns = [
            'admin', 'wp-admin', 'phpmyadmin', '.php', '.asp', '.jsp',
            'eval(', 'script>', '<script', 'javascript:', 'vbscript:',
            'onload=', 'onerror=', 'onclick=', '../', '..\\',
            'union select', 'drop table', 'insert into', 'delete from'
        ]
    
    def process_request(self, request):
        """Log security-relevant request information"""
        try:
            # Check for suspicious patterns in URL and parameters
            full_path = request.get_full_path().lower()
            suspicious_found = any(pattern in full_path for pattern in self.suspicious_patterns)
            
            if suspicious_found:
                security_logger.warning(
                    f"Suspicious request detected",
                    extra={
                        'ip': self.get_client_ip(request),
                        'method': request.method,
                        'path': request.path,
                        'full_path': request.get_full_path(),
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'referer': request.META.get('HTTP_REFERER', ''),
                        'user': str(request.user) if hasattr(request, 'user') else 'Anonymous'
                    }
                )
            
            # Log failed authentication attempts
            if request.path.startswith('/login/') and request.method == 'POST':
                security_logger.info(
                    f"Login attempt",
                    extra={
                        'ip': self.get_client_ip(request),
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'username': request.POST.get('username', 'unknown')
                    }
                )
        except Exception as e:
            # Don't let logging errors break the request
            security_logger.error(f"Error in security logging: {e}")
    
    def process_response(self, request, response):
        """Log security-relevant response information"""
        try:
            # Log 4xx and 5xx responses
            if response.status_code >= 400:
                level = logging.ERROR if response.status_code >= 500 else logging.WARNING
                security_logger.log(
                    level,
                    f"HTTP {response.status_code} response",
                    extra={
                        'ip': self.get_client_ip(request),
                        'method': request.method,
                        'path': request.path,
                        'status_code': response.status_code,
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'user': str(request.user) if hasattr(request, 'user') else 'Anonymous'
                    }
                )
            
            # Log successful logins
            if (request.path.startswith('/login/') and 
                request.method == 'POST' and 
                response.status_code in [200, 302]):
                security_logger.info(
                    f"Successful login",
                    extra={
                        'ip': self.get_client_ip(request),
                        'user': str(request.user) if hasattr(request, 'user') else 'Unknown',
                        'user_agent': request.META.get('HTTP_USER_AGENT', '')
                    }
                )
        except Exception as e:
            security_logger.error(f"Error in security response logging: {e}")
        
        return response
    
    def process_exception(self, request, exception):
        """Log security-related exceptions"""
        try:
            if isinstance(exception, SuspiciousOperation):
                security_logger.error(
                    f"Suspicious operation: {exception}",
                    extra={
                        'ip': self.get_client_ip(request),
                        'method': request.method,
                        'path': request.path,
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
                        'exception_type': type(exception).__name__,
                        'traceback': traceback.format_exc()
                    }
                )
        except Exception as e:
            security_logger.error(f"Error logging exception: {e}")
    
    def get_client_ip(self, request):
        """Get the real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class FileUploadLoggingMiddleware(MiddlewareMixin):
    """Middleware for monitoring file upload operations"""
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.upload_paths = ['/upload', '/media/upload', '/admin/']
        self.max_file_size = getattr(settings, 'FILE_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024)
    
    def process_request(self, request):
        """Monitor file upload requests"""
        try:
            # Check if this is a file upload request
            if (request.method == 'POST' and 
                any(path in request.path for path in self.upload_paths) and
                request.content_type and 'multipart/form-data' in request.content_type):
                
                content_length = request.META.get('CONTENT_LENGTH', 0)
                try:
                    content_length = int(content_length)
                except (ValueError, TypeError):
                    content_length = 0
                
                file_upload_logger.info(
                    f"File upload started",
                    extra={
                        'ip': self.get_client_ip(request),
                        'path': request.path,
                        'content_length': content_length,
                        'content_type': request.content_type,
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
                        'timestamp': time.time()
                    }
                )
                
                # Store start time for duration calculation
                request._upload_start_time = time.time()
                
                # Check file size limits
                if content_length > self.max_file_size:
                    file_upload_logger.warning(
                        f"File upload exceeds size limit",
                        extra={
                            'ip': self.get_client_ip(request),
                            'content_length': content_length,
                            'max_size': self.max_file_size,
                            'user': str(request.user) if hasattr(request, 'user') else 'Anonymous'
                        }
                    )
        except Exception as e:
            file_upload_logger.error(f"Error in upload request logging: {e}")
    
    def process_response(self, request, response):
        """Log file upload completion"""
        try:
            if hasattr(request, '_upload_start_time'):
                duration = time.time() - request._upload_start_time
                
                # Log upload completion
                level = logging.INFO if response.status_code < 400 else logging.ERROR
                file_upload_logger.log(
                    level,
                    f"File upload completed",
                    extra={
                        'ip': self.get_client_ip(request),
                        'path': request.path,
                        'status_code': response.status_code,
                        'duration': duration,
                        'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
                        'success': response.status_code < 400
                    }
                )
                
                # Log slow uploads
                if duration > 30:  # 30 seconds threshold
                    file_upload_logger.warning(
                        f"Slow file upload detected",
                        extra={
                            'ip': self.get_client_ip(request),
                            'duration': duration,
                            'path': request.path,
                            'user': str(request.user) if hasattr(request, 'user') else 'Anonymous'
                        }
                    )
        except Exception as e:
            file_upload_logger.error(f"Error in upload response logging: {e}")
        
        return response
    
    def get_client_ip(self, request):
        """Get the real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """Enhanced performance monitoring middleware"""
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.slow_request_threshold = getattr(settings, 'SLOW_REQUEST_THRESHOLD', 1.0)  # 1 second
        self.memory_threshold = getattr(settings, 'MEMORY_THRESHOLD', 100 * 1024 * 1024)  # 100MB
    
    def process_request(self, request):
        """Start performance monitoring"""
        request._performance_start_time = time.time()
        
        # Log high-traffic endpoints
        if request.path in ['/', '/admin/', '/upload/']:
            performance_logger.info(
                f"High-traffic endpoint accessed",
                extra={
                    'ip': self.get_client_ip(request),
                    'path': request.path,
                    'method': request.method,
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'user': str(request.user) if hasattr(request, 'user') else 'Anonymous'
                }
            )
    
    def process_response(self, request, response):
        """Log performance metrics"""
        try:
            if hasattr(request, '_performance_start_time'):
                duration = time.time() - request._performance_start_time
                
                # Log slow requests
                if duration > self.slow_request_threshold:
                    performance_logger.warning(
                        f"Slow request detected",
                        extra={
                            'ip': self.get_client_ip(request),
                            'method': request.method,
                            'path': request.path,
                            'duration': duration,
                            'status_code': response.status_code,
                            'response_size': len(response.content) if hasattr(response, 'content') else 0,
                            'user': str(request.user) if hasattr(request, 'user') else 'Anonymous'
                        }
                    )
                
                # Log performance metrics for all requests in debug mode
                if settings.DEBUG:
                    performance_logger.debug(
                        f"Request performance",
                        extra={
                            'method': request.method,
                            'path': request.path,
                            'duration': duration,
                            'status_code': response.status_code,
                            'response_size': len(response.content) if hasattr(response, 'content') else 0
                        }
                    )
        except Exception as e:
            performance_logger.error(f"Error in performance logging: {e}")
        
        return response
    
    def get_client_ip(self, request):
        """Get the real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
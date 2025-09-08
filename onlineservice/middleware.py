"""
Custom middleware for HTTPS security headers and configuration.
"""

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger('security')


class HTTPSSecurityMiddleware(MiddlewareMixin):
    """
    Middleware to add comprehensive HTTPS security headers and CSP.
    """
    
    def process_response(self, request, response):
        """
        Add comprehensive security headers to all responses.
        """
        # Add security headers in production or when explicitly enabled
        add_headers = (
            getattr(settings, 'SECURE_SSL_REDIRECT', False) or 
            getattr(settings, 'FORCE_SECURITY_HEADERS', False)
        )
        
        if add_headers:
            # Content Security Policy with comprehensive directives
            csp = self._get_content_security_policy(request)
            if csp:
                response['Content-Security-Policy'] = csp
                # Also add report-only version for monitoring
                csp_report_only = getattr(settings, 'SECURE_CONTENT_SECURITY_POLICY_REPORT_ONLY', None)
                if csp_report_only:
                    response['Content-Security-Policy-Report-Only'] = csp_report_only
            
            # HSTS with preload support
            hsts_seconds = getattr(settings, 'SECURE_HSTS_SECONDS', 0)
            if hsts_seconds > 0:
                hsts_header = f"max-age={hsts_seconds}"
                if getattr(settings, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', False):
                    hsts_header += "; includeSubDomains"
                if getattr(settings, 'SECURE_HSTS_PRELOAD', False):
                    hsts_header += "; preload"
                response['Strict-Transport-Security'] = hsts_header
            
            # X-Frame-Options with configurable value
            x_frame_options = getattr(settings, 'X_FRAME_OPTIONS', 'DENY')
            response['X-Frame-Options'] = x_frame_options
            
            # X-Content-Type-Options
            response['X-Content-Type-Options'] = 'nosniff'
            
            # X-XSS-Protection (legacy but still useful)
            response['X-XSS-Protection'] = '1; mode=block'
            
            # Referrer Policy
            referrer_policy = getattr(settings, 'SECURE_REFERRER_POLICY', 'strict-origin-when-cross-origin')
            response['Referrer-Policy'] = referrer_policy
            
            # Cross-Origin-Opener-Policy
            coop = getattr(settings, 'SECURE_CROSS_ORIGIN_OPENER_POLICY', 'same-origin')
            response['Cross-Origin-Opener-Policy'] = coop
            
            # Cross-Origin-Embedder-Policy
            coep = getattr(settings, 'SECURE_CROSS_ORIGIN_EMBEDDER_POLICY', None)
            if coep:
                response['Cross-Origin-Embedder-Policy'] = coep
            
            # Cross-Origin-Resource-Policy
            corp = getattr(settings, 'SECURE_CROSS_ORIGIN_RESOURCE_POLICY', None)
            if corp:
                response['Cross-Origin-Resource-Policy'] = corp
            
            # Permissions Policy for enhanced security
            permissions_policy = self._get_permissions_policy()
            if permissions_policy:
                response['Permissions-Policy'] = permissions_policy
            
            # Server header removal/modification
            server_header = getattr(settings, 'SECURE_SERVER_HEADER', None)
            if server_header is not None:
                if server_header:
                    response['Server'] = server_header
                else:
                    # Remove server header if it exists
                    if 'Server' in response:
                        del response['Server']
            
            # Clear-Site-Data header for logout pages
            if request.path in getattr(settings, 'CLEAR_SITE_DATA_PATHS', ['/logout/', '/admin/logout/']):
                response['Clear-Site-Data'] = '"cache", "cookies", "storage"'
        
        # CORS headers if configured
        self._add_cors_headers(request, response)
        
        return response
    
    def _get_content_security_policy(self, request):
        """
        Get Content Security Policy based on request context.
        """
        # Base CSP from settings
        base_csp = getattr(settings, 'SECURE_CONTENT_SECURITY_POLICY', None)
        if not base_csp:
            return None
        
        # Dynamic CSP based on request path
        if request.path.startswith('/admin/'):
            # More permissive CSP for admin interface
            admin_csp = getattr(settings, 'SECURE_CONTENT_SECURITY_POLICY_ADMIN', None)
            if admin_csp:
                return admin_csp
        
        # Check for nonce-based CSP
        nonce = getattr(request, 'csp_nonce', None)
        if nonce:
            # Replace 'unsafe-inline' with nonce for scripts and styles
            csp_with_nonce = base_csp.replace(
                "script-src 'self' 'unsafe-inline'",
                f"script-src 'self' 'nonce-{nonce}'"
            ).replace(
                "style-src 'self' 'unsafe-inline'",
                f"style-src 'self' 'nonce-{nonce}'"
            )
            return csp_with_nonce
        
        return base_csp
    
    def _get_permissions_policy(self):
        """
        Get Permissions Policy header value.
        """
        default_permissions = {
            'geolocation': '()',
            'microphone': '()',
            'camera': '()',
            'payment': '()',
            'usb': '()',
            'magnetometer': '()',
            'gyroscope': '()',
            'accelerometer': '()',
            'ambient-light-sensor': '()',
            'autoplay': '(self)',
            'encrypted-media': '(self)',
            'fullscreen': '(self)',
            'picture-in-picture': '()',
            'screen-wake-lock': '()',
            'web-share': '(self)',
        }
        
        # Allow customization via settings
        permissions = getattr(settings, 'SECURE_PERMISSIONS_POLICY', default_permissions)
        
        # Format as header value
        policy_parts = []
        for directive, allowlist in permissions.items():
            policy_parts.append(f"{directive}={allowlist}")
        
        return ', '.join(policy_parts)
    
    def _add_cors_headers(self, request, response):
        """
        Add CORS headers if configured.
        """
        cors_settings = getattr(settings, 'CORS_SETTINGS', {})
        if not cors_settings:
            return
        
        origin = request.META.get('HTTP_ORIGIN')
        if not origin:
            return
        
        # Check if origin is allowed
        allowed_origins = cors_settings.get('allowed_origins', [])
        allow_all_origins = cors_settings.get('allow_all_origins', False)
        
        if allow_all_origins or origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = str(
                cors_settings.get('allow_credentials', False)
            ).lower()
            
            # Handle preflight requests
            if request.method == 'OPTIONS':
                allowed_methods = cors_settings.get('allowed_methods', ['GET', 'POST', 'PUT', 'DELETE'])
                response['Access-Control-Allow-Methods'] = ', '.join(allowed_methods)
                
                allowed_headers = cors_settings.get('allowed_headers', ['Content-Type', 'Authorization'])
                response['Access-Control-Allow-Headers'] = ', '.join(allowed_headers)
                
                max_age = cors_settings.get('max_age', 86400)
                response['Access-Control-Max-Age'] = str(max_age)
            
            # Expose headers
            expose_headers = cors_settings.get('expose_headers', [])
            if expose_headers:
                response['Access-Control-Expose-Headers'] = ', '.join(expose_headers)


class CSPNonceMiddleware(MiddlewareMixin):
    """
    Middleware to generate and inject CSP nonces for inline scripts and styles.
    """
    
    def process_request(self, request):
        """
        Generate a unique nonce for this request.
        """
        import secrets
        import base64
        
        # Generate a cryptographically secure random nonce
        nonce_bytes = secrets.token_bytes(16)
        nonce = base64.b64encode(nonce_bytes).decode('ascii')
        
        # Store nonce in request for use in templates and CSP header
        request.csp_nonce = nonce
        
        # Log nonce generation for debugging (only in debug mode)
        if getattr(settings, 'DEBUG', False):
            logger.debug(f"Generated CSP nonce for {request.path}: {nonce}")
    
    def process_response(self, request, response):
        """
        Add nonce to response context if needed.
        """
        # Make nonce available in response for template context
        if hasattr(request, 'csp_nonce'):
            response['X-CSP-Nonce'] = request.csp_nonce
        
        return response
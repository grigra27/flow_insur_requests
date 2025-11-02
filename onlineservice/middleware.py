"""
Custom middleware for domain-based routing with HTTPS support.
"""
import logging
from django.http import Http404, HttpResponseBadRequest, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.conf import settings
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)


class DomainRoutingMiddleware:
    """
    Middleware for handling domain-based routing between main domains and subdomains with HTTPS support.
    
    Routes:
    - Main domains (insflow.ru, insflow.tw1.su) -> Landing page only
    - Subdomains (zs.insflow.ru, zs.insflow.tw1.su) -> Main application
    - Development domains (localhost, 127.0.0.1) -> Main application
    
    HTTPS Features:
    - Automatic HTTPS redirect for production domains when HTTPS is enabled
    - Proper SSL header handling for reverse proxy setups
    - Security logging for HTTPS-related events
    """
    
    # Paths allowed on main domains
    MAIN_DOMAIN_ALLOWED_PATHS = ['', 'landing', 'healthz', 'static', 'media']
    
    # Paths that should always be accessible over HTTP (for health checks, etc.)
    HTTP_ALLOWED_PATHS = ['healthz', 'health', '.well-known']
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Get domain configuration from settings
        self.main_domains = getattr(settings, 'MAIN_DOMAINS', ['insflow.tw1.su'])
        self.subdomains = getattr(settings, 'SUBDOMAINS', ['zs.insflow.tw1.su'])
        self.development_domains = getattr(settings, 'DEVELOPMENT_DOMAINS', ['localhost', '127.0.0.1', 'testserver'])
        
        # HTTPS configuration
        self.https_enabled = getattr(settings, 'ENABLE_HTTPS', False)
        self.ssl_redirect = getattr(settings, 'SECURE_SSL_REDIRECT', False)
        self.https_logging = getattr(settings, 'HTTPS_LOGGING_ENABLED', False)
        
        # All production domains (for HTTPS redirect logic)
        self.production_domains = self.main_domains + self.subdomains
        
        # Log configuration on startup
        logger.info(f"Domain routing initialized - Main domains: {self.main_domains}, Subdomains: {self.subdomains}")
        if self.https_enabled:
            logger.info(f"HTTPS enabled - SSL redirect: {self.ssl_redirect}, Production domains: {self.production_domains}")
        
    def __call__(self, request):
        # Get the host from the request
        host = request.get_host().lower()
        
        # Extract domain without port if present
        if ':' in host:
            host = host.split(':')[0]
        
        # Check if request is secure (HTTPS)
        is_secure = self._is_request_secure(request)
        
        # Log the request for monitoring
        protocol = 'https' if is_secure else 'http'
        if self.https_logging:
            logger.info(f"Domain routing: {protocol}://{host} -> {request.path}")
        
        # Handle HTTPS redirect for production domains
        if self._should_redirect_to_https(request, host, is_secure):
            return self._redirect_to_https(request, host)
        
        # Handle main domains routing (insflow.ru, insflow.tw1.su)
        if host in self.main_domains:
            return self._handle_main_domains(request)
        
        # Handle subdomains routing (zs.insflow.ru, zs.insflow.tw1.su)
        elif host in self.subdomains:
            return self._handle_subdomains(request)
        
        # Handle development domains
        elif host in self.development_domains:
            return self._handle_development(request)
        
        # Handle unknown domains
        else:
            return self._handle_unknown_domain(request, host)
            
    def _handle_main_domains(self, request):
        """Handle requests to main domains (insflow.ru, insflow.tw1.su)"""
        path = request.path.strip('/')
        
        # Extract first path segment for static files
        first_segment = path.split('/')[0] if path else ''
        
        if path == '' or path == 'landing':
            # Serve landing page for root and /landing/ paths
            # Add HTTPS context for template rendering
            context = {
                'is_secure': self._is_request_secure(request),
                'https_enabled': self.https_enabled
            }
            return render(request, 'landing/index.html', context)
        elif path == 'healthz':
            # Allow health check on main domains
            return self.get_response(request)
        elif first_segment == 'static' or first_segment == 'media':
            # Allow static and media files
            return self.get_response(request)
        else:
            # All other paths on main domains should return 404
            host = request.get_host().lower()
            if ':' in host:
                host = host.split(':')[0]
            
            protocol = 'https' if self._is_request_secure(request) else 'http'
            logger.warning(f"404 on main domain {protocol}://{host}: {request.path}")
            raise Http404("This page is not available on the main domain")
            
    def _handle_subdomains(self, request):
        """Handle requests to subdomains (zs.insflow.ru, zs.insflow.tw1.su)"""
        # For subdomains, serve normal application
        # Add HTTPS logging if enabled
        if self.https_logging and self.https_enabled:
            is_secure = self._is_request_secure(request)
            protocol = 'https' if is_secure else 'http'
            host = request.get_host().lower()
            if ':' in host:
                host = host.split(':')[0]
            logger.info(f"Subdomain access: {protocol}://{host}{request.path}")
        
        return self.get_response(request)
        
    def _handle_development(self, request):
        """Handle requests from development domains"""
        # For development, allow all requests to pass through normally
        return self.get_response(request)
        
    def _handle_unknown_domain(self, request, host):
        """Handle requests from unknown domains"""
        logger.warning(f"Request from unknown domain: {host}")
        
        # Check if domain is in ALLOWED_HOSTS
        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        if host not in allowed_hosts and '*' not in allowed_hosts:
            logger.error(f"Domain {host} not in ALLOWED_HOSTS: {allowed_hosts}")
            return HttpResponseBadRequest("Domain not allowed")
        
        # If domain is in ALLOWED_HOSTS but not recognized, treat as development
        return self.get_response(request)
    
    def _is_request_secure(self, request):
        """
        Determine if the request is secure (HTTPS).
        Handles both direct HTTPS and reverse proxy setups.
        """
        # Check if request is secure directly
        if request.is_secure():
            return True
        
        # Check X-Forwarded-Proto header (for reverse proxy setups like Nginx)
        forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '').lower()
        if forwarded_proto == 'https':
            return True
        
        # Check X-Forwarded-SSL header
        forwarded_ssl = request.META.get('HTTP_X_FORWARDED_SSL', '').lower()
        if forwarded_ssl in ('on', 'true', '1'):
            return True
        
        return False
    
    def _should_redirect_to_https(self, request, host, is_secure):
        """
        Determine if the request should be redirected to HTTPS.
        """
        # Don't redirect if HTTPS is not enabled or SSL redirect is disabled
        if not self.https_enabled or not self.ssl_redirect:
            return False
        
        # Don't redirect if already secure
        if is_secure:
            return False
        
        # Don't redirect development domains
        if host in self.development_domains:
            return False
        
        # Don't redirect certain paths that should remain accessible over HTTP
        path = request.path.strip('/')
        first_segment = path.split('/')[0] if path else ''
        
        if first_segment in self.HTTP_ALLOWED_PATHS or path in self.HTTP_ALLOWED_PATHS:
            return False
        
        # Redirect production domains to HTTPS
        return host in self.production_domains
    
    def _redirect_to_https(self, request, host):
        """
        Redirect the request to HTTPS.
        """
        https_url = f"https://{host}{request.get_full_path()}"
        
        if self.https_logging:
            logger.info(f"Redirecting to HTTPS: {request.build_absolute_uri()} -> {https_url}")
        
        return HttpResponsePermanentRedirect(https_url)


class HTTPSSecurityMiddleware(MiddlewareMixin):
    """
    Middleware to add HTTPS-specific security headers and handle SSL-related security.
    This middleware should be placed after DomainRoutingMiddleware in the middleware stack.
    """
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.https_enabled = getattr(settings, 'ENABLE_HTTPS', False)
        self.https_logging = getattr(settings, 'HTTPS_LOGGING_ENABLED', False)
        
    def process_response(self, request, response):
        """Add HTTPS security headers to responses when HTTPS is enabled."""
        
        if not self.https_enabled:
            return response
        
        # Only add headers for secure requests or when SSL redirect is enabled
        is_secure = self._is_request_secure(request)
        
        if is_secure:
            # Add security headers for HTTPS responses
            response['Strict-Transport-Security'] = self._get_hsts_header()
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = getattr(settings, 'SECURE_REFERRER_POLICY', 'strict-origin-when-cross-origin')
            
            # Add Content Security Policy if configured
            csp_header = self._build_csp_header()
            if csp_header:
                response['Content-Security-Policy'] = csp_header
            
            # Log HTTPS response if logging is enabled
            if self.https_logging:
                host = request.get_host().lower()
                if ':' in host:
                    host = host.split(':')[0]
                logger.info(f"HTTPS response: {host}{request.path} - Status: {response.status_code}")
        
        return response
    
    def _is_request_secure(self, request):
        """Check if request is secure (same logic as DomainRoutingMiddleware)."""
        if request.is_secure():
            return True
        
        forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '').lower()
        if forwarded_proto == 'https':
            return True
        
        forwarded_ssl = request.META.get('HTTP_X_FORWARDED_SSL', '').lower()
        if forwarded_ssl in ('on', 'true', '1'):
            return True
        
        return False
    
    def _get_hsts_header(self):
        """Build HSTS header value."""
        hsts_seconds = getattr(settings, 'SECURE_HSTS_SECONDS', 31536000)
        include_subdomains = getattr(settings, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
        preload = getattr(settings, 'SECURE_HSTS_PRELOAD', True)
        
        hsts_value = f'max-age={hsts_seconds}'
        
        if include_subdomains:
            hsts_value += '; includeSubDomains'
        
        if preload:
            hsts_value += '; preload'
        
        return hsts_value
    
    def _build_csp_header(self):
        """Build Content Security Policy header from settings."""
        csp_directives = []
        
        # Map of CSP directive names to settings
        csp_settings = {
            'default-src': 'CSP_DEFAULT_SRC',
            'script-src': 'CSP_SCRIPT_SRC',
            'style-src': 'CSP_STYLE_SRC',
            'img-src': 'CSP_IMG_SRC',
            'font-src': 'CSP_FONT_SRC',
            'connect-src': 'CSP_CONNECT_SRC',
            'frame-ancestors': 'CSP_FRAME_ANCESTORS',
        }
        
        for directive, setting_name in csp_settings.items():
            value = getattr(settings, setting_name, None)
            if value:
                csp_directives.append(f'{directive} {value}')
        
        return '; '.join(csp_directives) if csp_directives else None
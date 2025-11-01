"""
Custom middleware for domain-based routing.
"""
import logging
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render
from django.conf import settings


logger = logging.getLogger(__name__)


class DomainRoutingMiddleware:
    """
    Middleware for handling domain-based routing between main domain and subdomain.
    
    Routes:
    - insflow.tw1.su -> Landing page only
    - zs.insflow.tw1.su -> Main application
    - Development domains (localhost, 127.0.0.1) -> Main application
    """
    
    # Define allowed domains
    MAIN_DOMAIN = 'insflow.tw1.su'
    SUBDOMAIN = 'zs.insflow.tw1.su'
    DEVELOPMENT_DOMAINS = ['localhost', '127.0.0.1', 'testserver']
    
    # Paths allowed on main domain
    MAIN_DOMAIN_ALLOWED_PATHS = ['', 'landing', 'healthz', 'static']
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Get the host from the request
        host = request.get_host().lower()
        
        # Extract domain without port if present
        if ':' in host:
            host = host.split(':')[0]
            
        # Log the request for monitoring
        logger.info(f"Domain routing: {host} -> {request.path}")
        
        # Handle main domain routing
        if host == self.MAIN_DOMAIN:
            return self._handle_main_domain(request)
        
        # Handle subdomain routing
        elif host == self.SUBDOMAIN:
            return self._handle_subdomain(request)
        
        # Handle development domains
        elif host in self.DEVELOPMENT_DOMAINS:
            return self._handle_development(request)
        
        # Handle unknown domains
        else:
            return self._handle_unknown_domain(request, host)
            
    def _handle_main_domain(self, request):
        """Handle requests to the main domain (insflow.tw1.su)"""
        path = request.path.strip('/')
        
        # Extract first path segment for static files
        first_segment = path.split('/')[0] if path else ''
        
        if path == '' or path == 'landing':
            # Serve landing page for root and /landing/ paths
            return render(request, 'landing/index.html')
        elif path == 'healthz':
            # Allow health check on main domain
            return self.get_response(request)
        elif first_segment == 'static' or first_segment == 'media':
            # Allow static and media files
            return self.get_response(request)
        else:
            # All other paths on main domain should return 404
            logger.warning(f"404 on main domain: {request.path}")
            raise Http404("This page is not available on the main domain")
            
    def _handle_subdomain(self, request):
        """Handle requests to the subdomain (zs.insflow.tw1.su)"""
        # For subdomain, serve normal application
        # No special handling needed, let normal URL routing handle it
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
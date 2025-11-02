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
    Middleware for handling domain-based routing between main domains and subdomains.
    
    Routes:
    - Main domains (insflow.ru, insflow.tw1.su) -> Landing page only
    - Subdomains (zs.insflow.ru, zs.insflow.tw1.su) -> Main application
    - Development domains (localhost, 127.0.0.1) -> Main application
    """
    
    # Paths allowed on main domains
    MAIN_DOMAIN_ALLOWED_PATHS = ['', 'landing', 'healthz', 'static', 'media']
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Get domain configuration from settings
        self.main_domains = getattr(settings, 'MAIN_DOMAINS', ['insflow.tw1.su'])
        self.subdomains = getattr(settings, 'SUBDOMAINS', ['zs.insflow.tw1.su'])
        self.development_domains = getattr(settings, 'DEVELOPMENT_DOMAINS', ['localhost', '127.0.0.1', 'testserver'])
        
        # Log configuration on startup
        logger.info(f"Domain routing initialized - Main domains: {self.main_domains}, Subdomains: {self.subdomains}")
        
    def __call__(self, request):
        # Get the host from the request
        host = request.get_host().lower()
        
        # Extract domain without port if present
        if ':' in host:
            host = host.split(':')[0]
            
        # Log the request for monitoring
        logger.info(f"Domain routing: {host} -> {request.path}")
        
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
            return render(request, 'landing/index.html')
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
            logger.warning(f"404 on main domain {host}: {request.path}")
            raise Http404("This page is not available on the main domain")
            
    def _handle_subdomains(self, request):
        """Handle requests to subdomains (zs.insflow.ru, zs.insflow.tw1.su)"""
        # For subdomains, serve normal application
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
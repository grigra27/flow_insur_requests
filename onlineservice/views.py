"""
Views for the main onlineservice application.
"""
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)


def landing_view(request):
    """
    View function for serving the landing page.
    This view serves the corporate landing page for the main domain.
    """
    # Log landing page access
    client_ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
    
    logger.info(f"Landing page accessed from {client_ip} - User-Agent: {user_agent[:100]}")
    
    return render(request, 'landing/index.html')


@require_http_methods(["GET"])
@never_cache
def landing_health_check(request):
    """
    Health check endpoint specifically for the landing page.
    Returns JSON response with landing page status.
    """
    try:
        # Basic health check
        response_data = {
            'status': 'healthy',
            'service': 'landing_page',
            'timestamp': request.META.get('HTTP_DATE', 'unknown'),
            'domain': request.get_host()
        }
        
        logger.info(f"Landing health check OK from {get_client_ip(request)}")
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Landing health check failed: {e}")
        response_data = {
            'status': 'unhealthy',
            'service': 'landing_page',
            'error': str(e),
            'domain': request.get_host()
        }
        return JsonResponse(response_data, status=500)


def get_client_ip(request):
    """
    Get the client IP address from the request.
    Handles proxy headers properly.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return ip
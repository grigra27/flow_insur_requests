"""
URL configuration for onlineservice project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.http import HttpResponse
from insurance_requests.views import login_view, logout_view, access_denied_view
from .views import landing_view, landing_health_check


def domain_aware_redirect(request):
    """
    Redirect function that handles domain-aware routing.
    For subdomains, redirect to main app. For main domains, serve landing page.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    host = request.get_host().lower()
    if ':' in host:
        host = host.split(':')[0]
    
    logger.info(f"Domain aware redirect: {host} -> {request.path}")
    
    # Get domain configuration from settings
    main_domains = getattr(settings, 'MAIN_DOMAINS', ['insflow.tw1.su'])
    subdomains = getattr(settings, 'SUBDOMAINS', ['zs.insflow.tw1.su'])
    
    # If this is a main domain, serve landing page
    if host in main_domains:
        return landing_view(request)
    else:
        # For subdomains or development, redirect to main app
        try:
            return redirect('insurance_requests:request_list')
        except Exception as e:
            logger.error(f"Error redirecting to main app: {e}")
            # Fallback to a simple response
            from django.http import HttpResponse
            return HttpResponse("Application is available at the subdomain", status=200)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('access-denied/', access_denied_view, name='access_denied'),
    path('requests/', include('insurance_requests.urls')),
    path('summaries/', include('summaries.urls')),
    path('healthz/', lambda request: HttpResponse('OK'), name='health'),
    path('landing/', landing_view, name='landing'),
    path('landing/health/', landing_health_check, name='landing_health'),
    path('', domain_aware_redirect, name='home'),
]

# Custom error handlers
def custom_404_handler(request, exception):
    """Custom 404 handler that provides domain-specific error messages"""
    import logging
    logger = logging.getLogger(__name__)
    
    host = request.get_host().lower()
    if ':' in host:
        host = host.split(':')[0]
    
    logger.warning(f"404 error on {host}: {request.path}")
    
    # Get domain configuration from settings
    main_domains = getattr(settings, 'MAIN_DOMAINS', ['insflow.tw1.su'])
    subdomains = getattr(settings, 'SUBDOMAINS', ['zs.insflow.tw1.su'])
    
    if host in main_domains:
        # For main domains, suggest they use the corresponding subdomain
        # Determine the correct subdomain based on the main domain
        if host == 'insflow.ru':
            suggested_subdomain = 'zs.insflow.ru'
        elif host == 'insflow.tw1.su':
            suggested_subdomain = 'zs.insflow.tw1.su'
        else:
            # Fallback to first subdomain
            suggested_subdomain = subdomains[0] if subdomains else 'zs.insflow.tw1.su'
        
        from django.http import HttpResponseNotFound
        protocol = 'https' if request.is_secure() else 'http'
        return HttpResponseNotFound(
            f"<h1>Page Not Found</h1>"
            f"<p>This page is not available on the main domain.</p>"
            f"<p>Please visit <a href='{protocol}://{suggested_subdomain}'>{suggested_subdomain}</a> for the application.</p>"
        )
    else:
        # For subdomains, use default 404 handling
        from django.views.defaults import page_not_found
        return page_not_found(request, exception)

# Set custom error handler
handler404 = custom_404_handler

# Для разработки - обслуживание медиа и статических файлов
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

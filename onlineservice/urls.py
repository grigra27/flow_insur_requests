"""
URL configuration for onlineservice project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.http import JsonResponse
from insurance_requests.views import login_view, logout_view, access_denied_view

def health_check(request):
    """Simple health check endpoint for Docker health checks"""
    return JsonResponse({'status': 'healthy', 'service': 'django'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('access-denied/', access_denied_view, name='access_denied'),
    path('requests/', include('insurance_requests.urls')),
    path('summaries/', include('summaries.urls')),
    path('health/', health_check, name='health_check'),
    path('', lambda request: redirect('insurance_requests:request_list')),
]

# Для разработки - обслуживание медиа и статических файлов
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

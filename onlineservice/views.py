"""
Views for the main onlineservice application.
"""
import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.http import JsonResponse
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)


@never_cache
@require_safe
@login_required
def protected_media(request, path):
    """Выдаёт документы только действующим сотрудникам, сохраняя URL FileField."""
    user = request.user
    if not user.is_active or not (
        user.is_superuser
        or user.groups.filter(name__in=['Администраторы', 'Пользователи']).exists()
    ):
        return HttpResponseForbidden('Доступ к документам разрешён только сотрудникам.')

    # request.path уже декодирован Django. Повторное unquote разрешило бы обход
    # корня через двойное URL-кодирование; resolve также проверяет symlink.
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        if not path or '\\' in path or '\x00' in path or Path(path).is_absolute():
            raise ValueError
        if '..' in Path(path).parts:
            raise ValueError
        document = (root / path).resolve()
        relative_path = document.relative_to(root)
        if not document.is_file():
            raise ValueError
        size = document.stat().st_size
    except (OSError, RuntimeError, ValueError):
        raise Http404('Документ не найден.')

    content_type = mimetypes.guess_type(document.name)[0] or 'application/octet-stream'
    if settings.PROTECTED_MEDIA_USE_X_ACCEL_REDIRECT:
        response = HttpResponse(content_type=content_type)
        # Этот адрес закрыт директивой internal в Nginx. Файл отдаёт Nginx
        # после проверки сессии здесь, включая HEAD и частичные скачивания.
        response['X-Accel-Redirect'] = '/_protected_media/' + quote(
            relative_path.as_posix(), safe='/'
        )
    else:
        try:
            response = FileResponse(document.open('rb'), content_type=content_type)
        except OSError:
            raise Http404('Документ не найден.')
    response['Content-Length'] = size
    response['Content-Disposition'] = content_disposition_header(False, document.name)
    return response


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

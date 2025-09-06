from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.http import HttpResponseRedirect


class AuthenticationMiddleware:
    """
    Middleware для проверки аутентификации пользователей.
    Перенаправляет неавторизованных пользователей на страницу входа.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Список URL, не требующих аутентификации
        self.public_urls = [
            '/admin/login/',
            '/admin/logout/',
            '/login/',
            '/logout/',
            '/static/',
            '/media/',
        ]
    
    def __call__(self, request):
        # Проверяем, требует ли URL аутентификации
        if not self._is_public_url(request.path) and not request.user.is_authenticated:
            # Сохраняем URL, на который пользователь хотел попасть
            login_url = reverse('login')
            if request.path != login_url:
                # Добавляем параметр next для перенаправления после входа
                return HttpResponseRedirect(f"{login_url}?next={request.path}")
            else:
                return HttpResponseRedirect(login_url)
        
        response = self.get_response(request)
        return response
    
    def _is_public_url(self, path):
        """
        Проверяет, является ли URL публичным (не требующим аутентификации)
        """
        for public_url in self.public_urls:
            if path.startswith(public_url):
                return True
        return False
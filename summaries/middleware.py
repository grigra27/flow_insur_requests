"""Middleware приложения summaries."""
from ._current_user import set_current_user


class CurrentUserMiddleware:
    """Кладёт request.user в thread-local на время запроса.

    Используется сигналом StatusEvent, чтобы знать, кто менял статус.
    Должен стоять после django.contrib.auth.middleware.AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, 'user', None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)

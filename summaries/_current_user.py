"""Thread-local storage of the request user for signal handlers.

`StatusEvent` хочет знать, кто изменил статус, но Django-сигналы не имеют
доступа к request. Middleware кладёт текущего юзера в thread-local,
сигнал считывает.
"""
import threading

_local = threading.local()


def set_current_user(user):
    _local.user = user


def get_current_user():
    user = getattr(_local, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    return user

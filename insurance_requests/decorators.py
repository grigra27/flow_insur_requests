from functools import wraps
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def admin_required(view_func):
    """
    Декоратор для проверки, что пользователь является администратором.
    Требует, чтобы пользователь был в группе 'Администраторы'.
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.groups.filter(name='Администраторы').exists():
            return render(request, 'insurance_requests/access_denied.html', {
                'required_role': 'Администратор',
                'user_role': 'Пользователь' if request.user.groups.filter(name='Пользователи').exists() else 'Неопределенная роль'
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def user_required(view_func):
    """
    Декоратор для проверки, что пользователь имеет доступ к системе.
    Требует, чтобы пользователь был в группе 'Администраторы' или 'Пользователи'.
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not (request.user.groups.filter(name='Администраторы').exists() or 
                request.user.groups.filter(name='Пользователи').exists()):
            return render(request, 'insurance_requests/access_denied.html', {
                'required_role': 'Пользователь или Администратор',
                'user_role': 'Неопределенная роль'
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def get_user_role(user):
    """
    Вспомогательная функция для определения роли пользователя.
    """
    if user.groups.filter(name='Администраторы').exists():
        return 'Администратор'
    elif user.groups.filter(name='Пользователи').exists():
        return 'Пользователь'
    else:
        return 'Неопределенная роль'


def has_admin_access(user):
    """
    Проверяет, имеет ли пользователь права администратора.
    """
    return user.is_authenticated and user.groups.filter(name='Администраторы').exists()


def has_user_access(user):
    """
    Проверяет, имеет ли пользователь базовые права доступа к системе.
    """
    return user.is_authenticated and (
        user.groups.filter(name='Администраторы').exists() or 
        user.groups.filter(name='Пользователи').exists()
    )
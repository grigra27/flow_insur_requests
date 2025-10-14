from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """Позволяет получить значение из словаря по ключу в шаблоне"""
    return dictionary.get(key, [])

@register.filter
def div(value, divisor):
    """Делит значение на делитель"""
    try:
        if value is None or divisor is None:
            return 0
        return float(value) / float(divisor)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0

@register.filter
def status_color(status):
    """Возвращает цвет Bootstrap для статуса"""
    status_colors = {
        'collecting': 'warning',
        'ready': 'info', 
        'sent': 'success',
        'completed': 'secondary',
    }
    return status_colors.get(status, 'secondary')
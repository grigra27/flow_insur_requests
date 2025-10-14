from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """Позволяет получить значение из словаря по ключу в шаблоне"""
    return dictionary.get(key, [])

@register.filter
def get_item(dictionary, key):
    """Получает значение из словаря по ключу (альтернатива lookup для простых значений)"""
    if dictionary is None:
        return None
    return dictionary.get(key)

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

@register.filter
def format_branch(branch):
    """Форматирует отображение филиала"""
    if not branch or branch.strip() == '':
        return 'Не указан'
    return branch.strip()



@register.filter
def status_display_name(status):
    """Возвращает корректное отображение статуса с учетом новых названий"""
    status_mapping = {
        'collecting': 'Сбор предложений',
        'ready': 'Готов к отправке',
        'sent': 'Отправлен в Альянс',  # Обновленное название
        'completed': 'Завершен',
    }
    return status_mapping.get(status, status)

@register.filter
def companies_count_badge_class(count):
    """Возвращает CSS класс для бейджа количества компаний на основе цветовой схемы"""
    try:
        count = int(count) if count is not None else 0
    except (ValueError, TypeError):
        count = 0
    
    if count == 0:
        return 'bg-secondary'  # Серый
    elif count <= 2:
        return 'bg-warning text-dark'  # Желтый (1-2)
    elif count <= 4:
        return 'bg-info text-dark'  # Синий (3-4)
    elif count <= 6:
        return 'bg-success'  # Зеленый (5-6)
    else:
        return 'bg-primary'  # Фиолетовый (7+)

@register.filter
def companies_count_size_class(count):
    """Возвращает CSS класс для размера шрифта количества компаний"""
    try:
        count = int(count) if count is not None else 0
    except (ValueError, TypeError):
        count = 0
    
    if count >= 10:
        return 'fs-5 fw-bold'  # Большой размер для 10+
    elif count >= 5:
        return 'fs-6 fw-semibold'  # Средний размер для 5-9
    else:
        return 'fs-6'  # Обычный размер для 0-4
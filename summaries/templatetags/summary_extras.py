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
    from ..status_colors import get_status_color
    return get_status_color(status)

@register.filter
def status_badge_class(status):
    """Возвращает полный CSS класс для бейджа статуса с правильным цветом текста"""
    from ..status_colors import get_status_color
    color = get_status_color(status)
    
    # Для голубого (info) и желтого (warning) бейджей используем черный текст
    if color in ['info', 'warning']:
        return f"bg-{color} text-dark"
    else:
        return f"bg-{color}"

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
        'completed_accepted': 'Завершен: акцепт/распоряжение',  # Новый статус
        'completed_rejected': 'Завершен: не будет',  # Новый статус
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

@register.filter
def format_currency_with_spaces(value):
    """Форматирует валютные значения с пробелами между тысячами"""
    try:
        # Обработка граничных случаев
        if value is None or value == '':
            return '—'
        
        # Преобразуем в число, поддерживаем различные типы входных данных
        if isinstance(value, str):
            # Удаляем возможные пробелы и символы валюты для повторного форматирования
            clean_value = value.replace(' ', '').replace('₽', '').strip()
            if not clean_value:
                return '—'
            # Обрабатываем запятые как разделители тысяч (американский формат)
            if ',' in clean_value and '.' not in clean_value:
                # Если есть только запятые, это разделители тысяч
                clean_value = clean_value.replace(',', '')
            elif ',' in clean_value and '.' in clean_value:
                # Если есть и запятые и точки, запятые - разделители тысяч, точка - десятичный разделитель
                clean_value = clean_value.replace(',', '')
            elif ',' in clean_value and clean_value.count(',') == 1:
                # Если одна запятая в конце, это может быть десятичный разделитель
                parts = clean_value.split(',')
                if len(parts) == 2 and len(parts[1]) <= 2:
                    clean_value = clean_value.replace(',', '.')
                else:
                    clean_value = clean_value.replace(',', '')
            num_value = float(clean_value)
        elif isinstance(value, (int, float, Decimal)):
            num_value = float(value)
        else:
            # Попытка преобразования для других типов
            num_value = float(value)
        
        # Проверяем на отрицательные значения и ноль
        if num_value == 0:
            return '0 ₽'
        
        # Форматируем с пробелами между тысячами
        # Используем locale-независимый способ форматирования
        formatted = f"{num_value:,.0f}".replace(',', ' ')
        
        return f"{formatted} ₽"
        
    except (ValueError, TypeError, AttributeError):
        # В случае ошибки возвращаем исходное значение или прочерк
        if value is None or value == '':
            return '—'
        return str(value)


@register.filter
def sum_premiums_variant1(offers):
    """Суммирует премии с франшизой-1 для списка предложений"""
    try:
        total = Decimal('0')
        for offer in offers:
            if offer.premium_with_franchise_1:
                total += Decimal(str(offer.premium_with_franchise_1))
        return total
    except (ValueError, TypeError, AttributeError):
        return Decimal('0')


@register.filter
def sum_premiums_variant2(offers):
    """Суммирует премии с франшизой-2 для списка предложений"""
    try:
        total = Decimal('0')
        for offer in offers:
            if offer.premium_with_franchise_2:
                total += Decimal(str(offer.premium_with_franchise_2))
        return total
    except (ValueError, TypeError, AttributeError):
        return Decimal('0')


@register.filter
def has_variant2(offers):
    """Проверяет, есть ли хотя бы у одного предложения вариант с франшизой-2"""
    try:
        for offer in offers:
            if offer.premium_with_franchise_2:
                return True
        return False
    except (ValueError, TypeError, AttributeError):
        return False
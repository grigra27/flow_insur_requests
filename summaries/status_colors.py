"""
Централизованная система цветов для статусов сводов страхования.

Этот модуль обеспечивает единообразное отображение цветов статусов
на всех страницах системы.
"""

# Основная карта соответствия статусов и цветов Bootstrap
STATUS_COLOR_MAP = {
    # Статусы сводов
    'collecting': 'warning',           # Желтый - сбор предложений
    'ready': 'info',                  # Синий - готов к отправке
    'sent': 'secondary',              # Серый - отправлен в Альянс
    'completed_accepted': 'success',   # Зеленый - завершен: акцепт/распоряжение
    'completed_rejected': 'danger',    # Красный - завершен: не будет
    'completed': 'secondary',         # Серый - завершен (для обратной совместимости)
    
    # Статусы заявок
    'uploaded': 'secondary',          # Серый - загружено
    'email_generated': 'warning',     # Желтый - письмо сгенерировано
    'emails_sent': 'success',         # Зеленый - письма отправлены
}

def get_status_badge_class(status):
    """
    Возвращает CSS класс для бейджа статуса.
    
    Args:
        status (str): Статус свода
        
    Returns:
        str: CSS класс для Bootstrap badge
    """
    color = STATUS_COLOR_MAP.get(status, 'secondary')
    return f"badge bg-{color}"

def get_status_color(status):
    """
    Возвращает цвет Bootstrap для статуса.
    
    Args:
        status (str): Статус свода
        
    Returns:
        str: Название цвета Bootstrap (warning, info, success, secondary)
    """
    return STATUS_COLOR_MAP.get(status, 'secondary')

def get_status_display_data(status, display_text):
    """
    Возвращает полные данные для отображения статуса.
    
    Args:
        status (str): Статус свода
        display_text (str): Текст для отображения
        
    Returns:
        dict: Словарь с данными для отображения статуса
    """
    color = get_status_color(status)
    return {
        'status': status,
        'display': display_text,
        'color': color,
        'badge_class': get_status_badge_class(status)
    }

def get_all_status_colors():
    """
    Возвращает все доступные статусы с их цветами.
    
    Returns:
        dict: Словарь всех статусов и их цветов
    """
    return STATUS_COLOR_MAP.copy()
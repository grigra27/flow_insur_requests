"""
Константы для работы со страховыми компаниями
"""

# Резервный список страховых компаний (используется если модель недоступна)
FALLBACK_INSURANCE_COMPANIES = [
    ('', 'Выберите страховщика'),
    ('Абсолют', 'Абсолют'),
    ('Альфа', 'Альфа'),
    ('ВСК', 'ВСК'),
    ('Согаз', 'Согаз'),
    ('РЕСО', 'РЕСО'),
    ('Ингосстрах', 'Ингосстрах'),
    ('Ренессанс', 'Ренессанс'),
    ('Росгосстрах', 'Росгосстрах'),
    ('Пари', 'Пари'),
    ('Совкомбанк СК', 'Совкомбанк СК'),
    ('Согласие', 'Согласие'),
    ('Энергогарант', 'Энергогарант'),
    ('ПСБ-страхование', 'ПСБ-страхование'),
    ('Зетта', 'Зетта'),
    ('другое', 'Другое'),
]


def get_company_names():
    """
    Возвращает список названий страховых компаний (без пустого значения)
    
    Returns:
        list: Список названий компаний
    """
    try:
        # Пытаемся получить данные из модели
        from .models import InsuranceCompany
        return InsuranceCompany.get_company_names()
    except (ImportError, Exception):
        # Если модель недоступна, используем резервный список
        return [choice[0] for choice in FALLBACK_INSURANCE_COMPANIES if choice[0]]


def get_company_choices():
    """
    Возвращает полный список выборов для форм (включая пустое значение)
    
    Returns:
        list: Список кортежей (значение, отображаемое_название)
    """
    try:
        # Пытаемся получить данные из модели
        from .models import InsuranceCompany
        return InsuranceCompany.get_choices_for_forms()
    except (ImportError, Exception):
        # Если модель недоступна, используем резервный список
        return FALLBACK_INSURANCE_COMPANIES


# Для обратной совместимости
INSURANCE_COMPANIES = get_company_choices()


def is_valid_company_name(name):
    """
    Проверяет, является ли название компании валидным (входит в закрытый список)
    
    Args:
        name (str): Название компании для проверки
        
    Returns:
        bool: True если название валидно, False в противном случае
    """
    if not name:
        return False
    
    try:
        # Пытаемся использовать модель
        from .models import InsuranceCompany
        return InsuranceCompany.is_valid_company_name(name)
    except (ImportError, Exception):
        # Если модель недоступна, используем резервный список
        valid_names = [choice[0] for choice in FALLBACK_INSURANCE_COMPANIES if choice[0]]
        return name in valid_names


def get_matchable_company_names():
    """
    Возвращает список названий компаний для сопоставления (исключая "другое")
    
    Returns:
        list: Список названий компаний без значения "другое"
    """
    return [name for name in get_company_names() if name != 'другое']


def normalize_company_name(name):
    """
    Нормализует название компании (убирает лишние пробелы, приводит к единому формату)
    
    Args:
        name (str): Исходное название компании
        
    Returns:
        str: Нормализованное название или пустая строка если входное значение некорректно
    """
    if not name:
        return ''
    
    return str(name).strip()
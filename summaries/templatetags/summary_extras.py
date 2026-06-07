from django import template
from django.http import QueryDict
from decimal import Decimal

register = template.Library()


@register.simple_tag(takes_context=True)
def qs_replace(context, **kwargs):
    """Возвращает строку запроса текущего URL с переопределёнными параметрами.

    Передача значения None или '' удаляет параметр. Удобно для пагинации и
    фильтров: сохраняет все активные GET-параметры (филиал, ДФА, период,
    per_page), меняя лишь нужные. Возвращает строку вида '?a=1&b=2'.
    """
    request = context.get('request')
    params = request.GET.copy() if request is not None else QueryDict(mutable=True)
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return ('?' + encoded) if encoded else '?'

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


@register.inclusion_tag('components/status_progress.html')
def status_progress(insurance_request, summary=None):
    """Рендерит сквозной прогресс-бар статусов заявки и свода."""
    from ..status_colors import get_status_color

    STEPS = [
        {'key': 'uploaded',        'label': 'Загружено',  'sublabel': '',              'phase': 'request'},
        {'key': 'email_generated', 'label': 'Письмо',     'sublabel': 'сгенерировано', 'phase': 'request'},
        {'key': 'emails_sent',     'label': 'Письма',     'sublabel': 'отправлены',    'phase': 'request'},
        {'key': 'collecting',      'label': 'Сбор',       'sublabel': 'предложений',   'phase': 'summary'},
        {'key': 'ready',           'label': 'Готов к',    'sublabel': 'отправке',      'phase': 'summary'},
        {'key': 'sent',            'label': 'Отправлен',  'sublabel': 'в Альянс',      'phase': 'summary'},
        {'key': 'completed',       'label': 'Завершён',   'sublabel': '',              'phase': 'summary'},
    ]

    req_status = getattr(insurance_request, 'status', 'uploaded')
    REQUEST_ORDER = ['uploaded', 'email_generated', 'emails_sent']
    req_idx = REQUEST_ORDER.index(req_status) if req_status in REQUEST_ORDER else 0

    sum_status = getattr(summary, 'status', None) if summary else None
    is_terminal = sum_status in ('completed_accepted', 'completed_rejected')

    if sum_status is None:
        current_idx = req_idx
    elif is_terminal:
        current_idx = 7  # все шаги выполнены
    else:
        SUMMARY_TO_IDX = {'collecting': 3, 'ready': 4, 'sent': 5}
        current_idx = SUMMARY_TO_IDX.get(sum_status, 3)

    is_rejected = sum_status == 'completed_rejected'

    steps = []
    for i, step in enumerate(STEPS):
        if i < current_idx:
            state = 'done'
        elif i == current_idx:
            state = 'active'
        else:
            state = 'pending'

        # Цвет для активного шага
        if state == 'active':
            if step['phase'] == 'request':
                color = get_status_color(req_status)
            else:
                color = get_status_color(sum_status) if sum_status else 'secondary'
        else:
            color = ''

        step_is_rejected = (i == 6 and is_rejected)
        steps.append({
            'label': 'Отказ' if step_is_rejected else step['label'],
            'sublabel': '' if step_is_rejected else step['sublabel'],
            'phase': step['phase'],
            'state': state,
            'color': color,
            'is_rejected': step_is_rejected,
            'index': i + 1,
        })

    # Ширина заполненной части линии: от центра шага 0 до центра текущего шага
    # current_idx / 7 * 100% — при 7 равных flex-шагах
    fill_idx = min(current_idx, 6)
    progress_pct = round(fill_idx / 7 * 100, 3)

    from django.urls import reverse
    request_url = reverse('insurance_requests:request_detail', args=[insurance_request.pk])
    summary_url = reverse('summaries:summary_detail', args=[summary.pk]) if summary else None
    deal_summary_url = None
    if (summary and getattr(summary, 'status', None) == 'completed_accepted'
            and getattr(summary, 'selected_company', None)):
        deal_summary_url = reverse('summaries:deal_summary', args=[summary.pk])

    return {
        'steps': steps,
        'progress_pct': progress_pct,
        'request_url': request_url,
        'summary_url': summary_url,
        'deal_summary_url': deal_summary_url,
    }


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
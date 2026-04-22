"""Context processors for navigation and page orientation."""

from django.urls import NoReverseMatch, reverse


def _safe_reverse(route_name):
    """Resolve URL name safely for template navigation items."""
    try:
        return reverse(route_name)
    except NoReverseMatch:
        return '#'


MAIN_NAV_ITEMS = [
    {
        'label': 'Заявки',
        'icon': 'bi-list-ul',
        'route': 'insurance_requests:request_list',
        'match_app': 'insurance_requests',
        'exclude_urls': {'upload_excel'},
    },
    {
        'label': 'Загрузить заявку',
        'icon': 'bi-upload',
        'route': 'insurance_requests:upload_excel',
        'match_app': 'insurance_requests',
        'include_urls': {'upload_excel'},
    },
    {
        'label': 'Своды',
        'icon': 'bi-collection',
        'route': 'summaries:summary_list',
        'match_app': 'summaries',
        'exclude_urls': {'analytics', 'analytics_insurance_offers', 'deal_list'},
    },
    {
        'label': 'Сделки',
        'icon': 'bi-briefcase',
        'route': 'summaries:deal_list',
        'match_app': 'summaries',
        'include_urls': {'deal_list'},
        'requires_admin': True,
    },
    {
        'label': 'Аналитика',
        'icon': 'bi-bar-chart-line',
        'route': 'summaries:analytics',
        'match_app': 'summaries',
        'include_urls': {'analytics', 'analytics_insurance_offers'},
        'children': [
            ('Обзор аналитики', 'summaries:analytics'),
            ('Аналитика по страховым предложениям', 'summaries:analytics_insurance_offers'),
        ],
        'requires_admin': True,
    },
]


SECTION_CONFIG = {
    'insurance_requests': {
        'label': 'Заявки',
        'icon': 'bi-list-ul',
        'root': 'insurance_requests:request_list',
        'links': [
            ('Все заявки', 'insurance_requests:request_list'),
            ('Загрузить Excel', 'insurance_requests:upload_excel'),
        ],
    },
    'summaries': {
        'label': 'Своды',
        'icon': 'bi-collection',
        'root': 'summaries:summary_list',
        'links': [
            ('Список сводов', 'summaries:summary_list'),
            ('Статистика', 'summaries:statistics'),
            ('Справка', 'summaries:help'),
        ],
    },
    'deals': {
        'label': 'Сделки',
        'icon': 'bi-briefcase',
        'root': 'summaries:deal_list',
        'links': [
            ('Список сделок', 'summaries:deal_list'),
        ],
    },
    'analytics': {
        'label': 'Аналитика',
        'icon': 'bi-bar-chart-line',
        'root': 'summaries:analytics',
        'links': [
            ('Обзор аналитики', 'summaries:analytics'),
            ('Страховые предложения', 'summaries:analytics_insurance_offers'),
        ],
    },
}


ADMIN_ONLY_ROUTES = {
    'summaries:deal_list',
    'summaries:analytics',
    'summaries:analytics_insurance_offers',
}


SECTION_ROUTE_OVERRIDES = {
    ('summaries', 'deal_list'): 'deals',
    ('summaries', 'analytics'): 'analytics',
    ('summaries', 'analytics_insurance_offers'): 'analytics',
}


PAGE_LABELS = {
    ('insurance_requests', 'request_list'): 'Список заявок',
    ('insurance_requests', 'upload_excel'): 'Загрузка заявок',
    ('insurance_requests', 'request_detail'): 'Карточка заявки',
    ('insurance_requests', 'edit_request'): 'Редактирование заявки',
    ('insurance_requests', 'preview_email'): 'Предпросмотр письма',
    ('insurance_requests', 'access_denied'): 'Недостаточно прав',
    ('summaries', 'summary_list'): 'Список сводов',
    ('summaries', 'deal_list'): 'Список сделок',
    ('summaries', 'summary_detail'): 'Карточка свода',
    ('summaries', 'add_offer'): 'Добавление предложения',
    ('summaries', 'edit_offer'): 'Редактирование предложения',
    ('summaries', 'copy_offer'): 'Копирование предложения',
    ('summaries', 'deal_summary'): 'Сводка сделки',
    ('summaries', 'statistics'): 'Статистика',
    ('summaries', 'analytics'): 'Аналитика',
    ('summaries', 'analytics_insurance_offers'): 'Аналитика страховых предложений',
    ('summaries', 'help'): 'Справка',
    ('summaries', 'offer_search'): 'Поиск предложений',
}


BREADCRUMB_TEMPLATES = {
    ('insurance_requests', 'request_list'): [('Заявки', None)],
    ('insurance_requests', 'upload_excel'): [
        ('Заявки', 'insurance_requests:request_list'),
        ('Загрузка заявок', None),
    ],
    ('insurance_requests', 'request_detail'): [
        ('Заявки', 'insurance_requests:request_list'),
        ('Карточка заявки', None),
    ],
    ('insurance_requests', 'edit_request'): [
        ('Заявки', 'insurance_requests:request_list'),
        ('Карточка заявки', None),
        ('Редактирование', None),
    ],
    ('insurance_requests', 'preview_email'): [
        ('Заявки', 'insurance_requests:request_list'),
        ('Карточка заявки', None),
        ('Предпросмотр письма', None),
    ],
    ('summaries', 'summary_list'): [('Своды', None)],
    ('summaries', 'deal_list'): [('Сделки', None)],
    ('summaries', 'summary_detail'): [
        ('Своды', 'summaries:summary_list'),
        ('Карточка свода', None),
    ],
    ('summaries', 'create_summary'): [
        ('Своды', 'summaries:summary_list'),
        ('Создание свода', None),
    ],
    ('summaries', 'add_offer'): [
        ('Своды', 'summaries:summary_list'),
        ('Карточка свода', None),
        ('Добавить предложение', None),
    ],
    ('summaries', 'edit_offer'): [
        ('Своды', 'summaries:summary_list'),
        ('Карточка свода', None),
        ('Редактировать предложение', None),
    ],
    ('summaries', 'copy_offer'): [
        ('Своды', 'summaries:summary_list'),
        ('Карточка свода', None),
        ('Копировать предложение', None),
    ],
    ('summaries', 'deal_summary'): [
        ('Своды', 'summaries:summary_list'),
        ('Карточка свода', None),
        ('Сводка сделки', None),
    ],
    ('summaries', 'statistics'): [
        ('Своды', 'summaries:summary_list'),
        ('Статистика', None),
    ],
    ('summaries', 'analytics'): [('Аналитика', None)],
    ('summaries', 'analytics_insurance_offers'): [
        ('Аналитика', 'summaries:analytics'),
        ('Страховые предложения', None),
    ],
    ('summaries', 'help'): [
        ('Своды', 'summaries:summary_list'),
        ('Справка', None),
    ],
    ('summaries', 'offer_search'): [
        ('Своды', 'summaries:summary_list'),
        ('Поиск предложений', None),
    ],
}


LAYOUT_MODE_BY_PAGE = {
    ('insurance_requests', 'request_list'): 'wide',
    ('insurance_requests', 'upload_excel'): 'wide',
    ('insurance_requests', 'request_detail'): 'wide',
    ('summaries', 'summary_list'): 'wide',
    ('summaries', 'deal_list'): 'wide',
    ('summaries', 'statistics'): 'wide',
    ('summaries', 'analytics'): 'wide',
    ('summaries', 'analytics_insurance_offers'): 'wide',
    ('summaries', 'deal_summary'): 'wide',
    ('summaries', 'summary_detail'): 'wide',
}


LAYOUT_CLASS_BY_MODE = {
    'default': 'container app-layout-default',
    'wide': 'container app-layout-wide',
    'full': 'container-fluid app-layout-full',
}


def _is_nav_item_active(item, app_name, url_name):
    if app_name != item.get('match_app'):
        return False

    include_urls = item.get('include_urls')
    if include_urls is not None:
        return url_name in include_urls

    exclude_urls = item.get('exclude_urls', set())
    return url_name not in exclude_urls


def _humanize_url_name(url_name):
    if not url_name:
        return 'Раздел'
    return url_name.replace('_', ' ').strip().capitalize()


def _has_admin_navigation_access(user):
    """Check whether user can access admin-only navigation items."""
    if not getattr(user, 'is_authenticated', False):
        return False

    user_groups = getattr(user, 'groups', None)
    if user_groups is None:
        return False

    return user_groups.filter(name='Администраторы').exists()


def navigation_context(request):
    """Global navigation context for active menu, breadcrumbs and quick links."""
    resolver_match = getattr(request, 'resolver_match', None)
    app_name = getattr(resolver_match, 'app_name', '') or ''
    url_name = getattr(resolver_match, 'url_name', '') or ''
    section_key = SECTION_ROUTE_OVERRIDES.get((app_name, url_name), app_name)

    section = SECTION_CONFIG.get(section_key, {
        'label': 'Система',
        'icon': 'bi-grid-1x2',
        'root': 'insurance_requests:request_list',
        'links': [
            ('Заявки', 'insurance_requests:request_list'),
            ('Своды', 'summaries:summary_list'),
        ],
    })
    user_has_admin_access = _has_admin_navigation_access(getattr(request, 'user', None))

    main_items = []
    for item in MAIN_NAV_ITEMS:
        if item.get('requires_admin') and not user_has_admin_access:
            continue
        children = []
        for child_label, child_route in item.get('children', []):
            if child_route in ADMIN_ONLY_ROUTES and not user_has_admin_access:
                continue

            child_app, _, child_url_name = child_route.partition(':')
            children.append({
                'label': child_label,
                'url': _safe_reverse(child_route),
                'active': child_app == app_name and child_url_name == url_name,
            })

        is_active = _is_nav_item_active(item, app_name, url_name) or any(
            child['active'] for child in children
        )
        main_items.append({
            'label': item['label'],
            'icon': item['icon'],
            'url': _safe_reverse(item['route']),
            'active': is_active,
            'children': children,
        })

    section_items = []
    for label, route_name in section['links']:
        if route_name in ADMIN_ONLY_ROUTES and not user_has_admin_access:
            continue
        route_app, _, route_url_name = route_name.partition(':')
        section_items.append({
            'label': label,
            'url': _safe_reverse(route_name),
            'active': route_app == app_name and route_url_name == url_name,
        })

    current_page_label = PAGE_LABELS.get((app_name, url_name), _humanize_url_name(url_name))
    breadcrumb_template = BREADCRUMB_TEMPLATES.get((app_name, url_name))
    layout_mode = LAYOUT_MODE_BY_PAGE.get((app_name, url_name), 'default')
    layout_container_class = LAYOUT_CLASS_BY_MODE.get(layout_mode, LAYOUT_CLASS_BY_MODE['default'])

    if breadcrumb_template is None:
        breadcrumb_template = []
        if section.get('root'):
            breadcrumb_template.append((section['label'], section['root']))
        if current_page_label != section['label']:
            breadcrumb_template.append((current_page_label, None))
        if not breadcrumb_template:
            breadcrumb_template = [('Раздел', None)]

    breadcrumbs = []
    total = len(breadcrumb_template)
    for index, (label, route_name) in enumerate(breadcrumb_template, start=1):
        is_active = index == total
        breadcrumbs.append({
            'label': label,
            'url': '' if is_active or not route_name else _safe_reverse(route_name),
            'active': is_active,
        })

    current_context_label = section['label']
    if breadcrumbs and len(breadcrumbs) > 1:
        trailing_label = breadcrumbs[-1]['label']
        if trailing_label and trailing_label != section['label']:
            current_context_label = f"{section['label']} / {trailing_label}"

    return {
        'app_navigation': {
            'main_items': main_items,
            'section_items': section_items,
            'breadcrumbs': breadcrumbs,
            'current_section': {
                'label': section['label'],
                'icon': section['icon'],
            },
            'current_page': current_page_label,
            'current_context_label': current_context_label,
        },
        'app_layout': {
            'mode': layout_mode,
            'container_class': layout_container_class,
        },
    }

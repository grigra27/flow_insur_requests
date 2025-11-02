# Руководство разработчика: Система справочной документации

## Обзор

Система справочной документации предоставляет пользователям актуальную информацию о работе с заявками и сводами. Система состоит из двух основных компонентов:

1. **Обновленная справочная информация** на странице загрузки заявок
2. **Новая справочная страница** для модуля сводов с интеграцией в пользовательский интерфейс

## Архитектура системы

### Структура файлов

```
├── summaries/
│   ├── views.py                    # Содержит help_page view
│   ├── urls.py                     # URL маршрут для справки
│   ├── templates/summaries/
│   │   ├── help.html              # Основной шаблон справки
│   │   ├── summary_list.html      # Обновлен: добавлены ссылки на справку
│   │   ├── summary_detail.html    # Обновлен: добавлены ссылки на справку
│   │   └── add_offer.html         # Обновлен: добавлены ссылки на справку
│   └── test_help_integration.py   # Интеграционные тесты
├── insurance_requests/templates/insurance_requests/
│   └── upload_excel.html          # Обновлен: актуализирована справочная информация
├── static/css/
│   └── help.css                   # Стили для справочных страниц
└── docs/
    └── HELP_SYSTEM_DEVELOPER_GUIDE.md  # Данное руководство
```

### Компоненты системы

#### 1. Help Page View (`summaries/views.py`)

```python
@user_required
def help_page(request):
    """Справочная страница для модуля сводов"""
    try:
        context = {
            'title': 'Справка по работе со сводами',
            'sections': [
                'upload_responses',
                'export_summaries', 
                'examples'
            ]
        }
        return render(request, 'summaries/help.html', context)
    except Exception as e:
        logger.error(f"Error loading help page: {str(e)}", exc_info=True)
        messages.error(request, 'Произошла ошибка при загрузке справочной страницы. Обратитесь к администратору.')
        return redirect('summaries:summary_list')
```

**Особенности реализации:**
- Использует декоратор `@user_required` для контроля доступа
- Включает обработку ошибок с логированием
- Предоставляет graceful fallback при ошибках
- Передает структурированный контекст в шаблон

#### 2. URL Configuration (`summaries/urls.py`)

```python
urlpatterns = [
    # ... существующие маршруты
    path('help/', views.help_page, name='help'),
    # ... остальные маршруты
]
```

**Маршрут:** `/summaries/help/`  
**Имя:** `summaries:help`

#### 3. Help Template (`summaries/templates/summaries/help.html`)

Шаблон организован в следующие разделы:

- **Навигация** - быстрые ссылки по разделам
- **Загрузка ответов** - процесс загрузки файлов страховщиков
- **Выгрузка сводов** - генерация Excel файлов
- **Рабочий процесс** - жизненный цикл свода
- **Примеры** - образцы файлов и частые ошибки

**Ключевые особенности:**
- Адаптивный дизайн с Bootstrap 5
- Плавающая навигация для больших экранов
- Интерактивные элементы (аккордеоны, табы)
- Мобильная адаптация

#### 4. CSS Styles (`static/css/help.css`)

```css
/* Основные стили для справочных страниц */
.help-section {
    margin-bottom: 3rem;
    scroll-margin-top: 100px;
}

.help-navigation {
    position: sticky;
    top: 20px;
}

/* Плавающая навигация */
.quick-nav-floating {
    position: fixed;
    right: 20px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 1000;
    opacity: 0;
    transition: opacity 0.3s ease;
}

.quick-nav-floating.visible {
    opacity: 1;
}

/* Адаптивность */
@media (max-width: 991.98px) {
    .quick-nav-floating {
        display: none;
    }
}
```

## Интеграция в интерфейс

### Ссылки на справку

Ссылки на справочную страницу интегрированы в следующие места:

#### 1. Список сводов (`summary_list.html`)

```html
<div class="d-flex justify-content-between align-items-center mb-4">
    <h1>Своды предложений</h1>
    <div>
        <a href="#help-section" class="btn btn-outline-info">
            <i class="bi bi-question-circle"></i> Справка
        </a>
        <!-- другие кнопки -->
    </div>
</div>
```

#### 2. Детальный вид свода (`summary_detail.html`)

```html
<div class="card-header d-flex justify-content-between align-items-center">
    <h5 class="mb-0">Действия</h5>
    <a href="#help-section" class="btn btn-sm btn-outline-info">
        <i class="bi bi-question-circle"></i> Справка
    </a>
</div>
```

#### 3. Форма добавления предложения (`add_offer.html`)

```html
<div class="card-footer">
    <div class="d-flex justify-content-between">
        <a href="#upload-responses" class="btn btn-outline-info btn-sm">
            <i class="bi bi-info-circle"></i> Справка по загрузке
        </a>
        <button type="submit" class="btn btn-primary">Добавить предложение</button>
    </div>
</div>
```

### Обновленная страница загрузки заявок

Страница `upload_excel.html` была обновлена с актуальной информацией:

#### Новые параметры
- **КАСКО кат. C/E** (строка 45)
- **Перевозка** (C44 для имущества)
- **СМР** (C48 для имущества)
- **Дополнительные параметры КАСКО**
- **Территория страхования**

#### Логика смещения строк для ИП
```html
<div class="alert alert-info">
    <strong>Важно для заявок от ИП:</strong> 
    Для индивидуальных предпринимателей строки с 9 по 49 смещаются на +1 
    (например, строка 9 становится строкой 10).
</div>
```

#### Цветовое кодирование
```html
<tr class="table-warning">
    <td>Название клиента (ИП)</td>
    <td>D8</td>
    <td>Смещение +1 для ИП</td>
</tr>
```

## Тестирование

### Интеграционные тесты

Файл `summaries/test_help_integration.py` содержит комплексные тесты:

#### Базовый класс для тестов

```python
class BaseIntegrationTest(TestCase):
    """Базовый класс для интеграционных тестов с настройкой аутентификации"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        
        # Создаем группу пользователей
        self.user_group, created = Group.objects.get_or_create(name='Пользователи')
        
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        # Добавляем пользователя в группу
        self.user.groups.add(self.user_group)
```

#### Категории тестов

1. **HelpPageIntegrationTests** - тесты справочной страницы
2. **HelpLinksIntegrationTests** - тесты интеграции ссылок
3. **UploadPageDocumentationTests** - тесты обновленной документации
4. **NavigationIntegrationTests** - тесты навигации
5. **ErrorHandlingIntegrationTests** - тесты обработки ошибок
6. **PerformanceIntegrationTests** - тесты производительности
7. **MobileResponsivenessTests** - тесты мобильной адаптации
8. **AccessibilityIntegrationTests** - тесты доступности
9. **RegressionIntegrationTests** - регрессионные тесты

#### Запуск тестов

```bash
# Все интеграционные тесты
python manage.py test summaries.test_help_integration -v 2

# Конкретная категория тестов
python manage.py test summaries.test_help_integration.HelpPageIntegrationTests -v 2

# Конкретный тест
python manage.py test summaries.test_help_integration.HelpPageIntegrationTests.test_help_page_accessibility -v 2
```

## Безопасность и доступ

### Контроль доступа

Справочная страница использует декоратор `@user_required`, который:

1. **Проверяет аутентификацию** - пользователь должен быть авторизован
2. **Проверяет группы** - пользователь должен быть в группе "Пользователи" или "Администраторы"
3. **Возвращает 403** - при отсутствии прав доступа

```python
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
```

### Валидация данных

Все пользовательские данные проходят валидацию:

1. **URL параметры** - проверяются Django URL resolver
2. **Форма поиска** - санитизация через Django forms
3. **XSS защита** - автоматическая через Django templates

## Производительность

### Оптимизации

1. **Статический контент** - справочная информация кэшируется браузером
2. **Минимальные запросы к БД** - view не выполняет сложных запросов
3. **Ленивая загрузка** - JavaScript загружается только при необходимости
4. **Сжатие** - CSS и JS минифицированы в продакшене

### Мониторинг

```python
# Логирование времени загрузки
import time
start_time = time.time()
# ... код view
load_time = time.time() - start_time
logger.info(f"Help page loaded in {load_time:.2f} seconds")
```

## Мобильная адаптация

### Адаптивный дизайн

```html
<!-- Основная структура -->
<div class="row">
    <div class="col-lg-3">
        <!-- Навигация - скрывается на мобильных -->
        <nav class="help-navigation d-none d-lg-block">
            <!-- ... -->
        </nav>
    </div>
    <div class="col-lg-9">
        <!-- Основной контент -->
    </div>
</div>
```

### Мобильные особенности

1. **Плавающая навигация** - отключается на экранах < 992px
2. **Адаптивные таблицы** - используется `.table-responsive`
3. **Сжатый контент** - менее детальная информация на малых экранах
4. **Touch-friendly** - увеличенные области нажатия

## Доступность (Accessibility)

### Семантическая разметка

```html
<nav class="help-navigation" role="navigation" aria-label="Навигация по разделам справки">
    <ul class="nav nav-pills flex-column">
        <li class="nav-item">
            <a class="nav-link" href="#upload-responses" aria-describedby="upload-desc">
                <i class="bi bi-upload" aria-hidden="true"></i> Загрузка ответов
            </a>
        </li>
    </ul>
</nav>
```

### ARIA атрибуты

- `role` - определяет роль элемента
- `aria-label` - описание для скринридеров
- `aria-describedby` - связь с описанием
- `aria-hidden` - скрытие декоративных элементов

### Клавиатурная навигация

Все интерактивные элементы доступны через клавиатуру:

```javascript
// Обработка клавиш для навигации
document.addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
        // Логика табуляции
    }
    if (e.key === 'Enter' || e.key === ' ') {
        // Активация элементов
    }
});
```

## Интернационализация

### Подготовка к переводу

Все текстовые строки подготовлены для интернационализации:

```python
# В views.py
from django.utils.translation import gettext_lazy as _

context = {
    'title': _('Справка по работе со сводами'),
    'sections': [
        'upload_responses',
        'export_summaries', 
        'examples'
    ]
}
```

```html
<!-- В шаблонах -->
{% raw %}
{% load i18n %}
<h1>{% trans "Справка по работе со сводами" %}</h1>
{% endraw %}
```

### Создание переводов

```bash
# Создание файлов переводов
python manage.py makemessages -l en
python manage.py makemessages -l de

# Компиляция переводов
python manage.py compilemessages
```

## Расширение системы

### Добавление новых разделов

1. **Обновите контекст view:**
```python
context = {
    'sections': [
        'upload_responses',
        'export_summaries',
        'examples',
        'new_section'  # Новый раздел
    ]
}
```

2. **Добавьте раздел в шаблон:**
```html
<section id="new-section" class="help-section">
    <h3><i class="bi bi-new-icon"></i> Новый раздел</h3>
    <!-- Содержимое раздела -->
</section>
```

3. **Обновите навигацию:**
```html
<li class="nav-item">
    <a class="nav-link" href="#new-section">
        <i class="bi bi-new-icon"></i> Новый раздел
    </a>
</li>
```

4. **Добавьте тесты:**
```python
def test_new_section_content(self):
    """Тест нового раздела"""
    self.client.login(username='testuser', password='testpass123')
    response = self.client.get(reverse('summaries:help'))
    self.assertContains(response, 'id="new-section"')
```

### Кастомизация стилей

```css
/* Добавьте в help.css */
.new-section-specific {
    /* Стили для нового раздела */
}

/* Адаптивность для нового раздела */
@media (max-width: 768px) {
    .new-section-specific {
        /* Мобильные стили */
    }
}
```

## Отладка и диагностика

### Логирование

```python
import logging
logger = logging.getLogger(__name__)

# В view
logger.info(f"Help page accessed by user {request.user.username}")
logger.error(f"Error loading help page: {str(e)}", exc_info=True)
```

### Диагностические команды

```bash
# Проверка доступности справочной страницы
python manage.py shell -c "
from django.test import Client
from django.contrib.auth.models import User, Group
from django.urls import reverse

client = Client()
user = User.objects.first()
if user:
    client.force_login(user)
    response = client.get(reverse('summaries:help'))
    print(f'Status: {response.status_code}')
    print(f'Content length: {len(response.content)}')
else:
    print('No users found')
"

# Проверка шаблонов
python manage.py shell -c "
from django.template.loader import get_template
try:
    template = get_template('summaries/help.html')
    print('Template found successfully')
except Exception as e:
    print(f'Template error: {e}')
"
```

### Отладка JavaScript

```javascript
// Добавьте в help.html для отладки
console.log('Help page JavaScript loaded');

// Отладка навигации
document.querySelectorAll('.help-navigation .nav-link').forEach(link => {
    link.addEventListener('click', function(e) {
        console.log('Navigation clicked:', this.getAttribute('href'));
    });
});
```

## Развертывание

### Статические файлы

```bash
# Сбор статических файлов
python manage.py collectstatic --noinput

# Проверка наличия help.css
ls -la staticfiles/css/help.css
```

### Проверка после развертывания

```bash
# Проверка URL
curl -I https://your-domain.com/summaries/help/

# Проверка статических файлов
curl -I https://your-domain.com/static/css/help.css
```

### Мониторинг в продакшене

```python
# Добавьте в settings.py для продакшена
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'help_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/django/help_system.log',
        },
    },
    'loggers': {
        'summaries.views': {
            'handlers': ['help_file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

## Заключение

Система справочной документации предоставляет пользователям актуальную и легкодоступную информацию о работе с заявками и сводами. Система спроектирована с учетом:

- **Масштабируемости** - легко добавлять новые разделы
- **Производительности** - минимальная нагрузка на сервер
- **Доступности** - соответствие стандартам WCAG
- **Мобильности** - адаптация для всех устройств
- **Безопасности** - контроль доступа и валидация данных

Для получения дополнительной информации обратитесь к:
- Интеграционным тестам в `test_help_integration.py`
- Комментариям в коде шаблонов и views
- Документации Django по лучшим практикам
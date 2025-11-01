# Структура проекта: Система управления страховыми заявками

## Обзор архитектуры

Проект построен на Django 4.2 с модульной архитектурой, состоящей из двух основных приложений:
- `insurance_requests` - управление страховыми заявками
- `summaries` - управление сводами предложений

## Структура директорий

```
onlineservice/                          # Корневая директория проекта
├── manage.py                           # Django management script
├── requirements.txt                    # Python зависимости
├── docker-compose.yml                  # Docker конфигурация (Digital Ocean)
├── docker-compose.timeweb.yml          # Docker конфигурация (Timeweb)
├── Dockerfile                          # Docker образ приложения
├── entrypoint.sh                       # Docker entrypoint script
├── healthcheck.py                      # Health check для Docker
├── .env.example                        # Пример переменных окружения
├── .env.timeweb.example                # Пример переменных для Timeweb
├── .gitignore                          # Git ignore правила
├── README.md                           # Основная документация
├── DEPLOYMENT_GUIDE.md                 # Руководство по развертыванию
├── DEPLOYMENT_GUIDE_TIMEWEB.md         # Руководство по развертыванию на Timeweb
├── EXCEL_PROCESSING.md                 # Документация по обработке Excel
├── new_parameters_documentation.md     # Документация новых параметров
├── task_1_analysis_summary.md          # Анализ задач
├── analysis_current_excel_recognition.md # Анализ распознавания Excel
├── test-configs.sh                     # Скрипт тестирования конфигураций
├── monitor_domains.py                  # Мониторинг доменов
│
├── onlineservice/                      # Основной Django проект
│   ├── __init__.py
│   ├── settings.py                     # Настройки Django
│   ├── urls.py                         # Основные URL маршруты
│   ├── wsgi.py                         # WSGI конфигурация
│   ├── asgi.py                         # ASGI конфигурация
│   ├── middleware.py                   # Кастомные middleware
│   ├── views.py                        # Общие views (landing page)
│   └── test_domain_routing.py          # Тесты маршрутизации доменов
│
├── insurance_requests/                 # Django приложение "Заявки"
│   ├── __init__.py
│   ├── admin.py                        # Django admin конфигурация
│   ├── apps.py                         # Конфигурация приложения
│   ├── models.py                       # Модели данных заявок
│   ├── views.py                        # Views для работы с заявками
│   ├── urls.py                         # URL маршруты заявок
│   ├── forms.py                        # Django формы
│   ├── decorators.py                   # Декораторы аутентификации
│   ├── middleware.py                   # Middleware для заявок
│   ├── tests.py                        # Тесты приложения
│   ├── migrations/                     # Миграции базы данных
│   │   ├── 0001_initial.py
│   │   ├── 0002_alter_insurancerequest_response_deadline.py
│   │   ├── ...                         # Другие миграции
│   │   └── 0025_add_insurance_territory_field.py
│   ├── management/                     # Django management команды
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── setup_user_groups.py    # Создание групп пользователей
│   │       └── create_demo_data.py     # Создание демо данных
│   └── templates/insurance_requests/   # HTML шаблоны заявок
│       ├── base.html                   # Базовый шаблон
│       ├── request_list.html           # Список заявок
│       ├── request_detail.html         # Детали заявки
│       ├── upload_excel.html           # Загрузка Excel (с обновленной справкой)
│       ├── login.html                  # Страница входа
│       ├── access_denied.html          # Отказ в доступе
│       └── email_content.html          # Содержимое письма
│
├── summaries/                          # Django приложение "Своды"
│   ├── __init__.py
│   ├── admin.py                        # Django admin конфигурация
│   ├── apps.py                         # Конфигурация приложения
│   ├── models.py                       # Модели данных сводов
│   ├── views.py                        # Views для работы со сводами (включая help_page)
│   ├── urls.py                         # URL маршруты сводов (включая help/)
│   ├── forms.py                        # Django формы сводов
│   ├── constants.py                    # Константы приложения
│   ├── exceptions.py                   # Кастомные исключения
│   ├── status_colors.py                # Цветовое кодирование статусов
│   ├── tests.py                        # Основные тесты
│   ├── test_help_integration.py        # Интеграционные тесты справочной системы
│   ├── test_*.py                       # Другие специализированные тесты
│   ├── migrations/                     # Миграции базы данных
│   │   ├── 0001_initial.py
│   │   ├── ...                         # Другие миграции
│   │   └── 0011_populate_insurance_companies.py
│   ├── management/                     # Django management команды
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       └── cleanup_summaries.py    # Очистка сводов
│   ├── services/                       # Бизнес-логика сервисов
│   │   ├── __init__.py
│   │   ├── company_matcher.py          # Сопоставление компаний
│   │   ├── excel_services.py           # Сервисы работы с Excel
│   │   └── multiple_file_processor.py  # Обработка множественных файлов
│   ├── templatetags/                   # Кастомные template tags
│   │   ├── __init__.py
│   │   └── summary_extras.py           # Дополнительные теги для сводов
│   └── templates/summaries/            # HTML шаблоны сводов
│       ├── summary_list.html           # Список сводов (с ссылками на справку)
│       ├── summary_detail.html         # Детали свода (с ссылками на справку)
│       ├── add_offer.html              # Добавление предложения (с ссылками на справку)
│       ├── edit_offer.html             # Редактирование предложения
│       ├── copy_offer.html             # Копирование предложения
│       ├── help.html                   # Справочная страница сводов (НОВАЯ)
│       └── statistics.html             # Статистика сводов
│
├── core/                               # Универсальные модули
│   ├── __init__.py
│   ├── excel_utils.py                  # Утилиты для работы с Excel
│   ├── templates.py                    # Генерация шаблонов писем
│   └── tasks.py                        # Фоновые задачи
│
├── templates/                          # Общие шаблоны
│   ├── base.html                       # Базовый шаблон всего проекта
│   ├── base_landing.html               # Базовый шаблон для landing page
│   ├── summary_template.xlsx           # Шаблон Excel для сводов
│   ├── summary_template_simplified.xlsx # Упрощенный шаблон
│   ├── flow_answer_template.xlsx       # Шаблон ответов
│   └── landing/
│       └── index.html                  # Landing page
│
├── static/                             # Статические файлы
│   ├── css/
│   │   ├── custom.css                  # Основные стили
│   │   ├── help.css                    # Стили для справочной системы (НОВЫЙ)
│   │   ├── landing.css                 # Стили landing page
│   │   └── login.css                   # Стили страницы входа
│   ├── js/                             # JavaScript файлы
│   ├── favicon.ico                     # Favicon
│   ├── favicon-16x16.png
│   └── favicon-32x32.png
│
├── staticfiles/                        # Собранные статические файлы (продакшен)
│   ├── admin/                          # Django admin статика
│   ├── css/                            # CSS файлы
│   ├── js/                             # JavaScript файлы
│   └── rest_framework/                 # DRF статика
│
├── media/                              # Загруженные пользователями файлы
│   └── attachments/                    # Вложения к заявкам
│       └── 2025/                       # Файлы по годам
│
├── logs/                               # Логи приложения
│   ├── django.log                      # Основные логи Django
│   ├── errors.log                      # Логи ошибок
│   ├── performance.log                 # Логи производительности
│   ├── security.log                    # Логи безопасности
│   ├── audit.log                       # Аудит действий
│   ├── file_uploads.log                # Логи загрузки файлов
│   ├── multiple_upload.log             # Логи множественной загрузки
│   ├── queries.log                     # Логи SQL запросов
│   ├── landing.log                     # Логи landing page
│   └── domain_*.log                    # Логи доменной маршрутизации
│
├── docs/                               # Документация проекта
│   ├── README.md                       # Основная документация docs
│   ├── USER_MANUAL.md                  # Руководство пользователя
│   ├── USER_MANUAL.html                # HTML версия руководства
│   ├── USER_MANUAL.pdf                 # PDF версия руководства
│   ├── HELP_SYSTEM_DEVELOPER_GUIDE.md  # Руководство разработчика: Справочная система (НОВЫЙ)
│   ├── PROJECT_STRUCTURE.md            # Структура проекта (ЭТОТ ФАЙЛ)
│   ├── DEPLOYMENT_GUIDE_COMPLETE.md    # Полное руководство по развертыванию
│   ├── FAVICON_DEPLOYMENT_GUIDE.md     # Настройка favicon
│   ├── AUTHENTICATION_SYSTEM.md        # Система аутентификации
│   ├── DEPLOYMENT_CHECKLIST.md         # Чек-лист развертывания
│   ├── DEPLOYMENT_INSTRUCTIONS.md      # Инструкции по развертыванию
│   ├── README_DEPLOYMENT.md            # README для развертывания
│   ├── _config.yml                     # Конфигурация GitHub Pages
│   ├── index.md                        # Главная страница документации
│   ├── _includes/                      # Включаемые файлы Jekyll
│   ├── _layouts/                       # Макеты Jekyll
│   ├── _sass/                          # SASS стили
│   ├── assets/                         # Ресурсы документации
│   └── images/                         # Изображения документации
│
├── nginx/                              # Nginx конфигурация (Digital Ocean)
│   ├── Dockerfile                      # Docker образ nginx
│   └── default.conf                    # Конфигурация nginx
│
├── nginx-timeweb/                      # Nginx конфигурация (Timeweb)
│   ├── Dockerfile                      # Docker образ nginx для Timeweb
│   └── default.conf                    # Конфигурация nginx для Timeweb
│
├── scripts/                            # Скрипты развертывания и мониторинга
│   ├── domain-monitor.service          # Systemd сервис мониторинга
│   ├── setup-monitoring.sh             # Настройка мониторинга
│   └── verify_landing_deployment.sh    # Проверка развертывания landing
│
├── .github/                            # GitHub Actions workflows
│   └── workflows/
│       ├── deploy_do.yml               # Деплой на Digital Ocean
│       └── deploy_timeweb.yml          # Деплой на Timeweb
│
├── avtozayavka/                        # Тестовые данные и примеры
│   ├── real_requests/                  # Реальные заявки для тестирования
│   ├── im_request/                     # Заявки ИМ
│   ├── summaries_examples/             # Примеры сводов
│   ├── test_franchise_files/           # Тестовые файлы франшизы
│   ├── template.txt                    # Шаблон заявки
│   ├── summary_template.xlsx           # Шаблон свода
│   └── *.xls                          # Различные тестовые файлы
│
├── tests/                              # Общие тесты проекта
│   └── __pycache__/                    # Кэш Python
│
├── venv/                               # Виртуальное окружение Python (локальная разработка)
├── black_venv/                         # Виртуальное окружение для форматирования кода
└── db.sqlite3                          # База данных SQLite (разработка)
```

## Ключевые компоненты

### 1. Django Приложения

#### insurance_requests
- **Назначение**: Управление страховыми заявками
- **Основные модели**: `InsuranceRequest`, `RequestAttachment`
- **Ключевые функции**:
  - Загрузка и обработка Excel файлов
  - Извлечение данных из различных форматов
  - Генерация содержимого писем
  - Управление статусами заявок

#### summaries
- **Назначение**: Управление сводами предложений
- **Основные модели**: `InsuranceSummary`, `InsuranceOffer`, `InsuranceCompany`
- **Ключевые функции**:
  - Создание и управление сводами
  - Загрузка ответов страховых компаний
  - Выгрузка сводов в Excel
  - Справочная система (НОВАЯ ФУНКЦИОНАЛЬНОСТЬ)

### 2. Справочная система (Новая функциональность)

#### Компоненты справочной системы:
- **`summaries/views.py`**: `help_page` view с обработкой ошибок
- **`summaries/urls.py`**: Маршрут `/summaries/help/`
- **`summaries/templates/summaries/help.html`**: Основной шаблон справки
- **`static/css/help.css`**: Стили для справочной системы
- **`summaries/test_help_integration.py`**: Комплексные интеграционные тесты

#### Интеграция в интерфейс:
- Ссылки на справку в `summary_list.html`
- Ссылки на справку в `summary_detail.html`
- Контекстная справка в `add_offer.html`
- Обновленная документация в `upload_excel.html`

### 3. Система аутентификации

#### Группы пользователей:
- **Администраторы**: Полный доступ ко всем функциям
- **Пользователи**: Доступ к основным функциям

#### Декораторы:
- `@admin_required`: Требует права администратора
- `@user_required`: Требует базовые права пользователя

### 4. Обработка Excel файлов

#### Основные модули:
- **`core/excel_utils.py`**: Утилиты для работы с Excel
- **`summaries/services/excel_services.py`**: Сервисы Excel для сводов
- **`summaries/services/multiple_file_processor.py`**: Обработка множественных файлов

#### Поддерживаемые форматы:
- `.xls` - старый формат Excel
- `.xlsx` - современный формат Excel
- `.xltx` - шаблоны Excel

### 5. Система логирования

#### Категории логов:
- **django.log**: Основные события приложения
- **errors.log**: Ошибки и исключения
- **performance.log**: Метрики производительности
- **security.log**: События безопасности
- **audit.log**: Аудит действий пользователей
- **file_uploads.log**: Загрузка файлов
- **queries.log**: SQL запросы (для отладки)

### 6. Статические файлы и медиа

#### Статические файлы (`static/`):
- **CSS**: Bootstrap 5 + кастомные стили
- **JavaScript**: Минимальный JS для интерактивности
- **Изображения**: Favicon, иконки

#### Медиа файлы (`media/`):
- **attachments/**: Загруженные пользователями Excel файлы
- Организация по годам для удобства управления

### 7. Тестирование

#### Типы тестов:
- **Модульные тесты**: `tests.py` в каждом приложении
- **Интеграционные тесты**: `test_help_integration.py` (НОВЫЙ)
- **Функциональные тесты**: `tests_functional.py`
- **UI тесты**: `tests_ui.py`

#### Специализированные тесты:
- Тесты обработки Excel файлов
- Тесты системы аутентификации
- Тесты производительности
- Тесты мобильной адаптации
- Тесты доступности

### 8. Развертывание

#### Docker конфигурации:
- **docker-compose.yml**: Для Digital Ocean (onbr.site)
- **docker-compose.timeweb.yml**: Для Timeweb (zs.insflow.tw1.su)
- **Dockerfile**: Основной образ приложения
- **nginx/**: Конфигурация веб-сервера

#### CI/CD:
- **GitHub Actions**: Автоматический деплой на два хостинга
- **Health checks**: Проверка состояния сервисов
- **Мониторинг**: Отслеживание доступности доменов

## Потоки данных

### 1. Обработка заявки
```
Excel файл → core/excel_utils.py → InsuranceRequest → Валидация → Сохранение → Отображение
```

### 2. Создание свода
```
InsuranceRequest → InsuranceSummary → Добавление предложений → Выгрузка Excel
```

### 3. Справочная система (НОВАЯ)
```
Пользователь → summaries:help → help_page view → help.html → Отображение справки
```

### 4. Загрузка ответов страховщиков
```
Excel файл → services/excel_services.py → InsuranceOffer → Валидация → Интеграция в свод
```

## Безопасность

### 1. Аутентификация и авторизация
- Django встроенная аутентификация
- Группы пользователей с разными правами
- Декораторы для контроля доступа
- Защита от несанкционированного доступа

### 2. Валидация данных
- Django Forms для валидации пользовательского ввода
- Модельная валидация на уровне базы данных
- Санитизация загружаемых файлов
- Защита от XSS через Django templates

### 3. Защита файлов
- Ограничение типов загружаемых файлов
- Проверка размера файлов
- Безопасное хранение в media директории
- Контроль доступа к загруженным файлам

## Производительность

### 1. Оптимизация запросов
- `select_related()` и `prefetch_related()` для оптимизации ORM
- Индексы базы данных для часто используемых полей
- Пагинация для больших списков

### 2. Кэширование
- Django кэширование для статического контента
- Browser caching для статических файлов
- Оптимизация изображений и CSS/JS

### 3. Мониторинг
- Логирование производительности
- Мониторинг времени ответа
- Отслеживание использования ресурсов

## Масштабируемость

### 1. Модульная архитектура
- Разделение на независимые Django приложения
- Сервисный слой для бизнес-логики
- Возможность добавления новых модулей

### 2. База данных
- Готовность к миграции на PostgreSQL
- Структура миграций для версионирования схемы
- Возможность горизонтального масштабирования

### 3. Развертывание
- Docker контейнеризация
- Поддержка множественных сред (dev, staging, prod)
- Автоматизированный деплой через CI/CD

## Документация

### 1. Пользовательская документация
- Руководство пользователя в нескольких форматах
- Встроенная справочная система
- Контекстная помощь в интерфейсе

### 2. Техническая документация
- Руководство разработчика
- API документация
- Руководства по развертыванию
- Структура проекта (этот документ)

### 3. Документация процессов
- Чек-листы развертывания
- Инструкции по обслуживанию
- Руководства по устранению неполадок

## Заключение

Проект имеет хорошо организованную модульную структуру, которая обеспечивает:

- **Maintainability**: Четкое разделение ответственности между модулями
- **Scalability**: Возможность добавления новых функций без нарушения существующих
- **Security**: Многоуровневая система безопасности
- **Performance**: Оптимизация на всех уровнях
- **Documentation**: Комплексная документация для пользователей и разработчиков

Новая справочная система интегрирована в существующую архитектуру без нарушения принципов проектирования и обеспечивает пользователям удобный доступ к актуальной информации о работе с системой.
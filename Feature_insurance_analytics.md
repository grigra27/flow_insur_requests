**План Технической Реализации: «Аналитика по страховым компаниям»**

**1. Цель задачи**
1. Сделать отдельную страницу аналитики, где центральный объект анализа — страховая компания, а не заявка/свод.
2. Дать руководителю и операционке полный срез по СК: участие в сводах, выбор клиентом, ценовая позиция, динамика, разрезы по филиалам и менеджерам, контроль качества данных.
3. Встроить страницу в текущую архитектуру проекта без изменения схемы БД.

**2. Что именно должно получиться в итоге**
1. Новый раздел в меню аналитики: «Аналитика по страховым компаниям».
2. Новый URL и view с admin-доступом.
3. Полноценная страница с блоками:
   1. Фильтры.
   2. KPI-лента.
   3. Рейтинг СК.
   4. Ценовая конкурентность.
   5. Конверсия в выбор.
   6. Разрезы по филиалам/менеджерам/типам/статусам сделок.
   7. Динамика по времени.
   8. Data Quality.
   9. Детализация до конкретной сделки.
4. Набор тестов для доступа, фильтров, метрик и рендера.
5. Экспорт по ключевым блокам (XLSX, по аналогии с текущей статистикой).

**3. Контекст текущего проекта (точки интеграции)**
1. Модели:
[InsuranceSummary/InsuranceOffer/InsuranceCompany](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/models.py),
[InsuranceRequest](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/insurance_requests/models.py).
2. Текущий раздел аналитики:
[views.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/views.py) (`analytics_placeholder`, `analytics_insurance_offers`, `_parse_statistics_filters`, `_build_deal_price_row`),
[analytics_placeholder.html](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/templates/summaries/analytics_placeholder.html),
[analytics_insurance_offers.html](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/templates/summaries/analytics_insurance_offers.html).
3. Сделки и текущий drilldown:
[deal_list.html](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/templates/summaries/deal_list.html),
[deal_summary.html](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/templates/summaries/deal_summary.html).
4. Маршруты:
[urls.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/urls.py).
5. Навигация и access:
[context_processors.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/onlineservice/context_processors.py),
[decorators.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/insurance_requests/decorators.py).

**4. Объем реализации (что входит / не входит)**

Входит:
1. Новый аналитический экран.
2. Бэкенд-агрегации по СК.
3. Фильтры и визуализация.
4. Тесты.
5. Интеграция в меню/хлебные крошки.
6. Экспорт основных таблиц.

Не входит:
1. Миграции БД.
2. Убытки, маржа, комиссии (их нет как полноценного источника в текущих моделях).
3. Внешние BI/DWH интеграции.

**5. Логика данных и единицы анализа**
1. База «сделок» для company-аналитики:
`InsuranceSummary(status='completed_accepted', selected_company not empty)`.
2. СК «участвовала в сделке»:
есть valid offer (`InsuranceOffer.is_valid=True`) для этого summary.
3. СК «победила»:
`summary.selected_company == company_name`.
4. Ценовая позиция:
использовать текущую логику `_build_deal_price_row` (ранг, delta к минимуму, min selected).
5. Менеджер Онлайна:
`request.created_by`.
6. Менеджер Альянса:
`request.manager_name`.
7. Даты:
по умолчанию фильтр по `summary.created_at`, опционально режимы для `completed_at`/`received_at`.
8. Исторические пропуски:
`selected_franchise_variant` может быть пустым — учитывать как fallback в data-quality и расчетах.

**6. Целевая структура страницы (блоки и смысл)**
1. Блок фильтров.
2. KPI-лента.
3. Таблица рейтинга СК + график.
4. Ценовая конкурентность.
5. Конверсия в выбор клиента.
6. Разрезы:
`СК×Филиал`, `СК×Менеджер Онлайна`, `СК×Менеджер Альянса`, `СК×Тип страхования`, `СК×Статус сделки`.
7. Динамика по времени.
8. Data Quality.
9. Детализация сделок с переходом в `deal_summary` и `summary_detail`.

**7. Детализация метрик по блокам**

KPI-лента:
1. `total_deals`.
2. `comparable_deals`.
3. `distinct_companies_offered`.
4. `distinct_companies_selected`.
5. `min_selected_count`.
6. `min_selected_rate`.
7. `avg_competitors`.
8. `avg_selected_premium`.
9. `median_delta_abs`.
10. `median_delta_pct`.
11. `avg_rank`.
12. `multiyear_rate`.
13. `installment_rate`.
14. `sla_before_deadline_rate`.
15. `avg_hours_request_to_summary`.
16. `avg_hours_summary_to_close`.

Рейтинг СК:
1. `offered_in_deals_count`.
2. `selected_wins_count`.
3. `coverage_pct`.
4. `win_rate_when_offered_pct`.
5. `win_share_pct`.
6. `selected_premium_sum`.
7. `selected_premium_avg`.
8. `avg_rank_when_selected`.
9. `median_delta_abs_when_selected`.
10. `min_selected_rate_when_selected`.

**8. Техническая архитектура реализации**
1. Новый view в [summaries/views.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/views.py): `analytics_insurance_companies`.
2. Новый маршрут в [summaries/urls.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/urls.py): `analytics/insurance-companies/`.
3. Новый шаблон:
[summaries/templates/summaries/analytics_insurance_companies.html](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/summaries/templates/summaries/analytics_insurance_companies.html).
4. Вынесение вычислений в сервис:
`/summaries/services/analytics_insurance_companies.py`.
5. Переиспользование текущих helper-функций фильтров/периодов/ценового ранга.
6. Обновление навигации в [onlineservice/context_processors.py](/Users/grigoriigrachev/Yandex.Disk.localized/Работа/ОнлайнБрокер/soft/onlineservice/onlineservice/context_processors.py).
7. Добавление экспорта виджета по аналогии с `export_statistics_widget`.

**9. Пошаговый план реализации (этапы и очередность)**

**Этап 0. Data Contract и формулы**
1. Зафиксировать расчетные формулы всех KPI и таблиц.
2. Зафиксировать fallback-правила для пропусков.
3. Зафиксировать единый список фильтров и их приоритет.
4. Результат: документированная спецификация метрик.

**Этап 1. Каркас раздела**
1. Добавить route и пустой view.
2. Добавить пункт в аналитическое меню и в analytics-placeholder.
3. Добавить breadcrumbs/section config/page label/layout mode.
4. Результат: страница доступна администратору, видна в меню.

**Этап 2. Backend-пайплайн данных**
1. Реализовать сбор базового queryset.
2. Реализовать фильтры GET.
3. Реализовать расчет KPI.
4. Реализовать рейтинг СК.
5. Реализовать срезы и динамику.
6. Реализовать data-quality.
7. Реализовать deals-детализацию с пагинацией.
8. Результат: полный context без фронтенда.

**Этап 3. UI: фильтры + KPI + рейтинг**
1. Сверстать фильтры и сохранить совместимость query params.
2. Сверстать KPI-карточки.
3. Сверстать рейтинг таблицей.
4. Подключить первые графики Chart.js.
5. Результат: usable MVP экрана.

**Этап 4. UI: конкурентность + разрезы + динамика**
1. Добавить блок конкурентности цены.
2. Добавить табы/секции разрезов.
3. Добавить динамику по месяцам.
4. Результат: полная аналитическая глубина по СК.

**Этап 5. UI: data-quality + детализация**
1. Добавить отдельный блок качества данных.
2. Добавить подробную таблицу сделок.
3. Добавить drilldown-ссылки на `deal_summary` и `summary_detail`.
4. Результат: от KPI можно перейти к первичному объекту.

**Этап 6. Экспорт**
1. Добавить экспорт для новых таблиц и ключевых виджетов.
2. Прокинуть текущие фильтры в export URL.
3. Результат: управленческие выгрузки из нового раздела.

**Этап 7. Тесты и стабилизация**
1. Написать новый модуль тестов раздела.
2. Проверить совместимость со старыми analytics/deals/statistics тестами.
3. Проверить N+1 и оптимизировать select_related/prefetch_related.
4. Результат: стабильный production-ready экран.

**10. План тестирования**
1. Access:
admin=200, user=403.
2. Навигация:
пункт есть у админа, скрыт у обычного пользователя.
3. Рендер:
все ключевые блоки присутствуют.
4. Фильтры:
branch, insurance_type, manager_online, manager_alliance, selected_company, period.
5. Метрики:
проверка wins/win rate/rank/delta/min-selected на фикстурах.
6. Data quality:
кейсы пропущенного `selected_franchise_variant`, пустого `manager_name`.
7. Drilldown:
корректные URL в строках детализации.
8. Экспорт:
валидный XLSX и корректные заголовки.
9. Регресс:
существующие `analytics_insurance_offers`, `deal_list`, `statistics` не ломаются.

**11. Риски и меры**
1. Риск: маленькая выборка завершенных сделок.
Мера: показывать “insufficient data” и долю сопоставимых сделок.
2. Риск: исторические пропуски вариантов франшизы.
Мера: fallback + индикатор в data-quality.
3. Риск: расхождение менеджеров (`created_by` vs `manager_name`).
Мера: разделить как два независимых среза.
4. Риск: медленные агрегации.
Мера: предварительная оптимизация queryset + ограничение объемных таблиц + пагинация.

**12. Артефакты по завершению**
1. Новый route + view + шаблон.
2. Обновленная навигация и индекс аналитики.
3. Новый слой расчетов.
4. Новый модуль тестов.
5. Экспорт для новых блоков.
6. Краткая техдокументация формул (в код-комментариях и/или `docs`).

**13. Финальный Definition of Done**
1. Раздел полностью доступен в аналитике и работает только для администраторов.
2. На странице есть все 9 функциональных блоков.
3. Все фильтры работают сквозно.
4. Есть drilldown на сделку и свод.
5. Экспорт работает.
6. Тесты зеленые.
7. Нет критичных деградаций производительности.

# Депрекейт legacy-полей объекта (`vehicle_info`, `asset_status`)

Дата создания: 2026-06-05.
Обновлено: 2026-06-19.
Статус: **Фазы A, B, C реализованы**; **Фаза D (депрекейт V1 + удаление
столбцов) — не сделана**. Регрессия C-lite исправлена.

## Контекст

Исторически объект страхования в `InsuranceRequest` описывался двумя
свободнотекстовыми полями, которые заполнял ещё V1-парсер
(`core/excel_utils.py`):

- `vehicle_info` («Информация о предмете лизинга») — сводная строка объекта.
- `asset_status` («Статус имущества») — фактически «новое / б/у», но в виде
  свободного текста (иногда мусор вроде `2025 2025 2025`).

Парсер V2 (`insurance_requests/parsers/excel_v2/parser.py`) распознаёт объект
структурированно: `brand`, `model`, `condition` (enum `new`/`used`),
`equipment_type`, `power_or_capacity`, `acquisition_cost_value`,
`acquisition_cost_currency`, `manufacturing_year`, `source_object_count`.
В рамках принципа [«1 заявка = 1 объект»](own_insurance_request_form.md#ключевой-архитектурный-принцип-один-объект--одна-заявка)
структура однозначно описывает ровно один объект на заявку.

Это создаёт два дубля legacy ↔ modern:

| Legacy (V1, свободный текст) | Modern (V2, структура) |
|---|---|
| `vehicle_info` | `brand`/`model`/`condition`/`acquisition_cost`/`manufacturing_year` + `object_description` |
| `asset_status` | `condition` |

**Цель инициативы:** перевести всех потребителей на структурированные данные,
свести legacy-поля к роли fallback для исторических V1-заявок и в перспективе
удалить их вместе с депрекейтом V1-флоу.

## Что уже реализовано (Фазы A+B)

### Фаза A — модель

- Новое поле `object_description` (`TextField`, «Описание объекта (исходное)»)
  — lossless сырое описание одного объекта; миграция `0043`. Заполняется
  парсером V2 во всех трёх ветках извлечения объекта
  (`parser.py:1198`, `:1307`, `:1422`) и прокидывается при сохранении
  (`views.py:251`), а также из правок оператора в формах
  (`forms.py:638`, `:666`).
- Property `object_summary` (`models.py`): человекочитаемая сводка из
  `brand+model` (или `object_description`, если марки/модели нет) + год +
  `condition_label` + стоимость + `×N`; fallback на `vehicle_info`, затем на
  `object_description`.
- Property `condition_label` и `is_new_object` (`models.py`): берут `condition`,
  при пустом — fallback на `asset_status`.
- `to_dict()` отдаёт `object_summary`, `object_display_name`,
  `object_description`, `condition_label` (legacy-ключи `vehicle_info` /
  `asset_status` пока сохранены).

### Фаза B — потребители переведены на property

- Тема письма (`core/templates.py`) — `object_display_name` (короткая форма
  марка+модель).
- Своды: валидация и ячейки экспорта (`summaries/services/excel_services.py`),
  контекст view (`summaries/views.py`), шаблоны `deal_summary.html`,
  `summary_detail.html`, `add_offer.html` — на `object_summary` /
  `condition_label`.
- Карточка заявки (`request_detail.html`): дубль «Состояние» / «Статус
  имущества» убран — одно «Состояние» через `condition_label`.
- Список заявок (`request_list.html`), админка (`admin.py` — поиск +
  fieldset со структурой), exporter (`exporters.py` — `object_summary` как
  вычисляемое поле), completeness-аналитика (`analytics_managers.py`).

### Текущее состояние двойной записи

V2-парсер **по-прежнему** заполняет `vehicle_info` (`parser.py:621`) и
`asset_status` (`parser.py:681`) параллельно структуре — это сознательно
оставлено на Фазу A+B, чтобы ничего не сломать. V1-флоу не тронут.

---

## Фаза C — прекратить двойную запись и перевести ввод оператора (РЕАЛИЗОВАНО)

Цель фазы: новые **V2**-заявки больше не зависят от `vehicle_info` /
`asset_status` ни на запись, ни на ручной ввод. Legacy-поля остаются только
как fallback для исторических/V1-записей.

### C1. Прекращена двойная запись в V2 ✅

- **`vehicle_info`** (C-lite, коммит `1d12aa9`) — при распознанных объектах
  парсер ставит `data["vehicle_info"] = ""` (`parser.py:621`); во view вместо
  него сохраняется `object_description`.
- **`asset_status`** — парсер пишет его только как fallback: когда объектов нет
  вообще либо ни у одного объекта не распознан `condition`
  (`parser.py:_extract_asset_status` + гейт на `objects_have_condition`).
  Для нормальной V2-заявки с `condition` поле остаётся пустым — состояние
  живёт в `condition` (читается через `condition_label`, Фаза B).
  Это закрывает Risk A: состояние не теряется в краевом случае «condition не
  распознан, asset_status распознан».

### C2. Ввод оператора переведён на структуру ✅

- Object-форма предпросмотра (`ParserV2ObjectForm`) — без поля «Описание
  объекта», оператор правит структуру; raw `object_description` сохраняется
  серверно (C-lite).
- Форма ручного редактирования (`InsuranceRequestForm`) — в `__init__` для
  заявок со структурой (`has_structured_object_data`) поля
  `vehicle_info`/`asset_status` **убираются** из формы; редактируется только
  структура. Для исторических V1-заявок (структуры нет) legacy-поля
  остаются — там это единственный источник данных об объекте. Шаблон
  `edit_request.html` оборачивает legacy-блоки в `{% if form.vehicle_info %}` /
  `{% if form.asset_status %}`.
- Скалярная `ParserV2PreviewForm` сохраняет `vehicle_info`/`asset_status` —
  они нужны как fallback на пути «объекты не распознаны»; для object-флоу не
  заполняются и в трекинге исключаются (см. C3).

### C3. Edit-tracking переведён на структуру ✅

`edit_tracking._SCALAR_FIELDS_OBJECT_LEVEL` теперь
`{'vehicle_info', 'manufacturing_year', 'asset_status'}` — при распознанных
объектах оба legacy-поля исключаются из скалярного diff, потому что их
современные эквиваленты (`object_description`, `condition`) отслеживаются
пообъектно через `ParserV2ObjectForm`. Историческая статистика по
`vehicle_info` в `RequestFieldEdit` остаётся в БД нетронутой.

### ✅ Регрессия C-lite — исправлена

`_build_warnings` ложно выдавал `manual_required: «Предмет лизинга не
распознан.»` после того, как `vehicle_info` стал пустым для распознанных
объектов. Проверка переведена на факт распознавания (`insured_objects`); фикс
покрыт тестами `IdenticalObjectGroupingTests.*vehicle_info_warning*`.

### C4. Тесты Фазы C

- Парсер V2 больше не пишет `vehicle_info`/`asset_status` (структура заполнена,
  legacy пусты).
- Оператор редактирует структуру; edit-tracking ловит правки структурных
  полей, а не `vehicle_info`.
- Регресс: V1/исторические заявки по-прежнему корректно отображаются и
  экспортируются через fallback.

---

## Фаза D — депрекейт V1 и удаление legacy-полей (НЕ реализовано)

### D1. Депрекейт V1-флоу

`core/excel_utils.py` (`ExcelReader`) и legacy-ветка сохранения в
`views.py:347` (`:378` — `vehicle_info=`, `:817`/`:834` —
`vehicle_info`/`asset_status` из `excel_data`) — единственное, что ещё пишет
legacy-поля. Условие депрекейта: новый поток загрузки целиком на V2; решить,
нужен ли V1 как запасной парсер вообще.

### D2. Условия безопасного удаления `vehicle_info` / `asset_status`

Удалять поля можно, только когда выполнено всё:

1. Все runtime-чтения убраны или переведены на `object_summary` /
   `condition_label` (Фаза B — сделано; остаётся fallback в
   `models.py` и legacy-ключи `to_dict()`).
2. Ввод оператора и edit-tracking — на структуре (Фаза C).
3. V1-флоу либо удалён, либо тоже пишет структуру (Фаза D1).
4. Решён вопрос исторических данных: либо `object_summary`/`condition_label`
   навсегда сохраняют fallback на старые поля, **либо** выполнена
   data-миграция (см. D3) и поля можно дропнуть.
5. exporter, админка, completeness больше не ссылаются на legacy-поля.
6. Тесты совместимости V1/V2 переписаны.

### D3. (Опционально) data-миграция исторических записей

Если решено дропнуть поля, а не держать fallback вечно:

- **V2-записи**: надёжный backfill `object_description` и структуры из
  `additional_data['parser_v2']['parsed_payload']['insured_objects']`
  (management command или миграция) — точнее, чем повторный парсинг текста.
- **V1-записи**: best-effort разбор `vehicle_info`/`asset_status` в структуру
  (марка/модель/состояние) — только если бизнесу нужна историческая
  структуризация; иначе оставить fallback.

---

## Открытые вопросы (решить до Фазы C)

1. **Редактирование «сырого» описания**: оставлять ли оператору отдельное
   редактируемое поле `object_description` (lossless), или он правит только
   структуру?
2. **Форма «имущество»**: достаточно ли `object_description` из колонки C, или
   нужна доработка `split_brand_model` для лучшей разбивки на марку/модель
   ([parser_v2_property_form.md](parser_v2_property_form.md))?
3. **Историю удалять или держать fallback вечно?** От этого зависит, нужна ли
   data-миграция D3 и можно ли вообще дропать столбцы.
4. **Судьба V1-парсера**: депрекейт целиком или сохранение как запасного.

## Связанные документы

- [JSON Schema v2](json_schema_v2.md) — `insured_object` (singular), уже без
  `vehicle_info`-центричности.
- [Трекинг ручных правок оператора](operator_edits_tracking.md) — затрагивается
  в C3.
- [Парсер V2: форма «имущество»](parser_v2_property_form.md) — источник
  `object_description` для имущества.
- [Принцип «1 объект = 1 заявка»](own_insurance_request_form.md).

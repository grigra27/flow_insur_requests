# Parser V2: кратность полностью одинаковых объектов

Дата создания: 2026-06-04.
Статус: **реализовано** (2026-06-04). Поле, группировка, превью, создание
заявок, audit trail, отображение в detail/list, JSON Schema v2 и тесты сделаны.
На отдельный этап осталась только интеграция кратности в письма страховщикам и
своды (раздел 8/10) — поле `request.source_object_count` для них уже готово.

## Контекст

Parser V2 сейчас следует принципу: **одна `InsuranceRequest` = один объект
страхования**. Если в Excel-файле найдено N объектов, view `/upload-v2/`
создаёт N сестринских заявок, связанных `source_batch_id`, `item_no` и
`item_count`.

На реальных файлах встречается особенность выгрузки из базы лизинговой
компании: один и тот же объект может быть представлен несколькими полностью
идентичными строками.

В текущем коде Parser V2 такие строки **уже схлопываются**, но делают это
неявно и с потерей кратности: в
`ExcelRequestParserV2._extract_objects()` (`insurance_requests/parsers/excel_v2/parser.py`)
есть `seen = set()`, затем `if row_text in seen: continue`. Повторная строка
не попадает в `insured_objects`, её координаты не сохраняются, счётчик
исходных одинаковых строк теряется. Поэтому реальная проблема не в том, что
создаются одинаковые заявки, а в том, что создаётся одна заявка без информации
"эта позиция представляет N одинаковых строк исходной Excel-заявки".

## Целевое поведение

1. Если в файле один объект — создаётся одна заявка, как сейчас.
2. Если в файле несколько **разных** объектов — создаётся по одной заявке на
   каждый уникальный объект, как сейчас.
3. Если в файле несколько **полностью одинаковых** строк объекта — создаётся
   одна заявка, но в ней фиксируется, сколько исходных строк она представляет.
4. Если файл смешанный, например `A, A, A, B, C, C`, создаётся три заявки:
   - объект `A` с кратностью `3`;
   - объект `B` с кратностью `1`;
   - объект `C` с кратностью `2`.
5. Batch-поля (`source_batch_id`, `item_no`, `item_count`) считаются по числу
   создаваемых заявок после схлопывания дублей, а не по числу строк Excel.

## Выбранное решение

Добавить в модель `InsuranceRequest` одно бизнес-поле:

```python
source_object_count = models.PositiveIntegerField(
    default=1,
    validators=[MinValueValidator(1)],
)
```

Смысл поля: сколько полностью одинаковых строк исходной Excel-заявки
представляет эта запись `InsuranceRequest`.

Не использовать имя `quantity`: раньше `quantity` удалили из модели и схемы,
потому что в исходной заявке нет отдельной колонки "количество". Новое поле
описывает не заявленное в анкете количество, а результат группировки
идентичных строк выгрузки. Поэтому название должно явно указывать на источник
и семантику. Допустимые альтернативы, если при реализации выберем более
говорящее имя:

- `source_object_count` — рекомендовано, нейтрально и коротко.
- `identical_object_count` — точнее про дубли, но длиннее.
- `source_row_count` — подчёркивает строки Excel, но хуже читается в письмах.

Рекомендуемое имя для реализации: **`source_object_count`**.

## Что хранить в БД

В `InsuranceRequest`:

- `source_object_count` — бизнес-поле для писем, сводов, шаблонов, интерфейса
  и будущих экспортов.
- существующие объектные поля (`brand`, `model`, `manufacturing_year`,
  `vehicle_info`, `acquisition_cost_value`, `acquisition_cost_currency`, ...)
  остаются полями одной уникальной группы объектов.
- `item_count` продолжает означать размер партии заявок, а не количество
  одинаковых объектов внутри одной позиции.

В `additional_data.parser_v2.parsed_payload` оставить audit trail:

```json
{
  "object_grouping": {
    "raw_object_count": 6,
    "unique_object_count": 3,
    "groups": [
      {
        "group_index": 1,
        "source_object_count": 3,
        "sources": ["A12:N12", "A13:N13", "A14:N14"],
        "canonical_key": {
          "brand": "LADA",
          "model": "Vesta",
          "year": "2024",
          "acquisition_cost_value": "1490000",
          "acquisition_cost_currency": "RUB"
        }
      }
    ]
  }
}
```

То есть `object_grouping` должен лежать рядом с `insured_objects` внутри
`parser_v2_payload`. После текущего `_build_parser_v2_additional_data()` он
окажется в `additional_data.parser_v2.parsed_payload.object_grouping`.
`canonical_key` нужен только для диагностики. В пользовательский интерфейс его
выводить не надо.

## Где менять код

### 1. Модель и миграция

Файл: `insurance_requests/models.py`

Добавить поле в `InsuranceRequest` рядом с объектными полями:

```python
from django.core.validators import MinValueValidator

source_object_count = models.PositiveIntegerField(
    default=1,
    validators=[MinValueValidator(1)],
    help_text='Сколько одинаковых строк объекта из исходной Excel-заявки представляет эта заявка'
)
```

Миграция:

- добавить поле с `default=1`;
- существующие заявки получают `1`;
- data migration не нужна.

Важно: `PositiveIntegerField` допускает `0`, а семантика поля — минимум одна
исходная строка. Поэтому `MinValueValidator(1)` обязателен, а не опционален.

### 2. Переделка текущего `seen`-дедупа

Файл: `insurance_requests/parsers/excel_v2/parser.py`.

Сейчас `_extract_objects()` делает дедуп по сырому `row_text`:

```python
seen = set()
...
if row_text in seen:
    continue
seen.add(row_text)
```

Этот `continue` нельзя оставлять как есть: он выбрасывает повторную строку до
того, как новая логика успеет посчитать `raw_object_count`.

Нужно заменить `seen` на структуру, которая хранит индекс уже созданного
payload:

```python
seen_by_row_text = {}
...
source = self._row_source(row_cells)
if row_text in seen_by_row_text:
    existing = objects[seen_by_row_text[row_text]]
    existing["source_object_count"] = (existing.get("source_object_count") or 1) + 1
    existing.setdefault("duplicate_sources", [existing.get("source") or ""])
    existing["duplicate_sources"].append(source)
    continue

seen_by_row_text[row_text] = len(objects)
payload = self._build_object_payload(row_cells, row_text)
payload["source_object_count"] = 1
payload["duplicate_sources"] = [payload.get("source") or source]
objects.append(payload)
```

Точная реализация может отличаться, но обязательное поведение такое:

- полностью идентичная строка не создаёт второй объект;
- `source_object_count` инкрементируется;
- координаты всех поглощённых строк попадают в `duplicate_sources`;
- `raw_object_count` потом считается как сумма `source_object_count`, а не как
  `len(insured_objects)` после схлопывания.

Fallback-ветка `_extract_labeled_value(...)`, где объект создаётся из одного
значения, должна выставлять `source_object_count=1` и
`duplicate_sources=[source]`.

### 3. Группировка объектов до превью

Файл: `insurance_requests/parsers/excel_v2/parser.py` или отдельный helper рядом
с parser/view.

После исправления текущего `seen`-дедупа можно дополнительно сгруппировать
`insured_objects` по каноническому ключу. Это нужно не для полностью
идентичных `row_text` (они уже посчитаны на предыдущем шаге), а для строк,
которые бизнес-эквивалентны после нормализации: например отличаются пробелами
или форматом стоимости (`1490000` / `1 490 000` / `1490000.00`).

Группировку лучше сделать на parser-слое до создания `parser_v2_payload`, чтобы
preview уже работал с уникальными группами.

Рекомендуемая структура:

```python
def group_identical_objects(insured_objects):
    ...
    return grouped_objects, grouping_meta
```

`grouped_objects` — список объектов для превью и создания заявок. Каждый объект
получает:

```python
{
  ...,
  "source_object_count": 3,
  "duplicate_sources": ["A12:N12", "A13:N13", "A14:N14"]
}
```

`grouping_meta` — технический audit trail для `additional_data`.

При слиянии двух групп нужно суммировать `source_object_count` и объединять
`duplicate_sources`.

### 4. Канонический ключ

Сравнивать не сырой `row_text`, не `description` и не координаты строк, а
нормализованный структурный payload объекта. `description` в текущем parser v2
равен `row_text` (`_build_object_payload()`), поэтому включение `description`
в канонический ключ фактически воспроизводит старый дедуп и делает
нормализованную группировку бесполезной.

В основной ключ включить:

- `brand`;
- `model`;
- `year`;
- `condition`;
- `equipment_type`;
- `power_or_capacity`;
- `acquisition_cost_value`;
- `acquisition_cost_currency`;
- `vehicle_category`.

Не включать:

- `description` / `row_text`;
- `source`;
- `vehicle_category_source`;
- `duplicate_sources`;
- номер строки;
- любые координаты ячеек.

Исключение: если структурный ключ слишком бедный (например почти все поля
пустые), можно использовать агрессивно нормализованный `description` как
fallback-защиту от случайного слияния разных плохо распознанных строк. Но это
должно быть именно fallback-правило, а не часть основного ключа.

Нормализация:

- строки: `clean_value()`/`normalize_text()` по смыслу поля, trim, схлопывание
  пробелов, единый регистр для сравнения;
- пустые значения: приводить к `""`;
- Decimal/стоимость: приводить к строке без незначащих различий, чтобы
  `1490000`, `1 490 000` и `1490000.00` не расходились;
- валюта: нормализовать к текущему enum (`RUB`, `USD`, `EUR`) до построения
  ключа.

Группировка должна быть стабильной: порядок групп соответствует первому
появлению объекта в Excel. Это важно для `item_no`.

### 5. Preview formset

Файл: `insurance_requests/forms.py`

Добавить поле в `ParserV2ObjectForm`:

```python
source_object_count = forms.IntegerField(
    label='Количество одинаковых объектов',
    min_value=1,
    required=True,
    initial=1,
    widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
)
```

В `to_object_kwargs()` добавить:

```python
'source_object_count': cleaned.get('source_object_count') or 1,
```

В `parser_v2_object_initial_from_payload()` прокинуть:

```python
'source_object_count': obj.get('source_object_count') or 1,
```

Решение по UX: поле можно сделать редактируемым. Если оператор видит, что
автоматическая группировка ошиблась, он сможет исправить кратность в превью.
На первом этапе достаточно numeric input с min=1.

### 6. Два object→kwargs маппинга

Файлы: `insurance_requests/forms.py`, `insurance_requests/views.py`.

В коде есть два места, которые превращают объект parser payload / formset в
kwargs для `InsuranceRequest`:

- `ParserV2ObjectForm.to_object_kwargs()` — активный путь после preview, потому
  что `upload_excel_v2()` собирает `selected_object_kwargs` из formset после
  skip-фильтрации.
- `_parser_v2_object_fields()` во `views.py` — helper/fallback из payload. Даже
  если сейчас он не используется в основном confirm-пути, его нужно обновить,
  чтобы логика не разъехалась при следующем изменении.

В обоих местах нужно прокинуть:

```python
'source_object_count': ... or 1
```

### 7. Шаблон превью

Файл: `insurance_requests/templates/insurance_requests/upload_excel_v2_preview.html`

В карточке объекта добавить поле/бейдж кратности. Рекомендуемое поведение:

- если `source_object_count == 1`, показывать спокойно: "Количество: 1";
- если `source_object_count > 1`, явно подсветить: "Одинаковых строк: N";
- текст кнопки создания партии должен использовать количество создаваемых
  заявок после группировки, а не исходное количество строк.

Например для `A, A, A, B, C, C` в превью:

- `Объект 1 из 3`, одинаковых строк: 3;
- `Объект 2 из 3`, одинаковых строк: 1;
- `Объект 3 из 3`, одинаковых строк: 2;
- submit: `Создать партию из 3 заявок`.

### 8. Создание заявок

Файл: `insurance_requests/views.py`

`_create_requests_with_splitting()` уже принимает `object_kwargs_list`.
После доработки formset каждый `object_kwargs` будет содержать
`source_object_count`.

Проверить три ветки:

- `not object_kwargs_list` fallback: создать заявку с `source_object_count=1`.
- `len(object_kwargs_list) == 1`: создать одну заявку с кратностью из формы.
- `len(object_kwargs_list) >= 2`: создать сестёр, у каждой своя кратность.

Стык со skip: `upload_excel_v2()` сначала строит formset, затем фильтрует формы
с `skip=True`, и только потом передаёт `selected_object_kwargs` в
`_create_requests_with_splitting()`. Поэтому:

- `source_object_count` должен браться из `obj_form.to_object_kwargs()` только
  для неотскипанных форм;
- `item_count` должен считаться по `len(selected_object_kwargs)`, то есть по
  числу оставшихся уникальных групп после skip;
- если после skip осталась одна группа, создаётся одна заявка без
  `source_batch_id/item_no/item_count`, но со своей `source_object_count`.

`item_count` не умножать на `source_object_count`. Это разные сущности:

- `item_count` — сколько заявок в партии после группировки;
- `source_object_count` — сколько одинаковых исходных строк представляет одна
  конкретная заявка.

### 9. Сохранение audit trail

Файл: `insurance_requests/views.py`

`_build_parser_v2_additional_data()` сейчас сохраняет весь
`parser_v2_payload` как `additional_data.parser_v2.parsed_payload`. Нужно
убедиться, что туда попадают:

- сгруппированные `insured_objects`;
- `parsed_payload.object_grouping.raw_object_count`;
- `parsed_payload.object_grouping.unique_object_count`;
- `parsed_payload.object_grouping.groups`.

Если группировка будет сделана в parser-слое и записана в
`parser_v2_payload`, дополнительная логика во view может не потребоваться.

### 10. Детальная страница, список, письма и своды

Обязательный минимум в рамках реализации поля:

- request detail: показать `Количество одинаковых объектов: N`, особенно если
  `N > 1`;
- request list: можно добавить маленький badge `xN` рядом с объектом/ДФА, если
  `N > 1`;
- шаблоны писем страховщикам: использовать `request.source_object_count`;
- своды: использовать `request.source_object_count`, а не пытаться читать
  `additional_data`.

Если письма и своды пока реализуются отдельным этапом, в этом плане достаточно
создать поле и покрыть его тестами, чтобы следующие этапы могли безопасно
подключаться.

## Тесты

Файл: `insurance_requests/test_parser_v2.py`

Добавить тесты:

1. **Один объект без дублей**
   - Excel содержит один объект.
   - Создаётся одна заявка.
   - `source_object_count == 1`.
   - `source_batch_id`, `item_no`, `item_count` остаются `NULL`, как сейчас.

2. **Три полностью одинаковых строки**
   - Excel содержит три идентичных строки объекта.
   - Тест должен падать на текущем коде именно из-за потерянной кратности:
     существующий `seen` оставит одну карточку, но без `source_object_count=3`
     и без `raw_object_count=3`.
   - В превью одна карточка объекта.
   - Submit-кнопка: `Создать заявку`, не `Создать партию из 3 заявок`.
   - Создаётся одна заявка.
   - `source_object_count == 3`.
   - Batch-поля остаются `NULL`.
   - В `additional_data.parser_v2.parsed_payload.object_grouping.raw_object_count == 3`.
   - `unique_object_count == 1`.
   - `duplicate_sources` содержит координаты всех трёх исходных строк.

3. **Смешанный файл `A, A, A, B, C, C`**
   - В превью три карточки.
   - Создаётся три заявки.
   - У заявок кратности `[3, 1, 2]` в порядке первого появления.
   - У всех трёх общий `source_batch_id`.
   - `item_no == [1, 2, 3]`.
   - `item_count == 3`.

4. **Форматные эквиваленты схлопываются**
   - Две строки отличаются только форматированием значимых полей, например
     пробелами или записью стоимости (`1490000`, `1 490 000`, `1490000.00`).
   - В превью одна карточка.
   - `source_object_count == 2`.
   - `raw_object_count == 2`, `unique_object_count == 1`.

5. **Реально разные объекты не схлопываются**
   - Отличается хотя бы одно бизнес-поле, например стоимость или год.
   - Создаются отдельные заявки.
   - У каждой `source_object_count == 1`.

6. **Редактирование кратности в превью**
   - Parser поставил `source_object_count=3`.
   - Оператор поменял в formset на `2`.
   - В БД сохраняется `2`.

7. **Skip работает после группировки**
   - Excel `A, A, B`.
   - В превью две карточки: `A x2`, `B x1`.
   - Оператор skip-ает `A`.
   - Создаётся только `B` с `source_object_count=1`.
   - Так как осталась одна заявка, batch-поля остаются `NULL`.

## Совместимость и миграция данных

Исторические заявки не пересчитывать: у всех старых записей
`source_object_count=1`. В уже обработанных Parser V2 файлах точная кратность
могла быть потеряна текущим `seen`-дедупом до сохранения payload. Надёжно
восстановить её можно только повторным анализом исходных Excel-файлов, а это
отдельная задача и отдельный бизнес-риск.

Новая логика применяется только к новым загрузкам Parser V2.

## Открытые решения для реализации

1. **Где именно размещать helper группировки.**
   Рекомендация: рядом с parser-классом в `parser.py`, потому что группировка
   относится к интерпретации `insured_objects` до preview. Если helper станет
   большим, вынести в `insurance_requests/parsers/excel_v2/object_grouping.py`.

2. **Редактируемость `source_object_count`.**
   Рекомендация: сделать редактируемым в preview. Это минимальный ручной
   escape hatch без усложнения интерфейса.

3. **JSON Schema v2.**
   Так как кратность теперь становится значимым бизнес-параметром для писем и
   сводов, после реализации поля нужно обновить
   `docs/insurance_request_format_package/insurance_request_schema_v2.json`:
   добавить в `insured_object` поле вроде `source_object_count` или
   `identical_source_object_count`.

   Важно: не возвращать старое поле `quantity` без отдельного решения. Оно было
   удалено как отсутствующее в источнике, а новая кратность имеет другую
   семантику.

## Acceptance criteria

- Полностью одинаковые строки объекта не создают множественные одинаковые
  `InsuranceRequest` и не теряют кратность.
- Кратность доступна как `request.source_object_count`.
- Batch-поля отражают количество уникальных групп после схлопывания дублей.
- В `additional_data.parser_v2.parsed_payload.object_grouping` сохраняется
  audit trail исходных строк.
- Existing tests Parser V2 проходят.
- Новые тесты покрывают одиночный объект, полные дубли, смешанный файл,
  форматные эквиваленты, реальные различия, ручную правку кратности и skip
  после группировки.

## Связанные файлы

- `insurance_requests/parsers/excel_v2/parser.py` — извлечение объектов и место
  для группировки `insured_objects`.
- `insurance_requests/forms.py` — `ParserV2ObjectForm`, formset и initial из
  payload.
- `insurance_requests/views.py` — создание заявок после preview и сохранение
  `additional_data`.
- `insurance_requests/templates/insurance_requests/upload_excel_v2_preview.html`
  — карточки объектов в превью.
- `insurance_requests/models.py` — новое поле `source_object_count`.
- `insurance_requests/test_parser_v2.py` — основные regression tests.
- `docs/improvement_plans/json_schema_v2.md` — контекст, почему старое
  `quantity` было удалено.

# Аудит покрытия Excel → БД

Дата: 2026-05-18.
Корпус: `avtozayavka/real_requests/**` + `avtozayavka/im_request/**`, итого **178 файлов `.xls`**.
Скрипт: [`scripts/coverage_audit.py`](../../scripts/coverage_audit.py), полный JSON-отчёт: [`scripts/coverage_audit_result.json`](../../scripts/coverage_audit_result.json).
Связанный план: [own_insurance_request_form.md](own_insurance_request_form.md).

## Что прогоняли

- **Парсер v1** — `core.excel_utils.ExcelReader` (тот, что в проде).
- **Парсер v2** — `insurance_requests.parsers.excel_v2.ExcelRequestParserV2` (новый, с метками-якорями и массивом объектов).
- Для каждого файла оба парсера, режим `application_type`/`application_format` для v1 угадан по имени файла (для v2 определяется внутри).

Поле считается «извлечённым», если в результате парсера лежит не пустое и не дефолтное значение (фильтрация «не указан», `1234567890` и т.п.). Boolean «считается извлечённым» только при `True` — иначе нельзя отличить «нет признака» от «не нашли».

## Сводная таблица покрытия

Поля выстроены в порядке `InsuranceRequest`. Знак ✓ = присутствует в схеме v1.

| Поле модели                | V1 fill | V2 fill | Схема v1 | Замечание                                            |
|----------------------------|--------:|--------:|:--------:|------------------------------------------------------|
| `client_name`              | 92.1 %  | 92.7 %  | ✓        | `customer.name`                                      |
| `inn`                      | 93.8 %  | 92.1 %  | ✓        | `customer.inn`                                       |
| `insurance_type`           | 100 %   | 100 %   | ✓        | `insurance.product`                                  |
| `insurance_period`         | 97.2 %  | 98.3 %  | ✓        | только `kind` (`one_year`/`full_lease`)              |
| `vehicle_info`             | 95.5 %  | 100 %   | ✓        | **слипшийся текст, потеря структуры**                 |
| `dfa_number`               | 93.3 %  | 87.6 %  | ✓        | `request.request_number`                             |
| `branch`                   | 97.8 %  | 91.6 %  | ✓        | `request.branch.name`                                |
| `manager_name`             | 98.3 %  | 100 %   | ✓        | `request.manager.full_name`                          |
| `franchise_type`           | 100 %   | 100 %   | ✓        | только `mode`, без `options`                         |
| `has_installment`          | 12.9 %  | 98.3 %  | ✓        | **v1 почти не ловит** — критичный регресс            |
| `has_autostart`            | 15.2 %  | 44.4 %  | ✓        | `underwriting.autostart`                             |
| `has_casco_ce`             | 50 %    | 91.6 %  | ✓        | `underwriting.casco_category_ce`                     |
| `has_transportation`       | 3.9 %   | 32 %    | ✓        | `additional_coverages.transportation.required`       |
| `has_construction_work`    | **0 %** | **0 %** | ✓        | **ни один парсер не находит** — проверить логику     |
| `manufacturing_year`       | 86 %    | 100 %   | ✓        | `insured_object.manufacturing_year`                  |
| `asset_status`             | 86.5 %  | 88.8 %  | ✓        | регресс v2 устранён (см. ниже)                       |
| `key_completeness`         | 73.6 %  | 91.6 %  | ✓        | `underwriting.key_completeness`                      |
| `pts_psm`                  | 82.6 %  | 83.7 %  | ✓        | `underwriting.title_document`                        |
| `creditor_bank`            | 60.7 %  | 88.2 %  | ✓        | `lease.creditor_bank`                                |
| `usage_purposes`           | 94.9 %  | 98.3 %  | ✓        | `underwriting.usage_purposes`                        |
| `telematics_complex`       | 7.9 %   | 18.5 %  | ✓        | регресс v2 устранён (см. ниже)                       |
| `insurance_territory`      | 3.9 %   | 98.3 %  | ✓        | `insurance.territory`                                |

Падений парсера на 178 файлах: **0** (оба парсера работают best-effort).

## Многообъектные файлы → партии заявок

Распределение по числу объектов в исходном файле (v2):

| Объектов | Файлов |
|---------:|-------:|
| 1        | 132    |
| 2        | 21     |
| 3        | 4      |
| 4–5      | 4      |
| 6        | 11     |
| 8–11     | 5      |
| 15       | 1      |

**46 файлов из 178 (26 %) содержат больше одного объекта страхования.** Максимум — 15 объектов в одном файле.

Что с ними сейчас происходит:

- **V1** склеивает всё в текстовый `vehicle_info`. Структура полностью теряется. Историческое поведение остаётся как есть — историю не разбиваем.
- **V2** видит массив, кладёт его в `data["parser_v2_payload"]["insured_objects"]`. Этот payload в `views.py:143` сохраняется в `additional_data["parser_v2"]["parsed_payload"]` — то есть **в JSON-блоб в одной ячейке, без индексирования и связи**, и **всё ещё в одной записи `InsuranceRequest`**.

### Целевая модель: 1 файл → N заявок

Принципиальное решение: **одна `InsuranceRequest` = ровно один объект страхования.** Если в файле N объектов, V2 при загрузке создаёт N отдельных записей `InsuranceRequest`. Общие реквизиты (клиент, ИНН, тип/период страхования, франшиза, ДФА, филиал, менеджер, банк-кредитор, даты лизинга) дублируются в каждую запись; уникальны только объектные поля (марка, модель, VIN, год, состояние, стоимость, валюта).

Сёстры одной партии связываются полями `source_batch_id` (UUID, общий для всей партии) и `item_no` / `item_count` (1-based). Display-имя выводит «ДФА X / объект K из N» при `item_count > 1`. Каждая запись живёт независимо: свой статус, свой свод, свой PDF/JSON, **своё письмо страховщику**.

**Отдельной таблицы `InsuredObject` НЕ делаем.** Поля объекта живут прямо в `InsuranceRequest`. См. подробнее в [own_insurance_request_form.md](own_insurance_request_form.md#ключевой-архитектурный-принцип-один-объект--одна-заявка).

## Поля JSON Schema v1, которых нет в текущей модели

Эти поля схема предусматривает, но `InsuranceRequest` их не хранит, а парсер не извлекает:

### Заявка
- `request.submission_date` — дата подачи (в research-документе заполнена в 148 / 151).
- `request.applicant_type` (`legal_entity`/`individual_entrepreneur`) — сейчас лежит в `additional_data`, не нормализовано.
- `request.application_format` (`casco_equipment`/`property`) — то же.

### Страхователь
- `customer.legal_address` — research: 133 / 151; мини-аудит 2.2: 30/30.
  **Добавлено в модель** (этап 2.2, миграция `0035_add_customer_fields`).
- `customer.postal_address` — research: 86 / 151; мини-аудит 2.2: 30/30.
  **Добавлено в модель.**
- `customer.business_activity` — research: 115 / 151; мини-аудит 2.2: 30/30.
  **Добавлено в модель.**
- `customer.birth_date` — для ИП; мини-аудит 2.2: 6/30. **Добавлено.**
- `request.submission_date` — мини-аудит 2.2: 30/30. **Добавлено.**
- **ОГРН / КПП — НЕ добавляем.** Изначально предполагалось, но мини-аудит
  показал 0/30 hits. В Excel заявки от лизинга реквизиты ФНС
  страхователя системно отсутствуют (см.
  [json_schema_v2.md](json_schema_v2.md)).

### Лизинговая сделка
- `lease.contract_start_date` / `contract_end_date` — research: 131–134 / 151.
- `lease.insured_party` — лизингодатель / лизингополучатель / оба.

### Параметры страхования
- `insurance.period.start_date` / `end_date` / `months` — сейчас только `kind` enum.
- `coverage_terms.insured_sum_type` — агрегатная / неагрегатная.
- `coverage_terms.indemnity_basis` — с износом / без.
- `coverage_terms.guard_conditions`.
- `coverage_terms.property_location_right_holder` — для страхования имущества.
- `premium_payment.frequency` — поквартально / полугодие / годовая.
- `franchise.options[]` — детальные варианты франшизы с `kind`/`percent`/`amount`. Сейчас в БД только `franchise_type` enum + `franchise_details` JSON (без формальной структуры).

### Объект страхования — **самый большой пробел**

Поля по схеме v1 (`insured_object` — singular, **одна заявка = один объект**):

- `insured_object.brand`, `model`, `vin`, `serial_number` — сейчас слиты в текст.
- `insured_object.manufacturing_year` как integer (есть только текстом).
- `insured_object.condition` — `new` / `used` / `unknown` (есть `asset_status` строкой).
- `insured_object.equipment_type`, `power_or_capacity`, `quantity`.
- `insured_object.acquisition_cost` (money: value + currency) — **стоимость объекта, research показывает наличие в 148 / 151. Никуда не сохраняется.** Это критично для расчёта премии и для нашего PDF.

### Поля партии (новое)

При splitting'е N-объектного файла нужно различать заявки-сёстры:

- `source_batch_id` — UUID партии, общий для всех заявок из одного Excel.
- `item_no`, `item_count` — позиция и размер партии (1-based).

### Андеррайтинг / противоугонные
- `underwriting.telematics.required` (boolean отдельно от текста).
- `underwriting.anti_theft_systems` — `alarm`, `immobilizer`, `mechanical_devices[]`, `satellite_system` (бренд/модель/конфигурация). В исходной Excel-форме это есть (см. метки `OBJECT_TEMPLATE_ROW_MARKERS` в v2), но в БД не выгружается.
- `additional_coverages.transportation.origin` / `destination` / `estimated_days`.
- `additional_coverages.construction_work.description`.

## Ключевые регрессы и подозрительные нули

1. **`has_construction_work` = 0 % в обоих парсерах.** Либо признак в реальных заявках отсутствует (тогда поле в модели зря), либо логика поиска не работает. Нужно глазами проверить 2–3 файла с СМР, и решить.
2. **`asset_status` 86.5 % в v1 → 88.8 % в v2 (исправлено).** Изначально v2 давал 0 %: искал лейблы «статус имущества» / «состояние», которых в шапке столбца K нет. Добавлен fallback по координатам K43/K45/K47/K49 (+ столбец L как страховка от шаблонов со сдвигом и +1 строка для ИП). Теперь v2 обгоняет v1.
3. **`telematics_complex` 7.9 % в v1 → 18.5 % в v2 (исправлено).** Изначально 0 %: лейбл «Телематический комплекс» в C62/C63, а значение лежит **в столбце D через одну строку вниз** (сабхедер «Наименование»). Расширил extractor: ищем значение и в той же строке справа (inline-вариант, проверяется юнит-тестом), и в строках ниже в колонках правее лейбла, отсеивая под-заголовки. Покрытие выросло более чем вдвое относительно v1.
4. **`has_installment` 12.9 % в v1 → 98.3 % в v2.** Здесь v2 правит реальный баг v1 (логика «через отрицание пустоты» почти всегда ложно-отрицательна).
5. **`has_autostart` 15.2 % vs 44.4 %, `has_transportation` 3.9 % vs 32 %.** Похожая картина: v2 ловит ключевые слова, v1 — фиксированные ячейки, которые в реальных заявках часто пустые.

## Выводы для плана

### Что менять в модели до перехода на собственную форму заявки

Все новые поля добавляются **прямо в `InsuranceRequest`** как `null=True, blank=True`. Отдельной таблицы `InsuredObject` НЕ делаем — один объект на одну запись.

1. **Поля партии**: `source_batch_id` (UUID), `item_no` (int), `item_count` (int). Заполняются только V2; для одиночных заявок — `item_count=1`, `item_no=1`. Для исторических V1-заявок — `null`.
2. **Поля объекта** (живут в самой `InsuranceRequest`): `brand`, `model`, `vin`, `serial_number`, `manufacturing_year_int`, `condition` (enum `new`/`used`/`unknown`), `equipment_type`, `power_or_capacity`, `quantity`, `acquisition_cost_value`, `acquisition_cost_currency`.
3. **Реквизиты страхователя**: `ogrn`, `kpp`, `legal_address`, `postal_address`, `business_activity`, `birth_date` (для ИП), `submission_date`.
4. **Параметры сделки**: `contract_start_date`, `contract_end_date`, `insured_party`.
5. **Расширить параметры страхования**: `period_start_date`, `period_end_date`, `period_months`, `insured_sum_type`, `indemnity_basis`, `guard_conditions`, `property_location_right_holder`, `premium_frequency`.
6. **Structured-франшиза**: вместо `franchise_details` JSON-блоба — нормализованный JSON-список `franchise_options` с фиксированной формой (`kind` / `percent` / `amount_value` / `amount_currency`).
7. **Структурированные анти-теф и доп.покрытия**: `anti_theft_alarm`, `anti_theft_immobilizer`, `anti_theft_mechanical`, `anti_theft_satellite` (JSON-объекты); `transportation_origin`, `transportation_destination`, `transportation_estimated_days`; `construction_work_description`.

### Что менять в парсере параллельно

1. ~~Починить регрессы v2: `asset_status`, `telematics_complex`.~~ **Сделано.** Добавлен fallback по координатам K43/K45/K47/K49 для статуса, табличная логика «лейбл → значение в той же строке справа или строкой ниже» для телематики. Изменения локализованы в `_extract_asset_status` / `_extract_telematics_complex` в `insurance_requests/parsers/excel_v2/parser.py`.
2. Решить судьбу `has_construction_work`: либо вынести признак из модели, либо найти в корпусе СМР-заявки и понять, как они выглядят.
3. ~~**Разбор строки объекта** на отдельные поля.~~ **Сделано в этапе 3.1.** V2 теперь раскладывает строку объекта на структурированные поля: `brand`, `model`, `condition`, `equipment_type`, `power_or_capacity`, `acquisition_cost_value`, `acquisition_cost_currency`. Они живут в payload (`parser_v2_payload.insured_objects[]`), в БД пока не пишутся — это произойдёт на этапе 4 (splitting). Per-object fill rate на корпусе 178 файлов / 331 объект:

   | Поле                            | Per-object  | First-of-file |
   |---------------------------------|-------------|---------------|
   | `brand`                         | 98.5%       | 98.9%         |
   | `model`                         | 100%        | 100%          |
   | `condition`                     | 75.5%       | 93.8%         |
   | `equipment_type`                | 14.2%       | 19.7%         |
   | `power_or_capacity`             | 33.8%       | 44.4%         |
   | **`acquisition_cost_value`**    | **76.7%**   | **96.1%**     |
   | **`acquisition_cost_currency`** | **72.2%**   | **90.4%**     |

   Главное достижение: **стоимость объекта** теперь извлекается в 96.1% случаев (research-таргет был ~98%). Это поле раньше не извлекалось вообще ни одним парсером.

   На предыдущей итерации парсер пытался также извлекать `vin` / `serial_number` / `quantity`, но эти поля системно отсутствуют в лизинговой таблице объектов. Удалены — и из модели, и из парсера, и из планируемой [schema v2](json_schema_v2.md).
4. **Реквизиты страхователя**: `customer.legal_address`, `customer.postal_address`, `customer.business_activity`. Research показывает, что в Excel они есть (legal — 133/151, postal — 86/151, activity — 115/151), но V2 их не извлекает. Плюс ОГРН/КПП (нет даже в JSON Schema v1 — добавить в схему).
5. **Даты договора лизинга**: `lease.contract_start_date` / `contract_end_date` (research — 131–134/151), `lease.insured_party` (лизингодатель / лизингополучатель / оба).
6. **Расширение франшизы**: V2 уже находит выделенную колонку (`without_franchise` / `percent_franchise` / `absolute_franchise`), но конкретные значения процентов и абсолютных сумм не парсит. Достать их рядом с выбранной колонкой — заполнит `franchise.options[]` из схемы v1.
7. **Частота рассрочки** (`premium_payment.frequency`): сейчас V2 ловит только сам факт `has_installment` по словам «рассроч/ежекварт/ежемесяч». Добавить классификацию (`quarterly` / `semiannual` / `annual` / `custom`).
8. **Структура противоугонных систем** (`underwriting.anti_theft_systems`): сейчас V2 использует маркеры (`сигнализация`, `иммобилайзер`, `механические противоугонные устройства`, `спутниковая противоугонная система`) только чтобы **пропускать** эти строки в таблице объектов. Надо вместо этого извлекать из них значения: `alarm`/`immobilizer`/`mechanical_devices[]`/`satellite_system` с брендом/моделью.
9. **Условия покрытия для имущества и нестандартные параметры**: `coverage_terms.insured_sum_type` (агрегатная / неагрегатная), `coverage_terms.indemnity_basis` (с износом / без), `coverage_terms.guard_conditions`, `coverage_terms.property_location_right_holder`.
10. **Детали перевозки/СМР**: `additional_coverages.transportation.origin` / `destination` / `estimated_days`, `additional_coverages.construction_work.description`. Сейчас только boolean-флаги.
11. **Splitting-логика в V2-view'е**: при > 1 объект в парсе **создавать N заявок** (одна запись на объект) с общим `source_batch_id` и `item_no=1..N`. UI превью показывает список будущих заявок; оператор подтверждает или редактирует каждую. Это меняет существующий V2-флоу `/upload-v2/` — сейчас он создаёт ровно одну запись. Подробности — в [own_insurance_request_form.md](own_insurance_request_form.md#splitting-в-v2-1-файл--n-заявок).

### Совместимость V1 (прод) и V2 (разработка)

Главный архитектурный принцип — **V1 ничего не теряет и не ломается** при расширении модели. См. отдельную секцию в [own_insurance_request_form.md](own_insurance_request_form.md#совместимость-парсеров-v1-и-v2).

### Дальше — по плану

После расширения модели можно приступать к [пункту 3 плана](own_insurance_request_form.md#3-исходящая-заявка--наш-документ) — собственному PDF, потому что только тогда DTO по схеме v1 будет иметь все поля для рендеринга, а не пустыми местами.

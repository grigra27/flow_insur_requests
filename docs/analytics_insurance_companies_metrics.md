# Аналитика по страховым компаниям: метрики и fallback-правила

## Data Contract

- База сделок: `InsuranceSummary` со статусом `completed_accepted` и непустым `selected_company`.
- Участие СК в сделке: есть хотя бы одно `InsuranceOffer(is_valid=True)` по этой СК в рамках свода.
- Победа СК: `summary.selected_company == company_name`.
- Ценовая позиция: используется `summaries.views._build_deal_price_row`.
- Менеджер Онлайна: `request.created_by`.
- Менеджер Альянса: `request.manager_name`.

## Фильтры и приоритет

1. Даты: если заданы `start_date`/`end_date`, они приоритетнее `period`.
2. `date_mode`:
   - `summary_created`: фильтрация по `summary.created_at`.
   - `completed_at`: фильтрация по `Coalesce(summary.completed_at, summary.updated_at)`.
   - `received_at`: фильтрация по `offers.received_at` (`is_valid=True`).
3. Дополнительные фильтры: `branch`, `insurance_type`, `manager_online`, `manager_alliance`, `selected_company`, `deal_status`.
4. Режим сравнения цены: `comparison_mode` (`selected_variant` / `best_available`).
5. Сопоставимость лет: `full_coverage`.

## KPI (формулы)

- `total_deals`: количество сделок после фильтров.
- `comparable_deals`: сделки, где `_build_deal_price_row` вернул данные.
- `distinct_companies_offered`: число уникальных СК, участвовавших в сделках.
- `distinct_companies_selected`: число уникальных выбранных СК.
- `min_selected_count`: сделки, где выбранная СК = минимум цены.
- `min_selected_rate`: `min_selected_count / comparable_deals * 100`.
- `avg_competitors`: среднее `(comparable_companies_count - 1)` по сопоставимым сделкам.
- `avg_selected_premium`: средняя итоговая премия выбранной СК.
- `median_delta_abs`: медиана `delta_to_min_abs`.
- `median_delta_pct`: медиана `delta_to_min_pct`.
- `avg_rank`: средний `selected_rank` по сопоставимым сделкам.
- `multiyear_rate`: доля сделок, где выбранная СК имеет >1 года страхования.
- `installment_rate`: доля сделок, где у выбранной СК есть рассрочка по выбранному варианту.
- `competitive_deals_count`: число сделок, где участвовали 3 и более СК.
- `competitive_deals_rate`: `competitive_deals_count / total_deals * 100`.
- `avg_offered_companies_per_deal`: среднее число СК с валидными предложениями на одну сделку.
- `avg_hours_request_to_summary`: среднее время между `request.created_at` и `summary.created_at`.
- `avg_hours_summary_to_close`: среднее время между `summary.created_at` и датой закрытия (`completed_at` fallback `updated_at`).

## Рейтинг СК

- `offered_in_deals_count`: в скольких сделках СК участвовала.
- `selected_wins_count`: в скольких сделках СК выбрана.
- `coverage_pct`: `offered_in_deals_count / total_deals * 100`.
- `win_rate_when_offered_pct`: `selected_wins_count / offered_in_deals_count * 100`.
- `win_share_pct`: `selected_wins_count / total_deals * 100`.
- `selected_premium_sum`: сумма премий выбранной СК в победах.
- `selected_premium_avg`: средняя премия выбранной СК в победах.
- `avg_rank_when_selected`: средний ранг выбранной СК в победах.
- `median_delta_abs_when_selected`: медиана отклонения от минимума по победам.
- `min_selected_rate_when_selected`: доля побед, где выбор совпал с минимумом.

## Fallback-правила

- `selected_franchise_variant` пустой/некорректный: используется вариант `1`, это фиксируется в Data Quality.
- Нет валидной премии выбранной СК по одному из лет: `selected_total = None`.
- Пустые `manager_name`, `created_by`, `branch`: отображаются как `Не указан` и учитываются в Data Quality.
- Недостаток сопоставимых сделок (`comparable_deals < 5`): интерфейс показывает предупреждение `insufficient data`.

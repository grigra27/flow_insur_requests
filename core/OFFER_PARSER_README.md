# Парсер Excel файлов предложений страховых компаний

## Обзор

Модуль `offer_excel_parser.py` предоставляет функциональность для автоматического извлечения данных из Excel файлов предложений страховых компаний. Парсер поддерживает многолетние предложения и извлекает данные из специфических ячеек согласно установленному формату.

## Основные возможности

- ✅ Извлечение названия компании из объединенной ячейки A3:A5
- ✅ Извлечение данных по годам страхования из строк 3, 4, 5
- ✅ Поддержка различных числовых форматов (с пробелами, запятыми, символами валют)
- ✅ Обработка как .xlsx (openpyxl), так и .xls (pandas) файлов
- ✅ Валидация извлеченных данных
- ✅ Подробное логирование процесса парсинга
- ✅ Обработка ошибок с информативными сообщениями

## Структура извлекаемых данных

### Ячейки Excel файла

| Ячейка | Описание |
|--------|----------|
| A3:A5 | Название страховой компании (объединенная ячейка) |
| B3, B4, B5 | Года страхования ("1 год", "2 год", "3 год") |
| C3, C4, C5 | Страховые стоимости по годам |
| E3, E4, E5 | Страховые премии с франшизой |
| F3, F4, F5 | Размеры франшиз (вариант 1) |
| H3, H4, H5 | Страховые премии без франшизы |
| I3, I4, I5 | Размеры франшиз (вариант 2) |

### Формат возвращаемых данных

```python
{
    'company_name': str,  # Название компании
    'years_data': [
        {
            'year': str,                        # "1 год", "2 год", "3 год"
            'insurance_sum': Decimal or None,   # Страховая сумма
            'premium_with_franchise': Decimal or None,    # Премия с франшизой
            'franchise_variant1': Decimal or None,        # Франшиза (вариант 1)
            'premium_without_franchise': Decimal or None, # Премия без франшизы
            'franchise_variant2': Decimal or None         # Франшиза (вариант 2)
        },
        # ... до 3 лет
    ]
}
```

## Использование

### Базовое использование

```python
from core.offer_excel_parser import parse_offer_file, validate_offer_data

# Парсинг файла
try:
    offer_data = parse_offer_file('path/to/offer.xlsx')
    
    # Валидация данных
    validated_data = validate_offer_data(offer_data)
    
    print(f"Компания: {offer_data['company_name']}")
    print(f"Количество лет: {len(offer_data['years_data'])}")
    
except OfferParsingError as e:
    print(f"Ошибка парсинга: {e}")
```

### Использование класса напрямую

```python
from core.offer_excel_parser import OfferExcelParser

parser = OfferExcelParser('path/to/offer.xlsx')
try:
    data = parser.parse_offer()
    # Обработка данных
except Exception as e:
    print(f"Ошибка: {e}")
```

### Создание записей InsuranceOffer

```python
from summaries.models import InsuranceOffer, InsuranceSummary

# После парсинга файла
for year_data in offer_data['years_data']:
    offer = InsuranceOffer.objects.create(
        summary=summary,  # Существующий InsuranceSummary
        company_name=offer_data['company_name'],
        insurance_year=year_data['year'],
        insurance_sum=year_data['insurance_sum'],
        yearly_premium_with_franchise=year_data['premium_with_franchise'],
        yearly_premium_without_franchise=year_data['premium_without_franchise'],
        franchise_amount_variant1=year_data['franchise_variant1'],
        franchise_amount_variant2=year_data['franchise_variant2'],
        # Устанавливаем основные поля для совместимости
        insurance_premium=year_data['premium_with_franchise'] or year_data['premium_without_franchise'] or 0
    )
```

## Обработка ошибок

Парсер использует иерархию исключений для различных типов ошибок:

```python
OfferParsingError          # Базовый класс
├── FileParsingError       # Ошибки чтения файла
└── DataValidationError    # Ошибки валидации данных
```

### Примеры обработки ошибок

```python
from core.offer_excel_parser import (
    parse_offer_file, 
    FileParsingError, 
    DataValidationError
)

try:
    data = parse_offer_file('offer.xlsx')
except FileParsingError as e:
    # Файл поврежден или недоступен
    print(f"Не удалось прочитать файл: {e}")
except DataValidationError as e:
    # Данные не прошли валидацию
    print(f"Некорректные данные: {e}")
except Exception as e:
    # Другие ошибки
    print(f"Неожиданная ошибка: {e}")
```

## Валидация данных

Парсер выполняет несколько уровней валидации:

### 1. Структурная валидация
- Проверка наличия обязательных полей
- Проверка типов данных
- Проверка формата структуры

### 2. Бизнес-валидация
- Название компании не должно быть пустым
- Должны быть данные хотя бы по одному году
- Должно быть хотя бы одно числовое значение

### 3. Логическая валидация (предупреждения)
- Премия без франшизы должна быть больше премии с франшизой
- Премия не должна превышать страховую сумму более чем в 2 раза

## Логирование

Парсер использует стандартный модуль `logging` Python:

```python
import logging

# Настройка логирования для отладки
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('core.offer_excel_parser')
```

Уровни логирования:
- `DEBUG`: Детальная информация о процессе парсинга
- `INFO`: Основные этапы обработки
- `WARNING`: Предупреждения о потенциальных проблемах
- `ERROR`: Ошибки парсинга

## Тестирование

Модуль включает комплексные тесты в `test_offer_parser.py`:

```bash
# Запуск всех тестов
python -m unittest core.test_offer_parser -v

# Запуск конкретного теста
python -m unittest core.test_offer_parser.TestOfferExcelParser.test_parse_valid_xlsx_offer -v
```

### Покрытие тестами

- ✅ Парсинг валидных .xlsx файлов
- ✅ Fallback на pandas для проблемных файлов
- ✅ Обработка частичных данных
- ✅ Различные форматы чисел
- ✅ Нормализация строк года
- ✅ Обработка ошибок файлов
- ✅ Валидация данных
- ✅ Извлечение названий компаний

## Производительность

### Рекомендации по оптимизации

1. **Batch-обработка**: Обрабатывайте несколько файлов в одной транзакции
2. **Кэширование**: Сохраняйте результаты парсинга для повторного использования
3. **Асинхронная обработка**: Используйте Celery для больших файлов

### Ограничения

- Максимальный размер файла: зависит от доступной памяти
- Поддерживаемые форматы: .xlsx, .xls
- Максимальное количество лет: 3 (строки 3, 4, 5)

## Интеграция с Django

### Использование в представлениях

```python
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from core.offer_excel_parser import parse_offer_file, OfferParsingError

@require_http_methods(["POST"])
def upload_offer(request):
    uploaded_file = request.FILES.get('offer_file')
    
    if not uploaded_file:
        return JsonResponse({'error': 'Файл не загружен'}, status=400)
    
    try:
        # Сохраняем временный файл
        temp_path = handle_uploaded_file(uploaded_file)
        
        # Парсим файл
        offer_data = parse_offer_file(temp_path)
        
        # Создаем записи в базе данных
        create_offers_from_data(offer_data, request_id)
        
        return JsonResponse({
            'success': True,
            'company': offer_data['company_name'],
            'years': len(offer_data['years_data'])
        })
        
    except OfferParsingError as e:
        return JsonResponse({'error': str(e)}, status=400)
    finally:
        # Удаляем временный файл
        cleanup_temp_file(temp_path)
```

## Требования к формату файлов

### Обязательные элементы
- Название компании в ячейках A3, A4 или A5
- Хотя бы одно числовое значение в строках 3, 4 или 5

### Рекомендуемый формат
- Объединенная ячейка A3:A5 для названия компании
- Заполненные данные по всем трем годам
- Числовые значения без лишнего форматирования

### Поддерживаемые числовые форматы
- `1500000` - обычное число
- `1 500 000` - с пробелами
- `1,500,000` - с запятыми
- `1500000₽` - с символом валюты
- `1500000.50` - с десятичными знаками

## Примеры использования

См. файл `example_offer_parser_usage.py` для полного примера использования парсера.

## Поддержка и разработка

При возникновении проблем:

1. Проверьте логи парсера
2. Убедитесь, что файл соответствует ожидаемому формату
3. Запустите тесты для проверки работоспособности
4. Создайте минимальный пример для воспроизведения проблемы

## История изменений

### v1.0.0 (текущая версия)
- Базовая функциональность парсинга
- Поддержка многолетних предложений
- Валидация данных
- Комплексное тестирование
- Обработка ошибок
- Документация
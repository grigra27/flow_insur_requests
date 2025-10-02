# Обработка Excel файлов

## Обзор

Система автоматически извлекает данные из Excel файлов заявок на страхование. Поддерживаются форматы .xls, .xlsx и .xltx.

## Структура Excel файла

### Основные ячейки для извлечения данных

| Ячейка/Диапазон | Описание | Пример значения |
|-----------------|----------|-----------------|
| HIJ2 | Номер ДФА (договор финансовой аренды) | `ТС-20212-ГА-КЗ` |
| CDEF4 | Филиал | `Казанский филиал` |
| D7 (объединенная D-F) | Название клиента | `ООО "АЛТЫН ЯР"` |
| D9 (объединенная D-F) | ИНН клиента | `1234567890` |
| D21 | Тип страхования "КАСКО" | `любое значение` |
| D22 | Тип страхования "спецтехника" | `любое значение` |
| N17 | Период "1 год" | `любое значение` |
| N18 | Период "на весь срок лизинга" | `любое значение` |
| CDEFGHI43-49 | Информация о предмете лизинга | `специальный, грузовой бортовой...` |
| D29 | Франшизы НЕТ | `любое значение` |
| F34 | Рассрочки нет | `любое значение` |
| M24 | Автозапуск | `нет` или другое значение |
| CDEFGHI45 | КАСКО категория C/E | `любое значение в любой ячейке` |

### Новые функции (версия 2.0+)

#### Автоматическое определение КАСКО C/E

Система автоматически определяет наличие КАСКО категории C/E на основе строки 45:

- **Проверяемые ячейки**: C45, D45, E45, F45, G45, H45, I45
- **Логика**: Если любая из ячеек содержит непустое значение → `has_casco_ce = True`
- **По умолчанию**: Если все ячейки пустые → `has_casco_ce = False`

```python
# Пример логики определения
def _determine_casco_ce_openpyxl(self, sheet) -> bool:
    """Определяет наличие КАСКО кат. C/E на основе строки 45 столбцов CDEFGHI"""
    try:
        # Проверяем ячейки C45, D45, E45, F45, G45, H45, I45
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I']:
            cell_value = sheet[f'{col}45'].value
            if cell_value is not None and str(cell_value).strip():
                return True
        return False
    except Exception as e:
        logger.warning(f"Error determining CASCO C/E status: {str(e)}")
        return False
```

## Логика обработки

### 1. Определение типа страхования

```python
def determine_insurance_type(self, data):
    """Определяет тип страхования на основе заполненных ячеек"""
    if data.get('d21'):  # Ячейка D21 заполнена
        return 'КАСКО'
    elif data.get('d22'):  # Ячейка D22 заполнена
        return 'страхование спецтехники'
    else:
        return 'страхование имущества'  # По умолчанию
```

### 2. Определение периода страхования

```python
def determine_insurance_period(self, data):
    """Определяет период страхования"""
    if data.get('n17'):  # Ячейка N17 заполнена
        return '1 год'
    elif data.get('n18'):  # Ячейка N18 заполнена
        return 'на весь срок лизинга'
    else:
        return '1 год'  # По умолчанию
```

### 3. Извлечение информации о предмете лизинга

```python
def extract_leasing_subject_info(self, data):
    """Извлекает информацию о предмете лизинга из строк 43-49"""
    info_parts = []
    
    # Проверяем строки 43-49 в столбцах C-I
    for row in range(43, 50):
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I']:
            cell_key = f'{col.lower()}{row}'
            if data.get(cell_key):
                value = str(data[cell_key]).strip()
                if value and value not in info_parts:
                    info_parts.append(value)
    
    return ' '.join(info_parts) if info_parts else 'Не указано'
```

### 4. Определение наличия дополнительных опций

```python
def determine_additional_options(self, data):
    """Определяет наличие дополнительных опций"""
    return {
        'has_franchise': not bool(data.get('d29')),  # Если D29 пустая, то франшиза есть
        'has_installment': not bool(data.get('f34')),  # Если F34 пустая, то рассрочка есть
        'has_autostart': data.get('m24', '').lower() != 'нет',  # Если M24 не "нет", то автозапуск есть
        'has_casco_ce': self._determine_casco_ce(data)  # Автоматическое определение
    }
```

## Поддерживаемые форматы файлов

### .xlsx (Excel 2007+)
- Обработка через библиотеку `openpyxl`
- Поддержка объединенных ячеек
- Поддержка формул и форматирования

### .xls (Excel 97-2003)
- Обработка через библиотеку `pandas` с `xlrd`
- Ограниченная поддержка объединенных ячеек
- Базовое извлечение данных

### .xltx (Excel Template)
- Обработка как .xlsx файлы
- Поддержка шаблонов Excel

## Обработка ошибок

### Типичные ошибки и их обработка

1. **Файл поврежден или не является Excel файлом**
   ```python
   try:
       workbook = openpyxl.load_workbook(file_path)
   except Exception as e:
       logger.error(f"Cannot open Excel file: {str(e)}")
       raise ValidationError("Файл поврежден или не является Excel файлом")
   ```

2. **Отсутствие необходимых ячеек**
   ```python
   try:
       value = sheet['D7'].value
   except KeyError:
       logger.warning("Cell D7 not found, using default value")
       value = None
   ```

3. **Ошибки кодировки**
   ```python
   try:
       text_value = str(cell_value).encode('utf-8').decode('utf-8')
   except UnicodeError:
       logger.warning(f"Encoding error for cell value: {cell_value}")
       text_value = str(cell_value)
   ```

### Логирование

Система ведет подробное логирование процесса обработки:

```python
import logging
logger = logging.getLogger(__name__)

# Информационные сообщения
logger.info(f"Processing Excel file: {filename}")
logger.info(f"Extracted data: DFA={dfa_number}, Client={client_name}")

# Предупреждения
logger.warning(f"Cell D7 is empty, using default client name")
logger.warning(f"Cannot determine insurance type, using default")

# Ошибки
logger.error(f"Failed to process Excel file: {str(e)}")
```

## Примеры использования

### Базовое использование

```python
from core.excel_utils import ExcelReader

# Создание экземпляра читателя
reader = ExcelReader()

# Обработка файла
try:
    data = reader.read_excel_file('/path/to/file.xlsx')
    print(f"Клиент: {data['client_name']}")
    print(f"ДФА: {data['dfa_number']}")
    print(f"Тип страхования: {data['insurance_type']}")
    print(f"КАСКО C/E: {data['has_casco_ce']}")
except Exception as e:
    print(f"Ошибка обработки: {str(e)}")
```

### Обработка в Django view

```python
from django.shortcuts import render, redirect
from django.contrib import messages
from core.excel_utils import ExcelReader
from .models import InsuranceRequest

def upload_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        try:
            # Обработка Excel файла
            reader = ExcelReader()
            data = reader.read_excel_file(excel_file)
            
            # Создание заявки
            insurance_request = InsuranceRequest.objects.create(
                dfa_number=data['dfa_number'],
                branch=data['branch'],
                client_name=data['client_name'],
                inn=data['inn'],
                insurance_type=data['insurance_type'],
                insurance_period=data['insurance_period'],
                leasing_subject_info=data['leasing_subject_info'],
                has_franchise=data['has_franchise'],
                has_installment=data['has_installment'],
                has_autostart=data['has_autostart'],
                has_casco_ce=data['has_casco_ce'],  # Автоматически определено
                created_by=request.user
            )
            
            messages.success(request, f'Заявка {insurance_request.dfa_number} успешно создана')
            return redirect('request_detail', pk=insurance_request.pk)
            
        except Exception as e:
            messages.error(request, f'Ошибка обработки файла: {str(e)}')
    
    return render(request, 'upload_excel.html')
```

## Тестирование

### Создание тестовых файлов

```python
import openpyxl
from openpyxl import Workbook

def create_test_excel_file():
    """Создает тестовый Excel файл с данными"""
    wb = Workbook()
    ws = wb.active
    
    # Основные данные
    ws['H2'] = 'ТС-20212-ГА-КЗ'  # ДФА
    ws['C4'] = 'Казанский филиал'  # Филиал
    ws['D7'] = 'ООО "ТЕСТ КЛИЕНТ"'  # Клиент
    ws['D9'] = '1234567890'  # ИНН
    ws['D21'] = 'КАСКО'  # Тип страхования
    ws['N17'] = '1 год'  # Период
    ws['C45'] = 'C/E'  # КАСКО C/E
    
    # Информация о предмете лизинга
    ws['D43'] = 'легковой автомобиль'
    ws['E44'] = 'LADA Vesta'
    
    wb.save('test_file.xlsx')
    return 'test_file.xlsx'
```

### Unit тесты

```python
import unittest
from core.excel_utils import ExcelReader

class TestExcelReader(unittest.TestCase):
    
    def setUp(self):
        self.reader = ExcelReader()
        self.test_file = create_test_excel_file()
    
    def test_basic_data_extraction(self):
        """Тест базового извлечения данных"""
        data = self.reader.read_excel_file(self.test_file)
        
        self.assertEqual(data['dfa_number'], 'ТС-20212-ГА-КЗ')
        self.assertEqual(data['client_name'], 'ООО "ТЕСТ КЛИЕНТ"')
        self.assertEqual(data['insurance_type'], 'КАСКО')
    
    def test_casco_ce_detection(self):
        """Тест автоматического определения КАСКО C/E"""
        data = self.reader.read_excel_file(self.test_file)
        
        self.assertTrue(data['has_casco_ce'])
    
    def test_empty_file_handling(self):
        """Тест обработки пустого файла"""
        empty_file = create_empty_excel_file()
        
        with self.assertRaises(ValidationError):
            self.reader.read_excel_file(empty_file)
    
    def tearDown(self):
        # Очистка тестовых файлов
        os.remove(self.test_file)
```

## Производительность

### Оптимизация обработки

1. **Кэширование результатов**
   ```python
   from django.core.cache import cache
   
   def read_excel_file_cached(self, file_path):
       cache_key = f"excel_data_{hash(file_path)}"
       data = cache.get(cache_key)
       
       if data is None:
           data = self.read_excel_file(file_path)
           cache.set(cache_key, data, timeout=3600)  # 1 час
       
       return data
   ```

2. **Асинхронная обработка**
   ```python
   from celery import shared_task
   
   @shared_task
   def process_excel_file_async(file_path, user_id):
       """Асинхронная обработка Excel файла"""
       try:
           reader = ExcelReader()
           data = reader.read_excel_file(file_path)
           
           # Создание заявки
           InsuranceRequest.objects.create(
               **data,
               created_by_id=user_id
           )
           
           return {'status': 'success', 'data': data}
       except Exception as e:
           return {'status': 'error', 'message': str(e)}
   ```

3. **Пакетная обработка**
   ```python
   def process_multiple_files(self, file_paths):
       """Обработка нескольких файлов за раз"""
       results = []
       
       for file_path in file_paths:
           try:
               data = self.read_excel_file(file_path)
               results.append({'file': file_path, 'data': data, 'status': 'success'})
           except Exception as e:
               results.append({'file': file_path, 'error': str(e), 'status': 'error'})
       
       return results
   ```

## Миграция данных

### Обновление существующих заявок

При добавлении новых функций (например, автоматического определения КАСКО C/E) может потребоваться обновление существующих заявок:

```python
from django.core.management.base import BaseCommand
from insurance_requests.models import InsuranceRequest
from core.excel_utils import ExcelReader

class Command(BaseCommand):
    help = 'Update existing requests with CASCO C/E detection'
    
    def handle(self, *args, **options):
        reader = ExcelReader()
        updated_count = 0
        
        # Обновляем заявки, у которых есть прикрепленные файлы
        for request in InsuranceRequest.objects.filter(attachment__isnull=False):
            try:
                # Повторно обрабатываем файл
                file_path = request.attachment.file.path
                data = reader.read_excel_file(file_path)
                
                # Обновляем поле has_casco_ce
                if request.has_casco_ce != data['has_casco_ce']:
                    request.has_casco_ce = data['has_casco_ce']
                    request.save()
                    updated_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Error processing request {request.id}: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {updated_count} requests')
        )
```

## Расширение функциональности

### Добавление новых полей

Для добавления извлечения новых данных из Excel файлов:

1. **Обновите метод извлечения данных**:
   ```python
   def _extract_data_openpyxl(self, workbook):
       # ... существующий код ...
       
       # Новое поле
       data['new_field'] = self._get_cell_value(sheet, 'A1')
       
       return data
   ```

2. **Обновите модель данных**:
   ```python
   class InsuranceRequest(models.Model):
       # ... существующие поля ...
       new_field = models.CharField(max_length=255, blank=True, verbose_name='Новое поле')
   ```

3. **Создайте миграцию**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. **Обновите тесты**:
   ```python
   def test_new_field_extraction(self):
       data = self.reader.read_excel_file(self.test_file)
       self.assertIn('new_field', data)
   ```

### Поддержка новых форматов

Для добавления поддержки новых форматов файлов (например, .csv):

```python
import csv
import pandas as pd

class ExcelReader:
    def read_file(self, file_path):
        """Универсальный метод чтения файлов"""
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension in ['.xlsx', '.xltx']:
            return self._extract_data_openpyxl(file_path)
        elif file_extension == '.xls':
            return self._extract_data_pandas(file_path)
        elif file_extension == '.csv':
            return self._extract_data_csv(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
    
    def _extract_data_csv(self, file_path):
        """Извлечение данных из CSV файла"""
        data = self._get_default_data()
        
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            
            # Логика извлечения данных из CSV
            if 'client_name' in df.columns:
                data['client_name'] = df['client_name'].iloc[0] if not df.empty else ''
            
            # ... дополнительная логика ...
            
        except Exception as e:
            logger.error(f"Error reading CSV file: {str(e)}")
            raise
        
        return data
```

---

**Версия документа**: 2.0  
**Дата обновления**: $(date +%d.%m.%Y)  
**Автор**: Команда разработки системы управления страховыми заявками
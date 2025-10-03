# Обработка Excel файлов

## Обзор

Система автоматически извлекает данные из Excel файлов заявок на страхование. Поддерживаются форматы .xls, .xlsx и .xltx.

**Новая функциональность (версия 3.0+)**: Система поддерживает два типа заявок:
- **Заявка от юридического лица** - стандартная структура файла
- **Заявка от ИП** - структура с дополнительной строкой в позиции 8, что смещает данные ниже этой строки на одну позицию вниз

## Типы заявок и структура файлов

### Заявка от юридического лица (стандартная)

Используется существующая структура файла без изменений.

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

### Заявка от ИП (с смещением строк)

В заявках от ИП добавляется дополнительная строка в позиции 8, что приводит к смещению всех данных ниже 8-й строки на одну позицию вниз.

| Ячейка/Диапазон | Описание | Пример значения | Изменение |
|-----------------|----------|-----------------|-----------|
| HIJ2 | Номер ДФА | `ТС-20212-ГА-КЗ` | Без изменений |
| CDEF4 | Филиал | `Казанский филиал` | Без изменений |
| D7 (объединенная D-F) | Название клиента | `ИП Иванов И.И.` | Без изменений |
| **D10** (объединенная D-F) | ИНН клиента | `123456789012` | **Было D9** |
| **D22** | Тип страхования "КАСКО" | `любое значение` | **Было D21** |
| **D23** | Тип страхования "спецтехника" | `любое значение` | **Было D22** |
| **N18** | Период "1 год" | `любое значение` | **Было N17** |
| **N19** | Период "на весь срок лизинга" | `любое значение` | **Было N18** |
| CDEFGHI43-49 | Информация о предмете лизинга | `специальный, грузовой бортовой...` | Без изменений |
| **D30** | Франшизы НЕТ | `любое значение` | **Было D29** |
| **F35** | Рассрочки нет | `любое значение` | **Было F34** |
| **M25** | Автозапуск | `нет` или другое значение | **Было M24** |
| CDEFGHI45 | КАСКО категория C/E | `любое значение в любой ячейке` | Без изменений |

### Логика смещения строк

Система автоматически применяет следующую логику:

```python
def _get_adjusted_row(self, row_number: int) -> int:
    """
    Возвращает скорректированный номер строки с учетом типа заявки
    
    Args:
        row_number: Базовый номер строки для заявки от юр.лица
        
    Returns:
        Скорректированный номер строки
    """
    if self.application_type == 'individual_entrepreneur' and row_number > 8:
        return row_number + 1
    return row_number
```

**Правила смещения:**
- Строки 1-8: остаются без изменений для всех типов заявок
- Строки 9 и выше: для заявок от ИП смещаются на +1 позицию
- Столбцы: остаются без изменений для всех типов заявок

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

# Создание экземпляра читателя для заявки от юр.лица (по умолчанию)
reader = ExcelReader('/path/to/file.xlsx', application_type='legal_entity')

# Создание экземпляра читателя для заявки от ИП
reader_ip = ExcelReader('/path/to/file.xlsx', application_type='individual_entrepreneur')

# Обработка файла
try:
    data = reader.read_excel_file()
    print(f"Клиент: {data['client_name']}")
    print(f"ДФА: {data['dfa_number']}")
    print(f"Тип страхования: {data['insurance_type']}")
    print(f"КАСКО C/E: {data['has_casco_ce']}")
    print(f"Тип заявки: {reader.application_type}")
except Exception as e:
    print(f"Ошибка обработки: {str(e)}")
```

### Сравнение извлечения данных для разных типов заявок

```python
from core.excel_utils import ExcelReader

# Обработка одного и того же файла как разных типов заявок
file_path = '/path/to/application.xlsx'

# Как заявка от юр.лица
legal_reader = ExcelReader(file_path, application_type='legal_entity')
legal_data = legal_reader.read_excel_file()

# Как заявка от ИП
ip_reader = ExcelReader(file_path, application_type='individual_entrepreneur')
ip_data = ip_reader.read_excel_file()

# Сравнение результатов
print("Сравнение извлеченных данных:")
print(f"ИНН (юр.лицо): {legal_data['inn']} (из ячейки D9)")
print(f"ИНН (ИП): {ip_data['inn']} (из ячейки D10)")
print(f"Тип страхования (юр.лицо): {legal_data['insurance_type']} (из D21/D22)")
print(f"Тип страхования (ИП): {ip_data['insurance_type']} (из D22/D23)")
```

### Обработка в Django view

```python
from django.shortcuts import render, redirect
from django.contrib import messages
from core.excel_utils import ExcelReader
from .models import InsuranceRequest
from .forms import ExcelUploadForm

def upload_excel(request):
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            excel_file = form.cleaned_data['excel_file']
            application_type = form.cleaned_data['application_type']
            
            try:
                # Обработка Excel файла с указанием типа заявки
                reader = ExcelReader(excel_file, application_type=application_type)
                data = reader.read_excel_file()
                
                # Логирование выбранного типа заявки
                logger.info(f"Processing {application_type} application: {excel_file.name}")
                
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
                
                success_msg = f'Заявка {insurance_request.dfa_number} успешно создана (тип: {application_type})'
                messages.success(request, success_msg)
                return redirect('request_detail', pk=insurance_request.pk)
                
            except Exception as e:
                error_msg = f'Ошибка обработки файла (тип: {application_type}): {str(e)}'
                messages.error(request, error_msg)
                logger.error(f"Excel processing error for {application_type}: {str(e)}")
    else:
        form = ExcelUploadForm()
    
    return render(request, 'upload_excel.html', {'form': form})
```

## Тестирование

### Создание тестовых файлов

```python
import openpyxl
from openpyxl import Workbook

def create_test_legal_entity_file():
    """Создает тестовый Excel файл для заявки от юр.лица"""
    wb = Workbook()
    ws = wb.active
    
    # Основные данные (стандартные ячейки)
    ws['H2'] = 'ТС-20212-ГА-КЗ'  # ДФА
    ws['C4'] = 'Казанский филиал'  # Филиал
    ws['D7'] = 'ООО "ТЕСТ КЛИЕНТ"'  # Клиент
    ws['D9'] = '1234567890'  # ИНН (стандартная позиция)
    ws['D21'] = 'КАСКО'  # Тип страхования (стандартная позиция)
    ws['N17'] = '1 год'  # Период (стандартная позиция)
    ws['D29'] = ''  # Франшиза (стандартная позиция)
    ws['F34'] = ''  # Рассрочка (стандартная позиция)
    ws['M24'] = 'нет'  # Автозапуск (стандартная позиция)
    ws['C45'] = 'C/E'  # КАСКО C/E
    
    # Информация о предмете лизинга
    ws['D43'] = 'легковой автомобиль'
    ws['E44'] = 'LADA Vesta'
    
    wb.save('test_legal_entity.xlsx')
    return 'test_legal_entity.xlsx'

def create_test_ip_file():
    """Создает тестовый Excel файл для заявки от ИП"""
    wb = Workbook()
    ws = wb.active
    
    # Основные данные
    ws['H2'] = 'ТС-20212-ГА-КЗ'  # ДФА (без изменений)
    ws['C4'] = 'Казанский филиал'  # Филиал (без изменений)
    ws['D7'] = 'ИП Иванов И.И.'  # Клиент (без изменений)
    
    # Добавляем дополнительную строку в позиции 8
    ws['D8'] = 'Дополнительная информация для ИП'
    
    # Данные смещены на одну строку вниз
    ws['D10'] = '123456789012'  # ИНН (было D9)
    ws['D22'] = 'КАСКО'  # Тип страхования (было D21)
    ws['N18'] = '1 год'  # Период (было N17)
    ws['D30'] = ''  # Франшиза (было D29)
    ws['F35'] = ''  # Рассрочка (было F34)
    ws['M25'] = 'нет'  # Автозапуск (было M24)
    ws['C45'] = 'C/E'  # КАСКО C/E (без изменений)
    
    # Информация о предмете лизинга (без изменений)
    ws['D43'] = 'легковой автомобиль'
    ws['E44'] = 'LADA Vesta'
    
    wb.save('test_ip.xlsx')
    return 'test_ip.xlsx'

def create_comparison_test_files():
    """Создает пару файлов для сравнения типов заявок"""
    legal_file = create_test_legal_entity_file()
    ip_file = create_test_ip_file()
    
    return {
        'legal_entity': legal_file,
        'individual_entrepreneur': ip_file
    }
```

### Unit тесты

```python
import unittest
import os
from core.excel_utils import ExcelReader
from django.core.exceptions import ValidationError

class TestExcelReader(unittest.TestCase):
    
    def setUp(self):
        self.test_files = create_comparison_test_files()
        self.legal_file = self.test_files['legal_entity']
        self.ip_file = self.test_files['individual_entrepreneur']
    
    def test_legal_entity_data_extraction(self):
        """Тест извлечения данных из заявки от юр.лица"""
        reader = ExcelReader(self.legal_file, application_type='legal_entity')
        data = reader.read_excel_file()
        
        self.assertEqual(data['dfa_number'], 'ТС-20212-ГА-КЗ')
        self.assertEqual(data['client_name'], 'ООО "ТЕСТ КЛИЕНТ"')
        self.assertEqual(data['inn'], '1234567890')
        self.assertEqual(data['insurance_type'], 'КАСКО')
    
    def test_ip_data_extraction(self):
        """Тест извлечения данных из заявки от ИП"""
        reader = ExcelReader(self.ip_file, application_type='individual_entrepreneur')
        data = reader.read_excel_file()
        
        self.assertEqual(data['dfa_number'], 'ТС-20212-ГА-КЗ')
        self.assertEqual(data['client_name'], 'ИП Иванов И.И.')
        self.assertEqual(data['inn'], '123456789012')  # Из ячейки D10 вместо D9
        self.assertEqual(data['insurance_type'], 'КАСКО')
    
    def test_row_adjustment_logic(self):
        """Тест логики смещения строк"""
        legal_reader = ExcelReader(self.legal_file, application_type='legal_entity')
        ip_reader = ExcelReader(self.ip_file, application_type='individual_entrepreneur')
        
        # Проверяем, что строки до 8 включительно не смещаются
        self.assertEqual(legal_reader._get_adjusted_row(7), 7)
        self.assertEqual(ip_reader._get_adjusted_row(7), 7)
        self.assertEqual(legal_reader._get_adjusted_row(8), 8)
        self.assertEqual(ip_reader._get_adjusted_row(8), 8)
        
        # Проверяем, что строки после 8 смещаются только для ИП
        self.assertEqual(legal_reader._get_adjusted_row(9), 9)
        self.assertEqual(ip_reader._get_adjusted_row(9), 10)
        self.assertEqual(legal_reader._get_adjusted_row(21), 21)
        self.assertEqual(ip_reader._get_adjusted_row(21), 22)
    
    def test_application_type_comparison(self):
        """Тест сравнения результатов для разных типов заявок"""
        # Используем один файл, но обрабатываем как разные типы
        legal_reader = ExcelReader(self.legal_file, application_type='legal_entity')
        legal_data = legal_reader.read_excel_file()
        
        # Обрабатываем тот же файл как заявку от ИП
        ip_reader = ExcelReader(self.legal_file, application_type='individual_entrepreneur')
        ip_data = ip_reader.read_excel_file()
        
        # ИНН должен извлекаться из разных ячеек
        self.assertNotEqual(legal_data['inn'], ip_data['inn'])
        
        # Данные, которые не зависят от смещения, должны быть одинаковыми
        self.assertEqual(legal_data['dfa_number'], ip_data['dfa_number'])
        self.assertEqual(legal_data['client_name'], ip_data['client_name'])
    
    def test_casco_ce_detection(self):
        """Тест автоматического определения КАСКО C/E для разных типов заявок"""
        legal_reader = ExcelReader(self.legal_file, application_type='legal_entity')
        legal_data = legal_reader.read_excel_file()
        
        ip_reader = ExcelReader(self.ip_file, application_type='individual_entrepreneur')
        ip_data = ip_reader.read_excel_file()
        
        # КАСКО C/E должно определяться одинаково для обоих типов
        self.assertTrue(legal_data['has_casco_ce'])
        self.assertTrue(ip_data['has_casco_ce'])
    
    def test_backward_compatibility(self):
        """Тест обратной совместимости - по умолчанию используется тип 'legal_entity'"""
        # Создание читателя без указания типа заявки
        reader = ExcelReader(self.legal_file)
        self.assertEqual(reader.application_type, 'legal_entity')
        
        # Данные должны извлекаться корректно
        data = reader.read_excel_file()
        self.assertEqual(data['inn'], '1234567890')
    
    def test_invalid_application_type(self):
        """Тест обработки некорректного типа заявки"""
        with self.assertRaises(ValueError):
            ExcelReader(self.legal_file, application_type='invalid_type')
    
    def test_empty_file_handling(self):
        """Тест обработки пустого файла"""
        empty_file = create_empty_excel_file()
        reader = ExcelReader(empty_file, application_type='legal_entity')
        
        with self.assertRaises(ValidationError):
            reader.read_excel_file()
    
    def tearDown(self):
        # Очистка тестовых файлов
        for file_path in self.test_files.values():
            if os.path.exists(file_path):
                os.remove(file_path)
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

## Выбор типа заявки в интерфейсе

### Форма загрузки Excel файла

Начиная с версии 3.0, пользователи должны выбирать тип заявки перед загрузкой файла:

```python
# forms.py
from django import forms

class ExcelUploadForm(forms.Form):
    APPLICATION_TYPE_CHOICES = [
        ('legal_entity', 'Заявка от юр.лица'),
        ('individual_entrepreneur', 'Заявка от ИП'),
    ]
    
    application_type = forms.ChoiceField(
        choices=APPLICATION_TYPE_CHOICES,
        label='Тип заявки',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Выберите тип загружаемой заявки для корректной обработки данных'
    )
    
    excel_file = forms.FileField(
        label='Excel файл',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xls,.xlsx,.xltx'})
    )
```

### Валидация формы

```python
def clean_application_type(self):
    application_type = self.cleaned_data.get('application_type')
    
    if not application_type:
        raise forms.ValidationError('Необходимо выбрать тип заявки')
    
    if application_type not in ['legal_entity', 'individual_entrepreneur']:
        raise forms.ValidationError('Некорректный тип заявки')
    
    return application_type
```

### Отображение различий в шаблоне

В шаблоне `upload_excel.html` отображается таблица с различиями между типами заявок:

- **Желтым фоном** выделены строки, где есть различия между типами
- **Красным цветом** выделены ячейки, которые отличаются для заявок от ИП
- Приводятся примеры корректного заполнения для каждого типа

## Миграция и обновление

### Обновление существующего кода

При обновлении до версии 3.0 необходимо:

1. **Обновить вызовы ExcelReader**:
   ```python
   # Старый код
   reader = ExcelReader()
   data = reader.read_excel_file(file_path)
   
   # Новый код
   reader = ExcelReader(file_path, application_type='legal_entity')
   data = reader.read_excel_file()
   ```

2. **Обновить формы загрузки**:
   - Добавить поле выбора типа заявки
   - Обновить валидацию формы
   - Передавать тип заявки в ExcelReader

3. **Обновить тесты**:
   - Добавить тесты для обоих типов заявок
   - Проверить логику смещения строк
   - Убедиться в обратной совместимости

### Обратная совместимость

Система сохраняет обратную совместимость:
- По умолчанию используется тип `legal_entity`
- Существующий код продолжает работать без изменений
- Все существующие заявки обрабатываются корректно

---

**Версия документа**: 3.0  
**Дата обновления**: 03.10.2025  
**Автор**: Команда разработки системы управления страховыми заявками

### История изменений

- **v3.0** (03.10.2025): Добавлена поддержка заявок от ИП с логикой смещения строк
- **v2.0**: Добавлено автоматическое определение КАСКО C/E
- **v1.0**: Базовая функциональность обработки Excel файлов
"""
Сервисы для работы со сводами предложений
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook
from openpyxl.workbook import Workbook
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError

from ..models import InsuranceSummary, InsuranceOffer
from ..exceptions import DuplicateOfferError
from insurance_requests.models import InsuranceRequest


logger = logging.getLogger(__name__)


class ExcelExportServiceError(Exception):
    """Базовое исключение для ошибок ExcelExportService"""
    pass


class TemplateNotFoundError(ExcelExportServiceError):
    """Исключение для случаев, когда шаблон Excel не найден"""
    pass


class InvalidSummaryDataError(ExcelExportServiceError):
    """Исключение для случаев, когда данные свода некорректны"""
    pass


# Исключения для обработки Excel файлов с ответами компаний
class ExcelProcessingError(Exception):
    """Базовое исключение для ошибок обработки Excel файлов"""
    pass


class InvalidFileFormatError(ExcelProcessingError):
    """Ошибка неверного формата файла"""
    pass


class MissingDataError(ExcelProcessingError):
    """Ошибка отсутствующих данных"""
    def __init__(self, missing_cells):
        self.missing_cells = missing_cells
        super().__init__(f"Отсутствуют данные в ячейках: {', '.join(missing_cells)}")


class InvalidDataError(ExcelProcessingError):
    """Ошибка некорректных данных"""
    def __init__(self, field_name, value, expected_format):
        self.field_name = field_name
        self.value = value
        self.expected_format = expected_format
        super().__init__(f"Некорректное значение в поле '{field_name}': '{value}'. Ожидается: {expected_format}")


class RowProcessingError(ExcelProcessingError):
    """Ошибка обработки конкретной строки"""
    def __init__(self, row_number, field_name, error_message, cell_address=None):
        self.row_number = row_number
        self.field_name = field_name
        self.cell_address = cell_address
        self.error_message = error_message
        
        # Формируем детальное сообщение об ошибке
        if cell_address:
            super().__init__(f"Ошибка в строке {row_number}, ячейка {cell_address}, поле '{field_name}': {error_message}")
        else:
            super().__init__(f"Ошибка в строке {row_number}, поле '{field_name}': {error_message}")


class ExcelExportService:
    """Сервис для генерации Excel-файлов сводов предложений"""
    
    def __init__(self, template_path: str):
        """
        Инициализация сервиса
        
        Args:
            template_path: Путь к файлу шаблона Excel
        """
        self.template_path = Path(template_path)
        self._validate_template()
    
    def _validate_template(self) -> None:
        """Проверяет доступность шаблона Excel"""
        if not self.template_path.exists():
            error_msg = f"Шаблон Excel не найден по пути: {self.template_path}"
            logger.error(error_msg)
            raise TemplateNotFoundError(error_msg)
        
        if not self.template_path.is_file():
            error_msg = f"Путь к шаблону не является файлом: {self.template_path}"
            logger.error(error_msg)
            raise TemplateNotFoundError(error_msg)
    
    def generate_summary_excel(self, summary: InsuranceSummary) -> BytesIO:
        """
        Генерирует Excel-файл для свода предложений
        
        Args:
            summary: Объект свода предложений
            
        Returns:
            BytesIO: Сгенерированный Excel-файл в памяти
            
        Raises:
            InvalidSummaryDataError: Если данные свода некорректны
            ExcelExportServiceError: При ошибках работы с Excel
        """
        logger.info(f"Начинаем генерацию Excel-файла для свода ID: {summary.id}")
        
        try:
            # Валидация данных свода
            self._validate_summary_data(summary)
            
            # Загрузка шаблона
            workbook = self._load_template()
            
            # Заполнение данными
            self._fill_template_data(workbook, summary)
            
            # Сохранение в память
            excel_buffer = BytesIO()
            workbook.save(excel_buffer)
            excel_buffer.seek(0)
            
            logger.info(f"Excel-файл успешно сгенерирован для свода ID: {summary.id}")
            return excel_buffer
            
        except (InvalidSummaryDataError, TemplateNotFoundError):
            # Переброс известных исключений
            raise
        except Exception as e:
            error_msg = f"Ошибка при генерации Excel-файла для свода ID {summary.id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ExcelExportServiceError(error_msg) from e
    
    def _validate_summary_data(self, summary: InsuranceSummary) -> None:
        """
        Валидирует данные свода перед генерацией
        
        Args:
            summary: Объект свода предложений
            
        Raises:
            InvalidSummaryDataError: Если данные некорректны
        """
        missing_fields = []
        
        # Проверка наличия связанной заявки
        if not summary.request:
            missing_fields.append("связанная заявка")
        else:
            request = summary.request
            
            # Проверка обязательных полей заявки
            if not request.dfa_number or request.dfa_number.strip() == '':
                missing_fields.append("номер заявки (dfa_number)")
            
            if not request.vehicle_info or request.vehicle_info.strip() == '':
                missing_fields.append("информация о предмете лизинга (vehicle_info)")
            
            if not request.client_name or request.client_name.strip() == '':
                missing_fields.append("название клиента (client_name)")
        
        if missing_fields:
            error_msg = f"Отсутствуют обязательные данные: {', '.join(missing_fields)}"
            logger.error(f"Валидация данных свода ID {summary.id} не пройдена: {error_msg}")
            raise InvalidSummaryDataError(error_msg)
        
        logger.debug(f"Валидация данных свода ID {summary.id} успешно пройдена")
    
    def _load_template(self) -> Workbook:
        """
        Загружает шаблон Excel из файла
        
        Returns:
            Workbook: Загруженная книга Excel
            
        Raises:
            ExcelExportServiceError: При ошибках загрузки шаблона
        """
        try:
            logger.debug(f"Загружаем шаблон из файла: {self.template_path}")
            workbook = load_workbook(self.template_path)
            logger.debug("Шаблон успешно загружен")
            return workbook
        except Exception as e:
            error_msg = f"Ошибка при загрузке шаблона Excel: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ExcelExportServiceError(error_msg) from e
    
    def _fill_template_data(self, workbook: Workbook, summary: InsuranceSummary) -> None:
        """
        Заполняет шаблон данными из свода
        
        Args:
            workbook: Книга Excel для заполнения
            summary: Объект свода предложений
            
        Raises:
            ExcelExportServiceError: При ошибках заполнения данных
        """
        try:
            logger.debug(f"Начинаем заполнение данных для свода ID: {summary.id}")
            
            # Получаем рабочий лист (используем первый лист или ищем по имени)
            worksheet = self._get_target_worksheet(workbook)
            
            request = summary.request
            
            # Заполнение данных согласно требованиям:
            # CDE1 - номер заявки
            self._set_merged_cell_value(worksheet, 'C1', request.dfa_number)
            logger.debug(f"Записан номер заявки в C1: {request.dfa_number}")
            
            # CDE2 - информация о предмете лизинга
            self._set_merged_cell_value(worksheet, 'C2', request.vehicle_info)
            logger.debug(f"Записана информация о предмете лизинга в C2: {request.vehicle_info[:50]}...")
            
            # CDE3 - название клиента
            self._set_merged_cell_value(worksheet, 'C3', request.client_name)
            logger.debug(f"Записано название клиента в C3: {request.client_name}")
            
            logger.info(f"Данные успешно заполнены для свода ID: {summary.id}")
            
        except Exception as e:
            error_msg = f"Ошибка при заполнении данных в Excel: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ExcelExportServiceError(error_msg) from e
    
    def _get_target_worksheet(self, workbook: Workbook):
        """
        Получает целевой рабочий лист для заполнения
        
        Args:
            workbook: Книга Excel
            
        Returns:
            Worksheet: Рабочий лист для заполнения
            
        Raises:
            ExcelExportServiceError: Если не удается найти подходящий лист
        """
        try:
            # Сначала пытаемся найти лист с именем "summary_template_sheet"
            if 'summary_template_sheet' in workbook.sheetnames:
                logger.debug("Найден лист 'summary_template_sheet'")
                return workbook['summary_template_sheet']
            
            # Если не найден, используем первый лист
            if workbook.worksheets:
                worksheet = workbook.worksheets[0]
                logger.debug(f"Используем первый лист: {worksheet.title}")
                return worksheet
            
            # Если нет листов вообще
            raise ExcelExportServiceError("В шаблоне Excel не найдено ни одного рабочего листа")
            
        except Exception as e:
            error_msg = f"Ошибка при получении рабочего листа: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ExcelExportServiceError(error_msg) from e
    
    def _set_merged_cell_value(self, worksheet, cell_address: str, value: str) -> None:
        """
        Устанавливает значение в ячейку (может быть объединенной)
        
        Args:
            worksheet: Рабочий лист
            cell_address: Адрес ячейки (например, 'C1')
            value: Значение для записи
        """
        try:
            cell = worksheet[cell_address]
            cell.value = value
            logger.debug(f"Установлено значение в ячейку {cell_address}: {value}")
        except Exception as e:
            error_msg = f"Ошибка при записи в ячейку {cell_address}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ExcelExportServiceError(error_msg) from e


class ExcelResponseProcessor:
    """Сервис для обработки Excel файлов с ответами страховых компаний"""
    
    # Конфигурация для поддерживаемых строк
    MIN_YEAR_ROW = 6  # Минимальная строка для данных лет
    MAX_YEAR_ROW = 10  # Максимальная строка для данных лет
    
    # Маппинг колонок для данных лет
    YEAR_COLUMNS = {
        'year': 'A',
        'insurance_sum': 'B',
        'premium': 'D',
        'franchise': 'E',
        'installment': 'F',
        'premium_2': 'H',
        'franchise_2': 'I',
        'installment_2': 'J'
    }
    
    # Динамическая конфигурация маппинга ячеек
    CELL_MAPPING = {
        'company_name': 'B2',
        'year_rows': {
            'start_row': MIN_YEAR_ROW,
            'end_row': MAX_YEAR_ROW,
            'columns': YEAR_COLUMNS
        }
    }
    
    # Допустимые значения рассрочки
    VALID_INSTALLMENT_VALUES = [1, 2, 3, 4, 6, 12]
    
    def __init__(self):
        """Инициализация процессора"""
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        # Импортируем здесь, чтобы избежать циклических импортов
        from .company_matcher import create_company_matcher
        self.company_matcher = create_company_matcher()
    
    def _generate_year_mappings(self) -> Dict[str, Dict[str, str]]:
        """
        Генерирует маппинги ячеек для всех поддерживаемых лет (строки 6-10)
        
        Returns:
            Dict с маппингами для каждого года в формате:
            {
                'year_1': {'year': 'A6', 'insurance_sum': 'B6', ...},
                'year_2': {'year': 'A7', 'insurance_sum': 'B7', ...},
                ...
            }
        """
        mappings = {}
        year_config = self.CELL_MAPPING['year_rows']
        
        for row_num in range(year_config['start_row'], year_config['end_row'] + 1):
            year_key = f"year_{row_num - year_config['start_row'] + 1}"
            mappings[year_key] = {}
            
            for field_name, column_letter in year_config['columns'].items():
                cell_address = f"{column_letter}{row_num}"
                mappings[year_key][field_name] = cell_address
        
        self.logger.debug(f"Сгенерированы маппинги для {len(mappings)} лет: {list(mappings.keys())}")
        return mappings
    
    def _detect_available_years(self, worksheet) -> List[int]:
        """
        Обнаруживает, в каких строках присутствуют данные лет
        
        Args:
            worksheet: Рабочий лист Excel
            
        Returns:
            Список номеров строк с валидными данными года
        """
        available_rows = []
        skipped_rows = []
        year_config = self.CELL_MAPPING['year_rows']
        year_column = year_config['columns']['year']
        
        self.logger.info(f"Начинаем обнаружение данных лет в строках {year_config['start_row']}-{year_config['end_row']}")
        
        for row_num in range(year_config['start_row'], year_config['end_row'] + 1):
            year_cell = f"{year_column}{row_num}"
            year_value = self._get_cell_value(worksheet, year_cell)
            
            self.logger.debug(f"Строка {row_num}: проверяем ячейку {year_cell}, значение: '{year_value}'")
            
            # Проверяем, есть ли валидное значение года
            if year_value is not None and str(year_value).strip():
                try:
                    year_int = int(year_value)
                    if 1 <= year_int <= 10:  # Разумные ограничения для года страхования
                        available_rows.append(row_num)
                        self.logger.info(f"Строка {row_num}: найден валидный год страхования {year_int}")
                    else:
                        skipped_rows.append(row_num)
                        self.logger.warning(f"Строка {row_num}: год {year_int} вне допустимого диапазона (1-10), строка пропущена")
                except (ValueError, TypeError):
                    skipped_rows.append(row_num)
                    self.logger.warning(f"Строка {row_num}: некорректное значение года '{year_value}', строка пропущена")
                    continue
            else:
                skipped_rows.append(row_num)
                self.logger.debug(f"Строка {row_num}: пустое значение года, строка пропущена")
        
        self.logger.info(f"Обнаружение завершено: найдено {len(available_rows)} строк с данными, пропущено {len(skipped_rows)} строк")
        self.logger.info(f"Строки с данными: {available_rows}")
        if skipped_rows:
            self.logger.info(f"Пропущенные строки: {skipped_rows}")
        
        return available_rows
    
    def _extract_all_years_data(self, worksheet) -> Dict[str, Any]:
        """
        Извлекает данные для всех обнаруженных лет с информацией об обработке
        
        Args:
            worksheet: Рабочий лист Excel
            
        Returns:
            Dict с данными по годам и информацией об обработке:
            {
                'years': List[Dict[str, Any]],  # Данные по годам
                'processing_info': {
                    'total_rows_checked': int,
                    'rows_with_data': List[int],
                    'rows_skipped': List[int],
                    'years_processed': List[int]
                }
            }
        """
        self.logger.info("Начинаем извлечение данных по всем годам страхования")
        
        all_years_data = []
        available_rows = self._detect_available_years(worksheet)
        year_mappings = self._generate_year_mappings()
        year_config = self.CELL_MAPPING['year_rows']
        
        # Информация об обработке
        total_rows_checked = year_config['end_row'] - year_config['start_row'] + 1
        all_possible_rows = list(range(year_config['start_row'], year_config['end_row'] + 1))
        rows_skipped = [row for row in all_possible_rows if row not in available_rows]
        years_processed = []
        processing_errors = []
        
        self.logger.info(f"Будет обработано {len(available_rows)} строк с данными: {available_rows}")
        
        for row_num in available_rows:
            try:
                self.logger.debug(f"Обрабатываем строку {row_num}")
                
                # Создаем маппинг для конкретной строки
                row_mapping = {}
                for field_name, column_letter in year_config['columns'].items():
                    cell_address = f"{column_letter}{row_num}"
                    row_mapping[field_name] = cell_address
                
                self.logger.debug(f"Строка {row_num}: маппинг ячеек создан - {row_mapping}")
                
                # Извлекаем данные для этой строки
                year_data = self._extract_year_data(worksheet, row_mapping, row_num)
                if year_data:
                    all_years_data.append(year_data)
                    years_processed.append(year_data['year'])
                    self.logger.info(f"Строка {row_num}: успешно извлечены данные для {year_data['year']} года (сумма: {year_data['insurance_sum']}, премия: {year_data['premium']})")
                else:
                    self.logger.warning(f"Строка {row_num}: данные не извлечены (пустая строка)")
                    
            except RowProcessingError as e:
                # Логируем ошибку обработки строки и добавляем строку в пропущенные
                error_info = f"Строка {row_num}: {str(e)}"
                processing_errors.append(error_info)
                self.logger.error(f"Ошибка обработки - {error_info}")
                
                if row_num in available_rows:
                    available_rows.remove(row_num)
                if row_num not in rows_skipped:
                    rows_skipped.append(row_num)
                continue
        
        processing_info = {
            'total_rows_checked': total_rows_checked,
            'rows_with_data': [row for row in available_rows if any(year['year'] for year in all_years_data)],
            'rows_skipped': rows_skipped,
            'years_processed': years_processed,
            'processing_errors': processing_errors
        }
        
        # Итоговое логирование
        self.logger.info(f"Извлечение данных завершено:")
        self.logger.info(f"  - Всего проверено строк: {total_rows_checked}")
        self.logger.info(f"  - Успешно обработано лет: {len(all_years_data)}")
        self.logger.info(f"  - Годы страхования: {sorted(years_processed) if years_processed else 'нет'}")
        self.logger.info(f"  - Пропущено строк: {len(rows_skipped)} {rows_skipped if rows_skipped else ''}")
        
        if processing_errors:
            self.logger.warning(f"  - Ошибки обработки ({len(processing_errors)}): {processing_errors}")
        
        return {
            'years': all_years_data,
            'processing_info': processing_info
        }
    
    def process_excel_file(self, file, summary: InsuranceSummary) -> Dict[str, Any]:
        """
        Обрабатывает Excel файл и создает предложения
        
        Args:
            file: Загруженный файл Excel
            summary: Свод предложений для связи
            
        Returns:
            Dict с результатами обработки
            
        Raises:
            ExcelProcessingError: При ошибках обработки файла
        """
        self.logger.info(f"=== НАЧАЛО ОБРАБОТКИ EXCEL ФАЙЛА ===")
        self.logger.info(f"Свод ID: {summary.id}, Файл: {file.name}")
        
        try:
            # Загружаем Excel файл
            self.logger.info("Этап 1: Загрузка Excel файла")
            workbook = self._load_excel_file(file)
            worksheet = self._get_worksheet(workbook)
            
            # Извлекаем данные компании
            self.logger.info("Этап 2: Извлечение данных компании")
            company_data = self.extract_company_data(worksheet)
            
            # Логируем результаты извлечения
            processing_info = company_data.get('processing_info', {})
            self.logger.info(f"Результаты извлечения данных:")
            self.logger.info(f"  - Компания: {company_data['company_name']}")
            self.logger.info(f"  - Найдено лет: {len(company_data['years'])}")
            self.logger.info(f"  - Обработано строк: {processing_info.get('rows_with_data', [])}")
            self.logger.info(f"  - Пропущено строк: {processing_info.get('rows_skipped', [])}")
            
            # Валидируем извлеченные данные
            self.logger.info("Этап 3: Валидация извлеченных данных")
            self.validate_extracted_data(company_data)
            
            # Создаем предложения
            self.logger.info("Этап 4: Создание предложений в базе данных")
            created_offers = self.create_offers(company_data, summary)
            
            result = {
                'success': True,
                'company_name': company_data['company_name'],
                'offers_created': len(created_offers),
                'years': [offer.insurance_year for offer in created_offers],
                'skipped_rows': processing_info.get('rows_skipped', []),
                'processed_rows': processing_info.get('rows_with_data', []),
                'company_matching_info': company_data.get('company_matching_info', {}),
                'processing_errors': processing_info.get('processing_errors', [])
            }
            
            self.logger.info(f"=== ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО ===")
            self.logger.info(f"Создано предложений: {len(created_offers)} для лет: {sorted([offer.insurance_year for offer in created_offers])}")
            
            return result
            
        except (ExcelProcessingError, DuplicateOfferError) as e:
            self.logger.error(f"=== ОБРАБОТКА ЗАВЕРШЕНА С ОШИБКОЙ ===")
            self.logger.error(f"Тип ошибки: {type(e).__name__}, Сообщение: {str(e)}")
            # Переброс известных исключений
            raise
        except Exception as e:
            error_msg = f"Неожиданная ошибка при обработке Excel файла: {str(e)}"
            self.logger.error(f"=== ОБРАБОТКА ЗАВЕРШЕНА С КРИТИЧЕСКОЙ ОШИБКОЙ ===")
            self.logger.error(error_msg, exc_info=True)
            raise ExcelProcessingError(error_msg) from e
    
    def _load_excel_file(self, file):
        """
        Загружает Excel файл из загруженного файла
        
        Args:
            file: Загруженный файл
            
        Returns:
            Workbook: Загруженная книга Excel
            
        Raises:
            InvalidFileFormatError: При ошибках загрузки файла
        """
        try:
            self.logger.debug("Загружаем Excel файл")
            
            # Проверяем расширение файла
            if not file.name.lower().endswith('.xlsx'):
                raise InvalidFileFormatError("Файл должен иметь расширение .xlsx")
            
            # Загружаем файл
            workbook = load_workbook(file, data_only=True)
            self.logger.debug("Excel файл успешно загружен")
            return workbook
            
        except InvalidFileFormatError:
            raise
        except Exception as e:
            error_msg = f"Ошибка при загрузке Excel файла: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise InvalidFileFormatError(error_msg) from e
    
    def _get_worksheet(self, workbook):
        """
        Получает рабочий лист для обработки
        
        Args:
            workbook: Книга Excel
            
        Returns:
            Worksheet: Рабочий лист
            
        Raises:
            InvalidFileFormatError: Если не удается найти подходящий лист
        """
        try:
            if not workbook.worksheets:
                raise InvalidFileFormatError("В Excel файле не найдено ни одного рабочего листа")
            
            # Используем первый лист
            worksheet = workbook.worksheets[0]
            self.logger.debug(f"Используем рабочий лист: {worksheet.title}")
            return worksheet
            
        except Exception as e:
            error_msg = f"Ошибка при получении рабочего листа: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise InvalidFileFormatError(error_msg) from e
    
    def extract_company_data(self, worksheet) -> Dict[str, Any]:
        """
        Извлекает данные компании из Excel файла с сопоставлением названия компании
        
        Args:
            worksheet: Рабочий лист Excel
            
        Returns:
            Dict с извлеченными данными
            
        Raises:
            MissingDataError: При отсутствии обязательных данных
        """
        self.logger.info("Начинаем извлечение данных компании из Excel файла")
        
        try:
            data = {}
            
            # Извлекаем название компании
            self.logger.debug(f"Извлекаем название компании из ячейки {self.CELL_MAPPING['company_name']}")
            raw_company_name = self._get_cell_value(worksheet, self.CELL_MAPPING['company_name'])
            if not raw_company_name:
                self.logger.error(f"Название компании не найдено в ячейке {self.CELL_MAPPING['company_name']}")
                raise MissingDataError([self.CELL_MAPPING['company_name']])
            
            # Сопоставляем название компании с закрытым списком
            raw_name_str = str(raw_company_name).strip()
            self.logger.info(f"Исходное название компании: '{raw_name_str}'")
            
            standardized_name = self.company_matcher.match_company_name(raw_name_str)
            data['company_name'] = standardized_name
            
            # Сохраняем информацию о сопоставлении для пользователя
            matching_info = {
                'original_name': raw_name_str,
                'standardized_name': standardized_name,
                'was_matched': standardized_name != raw_name_str,
                'assigned_other': standardized_name == 'другое' and raw_name_str.lower() != 'другое'
            }
            data['company_matching_info'] = matching_info
            
            # Логируем процесс сопоставления
            if standardized_name == 'другое' and raw_name_str.lower() != 'другое':
                self.logger.warning(f"Название компании '{raw_name_str}' не найдено в закрытом списке, присвоено значение 'другое'")
            elif standardized_name != raw_name_str:
                self.logger.info(f"Название компании сопоставлено: '{raw_name_str}' -> '{standardized_name}'")
            else:
                self.logger.info(f"Название компании '{raw_name_str}' точно совпадает с элементом закрытого списка")
            
            # Извлекаем данные по годам с использованием динамического обнаружения
            self.logger.info("Начинаем извлечение данных по годам страхования")
            years_result = self._extract_all_years_data(worksheet)
            data['years'] = years_result['years']
            data['processing_info'] = years_result['processing_info']
            
            # Проверяем, что есть хотя бы один год с данными
            if not data['years']:
                self.logger.error("Не найдено ни одного года с валидными данными страхования")
                raise MissingDataError(['данные по годам страхования'])
            
            self.logger.info(f"Извлечение данных компании завершено успешно:")
            self.logger.info(f"  - Компания: '{data['company_name']}'")
            self.logger.info(f"  - Количество лет: {len(data['years'])}")
            self.logger.info(f"  - Годы: {[year['year'] for year in data['years']]}")
            
            return data
            
        except (MissingDataError, InvalidDataError):
            raise
        except Exception as e:
            error_msg = f"Ошибка при извлечении данных компании: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise ExcelProcessingError(error_msg) from e
    
    def _extract_year_data(self, worksheet, year_mapping: Dict[str, str], row_number: int) -> Optional[Dict[str, Any]]:
        """
        Извлекает данные для конкретного года
        
        Args:
            worksheet: Рабочий лист Excel
            year_mapping: Маппинг ячеек для года
            row_number: Номер строки Excel (для ошибок и логирования)
            
        Returns:
            Dict с данными года или None, если данных нет
            
        Raises:
            RowProcessingError: При ошибках валидации данных в строке
        """
        try:
            # Проверяем, есть ли год в ячейке
            year_value = self._get_cell_value(worksheet, year_mapping['year'])
            if not year_value:
                self.logger.debug(f"Строка {row_number}: год не указан, пропускаем")
                return None
            
            # Извлекаем основные данные года с обработкой ошибок для конкретной строки
            year_data = {
                'year': self._parse_year_with_row(year_value, year_mapping['year'], row_number),
                'insurance_sum': self._parse_decimal_with_row(
                    self._get_cell_value(worksheet, year_mapping['insurance_sum']),
                    year_mapping['insurance_sum'],
                    'страховая сумма',
                    row_number
                ),
                'premium': self._parse_decimal_with_row(
                    self._get_cell_value(worksheet, year_mapping['premium']),
                    year_mapping['premium'],
                    'премия',
                    row_number
                ),
                'franchise': self._parse_decimal_with_row(
                    self._get_cell_value(worksheet, year_mapping['franchise']),
                    year_mapping['franchise'],
                    'франшиза',
                    row_number,
                    default_value=Decimal('0')
                ),
                'installment': self._parse_installment_with_row(
                    self._get_cell_value(worksheet, year_mapping['installment']),
                    year_mapping['installment'],
                    row_number
                )
            }
            
            # Извлекаем дополнительные поля (H, I, J), если они присутствуют в маппинге
            if 'premium_2' in year_mapping:
                year_data['premium_2'] = self._parse_decimal_with_row(
                    self._get_cell_value(worksheet, year_mapping['premium_2']),
                    year_mapping['premium_2'],
                    'премия-2',
                    row_number,
                    required=False,
                    default_value=None
                )
            
            if 'franchise_2' in year_mapping:
                year_data['franchise_2'] = self._parse_decimal_with_row(
                    self._get_cell_value(worksheet, year_mapping['franchise_2']),
                    year_mapping['franchise_2'],
                    'франшиза-2',
                    row_number,
                    required=False,
                    default_value=None
                )
            
            if 'installment_2' in year_mapping:
                year_data['installment_2'] = self._parse_installment_with_row(
                    self._get_cell_value(worksheet, year_mapping['installment_2']),
                    year_mapping['installment_2'],
                    row_number,
                    required=False
                )
            
            self.logger.debug(f"Строка {row_number}: извлечены данные для {year_data['year']} года")
            return year_data
            
        except RowProcessingError:
            # Переброс ошибок строки как есть
            raise
        except Exception as e:
            # Неожиданные ошибки оборачиваем в RowProcessingError
            error_msg = f"Неожиданная ошибка при обработке данных: {str(e)}"
            self.logger.error(f"Строка {row_number}: {error_msg}")
            raise RowProcessingError(row_number, 'общая обработка', error_msg)
    
    def _get_cell_value(self, worksheet, cell_address: str):
        """
        Получает значение ячейки
        
        Args:
            worksheet: Рабочий лист
            cell_address: Адрес ячейки (например, 'B2')
            
        Returns:
            Значение ячейки или None
        """
        try:
            cell = worksheet[cell_address]
            return cell.value
        except Exception as e:
            self.logger.warning(f"Ошибка при чтении ячейки {cell_address}: {str(e)}")
            return None
    
    def _parse_year(self, value, cell_address: str) -> int:
        """
        Парсит значение года (устаревший метод для обратной совместимости)
        
        Args:
            value: Значение из ячейки
            cell_address: Адрес ячейки для ошибок
            
        Returns:
            Номер года
            
        Raises:
            InvalidDataError: При некорректном значении года
        """
        try:
            if value is None:
                raise InvalidDataError('год', value, 'положительное число')
            
            year = int(value)
            if year < 1 or year > 10:  # Разумные ограничения для года страхования
                raise InvalidDataError('год', value, 'число от 1 до 10')
            
            return year
            
        except (ValueError, TypeError):
            raise InvalidDataError('год', value, 'положительное число')
    
    def _parse_year_with_row(self, value, cell_address: str, row_number: int) -> int:
        """
        Парсит значение года с указанием номера строки
        
        Args:
            value: Значение из ячейки
            cell_address: Адрес ячейки для ошибок
            row_number: Номер строки Excel
            
        Returns:
            Номер года
            
        Raises:
            RowProcessingError: При некорректном значении года
        """
        try:
            if value is None:
                raise RowProcessingError(row_number, 'год', 'значение не указано', cell_address)
            
            year = int(value)
            if year < 1 or year > 10:  # Разумные ограничения для года страхования
                raise RowProcessingError(row_number, 'год', f'значение {value} вне допустимого диапазона (1-10)', cell_address)
            
            return year
            
        except (ValueError, TypeError):
            raise RowProcessingError(row_number, 'год', f'некорректное значение "{value}", ожидается положительное число', cell_address)
    
    def _parse_decimal(self, value, cell_address: str, field_name: str, default_value: Optional[Decimal] = None) -> Decimal:
        """
        Парсит десятичное значение (устаревший метод для обратной совместимости)
        
        Args:
            value: Значение из ячейки
            cell_address: Адрес ячейки для ошибок
            field_name: Название поля для ошибок
            default_value: Значение по умолчанию
            
        Returns:
            Десятичное значение
            
        Raises:
            InvalidDataError: При некорректном значении
        """
        try:
            if value is None or value == '':
                if default_value is not None:
                    return default_value
                raise InvalidDataError(field_name, value, 'числовое значение')
            
            # Преобразуем в Decimal
            decimal_value = Decimal(str(value))
            
            # Проверяем, что значение положительное (кроме франшизы, которая может быть 0)
            if decimal_value < 0:
                raise InvalidDataError(field_name, value, 'положительное число')
            
            return decimal_value
            
        except (InvalidOperation, ValueError, TypeError):
            raise InvalidDataError(field_name, value, 'числовое значение')
    
    def _parse_decimal_with_row(self, value, cell_address: str, field_name: str, row_number: int, default_value: Optional[Decimal] = None, required: bool = True) -> Optional[Decimal]:
        """
        Парсит десятичное значение с указанием номера строки
        
        Args:
            value: Значение из ячейки
            cell_address: Адрес ячейки для ошибок
            field_name: Название поля для ошибок
            row_number: Номер строки Excel
            default_value: Значение по умолчанию
            required: Обязательно ли поле (если False, пустые значения возвращают None)
            
        Returns:
            Десятичное значение или None для необязательных полей
            
        Raises:
            RowProcessingError: При некорректном значении
        """
        try:
            if value is None or value == '':
                if default_value is not None:
                    return default_value
                if not required:
                    return None
                raise RowProcessingError(row_number, field_name, 'значение не указано', cell_address)
            
            # Преобразуем в Decimal
            decimal_value = Decimal(str(value))
            
            # Проверяем, что значение положительное (кроме франшизы, которая может быть 0)
            if decimal_value < 0:
                raise RowProcessingError(row_number, field_name, f'отрицательное значение {value}, ожидается положительное число', cell_address)
            
            return decimal_value
            
        except (InvalidOperation, ValueError, TypeError):
            raise RowProcessingError(row_number, field_name, f'некорректное значение "{value}", ожидается числовое значение', cell_address)
    
    def _parse_installment(self, value, cell_address: str) -> int:
        """
        Парсит значение рассрочки (устаревший метод для обратной совместимости)
        
        Args:
            value: Значение из ячейки
            cell_address: Адрес ячейки для ошибок
            
        Returns:
            Количество платежей в год
            
        Raises:
            InvalidDataError: При некорректном значении рассрочки
        """
        try:
            if value is None or value == '':
                return 1  # По умолчанию - единовременная оплата
            
            installment = int(value)
            
            if installment not in self.VALID_INSTALLMENT_VALUES:
                raise InvalidDataError(
                    'рассрочка', 
                    value, 
                    f'одно из значений: {", ".join(map(str, self.VALID_INSTALLMENT_VALUES))}'
                )
            
            return installment
            
        except (ValueError, TypeError):
            raise InvalidDataError(
                'рассрочка', 
                value, 
                f'одно из значений: {", ".join(map(str, self.VALID_INSTALLMENT_VALUES))}'
            )
    
    def _parse_installment_with_row(self, value, cell_address: str, row_number: int, required: bool = True) -> Optional[int]:
        """
        Парсит значение рассрочки с указанием номера строки
        
        Args:
            value: Значение из ячейки
            cell_address: Адрес ячейки для ошибок
            row_number: Номер строки Excel
            required: Обязательно ли поле (если False, пустые значения возвращают None)
            
        Returns:
            Количество платежей в год или None для необязательных полей
            
        Raises:
            RowProcessingError: При некорректном значении рассрочки
        """
        try:
            if value is None or value == '':
                if not required:
                    return None
                return 1  # По умолчанию - единовременная оплата
            
            installment = int(value)
            
            if installment not in self.VALID_INSTALLMENT_VALUES:
                valid_values = ", ".join(map(str, self.VALID_INSTALLMENT_VALUES))
                raise RowProcessingError(
                    row_number, 
                    'рассрочка', 
                    f'недопустимое значение {value}, ожидается одно из: {valid_values}',
                    cell_address
                )
            
            return installment
            
        except (ValueError, TypeError):
            valid_values = ", ".join(map(str, self.VALID_INSTALLMENT_VALUES))
            raise RowProcessingError(
                row_number, 
                'рассрочка', 
                f'некорректное значение "{value}", ожидается одно из: {valid_values}',
                cell_address
            )
    
    def validate_extracted_data(self, data: Dict[str, Any]) -> None:
        """
        Валидирует извлеченные данные
        
        Args:
            data: Извлеченные данные
            
        Raises:
            InvalidDataError: При некорректных данных
        """
        self.logger.debug("Валидируем извлеченные данные")
        
        # Проверяем название компании
        if not data.get('company_name') or not data['company_name'].strip():
            raise InvalidDataError('название компании', data.get('company_name'), 'непустая строка')
        
        # Проверяем данные по годам
        if not data.get('years') or len(data['years']) == 0:
            raise InvalidDataError('данные по годам', 'отсутствуют', 'хотя бы один год с данными')
        
        # Валидируем каждый год
        for year_data in data['years']:
            self._validate_year_data(year_data)
        
        self.logger.debug("Валидация данных успешно завершена")
    
    def _validate_year_data(self, year_data: Dict[str, Any]) -> None:
        """
        Валидирует данные конкретного года
        
        Args:
            year_data: Данные года
            
        Raises:
            InvalidDataError: При некорректных данных
        """
        # Проверяем обязательные поля
        required_fields = ['year', 'insurance_sum', 'premium']
        for field in required_fields:
            if field not in year_data or year_data[field] is None:
                raise InvalidDataError(f'{field} (год {year_data.get("year", "?")})', None, 'обязательное поле')
        
        # Проверяем, что премия не больше страховой суммы (разумная проверка)
        if year_data['premium'] > year_data['insurance_sum']:
            raise InvalidDataError(
                f'премия (год {year_data["year"]})', 
                year_data['premium'], 
                f'не больше страховой суммы ({year_data["insurance_sum"]})'
            )
    
    def create_offers(self, data: Dict[str, Any], summary: InsuranceSummary) -> List[InsuranceOffer]:
        """
        Создает записи предложений в базе данных
        
        Args:
            data: Извлеченные и валидированные данные
            summary: Свод предложений
            
        Returns:
            Список созданных предложений
            
        Raises:
            DuplicateOfferError: При дублировании предложений
            ExcelProcessingError: При ошибках создания записей
        """
        self.logger.debug(f"Создаем предложения для компании '{data['company_name']}'")
        
        created_offers = []
        
        try:
            with transaction.atomic():
                for year_data in data['years']:
                    # Проверяем на дублирование
                    existing_offer = InsuranceOffer.objects.filter(
                        summary=summary,
                        company_name=data['company_name'],
                        insurance_year=year_data['year']
                    ).first()
                    
                    if existing_offer:
                        raise DuplicateOfferError(data['company_name'], year_data['year'])
                    
                    # Создаем предложение
                    offer = self._create_single_offer(data, year_data, summary)
                    created_offers.append(offer)
                    
                    self.logger.debug(f"Создано предложение для {year_data['year']} года")
                
                # Обновляем счетчик предложений в своде
                summary.update_total_offers_count()
                
            self.logger.info(f"Успешно создано {len(created_offers)} предложений для компании '{data['company_name']}'")
            return created_offers
            
        except DuplicateOfferError:
            raise
        except Exception as e:
            error_msg = f"Ошибка при создании предложений: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise ExcelProcessingError(error_msg) from e
    
    def _create_single_offer(self, company_data: Dict[str, Any], year_data: Dict[str, Any], summary: InsuranceSummary) -> InsuranceOffer:
        """
        Создает одно предложение
        
        Args:
            company_data: Данные компании
            year_data: Данные года
            summary: Свод предложений
            
        Returns:
            Созданное предложение
        """
        # Определяем параметры рассрочки для основного варианта
        installment_available = year_data['installment'] > 1
        payments_per_year = year_data['installment']
        
        # Определяем параметры рассрочки для дополнительного варианта (если есть)
        installment_2_available = False
        payments_per_year_2 = 1
        if year_data.get('installment_2') is not None:
            installment_2_available = year_data['installment_2'] > 1
            payments_per_year_2 = year_data['installment_2']
        
        # Подготавливаем данные для создания предложения
        offer_data = {
            'summary': summary,
            'company_name': company_data['company_name'],
            'insurance_year': year_data['year'],
            'insurance_sum': year_data['insurance_sum'],
            'franchise_1': year_data['franchise'],
            'premium_with_franchise_1': year_data['premium'],
            'installment_variant_1': installment_available,
            'payments_per_year_variant_1': payments_per_year,
            # Для обратной совместимости
            'installment_available': installment_available,
            'payments_per_year': payments_per_year,
            'is_valid': True
        }
        
        # Добавляем дополнительные поля, если они присутствуют
        if year_data.get('premium_2') is not None:
            offer_data['premium_with_franchise_2'] = year_data['premium_2']
        
        if year_data.get('franchise_2') is not None:
            offer_data['franchise_2'] = year_data['franchise_2']
        
        if year_data.get('installment_2') is not None:
            offer_data['installment_variant_2'] = installment_2_available
            offer_data['payments_per_year_variant_2'] = payments_per_year_2
        
        offer = InsuranceOffer.objects.create(**offer_data)
        
        return offer


def get_excel_export_service() -> ExcelExportService:
    """
    Фабричная функция для создания экземпляра ExcelExportService
    с настройками по умолчанию
    
    Returns:
        ExcelExportService: Настроенный экземпляр сервиса
        
    Raises:
        ExcelExportServiceError: Если не удается создать сервис
    """
    try:
        # Получаем путь к шаблону из настроек или используем значение по умолчанию
        template_path = getattr(
            settings, 
            'SUMMARY_TEMPLATE_PATH', 
            settings.BASE_DIR / 'templates' / 'summary_template.xlsx'
        )
        
        return ExcelExportService(str(template_path))
        
    except Exception as e:
        error_msg = f"Ошибка при создании ExcelExportService: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ExcelExportServiceError(error_msg) from e


def get_excel_response_processor() -> ExcelResponseProcessor:
    """
    Фабричная функция для создания экземпляра ExcelResponseProcessor
    
    Returns:
        ExcelResponseProcessor: Экземпляр процессора
    """
    return ExcelResponseProcessor()
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
    
    # Маппинг ячеек согласно техническому заданию
    CELL_MAPPING = {
        'company_name': 'B2',
        'year_1': {
            'year': 'A6',
            'insurance_sum': 'B6', 
            'premium': 'D6',
            'franchise': 'E6',
            'installment': 'F6'
        },
        'year_2': {
            'year': 'A7',
            'insurance_sum': 'B7',
            'premium': 'D7', 
            'franchise': 'E7',
            'installment': 'F7'
        }
    }
    
    # Допустимые значения рассрочки
    VALID_INSTALLMENT_VALUES = [1, 2, 3, 4, 12]
    
    def __init__(self):
        """Инициализация процессора"""
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        # Импортируем здесь, чтобы избежать циклических импортов
        from .company_matcher import create_company_matcher
        self.company_matcher = create_company_matcher()
    
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
        self.logger.info(f"Начинаем обработку Excel файла для свода ID: {summary.id}")
        
        try:
            # Загружаем Excel файл
            workbook = self._load_excel_file(file)
            worksheet = self._get_worksheet(workbook)
            
            # Извлекаем данные компании
            company_data = self.extract_company_data(worksheet)
            
            # Валидируем извлеченные данные
            self.validate_extracted_data(company_data)
            
            # Создаем предложения
            created_offers = self.create_offers(company_data, summary)
            
            result = {
                'success': True,
                'company_name': company_data['company_name'],
                'offers_created': len(created_offers),
                'years': [offer.insurance_year for offer in created_offers],
                'company_matching_info': company_data.get('company_matching_info', {})
            }
            
            self.logger.info(f"Excel файл успешно обработан для свода ID: {summary.id}. Создано предложений: {len(created_offers)}")
            return result
            
        except (ExcelProcessingError, DuplicateOfferError):
            # Переброс известных исключений
            raise
        except Exception as e:
            error_msg = f"Неожиданная ошибка при обработке Excel файла: {str(e)}"
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
        self.logger.debug("Извлекаем данные компании из Excel файла")
        
        try:
            data = {}
            
            # Извлекаем название компании
            raw_company_name = self._get_cell_value(worksheet, self.CELL_MAPPING['company_name'])
            if not raw_company_name:
                raise MissingDataError([self.CELL_MAPPING['company_name']])
            
            # Сопоставляем название компании с закрытым списком
            raw_name_str = str(raw_company_name).strip()
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
                self.logger.debug(f"Название компании '{raw_name_str}' точно совпадает с элементом закрытого списка")
            
            # Извлекаем данные по годам
            data['years'] = []
            
            # Обрабатываем первый год
            year_1_data = self._extract_year_data(worksheet, self.CELL_MAPPING['year_1'], 1)
            if year_1_data:
                data['years'].append(year_1_data)
            
            # Обрабатываем второй год
            year_2_data = self._extract_year_data(worksheet, self.CELL_MAPPING['year_2'], 2)
            if year_2_data:
                data['years'].append(year_2_data)
            
            # Проверяем, что есть хотя бы один год с данными
            if not data['years']:
                raise MissingDataError(['данные по годам страхования'])
            
            self.logger.debug(f"Извлечены данные для компании '{data['company_name']}' на {len(data['years'])} лет")
            return data
            
        except (MissingDataError, InvalidDataError):
            raise
        except Exception as e:
            error_msg = f"Ошибка при извлечении данных компании: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise ExcelProcessingError(error_msg) from e
    
    def _extract_year_data(self, worksheet, year_mapping: Dict[str, str], year_number: int) -> Optional[Dict[str, Any]]:
        """
        Извлекает данные для конкретного года
        
        Args:
            worksheet: Рабочий лист Excel
            year_mapping: Маппинг ячеек для года
            year_number: Номер года (для логирования)
            
        Returns:
            Dict с данными года или None, если данных нет
        """
        try:
            # Проверяем, есть ли год в ячейке
            year_value = self._get_cell_value(worksheet, year_mapping['year'])
            if not year_value:
                self.logger.debug(f"Год {year_number} не указан, пропускаем")
                return None
            
            # Извлекаем все данные года
            year_data = {
                'year': self._parse_year(year_value, year_mapping['year']),
                'insurance_sum': self._parse_decimal(
                    self._get_cell_value(worksheet, year_mapping['insurance_sum']),
                    year_mapping['insurance_sum'],
                    'страховая сумма'
                ),
                'premium': self._parse_decimal(
                    self._get_cell_value(worksheet, year_mapping['premium']),
                    year_mapping['premium'],
                    'премия'
                ),
                'franchise': self._parse_decimal(
                    self._get_cell_value(worksheet, year_mapping['franchise']),
                    year_mapping['franchise'],
                    'франшиза',
                    default_value=Decimal('0')
                ),
                'installment': self._parse_installment(
                    self._get_cell_value(worksheet, year_mapping['installment']),
                    year_mapping['installment']
                )
            }
            
            self.logger.debug(f"Извлечены данные для {year_data['year']} года")
            return year_data
            
        except Exception as e:
            self.logger.warning(f"Ошибка при извлечении данных {year_number} года: {str(e)}")
            return None
    
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
        Парсит значение года
        
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
    
    def _parse_decimal(self, value, cell_address: str, field_name: str, default_value: Optional[Decimal] = None) -> Decimal:
        """
        Парсит десятичное значение
        
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
    
    def _parse_installment(self, value, cell_address: str) -> int:
        """
        Парсит значение рассрочки
        
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
        # Определяем параметры рассрочки
        installment_available = year_data['installment'] > 1
        payments_per_year = year_data['installment']
        
        offer = InsuranceOffer.objects.create(
            summary=summary,
            company_name=company_data['company_name'],
            insurance_year=year_data['year'],
            insurance_sum=year_data['insurance_sum'],
            franchise_1=year_data['franchise'],
            premium_with_franchise_1=year_data['premium'],
            installment_variant_1=installment_available,
            payments_per_year_variant_1=payments_per_year,
            # Для обратной совместимости
            installment_available=installment_available,
            payments_per_year=payments_per_year,
            is_valid=True
        )
        
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
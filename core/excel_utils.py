"""
Утилиты для работы с Excel файлами
"""
from typing import Dict, Any, Optional
import pandas as pd
from openpyxl import load_workbook
from datetime import timedelta
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


# Маппинг полных названий филиалов на сокращенные
BRANCH_MAPPING = {
    "Казанский филиал": "Казань",
    "Нижегородский  филиал": "Нижний Новгород",
    "Краснодарский филиал": "Краснодар",
    "Санкт-Петербург": "Санкт-Петербург",
    "Мурманский филиал": "Мурманск",
    "Псковский филиал": "Псков",
    "Челябинский филиал": "Челябинск",
    "Московский филиал № 2": "Москва",
    "Новгородский филиал": "Великий Новгород",
    "Архангельский филиал": "Архангельск",
    "Ставропольское обособленное подразделение": "Краснодар",
}


def map_branch_name(full_branch_name: str) -> str:
    """
    Преобразует полное название филиала в сокращенное.
    
    Args:
        full_branch_name: Полное название филиала
        
    Returns:
        Сокращенное название филиала или оригинальное название, если маппинг не найден
    """
    if not full_branch_name or not isinstance(full_branch_name, str):
        return full_branch_name or "Филиал не указан"
    
    # Убираем лишние пробелы и приводим к единому виду
    normalized_name = full_branch_name.strip()
    
    # Ищем точное совпадение в маппинге
    if normalized_name in BRANCH_MAPPING:
        logger.debug(f"Mapped branch '{normalized_name}' to '{BRANCH_MAPPING[normalized_name]}'")
        return BRANCH_MAPPING[normalized_name]
    
    # Ищем частичное совпадение (если название содержит ключевые слова)
    for full_name, short_name in BRANCH_MAPPING.items():
        if full_name.lower() in normalized_name.lower() or normalized_name.lower() in full_name.lower():
            logger.debug(f"Partially mapped branch '{normalized_name}' to '{short_name}' via '{full_name}'")
            return short_name
    
    # Если маппинг не найден, логируем это и возвращаем оригинальное название
    logger.info(f"No mapping found for branch '{normalized_name}', using original name")
    return normalized_name


class ExcelReader:
    """Класс для чтения данных из Excel файлов"""
    
    def __init__(self, file_path: str, application_type: str = 'legal_entity', application_format: str = 'casco_equipment'):
        self.file_path = file_path
        
        # Валидация и fallback для типа заявки
        valid_types = ['legal_entity', 'individual_entrepreneur']
        if application_type not in valid_types:
            logger.warning(f"Invalid application_type '{application_type}' provided to ExcelReader, falling back to 'legal_entity'")
            application_type = 'legal_entity'
        
        self.application_type = application_type
        
        # Валидация и fallback для формата заявки
        valid_formats = ['casco_equipment', 'property']
        if application_format not in valid_formats:
            logger.warning(f"Invalid application_format '{application_format}' provided to ExcelReader, falling back to 'casco_equipment'")
            application_format = 'casco_equipment'
        
        self.application_format = application_format
        
        # Логируем выбранный тип и формат заявки при начале обработки
        app_type_display = "заявка от ИП" if application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        format_display = "КАСКО/спецтехника" if application_format == 'casco_equipment' else "имущество"
        logger.info(f"Initializing ExcelReader with application_type: {application_type} ({app_type_display}), application_format: {application_format} ({format_display}) for file: {file_path}")
        
        # Инициализируем счетчик примененных смещений для диагностики
        self._row_adjustments_applied = 0
    
    def _get_format_context(self) -> str:
        """
        Возвращает строку с контекстом формата для логирования
        
        Returns:
            str: Строка формата "Format: имущество, Type: заявка от ИП"
        """
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        format_display = "КАСКО/спецтехника" if self.application_format == 'casco_equipment' else "имущество"
        return f"Format: {format_display}, Type: {app_type_display}"
    
    def _get_detailed_format_context(self) -> str:
        """
        Возвращает детальную строку с контекстом формата для логирования
        
        Returns:
            str: Строка формата "application_type: individual_entrepreneur, application_format: property"
        """
        return f"application_type: {self.application_type}, application_format: {self.application_format}"
    
    def _get_adjusted_row(self, row_number: int) -> int:
        """
        Возвращает скорректированный номер строки с учетом типа заявки.
        
        Для заявок от ИП: если строка > 8, то добавляется смещение +1
        Для заявок от юр.лиц: номер строки остается неизменным
        
        Args:
            row_number: Базовый номер строки
            
        Returns:
            Скорректированный номер строки
        """
        format_context = self._get_format_context()
        
        if self.application_type == 'individual_entrepreneur' and row_number > 8:
            adjusted_row = row_number + 1
            self._row_adjustments_applied += 1
            
            # Специальное логирование для параметров перевозки и СМР
            if row_number in [44, 48]:  # C44 (transportation) or C48 (construction work)
                parameter_type = "transportation" if row_number == 44 else "construction work"
                logger.info(f"IP row offset applied for {parameter_type} parameter detection: C{row_number} -> C{adjusted_row} (total adjustments: {self._row_adjustments_applied}) | {format_context}")
            else:
                logger.debug(f"Row adjustment applied: {row_number} -> {adjusted_row} (IP application, total adjustments: {self._row_adjustments_applied}) | {format_context}")
            
            return adjusted_row
        else:
            # Специальное логирование для параметров перевозки и СМР
            if row_number in [44, 48]:  # C44 (transportation) or C48 (construction work)
                parameter_type = "transportation" if row_number == 44 else "construction work"
                logger.info(f"No row offset for {parameter_type} parameter detection: C{row_number} (legal entity application) | {format_context}")
            else:
                logger.debug(f"No row adjustment: {row_number} (legal entity or row <= 8) | {format_context}")
            
            return row_number
    
    def _get_cell_with_adjustment_openpyxl(self, sheet, column: str, row: int) -> Optional[str]:
        """
        Получает значение ячейки с учетом смещения строк для openpyxl.
        
        Args:
            sheet: Лист Excel (openpyxl)
            column: Буква столбца (A, B, C, ...)
            row: Базовый номер строки
            
        Returns:
            Значение ячейки или None
        """
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        format_display = "КАСКО/спецтехника" if self.application_format == 'casco_equipment' else "имущество"
        
        try:
            adjusted_row = self._get_adjusted_row(row)
            cell_address = f"{column}{adjusted_row}"
            value = self._get_cell_value(sheet, cell_address)
            
            # Логируем для диагностики только если применено смещение
            if self.application_type == 'individual_entrepreneur' and row > 8:
                logger.debug(f"Cell {column}{row} -> {cell_address} (IP adjustment), value: {value} | Format: {format_display}, Type: {app_type_display}")
            
            return value
        except Exception as e:
            logger.error(f"Error reading cell {column}{row} for {app_type_display} with format {format_display} (application_type: {self.application_type}, application_format: {self.application_format}): {str(e)}")
            return None
    
    def _get_cell_with_adjustment_pandas(self, df, row: int, col: int) -> Optional[str]:
        """
        Получает значение ячейки с учетом смещения строк для pandas.
        
        Args:
            df: DataFrame
            row: Базовый номер строки (1-based)
            col: Номер столбца (0-based)
            
        Returns:
            Значение ячейки или None
        """
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        format_display = "КАСКО/спецтехника" if self.application_format == 'casco_equipment' else "имущество"
        
        try:
            adjusted_row = self._get_adjusted_row(row)
            # Преобразуем в 0-based индекс для pandas
            pandas_row_index = adjusted_row - 1
            value = self._safe_get_cell(df, pandas_row_index, col)
            
            # Логируем для диагностики только если применено смещение
            if self.application_type == 'individual_entrepreneur' and row > 8:
                logger.debug(f"Cell row {row} col {col} -> row {adjusted_row} col {col} (IP adjustment), value: {value} | Format: {format_display}, Type: {app_type_display}")
            
            return value
        except Exception as e:
            logger.error(f"Error reading cell row {row} col {col} for {app_type_display} with format {format_display} (application_type: {self.application_type}, application_format: {self.application_format}): {str(e)}")
            return None
        
    def read_insurance_request(self) -> Dict[str, Any]:
        """
        Читает данные страховой заявки из Excel файла с улучшенной обработкой ошибок
        Возвращает словарь с извлеченными данными
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            logger.info(f"Starting to read Excel file {self.file_path} | {format_context}")
            
            # Пробуем сначала с openpyxl для .xlsx файлов
            try:
                workbook = load_workbook(self.file_path, data_only=True)
                sheet = workbook.active
                logger.info(f"Successfully loaded workbook with openpyxl from file: {self.file_path} | {format_context}")
                data = self._extract_data_openpyxl(sheet)
                logger.info(f"Data extraction completed with openpyxl | {format_context}")
            except Exception as openpyxl_error:
                logger.warning(f"openpyxl failed from file {self.file_path}, trying pandas: {str(openpyxl_error)} | {format_context}")
                # Если не получилось, пробуем с pandas для .xls файлов
                try:
                    df = pd.read_excel(self.file_path, sheet_name=0, header=None)
                    logger.info(f"Successfully loaded workbook with pandas from file: {self.file_path} | {format_context}")
                    data = self._extract_data_pandas(df)
                    logger.info(f"Data extraction completed with pandas | {format_context}")
                except Exception as pandas_error:
                    logger.error(f"Both openpyxl and pandas failed from file {self.file_path}. openpyxl: {str(openpyxl_error)}, pandas: {str(pandas_error)} | {format_context}")
                    raise Exception(f"Не удалось прочитать файл ({detailed_context}). Проверьте формат файла и целостность данных.")
            
            # Логируем информацию о примененных смещениях строк
            if self.application_type == 'individual_entrepreneur':
                logger.info(f"Successfully read data from {self.file_path}. Applied {self._row_adjustments_applied} row adjustments | {format_context}")
            else:
                logger.info(f"Successfully read data from {self.file_path}. No row adjustments needed | {format_context}")
            
            return data
            
        except Exception as e:
            error_msg = f"Ошибка чтения Excel файла {self.file_path} ({detailed_context}): {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Дополнительное логирование для диагностики
            logger.error(f"ExcelReader error context - File: {self.file_path}, ({detailed_context}), Row adjustments applied: {getattr(self, '_row_adjustments_applied', 0)} | {format_context}")
            
            # Логируем информацию о параметрах при ошибке
            if self.application_format == 'property':
                logger.error(f"Parameter detection failed for property insurance ({detailed_context}) - transportation and construction work parameters will default to False | {format_context}")
            else:
                logger.error(f"Parameter detection not applicable for CASCO/equipment format ({detailed_context}) - transportation and construction work parameters set to False | {format_context}")
            
            # Возвращаем данные по умолчанию с расширенной информацией об ошибке
            default_data = self._get_default_data()
            default_data['error_info'] = {
                'application_type': self.application_type,
                'application_format': self.application_format,
                'format_context': format_context,
                'detailed_context': detailed_context,
                'error_message': str(e),
                'fallback_used': True,
                'row_adjustments_applied': getattr(self, '_row_adjustments_applied', 0),
                'file_path': self.file_path,
                'parameter_detection_failed': self.application_format == 'property',
                'transportation_parameter_default': False,
                'construction_work_parameter_default': False
            }
            return default_data
    
    def _extract_data_openpyxl(self, sheet) -> Dict[str, Any]:
        """Извлекает данные используя openpyxl (для .xlsx файлов)"""
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        logger.info(f"Starting openpyxl data extraction | {format_context}")
        
        # Определяем тип страхования на основе формата заявки
        if self.application_format == 'property':
            # Для формата имущества используем специальную логику
            logger.info(f"Using property insurance processing logic | {format_context}")
            insurance_type = self._determine_insurance_type_property_openpyxl(sheet)
            vehicle_info = self._find_leasing_object_info_property_openpyxl(sheet)
            has_autostart = False  # Всегда False для страхования имущества
            has_casco_ce = False  # Всегда False для страхования имущества (не извлекается)
            logger.debug(f"Property insurance processing: autostart set to False, casco_ce set to False | {format_context}")
        else:
            # Для формата КАСКО/спецтехника используем существующую логику
            logger.info(f"Using CASCO/equipment insurance processing logic | {format_context}")
            insurance_type = self._determine_insurance_type_openpyxl(sheet)
            vehicle_info = self._find_leasing_object_info_openpyxl(sheet)
            # Определяем автозапуск (если M24 = "нет", то автозапуска нет)
            autostart_value = self._get_cell_with_adjustment_openpyxl(sheet, 'M', 24)
            has_autostart = bool(autostart_value) and str(autostart_value).lower().strip() != 'нет'
            # Определяем КАСКО кат. C/E на основе строки 45 (только для КАСКО/спецтехника)
            has_casco_ce = self._determine_casco_ce_openpyxl(sheet)
            logger.debug(f"CASCO/equipment processing: autostart determined as {has_autostart} (M24 value: {autostart_value}), casco_ce determined as {has_casco_ce} | {format_context}")
        
        # Определяем период страхования по новой логике N17/N18 (одинаково для всех форматов)
        insurance_period = self._determine_insurance_period_openpyxl(sheet)
        
        # Определяем срок ответа (текущее время + 3 часа) (одинаково для всех форматов)
        response_deadline = timezone.now() + timedelta(hours=3)
        
        # Определяем тип франшизы на основе анализа ячеек D29/D30, E29/E30, F29/F30
        logger.info(f"Starting franchise type determination (openpyxl) ({detailed_context}) | {format_context}")
        franchise_type = self._determine_franchise_type(sheet, is_openpyxl=True)
        
        # Обновляем has_franchise для обратной совместимости
        has_franchise = franchise_type in ['with_franchise', 'both_variants']
        logger.info(f"Franchise processing completed (openpyxl) ({detailed_context}): franchise_type='{franchise_type}', has_franchise={has_franchise} (backward compatibility) | {format_context}")
        
        # Получаем детальную информацию о франшизе для сохранения в additional_data
        franchise_details = self._get_franchise_details_openpyxl(sheet)
        logger.debug(f"Franchise details extracted (openpyxl) ({detailed_context}): {franchise_details} | {format_context}")
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ) (одинаково для всех форматов)
        has_installment = not bool(self._get_cell_with_adjustment_openpyxl(sheet, 'F', 34))
        
        # Извлекаем название клиента из D7 (одинаково для всех форматов)
        client_name = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 7) or 'Клиент не указан'
        
        # Извлекаем номер ДФА (одинаково для всех форматов)
        dfa_number = self._find_dfa_number_openpyxl(sheet)
        
        # Извлекаем филиал (одинаково для всех форматов)
        branch = self._find_branch_openpyxl(sheet)
        
        # Определяем параметры перевозки и строительно-монтажных работ
        if self.application_format == 'property':
            # Для формата имущества используем автоматическое определение параметров
            logger.info(f"Starting transportation and construction work parameter detection for property insurance ({detailed_context}) | {format_context}")
            
            has_transportation = self._detect_transportation_parameter_openpyxl(sheet)
            has_construction_work = self._detect_construction_work_parameter_openpyxl(sheet)
            
            # Логируем итоговые значения параметров после обнаружения
            logger.info(f"Property insurance parameter detection completed ({detailed_context}): has_transportation={has_transportation}, has_construction_work={has_construction_work} | {format_context}")
            
            # Дополнительное логирование для верификации
            if has_transportation or has_construction_work:
                active_params = []
                if has_transportation:
                    active_params.append("transportation")
                if has_construction_work:
                    active_params.append("construction_work")
                logger.info(f"Active parameters detected ({detailed_context}): {', '.join(active_params)} | {format_context}")
            else:
                logger.info(f"No additional parameters detected ({detailed_context}) - both transportation and construction work are False | {format_context}")
        else:
            # Для формата КАСКО/спецтехника параметры по умолчанию False (без автоматического определения)
            has_transportation = False
            has_construction_work = False
            logger.info(f"CASCO/equipment format ({detailed_context}): transportation and construction work parameters set to False (no automatic detection) | {format_context}")
        
        # Извлекаем дополнительные параметры в зависимости от формата заявки
        if self.application_format == 'casco_equipment':
            additional_parameters = self._extract_casco_additional_parameters_openpyxl(sheet)
        elif self.application_format == 'property':
            additional_parameters = self._extract_property_additional_parameters_openpyxl(sheet)
        else:
            additional_parameters = self._get_empty_additional_parameters()
        
        extracted_data = {
            'client_name': client_name,
            'inn': self._get_cell_with_adjustment_openpyxl(sheet, 'D', 9) or '',
            'insurance_type': insurance_type,
            'insurance_period': insurance_period,
            'vehicle_info': vehicle_info,
            'dfa_number': dfa_number,
            'branch': branch,
            'franchise_type': franchise_type,
            'has_franchise': has_franchise,
            'has_installment': has_installment,
            'has_autostart': has_autostart,
            'has_casco_ce': has_casco_ce,
            'has_transportation': has_transportation,
            'has_construction_work': has_construction_work,
            'response_deadline': response_deadline,
            'additional_data': {
                'franchise_details': franchise_details,
                'extraction_timestamp': timezone.now().isoformat(),
                'application_type': self.application_type,
                'application_format': self.application_format
            }
        }
        
        # Добавляем дополнительные параметры в extracted_data
        extracted_data.update(additional_parameters)
        
        # Логируем успешное извлечение данных с информацией о формате и новых параметрах
        additional_params_summary = f"additional_params: {len([v for v in additional_parameters.values() if v])} non-empty"
        logger.info(f"Successfully extracted data with openpyxl ({detailed_context}): client='{client_name}', insurance_type='{insurance_type}', dfa_number='{dfa_number}', branch='{branch}', franchise_type='{franchise_type}', has_franchise={has_franchise}, has_autostart={has_autostart}, has_casco_ce={has_casco_ce}, has_transportation={has_transportation}, has_construction_work={has_construction_work}, {additional_params_summary} | {format_context}")
        
        return extracted_data
    
    def _extract_data_pandas(self, df) -> Dict[str, Any]:
        """Извлекает данные используя pandas (для .xls файлов)"""
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        logger.info(f"Starting pandas data extraction | {format_context}")
        
        # Определяем тип страхования на основе формата заявки
        if self.application_format == 'property':
            # Для формата имущества используем специальную логику
            logger.info(f"Using property insurance processing logic | {format_context}")
            insurance_type = self._determine_insurance_type_property_pandas(df)
            vehicle_info = self._find_leasing_object_info_property_pandas(df)
            has_autostart = False  # Всегда False для страхования имущества
            has_casco_ce = False  # Всегда False для страхования имущества (не извлекается)
            logger.debug(f"Property insurance processing: autostart set to False, casco_ce set to False | {format_context}")
        else:
            # Для формата КАСКО/спецтехника используем существующую логику
            logger.info(f"Using CASCO/equipment insurance processing logic | {format_context}")
            insurance_type = self._determine_insurance_type_pandas(df)
            vehicle_info = self._find_leasing_object_info_pandas(df)
            # Определяем автозапуск (если M24 = "нет", то автозапуска нет)
            autostart_value = self._get_cell_with_adjustment_pandas(df, 24, 12)  # M24
            has_autostart = bool(autostart_value) and str(autostart_value).lower().strip() != 'нет'
            # Определяем КАСКО кат. C/E на основе строки 45 (только для КАСКО/спецтехника)
            has_casco_ce = self._determine_casco_ce_pandas(df)
            logger.debug(f"CASCO/equipment processing: autostart determined as {has_autostart} (M24 value: {autostart_value}), casco_ce determined as {has_casco_ce} | {format_context}")
        
        # Определяем период страхования по новой логике N17/N18 (одинаково для всех форматов)
        insurance_period = self._determine_insurance_period_pandas(df)
        
        # Определяем срок ответа (текущее время + 3 часа) (одинаково для всех форматов)
        response_deadline = timezone.now() + timedelta(hours=3)
        
        # Определяем тип франшизы на основе анализа ячеек D29/D30, E29/E30, F29/F30
        logger.info(f"Starting franchise type determination (pandas) ({detailed_context}) | {format_context}")
        franchise_type = self._determine_franchise_type(sheet=None, is_openpyxl=False, df=df)
        
        # Обновляем has_franchise для обратной совместимости
        has_franchise = franchise_type in ['with_franchise', 'both_variants']
        logger.info(f"Franchise processing completed (pandas) ({detailed_context}): franchise_type='{franchise_type}', has_franchise={has_franchise} (backward compatibility) | {format_context}")
        
        # Получаем детальную информацию о франшизе для сохранения в additional_data
        franchise_details = self._get_franchise_details_pandas(df)
        logger.debug(f"Franchise details extracted (pandas) ({detailed_context}): {franchise_details} | {format_context}")
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ) (одинаково для всех форматов)
        installment_value = self._get_cell_with_adjustment_pandas(df, 34, 5)  # F34
        has_installment = not bool(installment_value)
        
        # Извлекаем название клиента из D7 (одинаково для всех форматов)
        client_name = self._get_cell_with_adjustment_pandas(df, 7, 3) or 'Клиент не указан'
        
        # Извлекаем номер ДФА (одинаково для всех форматов)
        dfa_number = self._find_dfa_number_pandas(df)
        
        # Извлекаем филиал (одинаково для всех форматов)
        branch = self._find_branch_pandas(df)
        
        # Определяем параметры перевозки и строительно-монтажных работ
        if self.application_format == 'property':
            # Для формата имущества используем автоматическое определение параметров
            logger.info(f"Starting transportation and construction work parameter detection for property insurance ({detailed_context}) | {format_context}")
            
            has_transportation = self._detect_transportation_parameter_pandas(df)
            has_construction_work = self._detect_construction_work_parameter_pandas(df)
            
            # Логируем итоговые значения параметров после обнаружения
            logger.info(f"Property insurance parameter detection completed ({detailed_context}): has_transportation={has_transportation}, has_construction_work={has_construction_work} | {format_context}")
            
            # Дополнительное логирование для верификации
            if has_transportation or has_construction_work:
                active_params = []
                if has_transportation:
                    active_params.append("transportation")
                if has_construction_work:
                    active_params.append("construction_work")
                logger.info(f"Active parameters detected ({detailed_context}): {', '.join(active_params)} | {format_context}")
            else:
                logger.info(f"No additional parameters detected ({detailed_context}) - both transportation and construction work are False | {format_context}")
        else:
            # Для формата КАСКО/спецтехника параметры по умолчанию False (без автоматического определения)
            has_transportation = False
            has_construction_work = False
            logger.info(f"CASCO/equipment format ({detailed_context}): transportation and construction work parameters set to False (no automatic detection) | {format_context}")
        
        # Извлекаем дополнительные параметры в зависимости от формата заявки
        if self.application_format == 'casco_equipment':
            additional_parameters = self._extract_casco_additional_parameters_pandas(df)
        elif self.application_format == 'property':
            additional_parameters = self._extract_property_additional_parameters_pandas(df)
        else:
            additional_parameters = self._get_empty_additional_parameters()
        
        extracted_data = {
            'client_name': client_name,
            'inn': self._get_cell_with_adjustment_pandas(df, 9, 3) or '',  # D9
            'insurance_type': insurance_type,
            'insurance_period': insurance_period,
            'vehicle_info': vehicle_info,
            'dfa_number': dfa_number,
            'branch': branch,
            'franchise_type': franchise_type,
            'has_franchise': has_franchise,
            'has_installment': has_installment,
            'has_autostart': has_autostart,
            'has_casco_ce': has_casco_ce,
            'has_transportation': has_transportation,
            'has_construction_work': has_construction_work,
            'response_deadline': response_deadline,
            'additional_data': {
                'franchise_details': franchise_details,
                'extraction_timestamp': timezone.now().isoformat(),
                'application_type': self.application_type,
                'application_format': self.application_format
            }
        }
        
        # Добавляем дополнительные параметры в extracted_data
        extracted_data.update(additional_parameters)
        
        # Логируем успешное извлечение данных с информацией о формате и новых параметрах
        additional_params_summary = f"additional_params: {len([v for v in additional_parameters.values() if v])} non-empty"
        logger.info(f"Successfully extracted data with pandas ({detailed_context}): client='{client_name}', insurance_type='{insurance_type}', dfa_number='{dfa_number}', branch='{branch}', franchise_type='{franchise_type}', has_franchise={has_franchise}, has_autostart={has_autostart}, has_casco_ce={has_casco_ce}, has_transportation={has_transportation}, has_construction_work={has_construction_work}, {additional_params_summary} | {format_context}")
        
        return extracted_data
    
    def _determine_insurance_type_openpyxl(self, sheet) -> str:
        """
        Определяет тип страхования на основе ячеек D21 и D22 (openpyxl)
        
        Логика:
        1. Если D21 содержит любое значение -> "КАСКО"
        2. Если D21 пустая, но D22 содержит значение -> "страхование спецтехники"
        3. Если обе ячейки пустые -> "другое"
        
        Примечание: "страхование имущества" не определяется автоматически и должно устанавливаться вручную менеджерами
        
        Возвращает только допустимые значения согласно INSURANCE_TYPE_CHOICES
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            d21_value = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 21)
            d22_value = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 22)
            
            # Используем новый helper метод для проверки значений
            d21_has_value = self._has_value(d21_value)
            d22_has_value = self._has_value(d22_value)
            
            if d21_has_value:
                insurance_type = 'КАСКО'
            elif d22_has_value:
                insurance_type = 'страхование спецтехники'
            else:
                insurance_type = 'другое'
            
            # Валидируем, что тип соответствует допустимым значениям
            valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
            if insurance_type not in valid_types:
                logger.warning(f"Invalid insurance type '{insurance_type}' ({detailed_context}), defaulting to 'другое' | {format_context}")
                insurance_type = 'другое'
            
            logger.info(f"Determined insurance type '{insurance_type}' ({detailed_context}) (D21: {d21_value}, D22: {d22_value}) | {format_context}")
            return insurance_type
            
        except Exception as e:
            logger.error(f"Error determining insurance type ({detailed_context}): {str(e)} | {format_context}")
            return 'другое'
    
    def _determine_insurance_type_pandas(self, df) -> str:
        """
        Определяет тип страхования на основе ячеек D21 и D22 (pandas)
        
        Логика:
        1. Если D21 содержит любое значение -> "КАСКО"
        2. Если D21 пустая, но D22 содержит значение -> "страхование спецтехники"
        3. Если обе ячейки пустые -> "другое"
        
        Примечание: "страхование имущества" не определяется автоматически и должно устанавливаться вручную менеджерами
        
        Возвращает только допустимые значения согласно INSURANCE_TYPE_CHOICES
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            d21_value = self._get_cell_with_adjustment_pandas(df, 21, 3)  # D21
            d22_value = self._get_cell_with_adjustment_pandas(df, 22, 3)  # D22
            
            # Используем новый helper метод для проверки значений
            d21_has_value = self._has_value(d21_value)
            d22_has_value = self._has_value(d22_value)
            
            if d21_has_value:
                insurance_type = 'КАСКО'
            elif d22_has_value:
                insurance_type = 'страхование спецтехники'
            else:
                insurance_type = 'другое'
            
            # Валидируем, что тип соответствует допустимым значениям
            valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
            if insurance_type not in valid_types:
                logger.warning(f"Invalid insurance type '{insurance_type}' ({detailed_context}), defaulting to 'другое' | {format_context}")
                insurance_type = 'другое'
            
            logger.info(f"Determined insurance type '{insurance_type}' ({detailed_context}) (D21: {d21_value}, D22: {d22_value}) | {format_context}")
            return insurance_type
            
        except Exception as e:
            logger.error(f"Error determining insurance type ({detailed_context}): {str(e)} | {format_context}")
            return 'другое'

    def _determine_insurance_type_property_openpyxl(self, sheet) -> str:
        """
        Определяет тип страхования для формата имущества на основе ячейки B22 (B23 для ИП) (openpyxl)
        
        Логика:
        1. Если B22 (B23 для ИП) содержит любое значение -> "страхование имущества"
        2. Если ячейка пустая -> "другое"
        
        Применяет логику смещения строк для ИП (+1 для строк > 8)
        
        Returns:
            str: Тип страхования ("страхование имущества" или "другое")
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Для ИП проверяем B23, для юр.лица B22
            row_to_check = 23 if self.application_type == 'individual_entrepreneur' else 22
            b_value = self._get_cell_with_adjustment_openpyxl(sheet, 'B', row_to_check)
            
            # Проверяем, содержит ли ячейка значение
            b_has_value = self._has_value(b_value)
            
            if b_has_value:
                insurance_type = 'страхование имущества'
            else:
                insurance_type = 'другое'
            
            # Валидируем, что тип соответствует допустимым значениям
            valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
            if insurance_type not in valid_types:
                logger.warning(f"Invalid property insurance type '{insurance_type}' ({detailed_context}), defaulting to 'другое' | {format_context}")
                insurance_type = 'другое'
            
            adjusted_row = self._get_adjusted_row(row_to_check)
            logger.info(f"Determined property insurance type '{insurance_type}' ({detailed_context}) (B{adjusted_row}: {b_value}) | {format_context}")
            return insurance_type
            
        except Exception as e:
            logger.error(f"Error determining property insurance type ({detailed_context}): {str(e)} | {format_context}")
            return 'другое'

    def _determine_insurance_type_property_pandas(self, df) -> str:
        """
        Определяет тип страхования для формата имущества на основе ячейки B22 (B23 для ИП) (pandas)
        
        Логика:
        1. Если B22 (B23 для ИП) содержит любое значение -> "страхование имущества"
        2. Если ячейка пустая -> "другое"
        
        Применяет логику смещения строк для ИП (+1 для строк > 8)
        
        Returns:
            str: Тип страхования ("страхование имущества" или "другое")
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Для ИП проверяем B23, для юр.лица B22
            row_to_check = 23 if self.application_type == 'individual_entrepreneur' else 22
            b_value = self._get_cell_with_adjustment_pandas(df, row_to_check, 1)  # B column (index 1)
            
            # Проверяем, содержит ли ячейка значение
            b_has_value = self._has_value(b_value)
            
            if b_has_value:
                insurance_type = 'страхование имущества'
            else:
                insurance_type = 'другое'
            
            # Валидируем, что тип соответствует допустимым значениям
            valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
            if insurance_type not in valid_types:
                logger.warning(f"Invalid property insurance type '{insurance_type}' ({detailed_context}), defaulting to 'другое' | {format_context}")
                insurance_type = 'другое'
            
            adjusted_row = self._get_adjusted_row(row_to_check)
            logger.info(f"Determined property insurance type '{insurance_type}' ({detailed_context}) (B{adjusted_row}: {b_value}) | {format_context}")
            return insurance_type
            
        except Exception as e:
            logger.error(f"Error determining property insurance type ({detailed_context}): {str(e)} | {format_context}")
            return 'другое'

    def _determine_insurance_period_openpyxl(self, sheet) -> str:
        """
        Определяет период страхования на основе ячеек N17 и N18 (openpyxl)
        
        Логика:
        1. Если N17 содержит любое значение -> "1 год"
        2. Если N17 пустая, но N18 содержит значение -> "на весь срок лизинга"
        3. Если обе ячейки пустые -> пустая строка
        """
        n17_value = self._get_cell_with_adjustment_openpyxl(sheet, 'N', 17)
        n18_value = self._get_cell_with_adjustment_openpyxl(sheet, 'N', 18)
        
        # Проверяем, что значение не пустое (не None и не пустая строка)
        n17_has_value = n17_value is not None and str(n17_value).strip() != ''
        n18_has_value = n18_value is not None and str(n18_value).strip() != ''
        
        if n17_has_value:
            return "1 год"
        elif n18_has_value:
            return "на весь срок лизинга"
        else:
            return ""

    def _determine_insurance_period_pandas(self, df) -> str:
        """
        Определяет период страхования на основе ячеек N17 и N18 (pandas)
        
        Логика:
        1. Если N17 содержит любое значение -> "1 год"
        2. Если N17 пустая, но N18 содержит значение -> "на весь срок лизинга"
        3. Если обе ячейки пустые -> пустая строка
        """
        n17_value = self._get_cell_with_adjustment_pandas(df, 17, 13)  # N17
        n18_value = self._get_cell_with_adjustment_pandas(df, 18, 13)  # N18
        
        # Проверяем, что значение не пустое (не None и не пустая строка)
        n17_has_value = n17_value is not None and str(n17_value).strip() != ''
        n18_has_value = n18_value is not None and str(n18_value).strip() != ''
        
        if n17_has_value:
            return "1 год"
        elif n18_has_value:
            return "на весь срок лизинга"
        else:
            return ""

    def _determine_casco_ce_openpyxl(self, sheet) -> bool:
        """
        Определяет наличие КАСКО кат. C/E на основе строки 45 столбцов CDEFGHI (openpyxl)
        
        Логика:
        Если любая из ячеек C45, D45, E45, F45, G45, H45, I45 содержит непустое значение,
        то has_casco_ce = True, иначе False
        
        Returns:
            bool: True если найдено непустое значение в любой из проверяемых ячеек
        """
        try:
            # Столбцы для проверки в строке 45
            columns_to_check = ['C', 'D', 'E', 'F', 'G', 'H', 'I']
            
            for column in columns_to_check:
                value = self._get_cell_with_adjustment_openpyxl(sheet, column, 45)
                # Проверяем, что значение не пустое (не None и не пустая строка)
                if value is not None and str(value).strip() != '':
                    adjusted_row = self._get_adjusted_row(45)
                    logger.debug(f"Found CASCO C/E indicator in cell {column}{adjusted_row}: {value} (application_type: {self.application_type}, application_format: {self.application_format})")
                    return True
            
            logger.debug(f"No CASCO C/E indicators found in row 45 (application_type: {self.application_type}, application_format: {self.application_format})")
            return False
            
        except Exception as e:
            logger.warning(f"Error determining CASCO C/E status (openpyxl) for application_type {self.application_type}, application_format {self.application_format}: {str(e)}")
            return False

    def _determine_casco_ce_pandas(self, df) -> bool:
        """
        Определяет наличие КАСКО кат. C/E на основе строки 45 столбцов CDEFGHI (pandas)
        
        Логика:
        Если любая из ячеек C45, D45, E45, F45, G45, H45, I45 содержит непустое значение,
        то has_casco_ce = True, иначе False
        
        Returns:
            bool: True если найдено непустое значение в любой из проверяемых ячеек
        """
        try:
            # Столбцы для проверки в строке 45: столбцы C-I (индексы 2-8)
            columns_to_check = [2, 3, 4, 5, 6, 7, 8]  # C, D, E, F, G, H, I
            
            for col in columns_to_check:
                value = self._get_cell_with_adjustment_pandas(df, 45, col)
                # Проверяем, что значение не пустое (не None и не пустая строка)
                if value is not None and str(value).strip() != '':
                    adjusted_row = self._get_adjusted_row(45)
                    logger.debug(f"Found CASCO C/E indicator in cell row {adjusted_row}, col {col+1}: {value} (application_type: {self.application_type}, application_format: {self.application_format})")
                    return True
            
            logger.debug(f"No CASCO C/E indicators found in row 45 (application_type: {self.application_type}, application_format: {self.application_format})")
            return False
            
        except Exception as e:
            logger.warning(f"Error determining CASCO C/E status (pandas) for application_type {self.application_type}, application_format {self.application_format}: {str(e)}")
            return False

    def _detect_transportation_parameter_openpyxl(self, sheet) -> bool:
        """
        Определяет наличие параметра перевозки на основе ячейки C44 (C45 для ИП) (openpyxl)
        
        Логика:
        Если ячейка C44 (C45 для ИП) содержит любое непустое значение,
        то has_transportation = True, иначе False
        
        Применяет логику смещения строк для ИП (+1 для строк > 8)
        
        Returns:
            bool: True если найдено непустое значение в ячейке C44/C45
        """
        format_context = self._get_format_context()
        
        try:
            # Проверяем ячейку C44 с учетом смещения для ИП
            value = self._get_cell_with_adjustment_openpyxl(sheet, 'C', 44)
            has_transportation = self._has_value(value)
            
            # Получаем скорректированный номер строки для логирования
            adjusted_row = self._get_adjusted_row(44)
            
            logger.info(f"Transportation parameter detection: C{adjusted_row} = '{value}' -> {has_transportation} | {format_context}")
            
            return has_transportation
            
        except Exception as e:
            logger.error(f"Error detecting transportation parameter (openpyxl): {str(e)} | {format_context}")
            return False

    def _detect_transportation_parameter_pandas(self, df) -> bool:
        """
        Определяет наличие параметра перевозки на основе ячейки C44 (C45 для ИП) (pandas)
        
        Логика:
        Если ячейка C44 (C45 для ИП) содержит любое непустое значение,
        то has_transportation = True, иначе False
        
        Применяет логику смещения строк для ИП (+1 для строк > 8)
        
        Returns:
            bool: True если найдено непустое значение в ячейке C44/C45
        """
        format_context = self._get_format_context()
        
        try:
            # Проверяем ячейку C44 с учетом смещения для ИП (столбец C = индекс 2)
            value = self._get_cell_with_adjustment_pandas(df, 44, 2)
            has_transportation = self._has_value(value)
            
            # Получаем скорректированный номер строки для логирования
            adjusted_row = self._get_adjusted_row(44)
            
            logger.info(f"Transportation parameter detection: C{adjusted_row} = '{value}' -> {has_transportation} | {format_context}")
            
            return has_transportation
            
        except Exception as e:
            logger.error(f"Error detecting transportation parameter (pandas): {str(e)} | {format_context}")
            return False

    def _detect_construction_work_parameter_openpyxl(self, sheet) -> bool:
        """
        Определяет наличие параметра строительно-монтажных работ на основе ячейки C48 (C49 для ИП) (openpyxl)
        
        Логика:
        Если ячейка C48 (C49 для ИП) содержит любое непустое значение,
        то has_construction_work = True, иначе False
        
        Применяет логику смещения строк для ИП (+1 для строк > 8)
        
        Returns:
            bool: True если найдено непустое значение в ячейке C48/C49
        """
        format_context = self._get_format_context()
        
        try:
            # Проверяем ячейку C48 с учетом смещения для ИП
            value = self._get_cell_with_adjustment_openpyxl(sheet, 'C', 48)
            has_construction_work = self._has_value(value)
            
            # Получаем скорректированный номер строки для логирования
            adjusted_row = self._get_adjusted_row(48)
            
            logger.info(f"Construction work parameter detection: C{adjusted_row} = '{value}' -> {has_construction_work} | {format_context}")
            
            return has_construction_work
            
        except Exception as e:
            logger.error(f"Error detecting construction work parameter (openpyxl): {str(e)} | {format_context}")
            return False

    def _detect_construction_work_parameter_pandas(self, df) -> bool:
        """
        Определяет наличие параметра строительно-монтажных работ на основе ячейки C48 (C49 для ИП) (pandas)
        
        Логика:
        Если ячейка C48 (C49 для ИП) содержит любое непустое значение,
        то has_construction_work = True, иначе False
        
        Применяет логику смещения строк для ИП (+1 для строк > 8)
        
        Returns:
            bool: True если найдено непустое значение в ячейке C48/C49
        """
        format_context = self._get_format_context()
        
        try:
            # Проверяем ячейку C48 с учетом смещения для ИП (столбец C = индекс 2)
            value = self._get_cell_with_adjustment_pandas(df, 48, 2)
            has_construction_work = self._has_value(value)
            
            # Получаем скорректированный номер строки для логирования
            adjusted_row = self._get_adjusted_row(48)
            
            logger.info(f"Construction work parameter detection: C{adjusted_row} = '{value}' -> {has_construction_work} | {format_context}")
            
            return has_construction_work
            
        except Exception as e:
            logger.error(f"Error detecting construction work parameter (pandas): {str(e)} | {format_context}")
            return False

    def _get_default_data(self) -> Dict[str, Any]:
        """Возвращает данные по умолчанию с валидным типом страхования и информацией о типе заявки"""
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        format_display = "КАСКО/спецтехника" if self.application_format == 'casco_equipment' else "имущество"
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        # Логируем использование данных по умолчанию
        logger.warning(f"Using default data for {app_type_display} with format {format_display} due to processing error | {format_context}")
        
        # Логируем значения параметров по умолчанию
        logger.info(f"Default parameter values ({detailed_context}): has_transportation=False, has_construction_work=False (fallback data) | {format_context}")
        
        return {
            'client_name': f'Клиент не указан ({app_type_display}, {format_display})',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',  # Используем допустимое значение
            'insurance_period': '1 год',  # Используем новый формат периода
            'vehicle_info': f'Информация о предмете лизинга не указана ({app_type_display}, {format_display})',
            'dfa_number': f'Номер ДФА не указан ({app_type_display}, {format_display})',
            'branch': f'Филиал не указан ({app_type_display}, {format_display})',
            'franchise_type': 'none',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'has_transportation': False,
            'has_construction_work': False,
            'response_deadline': timezone.now() + timedelta(hours=3),
            'application_type': self.application_type,
            'application_format': self.application_format,
            'additional_data': {
                'franchise_details': {
                    'error': 'Failed to extract franchise details',
                    'fallback_used': True
                },
                'extraction_timestamp': timezone.now().isoformat(),
                'application_type': self.application_type,
                'application_format': self.application_format
            }
        }
    
    def _get_empty_additional_parameters(self) -> Dict[str, str]:
        """
        Возвращает пустые значения для всех дополнительных параметров
        
        Returns:
            Dict[str, str]: Словарь с пустыми значениями для всех дополнительных параметров
        """
        return {
            'key_completeness': '',
            'pts_psm': '',
            'creditor_bank': '',
            'usage_purposes': '',
            'telematics_complex': '',
            'insurance_territory': ''
        }
    
    def _extract_casco_additional_parameters_openpyxl(self, sheet) -> Dict[str, str]:
        """
        Извлекает дополнительные параметры КАСКО/спецтехника используя openpyxl
        
        Извлекает параметры из следующих ячеек:
        - MN25: Комплектность ключей (объединенная ячейка M25:N25)
        - MN26: ПТС/ПСМ (объединенная ячейка M25:N26)
        - DE17: Банк-кредитор (объединенная ячейка D17:E17)
        - DEF37: Цели использования (объединенная ячейка D37:F37)
        - DEF70: Телематический комплекс (объединенная ячейка D70:F70)
        
        Args:
            sheet: Лист Excel (openpyxl)
            
        Returns:
            Dict[str, str]: Словарь с извлеченными параметрами
        """
        format_context = self._get_format_context()
        
        try:
            # Извлекаем параметры с учетом смещения строк для заявок ИП
            # Для объединенных ячеек используем первую ячейку диапазона
            
            # MN25 - Комплектность ключей (используем M25)
            key_completeness = self._get_cell_with_adjustment_openpyxl(sheet, 'M', 25) or ''
            
            # MN26 - ПТС/ПСМ (используем M26)
            pts_psm = self._get_cell_with_adjustment_openpyxl(sheet, 'M', 26) or ''
            
            # DE17 - Банк-кредитор (используем D17)
            creditor_bank = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 17) or ''
            
            # DEF37 - Цели использования (используем D37)
            usage_purposes = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 37) or ''
            
            # DEF70 - Телематический комплекс (используем D70)
            telematics_complex = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 63) or ''
            
            # Очищаем значения от лишних пробелов
            parameters = {
                'key_completeness': str(key_completeness).strip() if key_completeness else '',
                'pts_psm': str(pts_psm).strip() if pts_psm else '',
                'creditor_bank': str(creditor_bank).strip() if creditor_bank else '',
                'usage_purposes': str(usage_purposes).strip() if usage_purposes else '',
                'telematics_complex': str(telematics_complex).strip() if telematics_complex else ''
            }
            
            # Логируем успешное извлечение параметров
            non_empty_params = [k for k, v in parameters.items() if v]
            if non_empty_params:
                logger.info(f"Successfully extracted CASCO additional parameters (openpyxl): {len(non_empty_params)} non-empty parameters ({', '.join(non_empty_params)}) | {format_context}")
            else:
                logger.info(f"CASCO additional parameters extraction completed (openpyxl): all parameters are empty | {format_context}")
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error extracting CASCO additional parameters (openpyxl): {str(e)} | {format_context}")
            return self._get_empty_additional_parameters()
    
    def _extract_casco_additional_parameters_pandas(self, df) -> Dict[str, str]:
        """
        Извлекает дополнительные параметры КАСКО/спецтехника используя pandas
        
        Извлекает параметры из следующих ячеек:
        - MN25: Комплектность ключей (столбец M, индекс 12)
        - MN26: ПТС/ПСМ (столбец M, индекс 12)
        - DE17: Банк-кредитор (столбец D, индекс 3)
        - DEF37: Цели использования (столбец D, индекс 3)
        - DEF70: Телематический комплекс (столбец D, индекс 3)
        
        Args:
            df: DataFrame
            
        Returns:
            Dict[str, str]: Словарь с извлеченными параметрами
        """
        format_context = self._get_format_context()
        
        try:
            # Извлекаем параметры с учетом смещения строк для заявок ИП
            # Для объединенных ячеек используем первую ячейку диапазона
            
            # MN25 - Комплектность ключей (столбец M, индекс 12)
            key_completeness = self._get_cell_with_adjustment_pandas(df, 25, 12) or ''
            
            # MN26 - ПТС/ПСМ (столбец M, индекс 12)
            pts_psm = self._get_cell_with_adjustment_pandas(df, 26, 12) or ''
            
            # DE17 - Банк-кредитор (столбец D, индекс 3)
            creditor_bank = self._get_cell_with_adjustment_pandas(df, 17, 3) or ''
            
            # DEF37 - Цели использования (столбец D, индекс 3)
            usage_purposes = self._get_cell_with_adjustment_pandas(df, 37, 3) or ''
            
            # DEF70 - Телематический комплекс (столбец D, индекс 3)
            telematics_complex = self._get_cell_with_adjustment_pandas(df, 63, 3) or ''
            
            # Очищаем значения от лишних пробелов
            parameters = {
                'key_completeness': str(key_completeness).strip() if key_completeness else '',
                'pts_psm': str(pts_psm).strip() if pts_psm else '',
                'creditor_bank': str(creditor_bank).strip() if creditor_bank else '',
                'usage_purposes': str(usage_purposes).strip() if usage_purposes else '',
                'telematics_complex': str(telematics_complex).strip() if telematics_complex else ''
            }
            
            # Логируем успешное извлечение параметров
            non_empty_params = [k for k, v in parameters.items() if v]
            if non_empty_params:
                logger.info(f"Successfully extracted CASCO additional parameters (pandas): {len(non_empty_params)} non-empty parameters ({', '.join(non_empty_params)}) | {format_context}")
            else:
                logger.info(f"CASCO additional parameters extraction completed (pandas): all parameters are empty | {format_context}")
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error extracting CASCO additional parameters (pandas): {str(e)} | {format_context}")
            return self._get_empty_additional_parameters()
    
    def _extract_property_additional_parameters_openpyxl(self, sheet) -> Dict[str, str]:
        """
        Извлекает дополнительные параметры страхования имущества используя openpyxl
        
        Извлекает параметры из следующих ячеек:
        - DE17: Банк-кредитор (объединенная ячейка D17:E17)
        - DEF37: Цели использования (объединенная ячейка D37:F37)
        - LMN20-22: Территория страхования (объединенная ячейка L20:N22)
        
        Args:
            sheet: Лист Excel (openpyxl)
            
        Returns:
            Dict[str, str]: Словарь с извлеченными параметрами
        """
        format_context = self._get_format_context()
        
        try:
            # Извлекаем параметры с учетом смещения строк для заявок ИП
            # Для объединенных ячеек используем первую ячейку диапазона
            
            # DE17 - Банк-кредитор (используем D17)
            creditor_bank = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 17) or ''
            
            # DEF37 - Цели использования (используем D37)
            usage_purposes = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 37) or ''
            
            # LMN20-22 - Территория страхования (используем L20)
            insurance_territory = self._get_cell_with_adjustment_openpyxl(sheet, 'L', 20) or ''
            
            # Очищаем значения от лишних пробелов
            parameters = {
                'key_completeness': '',  # Не используется для страхования имущества
                'pts_psm': '',  # Не используется для страхования имущества
                'creditor_bank': str(creditor_bank).strip() if creditor_bank else '',
                'usage_purposes': str(usage_purposes).strip() if usage_purposes else '',
                'telematics_complex': '',  # Не используется для страхования имущества
                'insurance_territory': str(insurance_territory).strip() if insurance_territory else ''
            }
            
            # Логируем успешное извлечение параметров
            non_empty_params = [k for k, v in parameters.items() if v]
            if non_empty_params:
                logger.info(f"Successfully extracted property insurance additional parameters (openpyxl): {len(non_empty_params)} non-empty parameters ({', '.join(non_empty_params)}) | {format_context}")
            else:
                logger.info(f"Property insurance additional parameters extraction completed (openpyxl): all parameters are empty | {format_context}")
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error extracting property insurance additional parameters (openpyxl): {str(e)} | {format_context}")
            return self._get_empty_additional_parameters()
    
    def _extract_property_additional_parameters_pandas(self, df) -> Dict[str, str]:
        """
        Извлекает дополнительные параметры страхования имущества используя pandas
        
        Извлекает параметры из следующих ячеек:
        - DE17: Банк-кредитор (столбец D, индекс 3)
        - DEF37: Цели использования (столбец D, индекс 3)
        - LMN20-22: Территория страхования (столбец L, индекс 11)
        
        Args:
            df: DataFrame
            
        Returns:
            Dict[str, str]: Словарь с извлеченными параметрами
        """
        format_context = self._get_format_context()
        
        try:
            # Извлекаем параметры с учетом смещения строк для заявок ИП
            # Для объединенных ячеек используем первую ячейку диапазона
            
            # DE17 - Банк-кредитор (столбец D, индекс 3)
            creditor_bank = self._get_cell_with_adjustment_pandas(df, 17, 3) or ''
            
            # DEF37 - Цели использования (столбец D, индекс 3)
            usage_purposes = self._get_cell_with_adjustment_pandas(df, 37, 3) or ''
            
            # LMN20-22 - Территория страхования (столбец L, индекс 11)
            insurance_territory = self._get_cell_with_adjustment_pandas(df, 20, 11) or ''
            
            # Очищаем значения от лишних пробелов
            parameters = {
                'key_completeness': '',  # Не используется для страхования имущества
                'pts_psm': '',  # Не используется для страхования имущества
                'creditor_bank': str(creditor_bank).strip() if creditor_bank else '',
                'usage_purposes': str(usage_purposes).strip() if usage_purposes else '',
                'telematics_complex': '',  # Не используется для страхования имущества
                'insurance_territory': str(insurance_territory).strip() if insurance_territory else ''
            }
            
            # Логируем успешное извлечение параметров
            non_empty_params = [k for k, v in parameters.items() if v]
            if non_empty_params:
                logger.info(f"Successfully extracted property insurance additional parameters (pandas): {len(non_empty_params)} non-empty parameters ({', '.join(non_empty_params)}) | {format_context}")
            else:
                logger.info(f"Property insurance additional parameters extraction completed (pandas): all parameters are empty | {format_context}")
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error extracting property insurance additional parameters (pandas): {str(e)} | {format_context}")
            return self._get_empty_additional_parameters()

    
    def _find_leasing_object_info_pandas(self, df) -> str:
        """Ищет информацию о предмете лизинга в указанных ячейках"""
        # Строки и столбцы для поиска: CDEFGHI43, CDEFGHI45, CDEFGHI47, CDEFGHI49
        rows_to_check = [43, 45, 47, 49]
        columns_to_check = [2, 3, 4, 5, 6, 7, 8]  # C-I (индексы 2-8)
        
        vehicle_info_parts = []
        
        for row in rows_to_check:
            for col in columns_to_check:
                value = self._get_cell_with_adjustment_pandas(df, row, col)
                if value and str(value).strip():
                    vehicle_info_parts.append(str(value).strip())
        
        # Объединяем найденную информацию
        if vehicle_info_parts:
            return ' '.join(vehicle_info_parts)
        else:
            return 'Информация о предмете лизинга не указана'

    def _find_leasing_object_info_property_pandas(self, df) -> str:
        """
        Извлекает информацию о предмете лизинга для формата имущества (pandas)
        
        Логика:
        - Для юр.лица: извлекает из CDEFGHIJ42 (без смещения)
        - Для ИП: извлекает из CDEFGHIJ43 (без смещения, так как 43 уже является IP-специфичной строкой)
        
        Примечание: В отличие от других полей, для property insurance asset info 
        строки 42/43 уже учитывают тип заявки, поэтому дополнительное смещение не применяется.
        
        Returns:
            str: Информация о предмете лизинга или сообщение по умолчанию
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем строку для извлечения данных (без применения смещения)
            if self.application_type == 'individual_entrepreneur':
                row_to_check = 43  # Для ИП используем строку 43 (уже учитывает тип заявки)
            else:
                row_to_check = 42  # Для юр.лица используем строку 42
            
            # Столбцы для извлечения: CDEFGHIJ (индексы 2-9, включая столбец J)
            columns_to_check = [2, 3, 4, 5, 6, 7, 8, 9]  # C, D, E, F, G, H, I, J
            vehicle_info_parts = []
            
            for col in columns_to_check:
                # Используем прямое обращение к ячейке без смещения для property insurance
                # Преобразуем в 0-based индекс для pandas
                pandas_row_index = row_to_check - 1
                value = self._safe_get_cell(df, pandas_row_index, col)
                if value and str(value).strip():
                    vehicle_info_parts.append(str(value).strip())
            
            # Объединяем найденную информацию
            if vehicle_info_parts:
                result = ' '.join(vehicle_info_parts)
                logger.info(f"Extracted property asset info ({detailed_context}) from row {row_to_check} (CDEFGHIJ): {result} | {format_context}")
                return result
            else:
                logger.info(f"No property asset info found ({detailed_context}) in row {row_to_check} (CDEFGHIJ) | {format_context}")
                return 'Информация о предмете лизинга не указана'
                
        except Exception as e:
            logger.error(f"Error extracting property asset info ({detailed_context}): {str(e)} | {format_context}")
            return 'Информация о предмете лизинга не указана'
    
    def _find_dfa_number_pandas(self, df) -> str:
        """Извлекает номер ДФА из ячеек HIJ2"""
        # Ячейки HIJ2: строка 2, столбцы H,I,J (индексы 7,8,9)
        columns_to_check = [7, 8, 9]  # H, I, J
        dfa_parts = []
        
        for col in columns_to_check:
            value = self._get_cell_with_adjustment_pandas(df, 2, col)
            if value and str(value).strip():
                dfa_parts.append(str(value).strip())
        
        return ' '.join(dfa_parts) if dfa_parts else 'Номер ДФА не указан'
    
    def _find_branch_pandas(self, df) -> str:
        """Извлекает филиал из ячеек CDEF4"""
        # Ячейки CDEF4: строка 4, столбцы C,D,E,F (индексы 2,3,4,5)
        columns_to_check = [2, 3, 4, 5]  # C, D, E, F
        branch_parts = []
        
        for col in columns_to_check:
            value = self._get_cell_with_adjustment_pandas(df, 4, col)
            if value and str(value).strip():
                branch_parts.append(str(value).strip())
        
        full_branch_name = ' '.join(branch_parts) if branch_parts else 'Филиал не указан'
        
        # Применяем маппинг названий филиалов
        return map_branch_name(full_branch_name)
    
    def _find_leasing_object_info_openpyxl(self, sheet) -> str:
        """Ищет информацию о предмете лизинга в указанных ячейках (openpyxl)"""
        # Строки и столбцы для поиска: CDEFGHI43, CDEFGHI45, CDEFGHI47, CDEFGHI49
        rows_to_check = [43, 45, 47, 49]
        columns_to_check = ['C', 'D', 'E', 'F', 'G', 'H', 'I']
        
        vehicle_info_parts = []
        
        for row in rows_to_check:
            for column in columns_to_check:
                value = self._get_cell_with_adjustment_openpyxl(sheet, column, row)
                if value and str(value).strip():
                    vehicle_info_parts.append(str(value).strip())
        
        # Объединяем найденную информацию
        if vehicle_info_parts:
            return ' '.join(vehicle_info_parts)
        else:
            return 'Информация о предмете лизинга не указана'

    def _find_leasing_object_info_property_openpyxl(self, sheet) -> str:
        """
        Извлекает информацию о предмете лизинга для формата имущества (openpyxl)
        
        Логика:
        - Для юр.лица: извлекает из CDEFGHIJ42 (без смещения)
        - Для ИП: извлекает из CDEFGHIJ43 (без смещения, так как 43 уже является IP-специфичной строкой)
        
        Примечание: В отличие от других полей, для property insurance asset info 
        строки 42/43 уже учитывают тип заявки, поэтому дополнительное смещение не применяется.
        
        Returns:
            str: Информация о предмете лизинга или сообщение по умолчанию
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем строку для извлечения данных (без применения смещения)
            if self.application_type == 'individual_entrepreneur':
                row_to_check = 43  # Для ИП используем строку 43 (уже учитывает тип заявки)
            else:
                row_to_check = 42  # Для юр.лица используем строку 42
            
            # Столбцы для извлечения: CDEFGHIJ (включая столбец J)
            columns_to_check = ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
            vehicle_info_parts = []
            
            for column in columns_to_check:
                # Используем прямое обращение к ячейке без смещения для property insurance
                cell_address = f"{column}{row_to_check}"
                value = self._get_cell_value(sheet, cell_address)
                if value and str(value).strip():
                    vehicle_info_parts.append(str(value).strip())
            
            # Объединяем найденную информацию
            if vehicle_info_parts:
                result = ' '.join(vehicle_info_parts)
                logger.info(f"Extracted property asset info ({detailed_context}) from row {row_to_check} (CDEFGHIJ): {result} | {format_context}")
                return result
            else:
                logger.info(f"No property asset info found ({detailed_context}) in row {row_to_check} (CDEFGHIJ) | {format_context}")
                return 'Информация о предмете лизинга не указана'
                
        except Exception as e:
            logger.error(f"Error extracting property asset info ({detailed_context}): {str(e)} | {format_context}")
            return 'Информация о предмете лизинга не указана'
    
    def _find_dfa_number_openpyxl(self, sheet) -> str:
        """Извлекает номер ДФА из ячеек HIJ2 (openpyxl)"""
        # Ячейки HIJ2: строка 2, столбцы H,I,J
        columns_to_check = ['H', 'I', 'J']
        dfa_parts = []
        
        for column in columns_to_check:
            value = self._get_cell_with_adjustment_openpyxl(sheet, column, 2)
            if value and str(value).strip():
                dfa_parts.append(str(value).strip())
        
        return ' '.join(dfa_parts) if dfa_parts else 'Номер ДФА не указан'
    
    def _find_branch_openpyxl(self, sheet) -> str:
        """Извлекает филиал из ячеек CDEF4 (openpyxl)"""
        # Ячейки CDEF4: строка 4, столбцы C,D,E,F
        columns_to_check = ['C', 'D', 'E', 'F']
        branch_parts = []
        
        for column in columns_to_check:
            value = self._get_cell_with_adjustment_openpyxl(sheet, column, 4)
            if value and str(value).strip():
                branch_parts.append(str(value).strip())
        
        full_branch_name = ' '.join(branch_parts) if branch_parts else 'Филиал не указан'
        
        # Применяем маппинг названий филиалов
        return map_branch_name(full_branch_name)
    
    def _safe_get_cell(self, df, row: int, col: int) -> Optional[str]:
        """Безопасно получает значение ячейки из DataFrame"""
        try:
            if row < len(df) and col < len(df.columns):
                value = df.iloc[row, col]
                return str(value) if pd.notna(value) else None
            return None
        except Exception:
            return None
    
    def _safe_int(self, value: Optional[str], default: int = 0) -> int:
        """Безопасно преобразует значение в int"""
        if value is None:
            return default
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return default
    
    def _safe_bool(self, value: Optional[str]) -> bool:
        """Безопасно преобразует значение в bool"""
        if value is None:
            return False
        value_str = str(value).lower().strip()
        return value_str in ['да', 'yes', '1', 'true', 'истина', '+']
    
    def _detect_transportation_parameter_openpyxl(self, sheet) -> bool:
        """
        Определяет параметр перевозки из ячейки C44 (C45 для ИП) (openpyxl)
        
        Args:
            sheet: Лист Excel (openpyxl)
            
        Returns:
            bool: True если требуется перевозка, False иначе
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем базовую строку для проверки (C44)
            base_row = 44
            
            # Получаем значение ячейки с учетом смещения для ИП
            cell_value = self._get_cell_with_adjustment_openpyxl(sheet, 'C', base_row)
            
            # Определяем фактическую ячейку после применения смещения
            actual_row = self._get_adjusted_row(base_row)
            actual_cell = f"C{actual_row}"
            
            # Проверяем наличие значения
            has_transportation = self._has_value(cell_value)
            
            # Логируем детали обнаружения параметра перевозки
            if self.application_type == 'individual_entrepreneur' and base_row > 8:
                logger.info(f"Transportation parameter detection ({detailed_context}): C{base_row} -> {actual_cell} (IP row offset applied), value: '{cell_value}', result: {has_transportation} | {format_context}")
            else:
                logger.info(f"Transportation parameter detection ({detailed_context}): {actual_cell}, value: '{cell_value}', result: {has_transportation} | {format_context}")
            
            return has_transportation
            
        except Exception as e:
            logger.error(f"Error detecting transportation parameter ({detailed_context}): {str(e)}, defaulting to False | {format_context}")
            return False
    
    def _detect_transportation_parameter_pandas(self, df) -> bool:
        """
        Определяет параметр перевозки из ячейки C44 (C45 для ИП) (pandas)
        
        Args:
            df: DataFrame
            
        Returns:
            bool: True если требуется перевозка, False иначе
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем базовую строку для проверки (C44)
            base_row = 44
            
            # Получаем значение ячейки с учетом смещения для ИП (C = column index 2)
            cell_value = self._get_cell_with_adjustment_pandas(df, base_row, 2)
            
            # Определяем фактическую ячейку после применения смещения
            actual_row = self._get_adjusted_row(base_row)
            actual_cell = f"C{actual_row}"
            
            # Проверяем наличие значения
            has_transportation = self._has_value(cell_value)
            
            # Логируем детали обнаружения параметра перевозки
            if self.application_type == 'individual_entrepreneur' and base_row > 8:
                logger.info(f"Transportation parameter detection ({detailed_context}): C{base_row} -> {actual_cell} (IP row offset applied), value: '{cell_value}', result: {has_transportation} | {format_context}")
            else:
                logger.info(f"Transportation parameter detection ({detailed_context}): {actual_cell}, value: '{cell_value}', result: {has_transportation} | {format_context}")
            
            return has_transportation
            
        except Exception as e:
            logger.error(f"Error detecting transportation parameter ({detailed_context}): {str(e)}, defaulting to False | {format_context}")
            return False
    
    def _detect_construction_work_parameter_openpyxl(self, sheet) -> bool:
        """
        Определяет параметр строительно-монтажных работ из ячейки C48 (C49 для ИП) (openpyxl)
        
        Args:
            sheet: Лист Excel (openpyxl)
            
        Returns:
            bool: True если требуются СМР, False иначе
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем базовую строку для проверки (C48)
            base_row = 48
            
            # Получаем значение ячейки с учетом смещения для ИП
            cell_value = self._get_cell_with_adjustment_openpyxl(sheet, 'C', base_row)
            
            # Определяем фактическую ячейку после применения смещения
            actual_row = self._get_adjusted_row(base_row)
            actual_cell = f"C{actual_row}"
            
            # Проверяем наличие значения
            has_construction_work = self._has_value(cell_value)
            
            # Логируем детали обнаружения параметра СМР
            if self.application_type == 'individual_entrepreneur' and base_row > 8:
                logger.info(f"Construction work parameter detection ({detailed_context}): C{base_row} -> {actual_cell} (IP row offset applied), value: '{cell_value}', result: {has_construction_work} | {format_context}")
            else:
                logger.info(f"Construction work parameter detection ({detailed_context}): {actual_cell}, value: '{cell_value}', result: {has_construction_work} | {format_context}")
            
            return has_construction_work
            
        except Exception as e:
            logger.error(f"Error detecting construction work parameter ({detailed_context}): {str(e)}, defaulting to False | {format_context}")
            return False
    
    def _detect_construction_work_parameter_pandas(self, df) -> bool:
        """
        Определяет параметр строительно-монтажных работ из ячейки C48 (C49 для ИП) (pandas)
        
        Args:
            df: DataFrame
            
        Returns:
            bool: True если требуются СМР, False иначе
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем базовую строку для проверки (C48)
            base_row = 48
            
            # Получаем значение ячейки с учетом смещения для ИП (C = column index 2)
            cell_value = self._get_cell_with_adjustment_pandas(df, base_row, 2)
            
            # Определяем фактическую ячейку после применения смещения
            actual_row = self._get_adjusted_row(base_row)
            actual_cell = f"C{actual_row}"
            
            # Проверяем наличие значения
            has_construction_work = self._has_value(cell_value)
            
            # Логируем детали обнаружения параметра СМР
            if self.application_type == 'individual_entrepreneur' and base_row > 8:
                logger.info(f"Construction work parameter detection ({detailed_context}): C{base_row} -> {actual_cell} (IP row offset applied), value: '{cell_value}', result: {has_construction_work} | {format_context}")
            else:
                logger.info(f"Construction work parameter detection ({detailed_context}): {actual_cell}, value: '{cell_value}', result: {has_construction_work} | {format_context}")
            
            return has_construction_work
            
        except Exception as e:
            logger.error(f"Error detecting construction work parameter ({detailed_context}): {str(e)}, defaulting to False | {format_context}")
            return False

    def _has_value(self, value) -> bool:
        """
        Проверяет, содержит ли значение непустые данные.
        
        Args:
            value: Значение для проверки
            
        Returns:
            bool: True если значение не пустое, False иначе
        """
        if value is None:
            return False
        
        # Специальная обработка для boolean False
        if isinstance(value, bool) and value is False:
            return False
        
        # Преобразуем в строку и убираем пробелы
        str_value = str(value).strip()
        
        # Проверяем на пустую строку или специальные значения
        if str_value == '' or str_value.lower() in ['none', 'nan', 'null', 'false']:
            return False
            
        return True
    
    def _get_cell_value(self, sheet, cell_address: str) -> Optional[str]:
        """Безопасно получает значение ячейки"""
        try:
            cell_value = sheet[cell_address].value
            return str(cell_value) if cell_value is not None else None
        except Exception:
            return None
    
    def _determine_franchise_type(self, sheet, is_openpyxl: bool = True, df=None) -> str:
        """
        Определяет тип франшизы на основе анализа ячеек Excel
        
        Логика определения:
        1. Определяет тип заявки (ИП или обычная компания) на основе application_type
        2. Выбирает соответствующие ячейки:
           - Обычная компания: D29, E29, F29
           - ИП: D30, E30, F30
        3. Анализирует содержимое ячеек:
           - Если D29/D30 не пустая И E29/E30, F29/F30 пустые -> 'none' (без франшизы)
           - Если D29/D30 пустая И (E29/E30 ИЛИ F29/F30) не пустые -> 'with_franchise' (только с франшизой)
           - Если D29/D30 не пустая И (E29/E30 ИЛИ F29/F30) не пустые -> 'both_variants' (оба варианта)
           - Если все ячейки пустые -> 'none' (по умолчанию)
        
        Args:
            sheet: Лист Excel (для openpyxl) или None (для pandas)
            is_openpyxl: True если используется openpyxl, False для pandas
            df: DataFrame (для pandas) или None (для openpyxl)
            
        Returns:
            str: Тип франшизы ('none', 'with_franchise', 'both_variants')
        """
        format_context = self._get_format_context()
        detailed_context = self._get_detailed_format_context()
        
        try:
            # Определяем, является ли это заявкой от ИП
            is_ip_format = self.application_type == 'individual_entrepreneur'
            
            # Используем базовую строку 29 для всех типов заявок
            # Смещение для ИП будет применено автоматически в _get_adjusted_row
            d_row, e_row, f_row = 29, 29, 29
            
            if is_ip_format:
                logger.debug(f"Using base row 29 for IP format (will be adjusted to 30 automatically): D29->D30, E29->E30, F29->F30 ({detailed_context}) | {format_context}")
            else:
                logger.debug(f"Using legal entity format cells: D29, E29, F29 ({detailed_context}) | {format_context}")
            
            # Получаем значения ячеек в зависимости от используемой библиотеки
            if is_openpyxl:
                d_value = self._get_cell_with_adjustment_openpyxl(sheet, 'D', d_row)
                e_value = self._get_cell_with_adjustment_openpyxl(sheet, 'E', e_row)
                f_value = self._get_cell_with_adjustment_openpyxl(sheet, 'F', f_row)
            else:
                # Для pandas: D=колонка 3, E=колонка 4, F=колонка 5 (0-based)
                d_value = self._get_cell_with_adjustment_pandas(df, d_row, 3)
                e_value = self._get_cell_with_adjustment_pandas(df, e_row, 4)
                f_value = self._get_cell_with_adjustment_pandas(df, f_row, 5)
            
            # Проверяем наличие значений в ячейках
            d_has_value = self._has_value(d_value)
            e_has_value = self._has_value(e_value)
            f_has_value = self._has_value(f_value)
            
            # Определяем фактические ячейки после корректировки для логирования
            actual_d_row = self._get_adjusted_row(d_row)
            actual_e_row = self._get_adjusted_row(e_row)
            actual_f_row = self._get_adjusted_row(f_row)
            
            # Логируем значения ячеек для отладки
            logger.debug(f"Franchise cells analysis ({detailed_context}): D{actual_d_row}='{d_value}' ({d_has_value}), E{actual_e_row}='{e_value}' ({e_has_value}), F{actual_f_row}='{f_value}' ({f_has_value}) | {format_context}")
            
            # Определяем тип франшизы по логике
            if d_has_value and not e_has_value and not f_has_value:
                # D не пустая, E и F пустые -> без франшизы
                franchise_type = 'none'
                logger.info(f"Determined franchise type 'none' ({detailed_context}): D{actual_d_row} has value, E{actual_e_row} and F{actual_f_row} are empty | {format_context}")
            elif not d_has_value and (e_has_value or f_has_value):
                # D пустая, но E или F не пустые -> только с франшизой
                franchise_type = 'with_franchise'
                logger.info(f"Determined franchise type 'with_franchise' ({detailed_context}): D{actual_d_row} is empty, E{actual_e_row} or F{actual_f_row} has value | {format_context}")
            elif d_has_value and (e_has_value or f_has_value):
                # D не пустая И (E или F не пустые) -> оба варианта
                franchise_type = 'both_variants'
                logger.info(f"Determined franchise type 'both_variants' ({detailed_context}): D{actual_d_row} has value AND E{actual_e_row} or F{actual_f_row} has value | {format_context}")
            else:
                # Все ячейки пустые или неопределенное состояние -> по умолчанию без франшизы
                franchise_type = 'none'
                logger.info(f"Determined franchise type 'none' (default) ({detailed_context}): all cells are empty or undefined state | {format_context}")
            
            # Сохраняем детальную информацию о франшизе в additional_data для анализа
            franchise_details = {
                'd_cell_value': str(d_value) if d_value is not None else None,
                'e_cell_value': str(e_value) if e_value is not None else None,
                'f_cell_value': str(f_value) if f_value is not None else None,
                'is_ip_format': is_ip_format,
                'base_d_row': d_row,
                'base_e_row': e_row,
                'base_f_row': f_row,
                'actual_d_row': actual_d_row,
                'actual_e_row': actual_e_row,
                'actual_f_row': actual_f_row,
                'determined_type': franchise_type
            }
            
            logger.info(f"Franchise type determination completed ({detailed_context}): '{franchise_type}' | {format_context}")
            
            return franchise_type
            
        except Exception as e:
            logger.error(f"Error determining franchise type ({detailed_context}): {str(e)} | {format_context}")
            # В случае ошибки возвращаем безопасное значение по умолчанию
            logger.warning(f"Falling back to franchise type 'none' due to error ({detailed_context}) | {format_context}")
            return 'none'
    
    def _get_franchise_details_openpyxl(self, sheet) -> Dict[str, Any]:
        """
        Получает детальную информацию о франшизе для сохранения в additional_data (openpyxl)
        
        Args:
            sheet: Лист Excel (openpyxl)
            
        Returns:
            Dict с детальной информацией о франшизе
        """
        try:
            is_ip_format = self.application_type == 'individual_entrepreneur'
            
            # Используем базовую строку 29 для всех типов заявок
            # Смещение для ИП будет применено автоматически в _get_adjusted_row
            d_row, e_row, f_row = 29, 29, 29
            
            d_value = self._get_cell_with_adjustment_openpyxl(sheet, 'D', d_row)
            e_value = self._get_cell_with_adjustment_openpyxl(sheet, 'E', e_row)
            f_value = self._get_cell_with_adjustment_openpyxl(sheet, 'F', f_row)
            
            # Определяем фактические строки после корректировки
            actual_d_row = self._get_adjusted_row(d_row)
            actual_e_row = self._get_adjusted_row(e_row)
            actual_f_row = self._get_adjusted_row(f_row)
            
            return {
                'd_cell_value': str(d_value) if d_value is not None else None,
                'e_cell_value': str(e_value) if e_value is not None else None,
                'f_cell_value': str(f_value) if f_value is not None else None,
                'is_ip_format': is_ip_format,
                'base_d_row': d_row,
                'base_e_row': e_row,
                'base_f_row': f_row,
                'actual_d_row': actual_d_row,
                'actual_e_row': actual_e_row,
                'actual_f_row': actual_f_row,
                'extraction_method': 'openpyxl'
            }
        except Exception as e:
            logger.error(f"Error getting franchise details (openpyxl): {str(e)}")
            return {}
    
    def _get_franchise_details_pandas(self, df) -> Dict[str, Any]:
        """
        Получает детальную информацию о франшизе для сохранения в additional_data (pandas)
        
        Args:
            df: DataFrame (pandas)
            
        Returns:
            Dict с детальной информацией о франшизе
        """
        try:
            is_ip_format = self.application_type == 'individual_entrepreneur'
            
            # Используем базовую строку 29 для всех типов заявок
            # Смещение для ИП будет применено автоматически в _get_adjusted_row
            d_row, e_row, f_row = 29, 29, 29
            
            d_value = self._get_cell_with_adjustment_pandas(df, d_row, 3)  # D
            e_value = self._get_cell_with_adjustment_pandas(df, e_row, 4)  # E
            f_value = self._get_cell_with_adjustment_pandas(df, f_row, 5)  # F
            
            # Определяем фактические строки после корректировки
            actual_d_row = self._get_adjusted_row(d_row)
            actual_e_row = self._get_adjusted_row(e_row)
            actual_f_row = self._get_adjusted_row(f_row)
            
            return {
                'd_cell_value': str(d_value) if d_value is not None else None,
                'e_cell_value': str(e_value) if e_value is not None else None,
                'f_cell_value': str(f_value) if f_value is not None else None,
                'is_ip_format': is_ip_format,
                'base_d_row': d_row,
                'base_e_row': e_row,
                'base_f_row': f_row,
                'actual_d_row': actual_d_row,
                'actual_e_row': actual_e_row,
                'actual_f_row': actual_f_row,
                'extraction_method': 'pandas'
            }
        except Exception as e:
            logger.error(f"Error getting franchise details (pandas): {str(e)}")
            return {}


class ExcelWriter:
    """Класс для создания Excel отчетов"""
    
    def create_report(self, data: Dict[str, Any], output_path: str) -> None:
        """
        Создает Excel отчет на основе данных
        """
        try:
            df = pd.DataFrame(data)
            
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Отчет', index=False)
                
            logger.info(f"Report created successfully: {output_path}")
            
        except Exception as e:
            logger.error(f"Error creating Excel report: {str(e)}")
            raise
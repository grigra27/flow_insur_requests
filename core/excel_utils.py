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
            logger.debug(f"Row adjustment applied: {row_number} -> {adjusted_row} (IP application, total adjustments: {self._row_adjustments_applied}) | {format_context}")
            return adjusted_row
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
                'file_path': self.file_path
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
        
        # Определяем наличие франшизы (если D29 не пустая, то франшизы НЕТ) (одинаково для всех форматов)
        d29_value = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 29)
        has_franchise = not bool(d29_value and str(d29_value).strip())
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ) (одинаково для всех форматов)
        has_installment = not bool(self._get_cell_with_adjustment_openpyxl(sheet, 'F', 34))
        
        # Извлекаем название клиента из D7 (одинаково для всех форматов)
        client_name = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 7) or 'Клиент не указан'
        
        # Извлекаем номер ДФА (одинаково для всех форматов)
        dfa_number = self._find_dfa_number_openpyxl(sheet)
        
        # Извлекаем филиал (одинаково для всех форматов)
        branch = self._find_branch_openpyxl(sheet)
        
        extracted_data = {
            'client_name': client_name,
            'inn': self._get_cell_with_adjustment_openpyxl(sheet, 'D', 9) or '',
            'insurance_type': insurance_type,
            'insurance_period': insurance_period,
            'vehicle_info': vehicle_info,
            'dfa_number': dfa_number,
            'branch': branch,
            'has_franchise': has_franchise,
            'has_installment': has_installment,
            'has_autostart': has_autostart,
            'has_casco_ce': has_casco_ce,
            'response_deadline': response_deadline,
        }
        
        # Логируем успешное извлечение данных с информацией о формате
        logger.info(f"Successfully extracted data with openpyxl ({detailed_context}): client='{client_name}', insurance_type='{insurance_type}', dfa_number='{dfa_number}', branch='{branch}', has_autostart={has_autostart}, has_casco_ce={has_casco_ce} | {format_context}")
        
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
        
        # Определяем наличие франшизы (если D29 не пустая, то франшизы НЕТ) (одинаково для всех форматов)
        franchise_value = self._get_cell_with_adjustment_pandas(df, 29, 3)  # D29
        has_franchise = not bool(franchise_value and str(franchise_value).strip())
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ) (одинаково для всех форматов)
        installment_value = self._get_cell_with_adjustment_pandas(df, 34, 5)  # F34
        has_installment = not bool(installment_value)
        
        # Извлекаем название клиента из D7 (одинаково для всех форматов)
        client_name = self._get_cell_with_adjustment_pandas(df, 7, 3) or 'Клиент не указан'
        
        # Извлекаем номер ДФА (одинаково для всех форматов)
        dfa_number = self._find_dfa_number_pandas(df)
        
        # Извлекаем филиал (одинаково для всех форматов)
        branch = self._find_branch_pandas(df)
        
        extracted_data = {
            'client_name': client_name,
            'inn': self._get_cell_with_adjustment_pandas(df, 9, 3) or '',  # D9
            'insurance_type': insurance_type,
            'insurance_period': insurance_period,
            'vehicle_info': vehicle_info,
            'dfa_number': dfa_number,
            'branch': branch,
            'has_franchise': has_franchise,
            'has_installment': has_installment,
            'has_autostart': has_autostart,
            'has_casco_ce': has_casco_ce,
            'response_deadline': response_deadline,
        }
        
        # Логируем успешное извлечение данных с информацией о формате
        logger.info(f"Successfully extracted data with pandas ({detailed_context}): client='{client_name}', insurance_type='{insurance_type}', dfa_number='{dfa_number}', branch='{branch}', has_autostart={has_autostart}, has_casco_ce={has_casco_ce} | {format_context}")
        
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

    def _get_default_data(self) -> Dict[str, Any]:
        """Возвращает данные по умолчанию с валидным типом страхования и информацией о типе заявки"""
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        format_display = "КАСКО/спецтехника" if self.application_format == 'casco_equipment' else "имущество"
        
        # Логируем использование данных по умолчанию
        logger.warning(f"Using default data for {app_type_display} with format {format_display} due to processing error")
        
        return {
            'client_name': f'Клиент не указан ({app_type_display}, {format_display})',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',  # Используем допустимое значение
            'insurance_period': '1 год',  # Используем новый формат периода
            'vehicle_info': f'Информация о предмете лизинга не указана ({app_type_display}, {format_display})',
            'dfa_number': f'Номер ДФА не указан ({app_type_display}, {format_display})',
            'branch': f'Филиал не указан ({app_type_display}, {format_display})',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': timezone.now() + timedelta(hours=3),
            'application_type': self.application_type,
            'application_format': self.application_format,
        }
    

    
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
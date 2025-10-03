"""
Утилиты для работы с Excel файлами
"""
from typing import Dict, Any, Optional
import pandas as pd
from openpyxl import load_workbook
from datetime import datetime, timedelta, date
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
    
    def __init__(self, file_path: str, application_type: str = 'legal_entity'):
        self.file_path = file_path
        
        # Валидация и fallback для типа заявки
        valid_types = ['legal_entity', 'individual_entrepreneur']
        if application_type not in valid_types:
            logger.warning(f"Invalid application_type '{application_type}' provided to ExcelReader, falling back to 'legal_entity'")
            application_type = 'legal_entity'
        
        self.application_type = application_type
        
        # Логируем выбранный тип заявки при начале обработки
        app_type_display = "заявка от ИП" if application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        logger.info(f"Initializing ExcelReader with application_type: {application_type} ({app_type_display}) for file: {file_path}")
        
        # Инициализируем счетчик примененных смещений для диагностики
        self._row_adjustments_applied = 0
    
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
        if self.application_type == 'individual_entrepreneur' and row_number > 8:
            adjusted_row = row_number + 1
            self._row_adjustments_applied += 1
            logger.debug(f"Row adjustment applied: {row_number} -> {adjusted_row} (IP application, total adjustments: {self._row_adjustments_applied})")
            return adjusted_row
        else:
            logger.debug(f"No row adjustment: {row_number} (legal entity or row <= 8)")
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
        try:
            adjusted_row = self._get_adjusted_row(row)
            cell_address = f"{column}{adjusted_row}"
            value = self._get_cell_value(sheet, cell_address)
            
            # Логируем для диагностики только если применено смещение
            if self.application_type == 'individual_entrepreneur' and row > 8:
                logger.debug(f"Cell {column}{row} -> {cell_address} (IP adjustment), value: {value}")
            
            return value
        except Exception as e:
            app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
            logger.error(f"Error reading cell {column}{row} for {app_type_display} (application_type: {self.application_type}): {str(e)}")
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
        try:
            adjusted_row = self._get_adjusted_row(row)
            # Преобразуем в 0-based индекс для pandas
            pandas_row_index = adjusted_row - 1
            value = self._safe_get_cell(df, pandas_row_index, col)
            
            # Логируем для диагностики только если применено смещение
            if self.application_type == 'individual_entrepreneur' and row > 8:
                logger.debug(f"Cell row {row} col {col} -> row {adjusted_row} col {col} (IP adjustment), value: {value}")
            
            return value
        except Exception as e:
            app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
            logger.error(f"Error reading cell row {row} col {col} for {app_type_display} (application_type: {self.application_type}): {str(e)}")
            return None
        
    def read_insurance_request(self) -> Dict[str, Any]:
        """
        Читает данные страховой заявки из Excel файла с улучшенной обработкой ошибок
        Возвращает словарь с извлеченными данными
        """
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        
        try:
            logger.info(f"Starting to read Excel file {self.file_path} as {app_type_display}")
            
            # Пробуем сначала с openpyxl для .xlsx файлов
            try:
                workbook = load_workbook(self.file_path, data_only=True)
                sheet = workbook.active
                logger.debug(f"Successfully loaded workbook with openpyxl for {app_type_display}")
                data = self._extract_data_openpyxl(sheet)
            except Exception as openpyxl_error:
                logger.debug(f"openpyxl failed for {app_type_display}, trying pandas: {str(openpyxl_error)}")
                # Если не получилось, пробуем с pandas для .xls файлов
                try:
                    df = pd.read_excel(self.file_path, sheet_name=0, header=None)
                    logger.debug(f"Successfully loaded workbook with pandas for {app_type_display}")
                    data = self._extract_data_pandas(df)
                except Exception as pandas_error:
                    logger.error(f"Both openpyxl and pandas failed for {app_type_display}. openpyxl: {str(openpyxl_error)}, pandas: {str(pandas_error)}")
                    raise Exception(f"Не удалось прочитать файл как {app_type_display}. Проверьте формат файла и целостность данных.")
            
            # Логируем информацию о примененных смещениях строк
            if self.application_type == 'individual_entrepreneur':
                logger.info(f"Successfully read data from {self.file_path} as {app_type_display}. Applied {self._row_adjustments_applied} row adjustments.")
            else:
                logger.info(f"Successfully read data from {self.file_path} as {app_type_display}. No row adjustments needed.")
            
            return data
            
        except Exception as e:
            error_msg = f"Ошибка чтения Excel файла {self.file_path} как {app_type_display} (application_type: {self.application_type}): {str(e)}"
            logger.error(error_msg)
            
            # Возвращаем данные по умолчанию с информацией об ошибке
            default_data = self._get_default_data()
            default_data['error_info'] = {
                'application_type': self.application_type,
                'error_message': str(e),
                'fallback_used': True,
                'row_adjustments_applied': getattr(self, '_row_adjustments_applied', 0)
            }
            return default_data
    
    def _extract_data_openpyxl(self, sheet) -> Dict[str, Any]:
        """Извлекает данные используя openpyxl (для .xlsx файлов)"""
        # Определяем тип страхования
        insurance_type = self._determine_insurance_type_openpyxl(sheet)
        
        # Определяем период страхования по новой логике N17/N18
        insurance_period = self._determine_insurance_period_openpyxl(sheet)
        
        # Для обратной совместимости устанавливаем даты как None
        # так как теперь используется текстовое описание периода
        insurance_start_date = None
        insurance_end_date = None
        
        # Определяем срок ответа (текущее время + 3 часа)
        response_deadline = timezone.now() + timedelta(hours=3)
        
        # Определяем наличие франшизы (если D29 не пустая, то франшизы НЕТ)
        d29_value = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 29)
        has_franchise = not bool(d29_value and str(d29_value).strip())
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ)
        has_installment = not bool(self._get_cell_with_adjustment_openpyxl(sheet, 'F', 34))
        
        # Определяем автозапуск (если M24 = "нет", то автозапуска нет)
        autostart_value = self._get_cell_with_adjustment_openpyxl(sheet, 'M', 24)
        has_autostart = bool(autostart_value) and str(autostart_value).lower().strip() != 'нет'
        
        # Определяем КАСКО кат. C/E на основе строки 45
        has_casco_ce = self._determine_casco_ce_openpyxl(sheet)
        
        # Извлекаем название клиента из D7
        client_name = self._get_cell_with_adjustment_openpyxl(sheet, 'D', 7) or 'Клиент не указан'
        
        # Извлекаем информацию о предмете лизинга
        vehicle_info = self._find_leasing_object_info_openpyxl(sheet)
        
        # Извлекаем номер ДФА
        dfa_number = self._find_dfa_number_openpyxl(sheet)
        
        # Извлекаем филиал
        branch = self._find_branch_openpyxl(sheet)
        
        return {
            'client_name': client_name,
            'inn': self._get_cell_with_adjustment_openpyxl(sheet, 'D', 9) or '',
            'insurance_type': insurance_type,
            'insurance_period': insurance_period,
            'insurance_start_date': insurance_start_date,
            'insurance_end_date': insurance_end_date,
            'vehicle_info': vehicle_info,
            'dfa_number': dfa_number,
            'branch': branch,
            'has_franchise': has_franchise,
            'has_installment': has_installment,
            'has_autostart': has_autostart,
            'has_casco_ce': has_casco_ce,
            'response_deadline': response_deadline,
        }
    
    def _extract_data_pandas(self, df) -> Dict[str, Any]:
        """Извлекает данные используя pandas (для .xls файлов)"""
        # Определяем тип страхования
        insurance_type = self._determine_insurance_type_pandas(df)
        
        # Определяем период страхования по новой логике N17/N18
        insurance_period = self._determine_insurance_period_pandas(df)
        
        # Для обратной совместимости устанавливаем даты как None
        # так как теперь используется текстовое описание периода
        insurance_start_date = None
        insurance_end_date = None
        
        # Определяем срок ответа (текущее время + 3 часа)
        response_deadline = timezone.now() + timedelta(hours=3)
        
        # Определяем наличие франшизы (если D29 не пустая, то франшизы НЕТ)
        franchise_value = self._get_cell_with_adjustment_pandas(df, 29, 3)  # D29
        has_franchise = not bool(franchise_value and str(franchise_value).strip())
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ)
        installment_value = self._get_cell_with_adjustment_pandas(df, 34, 5)  # F34
        has_installment = not bool(installment_value)
        
        # Определяем автозапуск (если M24 = "нет", то автозапуска нет)
        autostart_value = self._get_cell_with_adjustment_pandas(df, 24, 12)  # M24
        has_autostart = bool(autostart_value) and str(autostart_value).lower().strip() != 'нет'
        
        # Определяем КАСКО кат. C/E на основе строки 45
        has_casco_ce = self._determine_casco_ce_pandas(df)
        
        # Извлекаем название клиента из D7 (индекс 6, 3)
        client_name = self._get_cell_with_adjustment_pandas(df, 7, 3) or 'Клиент не указан'
        
        # Извлекаем информацию о предмете лизинга
        vehicle_info = self._find_leasing_object_info_pandas(df)
        
        # Извлекаем номер ДФА
        dfa_number = self._find_dfa_number_pandas(df)
        
        # Извлекаем филиал
        branch = self._find_branch_pandas(df)
        
        return {
            'client_name': client_name,
            'inn': self._get_cell_with_adjustment_pandas(df, 9, 3) or '',  # D9
            'insurance_type': insurance_type,
            'insurance_period': insurance_period,
            'insurance_start_date': insurance_start_date,
            'insurance_end_date': insurance_end_date,
            'vehicle_info': vehicle_info,
            'dfa_number': dfa_number,
            'branch': branch,
            'has_franchise': has_franchise,
            'has_installment': has_installment,
            'has_autostart': has_autostart,
            'has_casco_ce': has_casco_ce,
            'response_deadline': response_deadline,
        }
    
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
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        
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
                logger.warning(f"Invalid insurance type '{insurance_type}' for {app_type_display} (application_type: {self.application_type}), defaulting to 'другое'")
                insurance_type = 'другое'
            
            logger.info(f"Determined insurance type '{insurance_type}' for {app_type_display} (application_type: {self.application_type}) (D21: {d21_value}, D22: {d22_value})")
            return insurance_type
            
        except Exception as e:
            logger.error(f"Error determining insurance type for {app_type_display} (application_type: {self.application_type}): {str(e)}")
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
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        
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
                logger.warning(f"Invalid insurance type '{insurance_type}' for {app_type_display} (application_type: {self.application_type}), defaulting to 'другое'")
                insurance_type = 'другое'
            
            logger.info(f"Determined insurance type '{insurance_type}' for {app_type_display} (application_type: {self.application_type}) (D21: {d21_value}, D22: {d22_value})")
            return insurance_type
            
        except Exception as e:
            logger.error(f"Error determining insurance type for {app_type_display} (application_type: {self.application_type}): {str(e)}")
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
                    logger.debug(f"Found CASCO C/E indicator in cell {column}{adjusted_row}: {value}")
                    return True
            
            logger.debug("No CASCO C/E indicators found in row 45")
            return False
            
        except Exception as e:
            logger.warning(f"Error determining CASCO C/E status (openpyxl) for application_type {self.application_type}: {str(e)}")
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
                    logger.debug(f"Found CASCO C/E indicator in cell row {adjusted_row}, col {col+1}: {value}")
                    return True
            
            logger.debug("No CASCO C/E indicators found in row 45")
            return False
            
        except Exception as e:
            logger.warning(f"Error determining CASCO C/E status (pandas) for application_type {self.application_type}: {str(e)}")
            return False

    def _get_default_data(self) -> Dict[str, Any]:
        """Возвращает данные по умолчанию с валидным типом страхования и информацией о типе заявки"""
        app_type_display = "заявка от ИП" if self.application_type == 'individual_entrepreneur' else "заявка от юр.лица"
        
        return {
            'client_name': f'Клиент не указан ({app_type_display})',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',  # Используем допустимое значение
            'insurance_period': '1 год',  # Используем новый формат периода
            'insurance_start_date': None,  # Теперь не используем конкретные даты
            'insurance_end_date': None,    # Теперь не используем конкретные даты
            'vehicle_info': f'Информация о предмете лизинга не указана ({app_type_display})',
            'dfa_number': f'Номер ДФА не указан ({app_type_display})',
            'branch': f'Филиал не указан ({app_type_display})',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': timezone.now() + timedelta(hours=3),
            'application_type': self.application_type,
        }
    

    
    def _parse_date(self, date_value) -> Optional[datetime.date]:
        """
        Парсит дату из различных форматов и возвращает объект date.
        Поддерживает форматы: DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY
        """
        if not date_value:
            return None
        
        # Если это уже объект datetime или date
        if isinstance(date_value, datetime):
            return date_value.date()
        elif hasattr(date_value, 'date') and callable(date_value.date):
            return date_value.date()
        
        date_str = str(date_value).strip()
        if not date_str or date_str.lower() in ['none', 'nan', '']:
            return None
        
        # Пробуем разные форматы дат
        formats = [
            '%d.%m.%Y',    # DD.MM.YYYY
            '%Y-%m-%d',    # YYYY-MM-DD
            '%d/%m/%Y',    # DD/MM/YYYY
            '%m/%d/%Y',    # MM/DD/YYYY
            '%d.%m.%y',    # DD.MM.YY
            '%d/%m/%y',    # DD/MM/YY
            '%Y/%m/%d',    # YYYY/MM/DD
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.date()
            except ValueError:
                continue
        
        # Если не удалось распарсить, логируем и возвращаем None
        logger.warning(f"Could not parse date: {date_str}")
        return None
    

    
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
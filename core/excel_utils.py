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
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        
    def read_insurance_request(self) -> Dict[str, Any]:
        """
        Читает данные страховой заявки из Excel файла
        Возвращает словарь с извлеченными данными
        """
        try:
            # Пробуем сначала с openpyxl для .xlsx файлов
            try:
                workbook = load_workbook(self.file_path, data_only=True)
                sheet = workbook.active
                data = self._extract_data_openpyxl(sheet)
            except Exception:
                # Если не получилось, пробуем с pandas для .xls файлов
                df = pd.read_excel(self.file_path, sheet_name=0, header=None)
                data = self._extract_data_pandas(df)
            
            logger.info(f"Successfully read data from {self.file_path}")
            return data
            
        except Exception as e:
            logger.error(f"Error reading Excel file {self.file_path}: {str(e)}")
            # Возвращаем данные по умолчанию, чтобы не ломать процесс
            return self._get_default_data()
    
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
        d29_value = self._get_cell_value(sheet, 'D29')
        has_franchise = not bool(d29_value and str(d29_value).strip())
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ)
        has_installment = not bool(self._get_cell_value(sheet, 'F34'))
        
        # Определяем автозапуск (если M24 = "нет", то автозапуска нет)
        autostart_value = self._get_cell_value(sheet, 'M24')
        has_autostart = bool(autostart_value) and str(autostart_value).lower().strip() != 'нет'
        
        # Определяем КАСКО кат. C/E на основе строки 45
        has_casco_ce = self._determine_casco_ce_openpyxl(sheet)
        
        # Извлекаем название клиента из D7
        client_name = self._get_cell_value(sheet, 'D7') or 'Клиент не указан'
        
        # Извлекаем информацию о предмете лизинга
        vehicle_info = self._find_leasing_object_info_openpyxl(sheet)
        
        # Извлекаем номер ДФА
        dfa_number = self._find_dfa_number_openpyxl(sheet)
        
        # Извлекаем филиал
        branch = self._find_branch_openpyxl(sheet)
        
        return {
            'client_name': client_name,
            'inn': self._get_cell_value(sheet, 'D9') or '',
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
        franchise_value = self._safe_get_cell(df, 28, 3)  # D29
        has_franchise = not bool(franchise_value and str(franchise_value).strip())
        
        # Определяем рассрочку (если F34 не пустая, то рассрочки НЕТ)
        installment_value = self._safe_get_cell(df, 33, 5)  # F34
        has_installment = not bool(installment_value)
        
        # Определяем автозапуск (если M24 = "нет", то автозапуска нет)
        autostart_value = self._safe_get_cell(df, 23, 12)  # M24
        has_autostart = bool(autostart_value) and str(autostart_value).lower().strip() != 'нет'
        
        # Определяем КАСКО кат. C/E на основе строки 45
        has_casco_ce = self._determine_casco_ce_pandas(df)
        
        # Извлекаем название клиента из D7 (индекс 6, 3)
        client_name = self._safe_get_cell(df, 6, 3) or 'Клиент не указан'
        
        # Извлекаем информацию о предмете лизинга
        vehicle_info = self._find_leasing_object_info_pandas(df)
        
        # Извлекаем номер ДФА
        dfa_number = self._find_dfa_number_pandas(df)
        
        # Извлекаем филиал
        branch = self._find_branch_pandas(df)
        
        return {
            'client_name': client_name,
            'inn': self._safe_get_cell(df, 8, 3) or '',  # D9
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
        Определяет тип страхования на основе ячеек D21, D22 и D23 (openpyxl)
        
        Логика:
        1. Если D21 содержит любое значение -> "КАСКО"
        2. Если D21 пустая, но D22 содержит значение -> "страхование спецтехники"
        3. Если D21 и D22 пустые, но D23 содержит значение -> "страхование имущества"
        4. Если все ячейки пустые -> "другое"
        
        Возвращает только допустимые значения согласно INSURANCE_TYPE_CHOICES
        """
        d21_value = self._get_cell_value(sheet, 'D21')
        d22_value = self._get_cell_value(sheet, 'D22')
        d23_value = self._get_cell_value(sheet, 'D23')
        
        # Проверяем, что значение не пустое (не None и не пустая строка)
        d21_has_value = d21_value is not None and str(d21_value).strip() != ''
        d22_has_value = d22_value is not None and str(d22_value).strip() != ''
        d23_has_value = d23_value is not None and str(d23_value).strip() != ''
        
        if d21_has_value:
            insurance_type = 'КАСКО'
        elif d22_has_value:
            insurance_type = 'страхование спецтехники'
        elif d23_has_value:
            insurance_type = 'страхование имущества'
        else:
            insurance_type = 'другое'
        
        # Валидируем, что тип соответствует допустимым значениям
        valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
        if insurance_type not in valid_types:
            logger.warning(f"Invalid insurance type '{insurance_type}', defaulting to 'другое'")
            insurance_type = 'другое'
        
        return insurance_type
    
    def _determine_insurance_type_pandas(self, df) -> str:
        """
        Определяет тип страхования на основе ячеек D21, D22 и D23 (pandas)
        
        Логика:
        1. Если D21 содержит любое значение -> "КАСКО"
        2. Если D21 пустая, но D22 содержит значение -> "страхование спецтехники"
        3. Если D21 и D22 пустые, но D23 содержит значение -> "страхование имущества"
        4. Если все ячейки пустые -> "другое"
        
        Возвращает только допустимые значения согласно INSURANCE_TYPE_CHOICES
        """
        d21_value = self._safe_get_cell(df, 20, 3)  # D21 (индексы с 0)
        d22_value = self._safe_get_cell(df, 21, 3)  # D22
        d23_value = self._safe_get_cell(df, 22, 3)  # D23
        
        # Проверяем, что значение не пустое (не None и не пустая строка)
        d21_has_value = d21_value is not None and str(d21_value).strip() != ''
        d22_has_value = d22_value is not None and str(d22_value).strip() != ''
        d23_has_value = d23_value is not None and str(d23_value).strip() != ''
        
        if d21_has_value:
            insurance_type = 'КАСКО'
        elif d22_has_value:
            insurance_type = 'страхование спецтехники'
        elif d23_has_value:
            insurance_type = 'страхование имущества'
        else:
            insurance_type = 'другое'
        
        # Валидируем, что тип соответствует допустимым значениям
        valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
        if insurance_type not in valid_types:
            logger.warning(f"Invalid insurance type '{insurance_type}', defaulting to 'другое'")
            insurance_type = 'другое'
        
        return insurance_type

    def _determine_insurance_period_openpyxl(self, sheet) -> str:
        """
        Определяет период страхования на основе ячеек N17 и N18 (openpyxl)
        
        Логика:
        1. Если N17 содержит любое значение -> "1 год"
        2. Если N17 пустая, но N18 содержит значение -> "на весь срок лизинга"
        3. Если обе ячейки пустые -> пустая строка
        """
        n17_value = self._get_cell_value(sheet, 'N17')
        n18_value = self._get_cell_value(sheet, 'N18')
        
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
        n17_value = self._safe_get_cell(df, 16, 13)  # N17 (индексы с 0)
        n18_value = self._safe_get_cell(df, 17, 13)  # N18
        
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
            # Ячейки для проверки в строке 45
            cells_to_check = ['C45', 'D45', 'E45', 'F45', 'G45', 'H45', 'I45']
            
            for cell_address in cells_to_check:
                value = self._get_cell_value(sheet, cell_address)
                # Проверяем, что значение не пустое (не None и не пустая строка)
                if value is not None and str(value).strip() != '':
                    logger.debug(f"Found CASCO C/E indicator in cell {cell_address}: {value}")
                    return True
            
            logger.debug("No CASCO C/E indicators found in row 45")
            return False
            
        except Exception as e:
            logger.warning(f"Error determining CASCO C/E status (openpyxl): {str(e)}")
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
            # Ячейки для проверки в строке 45 (индекс 44): столбцы C-I (индексы 2-8)
            cells_to_check = [
                (44, 2),  # C45
                (44, 3),  # D45
                (44, 4),  # E45
                (44, 5),  # F45
                (44, 6),  # G45
                (44, 7),  # H45
                (44, 8),  # I45
            ]
            
            for row, col in cells_to_check:
                value = self._safe_get_cell(df, row, col)
                # Проверяем, что значение не пустое (не None и не пустая строка)
                if value is not None and str(value).strip() != '':
                    logger.debug(f"Found CASCO C/E indicator in cell row {row+1}, col {col+1}: {value}")
                    return True
            
            logger.debug("No CASCO C/E indicators found in row 45")
            return False
            
        except Exception as e:
            logger.warning(f"Error determining CASCO C/E status (pandas): {str(e)}")
            return False

    def _get_default_data(self) -> Dict[str, Any]:
        """Возвращает данные по умолчанию с валидным типом страхования"""
        return {
            'client_name': 'Тестовый клиент',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',  # Используем допустимое значение
            'insurance_period': '1 год',  # Используем новый формат периода
            'insurance_start_date': None,  # Теперь не используем конкретные даты
            'insurance_end_date': None,    # Теперь не используем конкретные даты
            'vehicle_info': 'Информация о предмете лизинга не указана',
            'dfa_number': 'Номер ДФА не указан',
            'branch': 'Филиал не указан',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': timezone.now() + timedelta(hours=3),
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
        # Ячейки для поиска: CDEFGHI43, CDEFGHI45, CDEFGHI47, CDEFGHI49
        vehicle_cells = [
            # Строка 43 (индекс 42): C-I (индексы 2-8)
            (42, 2), (42, 3), (42, 4), (42, 5), (42, 6), (42, 7), (42, 8),
            # Строка 45 (индекс 44): C-I (индексы 2-8)
            (44, 2), (44, 3), (44, 4), (44, 5), (44, 6), (44, 7), (44, 8),
            # Строка 47 (индекс 46): C-I (индексы 2-8)
            (46, 2), (46, 3), (46, 4), (46, 5), (46, 6), (46, 7), (46, 8),
            # Строка 49 (индекс 48): C-I (индексы 2-8)
            (48, 2), (48, 3), (48, 4), (48, 5), (48, 6), (48, 7), (48, 8),
        ]
        
        vehicle_info_parts = []
        
        for row, col in vehicle_cells:
            value = self._safe_get_cell(df, row, col)
            if value and str(value).strip():
                vehicle_info_parts.append(str(value).strip())
        
        # Объединяем найденную информацию
        if vehicle_info_parts:
            return ' '.join(vehicle_info_parts)
        else:
            return 'Информация о предмете лизинга не указана'
    
    def _find_dfa_number_pandas(self, df) -> str:
        """Извлекает номер ДФА из ячеек HIJ2"""
        # Ячейки HIJ2 (индексы: строка 1, столбцы 7,8,9)
        dfa_cells = [(1, 7), (1, 8), (1, 9)]  # H2, I2, J2
        dfa_parts = []
        
        for row, col in dfa_cells:
            value = self._safe_get_cell(df, row, col)
            if value and str(value).strip():
                dfa_parts.append(str(value).strip())
        
        return ' '.join(dfa_parts) if dfa_parts else 'Номер ДФА не указан'
    
    def _find_branch_pandas(self, df) -> str:
        """Извлекает филиал из ячеек CDEF4"""
        # Ячейки CDEF4 (индексы: строка 3, столбцы 2,3,4,5)
        branch_cells = [(3, 2), (3, 3), (3, 4), (3, 5)]  # C4, D4, E4, F4
        branch_parts = []
        
        for row, col in branch_cells:
            value = self._safe_get_cell(df, row, col)
            if value and str(value).strip():
                branch_parts.append(str(value).strip())
        
        full_branch_name = ' '.join(branch_parts) if branch_parts else 'Филиал не указан'
        
        # Применяем маппинг названий филиалов
        return map_branch_name(full_branch_name)
    
    def _find_leasing_object_info_openpyxl(self, sheet) -> str:
        """Ищет информацию о предмете лизинга в указанных ячейках (openpyxl)"""
        # Ячейки для поиска: CDEFGHI43, CDEFGHI45, CDEFGHI47, CDEFGHI49
        vehicle_cells = [
            'C43', 'D43', 'E43', 'F43', 'G43', 'H43', 'I43',
            'C45', 'D45', 'E45', 'F45', 'G45', 'H45', 'I45',
            'C47', 'D47', 'E47', 'F47', 'G47', 'H47', 'I47',
            'C49', 'D49', 'E49', 'F49', 'G49', 'H49', 'I49',
        ]
        
        vehicle_info_parts = []
        
        for cell_address in vehicle_cells:
            value = self._get_cell_value(sheet, cell_address)
            if value and str(value).strip():
                vehicle_info_parts.append(str(value).strip())
        
        # Объединяем найденную информацию
        if vehicle_info_parts:
            return ' '.join(vehicle_info_parts)
        else:
            return 'Информация о предмете лизинга не указана'
    
    def _find_dfa_number_openpyxl(self, sheet) -> str:
        """Извлекает номер ДФА из ячеек HIJ2 (openpyxl)"""
        # Ячейки HIJ2
        dfa_cells = ['H2', 'I2', 'J2']
        dfa_parts = []
        
        for cell_address in dfa_cells:
            value = self._get_cell_value(sheet, cell_address)
            if value and str(value).strip():
                dfa_parts.append(str(value).strip())
        
        return ' '.join(dfa_parts) if dfa_parts else 'Номер ДФА не указан'
    
    def _find_branch_openpyxl(self, sheet) -> str:
        """Извлекает филиал из ячеек CDEF4 (openpyxl)"""
        # Ячейки CDEF4
        branch_cells = ['C4', 'D4', 'E4', 'F4']
        branch_parts = []
        
        for cell_address in branch_cells:
            value = self._get_cell_value(sheet, cell_address)
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
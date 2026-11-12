"""Read insurer Excel responses and preserve their company data."""
import logging
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from openpyxl import load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from django.db import transaction

from ..models import InsuranceSummary, InsuranceOffer, InsurerResponse
from ..exceptions import (
    DuplicateOfferError, ExcelProcessingError, InvalidFileFormatError,
    MissingDataError, InvalidDataError, RowProcessingError,
)

logger = logging.getLogger(__name__)
CURRENCY_SUFFIX_RE = re.compile(r'(?:руб(?:лей|ля|ль)?|р|₽|rub|rur)\.?$', re.IGNORECASE)


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
        'coverage_territory': 'B3',
        'notes_first_year': 'F2',  # Объединенная ячейка FGHIJ2 для примечаний первого года
        'year_rows': {
            'start_row': MIN_YEAR_ROW,
            'end_row': MAX_YEAR_ROW,
            'columns': YEAR_COLUMNS
        }
    }
    
    # Допустимые значения рассрочки
    VALID_INSTALLMENT_VALUES = [1, 2, 3, 4, 6, 12]

    MISSING_TERRITORY_MESSAGE = (
        'Ответ СК «{company}» не загружен: не заполнена территория страхования (ячейка {cell}). '
        'Запросите у страховой компании корректное предложение с заполненной территорией '
        'страхования и территориальными ограничениями и загрузите файл снова.'
    )

    # Шаблон ответа V2: дополнительные блоки (docs/improvement_plans/insurer_response_v2.md, §6)
    SECTION_MISSING_MESSAGE = (
        'Ответ СК «{company}» не загружен: не заполнен блок «{section}»{field}. '
        'Запросите у страховой компании корректное предложение с заполненным блоком и загрузите файл снова.'
    )
    SECTION_INVALID_MESSAGE = (
        'Ответ СК «{company}» не загружен: в блоке «{section}» поле «{field}» заполнено неверно — '
        '«{value}» ({expected}). Запросите у страховой компании корректное предложение и загрузите файл снова.'
    )
    OLD_TEMPLATE_MESSAGE = (
        'Ответ СК «{company}» не загружен: файл в старом шаблоне ответа, а по этой заявке {required} '
        '«{sections}». Отправьте страховщику шаблон ответа V2 (персональный, с карточки свода) '
        'и загрузите заполненный файл.'
    )
    SUMMARY_MISMATCH_WARNING = (
        'Шаблон ответа был сформирован для свода #{expected}, а загружен в свод #{actual} — '
        'проверьте, что это ответ на нужный запрос.'
    )
    REQUEST_MISMATCH_WARNING = (
        'Шаблон ответа был сформирован для другой заявки (#{expected}), а загружен в свод по заявке '
        '{actual} — проверьте, что это ответ на нужный запрос.'
    )

    # Текст-заглушка в B2 из шаблонов разных лет (сравнение без учёта регистра)
    COMPANY_PLACEHOLDERS = {'название ск', 'выберите компанию', 'выберите компанию из списка'}
    
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
    
    def process_excel_file(self, file, summary: InsuranceSummary, user=None) -> Dict[str, Any]:
        """
        Обрабатывает Excel файл и создает предложения
        
        Args:
            file: Загруженный файл Excel
            summary: Свод предложений для связи
            user: Кто загружает — определяет строгость проверок шаблона V2 (insurer_response.v2_strict)
            
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

            # Дополнительные блоки шаблона V2 (риски РНПК, перевозка) — до записи в базу:
            # в контуре V2 пустой обязательный блок или старый шаблон отклоняют весь файл
            from .insurer_response import attach_source_file, save_response, save_upload_company_fields, v2_strict
            strict = v2_strict(user, summary.request)
            sections = self.extract_response_sections(
                workbook, summary, company_data['company_name'], strict=strict,
            )

            # Создаем предложения
            self.logger.info("Этап 4: Создание предложений в базе данных")
            with transaction.atomic():
                created_offers = self.create_offers(company_data, summary)
                if strict or sections['version'] == InsurerResponse.TEMPLATE_V2:
                    save_response(summary, company_data['company_name'], sections['values'],
                                  sections['version'], user=user)
                save_upload_company_fields(
                    summary.pk, company_data['company_name'], company_data.get('coverage_territory', ''),
                    next((y.get('notes', '') for y in company_data['years'] if y.get('notes')), ''),
                )
            attach_source_file(summary.pk, company_data['company_name'], file)

            result = {
                'success': True,
                'company_name': company_data['company_name'],
                'offers_created': len(created_offers),
                'years': [offer.insurance_year for offer in created_offers],
                'skipped_rows': processing_info.get('rows_skipped', []),
                'processed_rows': processing_info.get('rows_with_data', []),
                'company_matching_info': company_data.get('company_matching_info', {}),
                'processing_errors': processing_info.get('processing_errors', []),
                'coverage_territory': company_data.get('coverage_territory', ''),
                'template_version': sections['version'],
                'response_warnings': sections['warnings'],
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
            if raw_name_str.lower() in self.COMPANY_PLACEHOLDERS:
                # Заглушка старого шаблона: без этой проверки ушла бы в «другое» молча
                self.logger.error(f"В ячейке B2 осталась заглушка шаблона: '{raw_name_str}'")
                raise MissingDataError(message=(
                    f"Страховая компания не выбрана: в ячейке B2 осталось «{raw_name_str}». "
                    f"Выберите компанию из списка и загрузите файл снова."
                ))
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

            raw_coverage_territory = self._get_cell_value(
                worksheet,
                self.CELL_MAPPING['coverage_territory']
            )
            coverage_territory = (
                str(raw_coverage_territory).strip()
                if raw_coverage_territory is not None
                else ''
            )
            # Территория обязательна (решение владельца 2026-10-06): ответ без неё не загружается.
            # Прочерк или пробелы без букв и цифр — тоже «не заполнено».
            if not any(char.isalnum() for char in coverage_territory):
                self.logger.error(
                    f"Ответ СК '{standardized_name}': не заполнена территория страхования "
                    f"в ячейке {self.CELL_MAPPING['coverage_territory']} ('{coverage_territory}')"
                )
                raise MissingDataError(message=self.MISSING_TERRITORY_MESSAGE.format(
                    company=standardized_name, cell=self.CELL_MAPPING['coverage_territory'],
                ))
            data['coverage_territory'] = coverage_territory
            self.logger.info(
                "Найдена территория страхования, подтвержденная страховщиком: "
                f"{coverage_territory[:100]}"
            )
            
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
            
            # Извлекаем примечания для первого года из объединенной ячейки FGHIJ2
            self.logger.debug(f"Извлекаем примечания первого года из ячейки {self.CELL_MAPPING['notes_first_year']}")
            notes_first_year = self._get_cell_value(worksheet, self.CELL_MAPPING['notes_first_year'])
            if notes_first_year and str(notes_first_year).strip():
                notes_text = str(notes_first_year).strip()
                self.logger.info(f"Найдены примечания для первого года: {notes_text[:50]}...")
                # Добавляем примечания к первому году (год = 1)
                for year_data in data['years']:
                    if year_data['year'] == 1:
                        year_data['notes'] = notes_text
                        self.logger.debug(f"Примечания добавлены к году {year_data['year']}")
                        break
            else:
                self.logger.debug("Примечания для первого года не найдены или пусты")
            
            # Проверяем, что есть хотя бы один год с данными
            if not data['years']:
                self.logger.error("Не найдено ни одного года с валидными данными страхования")
                processing_errors = data.get('processing_info', {}).get('processing_errors', [])
                if processing_errors:
                    details = '; '.join(processing_errors)
                    raise MissingDataError(message=(
                        f"Не удалось обработать данные по годам страхования. {details}. "
                        f"Пожалуйста, проверьте корректность значений согласно шаблону."
                    ))
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
    
    @staticmethod
    def _defined_name_value(workbook, name: str):
        """Значение именованной ячейки книги; None, если имени нет."""
        defined = workbook.defined_names.get(name)
        if defined is None:
            return None
        for sheet, ref in defined.destinations:
            if sheet in workbook.sheetnames:
                return workbook[sheet][ref.replace('$', '')].value
        return None

    def extract_response_sections(self, workbook, summary: InsuranceSummary, company_name: str,
                                  strict: bool) -> Dict[str, Any]:
        """
        Дополнительные блоки ответа (риски РНПК, перевозка): версия шаблона, значения, предупреждения.

        Читаются только блоки, нужные по заявке свода (а не по тому, что заполнил страховщик).
        strict (контур V2): пустой обязательный блок, неверное значение или старый шаблон при
        обязательных блоках — MissingDataError; иначе такие значения молча пропускаются.
        """
        from ..response_sections import CHOICE, MONEY, required_sections
        from ..response_template import META_SHEET, TEMPLATE_VERSION_V2

        result = {'version': InsurerResponse.TEMPLATE_V1, 'values': {}, 'warnings': []}
        meta = workbook[META_SHEET] if META_SHEET in workbook.sheetnames else None
        if meta is not None and meta['B1'].value == TEMPLATE_VERSION_V2:
            result['version'] = InsurerResponse.TEMPLATE_V2
        required = required_sections(summary.request)

        if result['version'] != InsurerResponse.TEMPLATE_V2:
            if strict and required:
                raise MissingDataError(message=self.OLD_TEMPLATE_MESSAGE.format(
                    company=company_name, sections='», «'.join(section.title for section in required),
                    required='обязательны блоки' if len(required) > 1 else 'обязателен блок',
                ))
            return result

        # Шаблон со страницы заявки сверяется по заявке, ранние шаблоны со свода — по своду
        expected_request = meta['B3'].value if meta['A3'].value == 'request_id' else None
        expected_summary = meta['B2'].value
        warning = None
        if expected_request not in (None, ''):
            if str(expected_request) != str(summary.request_id):
                warning = self.REQUEST_MISMATCH_WARNING.format(
                    expected=expected_request, actual=summary.request.dfa_number or f'#{summary.request_id}')
        elif expected_summary not in (None, '') and str(expected_summary) != str(summary.pk):
            warning = self.SUMMARY_MISMATCH_WARNING.format(expected=expected_summary, actual=summary.pk)
        if warning:
            self.logger.warning(f"Ответ СК '{company_name}': {warning}")
            result['warnings'].append(warning)

        for section in required:
            if section.key == 'equipment_assembly':
                from ..equipment_assembly import EquipmentAssemblyError, clean_values
                raw_values = {fld.name: self._defined_name_value(workbook, fld.cell_name) for fld in section.fields}
                rate_name = workbook.defined_names.get('resp_equipment_assembly_rate')
                percent_rate = False
                if rate_name is not None:
                    for sheet, ref in rate_name.destinations:
                        if sheet in workbook.sheetnames:
                            percent_rate = '%' in workbook[sheet][ref.replace('$', '')].number_format
                            break
                try:
                    result['values'].update(clean_values(raw_values, required=strict, percent_rate=percent_rate))
                except EquipmentAssemblyError as error:
                    # Пустой старый ответ допустим вне strict. Заполненный противоречивый блок — никогда.
                    raise MissingDataError(message=f'Ответ СК «{company_name}»: {error}') from error
                continue
            for fld in section.fields:
                raw = self._defined_name_value(workbook, fld.cell_name)
                text = '' if raw is None else str(raw).strip()
                if not any(char.isalnum() for char in text):  # пусто, пробелы или «—»
                    if fld.required and strict:
                        raise MissingDataError(message=self.SECTION_MISSING_MESSAGE.format(
                            company=company_name, section=section.title,
                            field='' if fld.label == section.title else f' (поле «{fld.label}»)',
                        ))
                    continue
                if fld.kind == CHOICE:
                    value = fld.match_choice(text)
                    expected = 'ожидается одно из: ' + ', '.join(fld.choice_labels)
                elif fld.kind == MONEY:
                    try:
                        value = Decimal(self._normalize_decimal_input(raw)).quantize(Decimal('0.01'))
                        value = value if value >= 0 else None
                    except (InvalidOperation, ValueError, TypeError):
                        value = None
                    expected = 'ожидается сумма в рублях'
                else:
                    value = ILLEGAL_CHARACTERS_RE.sub('', text)
                    expected = ''
                if value is None:
                    if strict:
                        raise MissingDataError(message=self.SECTION_INVALID_MESSAGE.format(
                            company=company_name, section=section.title, field=fld.label,
                            value=text[:100], expected=expected,
                        ))
                    self.logger.warning(
                        f"Ответ СК '{company_name}': значение «{text[:100]}» в поле «{fld.label}» пропущено"
                    )
                    continue
                result['values'][fld.name] = value

        self.logger.info(
            f"Блоки ответа V{result['version']} для '{company_name}': "
            f"нужны {[section.key for section in required]}, прочитано {sorted(result['values'])}"
        )
        return result

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

            # Страховщики часто оставляют номер года, но ставят нули (или ничего)
            # в сумме и премии для лет, которые не предлагают. Такая строка —
            # «год не предложен», а не ошибка: пропускаем её, не роняя файл.
            raw_insurance_sum = self._get_cell_value(worksheet, year_mapping['insurance_sum'])
            raw_premium = self._get_cell_value(worksheet, year_mapping['premium'])
            if self._is_empty_or_zero(raw_insurance_sum) and self._is_empty_or_zero(raw_premium):
                self.logger.info(
                    f"Строка {row_number}: страховая сумма и премия не заполнены или равны 0 — "
                    f"год не предложен страховщиком, строка пропущена"
                )
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

            # Ноль только в одном из полей — это ошибка заполнения, а не «год не предложен»
            for field_key, field_name in (('insurance_sum', 'страховая сумма'), ('premium', 'премия')):
                if year_data[field_key] == 0:
                    raise RowProcessingError(
                        row_number,
                        field_name,
                        'нулевое значение при заполненном соседнем поле; '
                        'если год не предлагается, оставьте пустыми или нулевыми и сумму, и премию',
                        year_mapping[field_key]
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
    
    def _is_empty_or_zero(self, value) -> bool:
        """Пустая ячейка или число, равное нулю (включая строки вида "0,00")."""
        if value is None or str(value).strip() == '':
            return True
        try:
            return Decimal(self._normalize_decimal_input(value)) == 0
        except (InvalidOperation, ValueError, TypeError):
            return False

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
            value = cell.value
            return value
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

    def _sanitize_numeric_string(self, value: Any) -> str:
        """
        Удаляет из числовой строки невидимые управляющие/форматирующие символы и пробелы.

        Включая кейсы вроде U+202C (POP DIRECTIONAL FORMATTING), которые визуально не заметны,
        но ломают Decimal().
        """
        value_str = str(value).strip()
        cleaned_chars = []
        for char in value_str:
            category = unicodedata.category(char)
            if char.isspace() or category in {'Cf', 'Cc'}:
                continue
            cleaned_chars.append(char)
        return ''.join(cleaned_chars)

    def _normalize_decimal_separator_for_parser(self, value_str: str) -> str:
        """
        Нормализует десятичный разделитель для парсинга в Decimal.

        Поддерживаемые примеры:
        - "382171,80" -> "382171.80"
        - "382171.80" -> "382171.80"
        - "1.234,56" -> "1234.56"
        - "1,234.56" -> "1234.56"
        - "4 342 000 руб." / "138 758,17 ₽" -> "4342000" / "138758.17"
        - "247499.99999999996" -> "247499.99999999996" (float, вставленный как текст)
        """
        normalized = CURRENCY_SUFFIX_RE.sub('', self._sanitize_numeric_string(value_str))

        if ',' not in normalized and '.' not in normalized:
            return normalized

        # Если есть и точка, и запятая — последняя встреченная считается десятичным разделителем
        if ',' in normalized and '.' in normalized:
            comma_pos = normalized.rfind(',')
            dot_pos = normalized.rfind('.')
            if comma_pos > dot_pos:
                # 1.234,56 -> 1234.56
                return normalized.replace('.', '').replace(',', '.')
            # 1,234.56 -> 1234.56
            return normalized.replace(',', '')

        # Только запятая
        if ',' in normalized:
            comma_pos = normalized.rfind(',')
            fractional = normalized[comma_pos + 1:]

            # 1-2 знака после запятой считаем десятичной частью; больше трёх —
            # тоже (разделитель тысяч отделяет ровно три цифры)
            if fractional.isdigit() and normalized.count(',') == 1 and len(fractional) != 3:
                return normalized.replace(',', '.')

            # Иначе считаем запятую разделителем тысяч
            return normalized.replace(',', '')

        # Только точка
        if '.' in normalized:
            dot_pos = normalized.rfind('.')
            fractional = normalized[dot_pos + 1:]

            # 1-2 знака после точки считаем десятичной частью; больше трёх —
            # тоже (разделитель тысяч отделяет ровно три цифры)
            if fractional.isdigit() and normalized.count('.') == 1 and len(fractional) != 3:
                return normalized

            # Иначе считаем точку разделителем тысяч
            return normalized.replace('.', '')

        return normalized

    def _normalize_decimal_input(self, value: Any) -> str:
        """Подготовка входного значения к безопасному Decimal-парсингу."""
        # Числовые типы (openpyxl возвращает float/int для числовых ячеек)
        # уже однозначны: разделителей тысяч в них быть не может, а точка —
        # всегда десятичная. Прогонять их через эвристику нельзя — длинный
        # дробный хвост float (например, 24749.999999999996) ошибочно
        # принимается за разделитель тысяч.
        if isinstance(value, bool):
            return str(int(value))
        if isinstance(value, (int, Decimal)):
            return str(value)
        if isinstance(value, float):
            return repr(value)
        return self._normalize_decimal_separator_for_parser(str(value))
    
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
            
            # Нормализуем и преобразуем в Decimal (поддерживаем и "," и ".")
            decimal_value = Decimal(self._normalize_decimal_input(value))
            
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
            
            # Нормализуем и преобразуем в Decimal (поддерживаем и "," и ".")
            decimal_value = Decimal(self._normalize_decimal_input(value))
            
            # Ограничиваем точность до 15 цифр (13 до запятой + 2 после)
            # Это соответствует ограничению модели max_digits=15, decimal_places=2
            decimal_value = decimal_value.quantize(Decimal('0.01'))
            
            # Проверяем, что значение положительное (кроме франшизы, которая может быть 0)
            if decimal_value < 0:
                raise RowProcessingError(row_number, field_name, f'отрицательное значение {value}, ожидается положительное число', cell_address)
            
            # Проверяем, что значение не превышает максимально допустимое для модели
            max_value = Decimal('9999999999999.99')  # 13 цифр до запятой + 2 после = 15 цифр всего
            if decimal_value > max_value:
                raise RowProcessingError(row_number, field_name, f'значение {decimal_value} слишком большое, максимум {max_value}', cell_address)
            
            return decimal_value
            
        except (InvalidOperation, ValueError, TypeError):
            # Специальная обработка для франшизы: текстовые значения интерпретируются как 0
            if 'франшиз' in field_name.lower():
                self.logger.info(f"Строка {row_number}: текстовое значение '{value}' в поле '{field_name}' интерпретировано как 0")
                return Decimal('0')
            
            raise RowProcessingError(row_number, field_name, f'некорректное значение "{value}", ожидается числовое значение', cell_address)
    
    def _to_installment_int(self, value) -> int:
        """Число платежей: принимает 4, 4.0, «4,0»; дробное значение — ValueError."""
        try:
            number = Decimal(self._normalize_decimal_input(value))
        except InvalidOperation as exc:
            raise ValueError(value) from exc
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError(value)
        return int(number)

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
            
            installment = self._to_installment_int(value)
            
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
            
            installment = self._to_installment_int(value)
            
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
        # Округляем Decimal значения до 2 знаков после запятой для соответствия модели
        # Сравнение с None, а не по истинности: Decimal('0.00') ложен и превращался в NULL
        insurance_sum = year_data['insurance_sum'].quantize(Decimal('0.01')) if year_data['insurance_sum'] is not None else None
        franchise = year_data['franchise'].quantize(Decimal('0.01')) if year_data['franchise'] else Decimal('0.00')
        premium = year_data['premium'].quantize(Decimal('0.01')) if year_data['premium'] is not None else None
        
        offer_data = {
            'summary': summary,
            'company_name': company_data['company_name'],
            'insurance_year': year_data['year'],
            'insurance_sum': insurance_sum,
            'franchise_1': franchise,
            'premium_with_franchise_1': premium,
            'installment_variant_1': installment_available,
            'payments_per_year_variant_1': payments_per_year,
            # Для обратной совместимости
            'installment_available': installment_available,
            'payments_per_year': payments_per_year,
            'is_valid': True
        }
        
        # Добавляем дополнительные поля, если они присутствуют
        if year_data.get('premium_2') is not None:
            premium_2 = year_data['premium_2'].quantize(Decimal('0.01')) if year_data['premium_2'] else None
            offer_data['premium_with_franchise_2'] = premium_2
        
        if year_data.get('franchise_2') is not None:
            franchise_2 = year_data['franchise_2'].quantize(Decimal('0.01')) if year_data['franchise_2'] else None
            offer_data['franchise_2'] = franchise_2
        
        if year_data.get('installment_2') is not None:
            offer_data['installment_variant_2'] = installment_2_available
            offer_data['payments_per_year_variant_2'] = payments_per_year_2
        
        # Территория и примечания — одни на СК в своде, пишутся в «Ответ СК» (process_excel_file)
        offer = InsuranceOffer.objects.create(**offer_data)
        
        return offer


def get_excel_response_processor() -> ExcelResponseProcessor:
    """
    Фабричная функция для создания экземпляра ExcelResponseProcessor
    
    Returns:
        ExcelResponseProcessor: Экземпляр процессора
    """
    return ExcelResponseProcessor()

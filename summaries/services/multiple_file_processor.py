"""
Сервис для обработки множественных файлов страховых предложений
"""

import logging
import threading
from typing import List, Dict, Any, Optional
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction, OperationalError

from ..models import InsuranceSummary, InsuranceOffer
from ..exceptions import ExcelProcessingError, DuplicateOfferError, InvalidFileFormatError
from .excel_services import get_excel_response_processor


class MultipleFileProcessor:
    """Сервис для координации обработки нескольких файлов"""
    
    # Ограничения для безопасности
    MAX_FILES_PER_UPLOAD = 10
    MAX_FILE_SIZE_MB = 1
    MAX_TOTAL_SIZE_MB = 10
    ALLOWED_EXTENSIONS = ['.xlsx']
    
    # Блокировка для предотвращения параллельной записи в БД
    _db_lock = threading.Lock()
    
    def __init__(self, summary: InsuranceSummary):
        """
        Инициализация процессора
        
        Args:
            summary: Свод предложений для обработки файлов
        """
        self.summary = summary
        self.excel_processor = get_excel_response_processor()
        self.results = []
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        
        # Логирование инициализации с контекстной информацией
        self.logger.info(
            f"PROCESSOR_INIT - Инициализирован MultipleFileProcessor | "
            f"summary_id={summary.id} | summary_status={summary.status} | "
            f"summary_name={getattr(summary, 'name', 'N/A')}"
        )
    
    def process_files(self, files: List[UploadedFile]) -> List[Dict[str, Any]]:
        """
        Обработка списка файлов
        
        Args:
            files: Список загруженных файлов
            
        Returns:
            Список результатов обработки каждого файла
            
        Raises:
            ExcelProcessingError: При критических ошибках валидации
        """
        import time
        
        # Используем блокировку для всего процесса обработки файлов
        with self._db_lock:
            batch_start_time = time.time()
            total_size_mb = sum(file.size for file in files) / (1024 * 1024)
        
            # Логирование начала обработки пакета с детальной информацией
            self.logger.info(
                f"BATCH_START - Начало обработки пакета файлов | "
                f"summary_id={self.summary.id} | files_count={len(files)} | "
                f"total_size_mb={total_size_mb:.2f} | "
                f"files=[{', '.join(f.name for f in files)}]"
            )
            
            # Валидация общих ограничений
            try:
                self._validate_files_batch(files)
                self.logger.debug(f"BATCH_VALIDATION_SUCCESS - Валидация пакета файлов успешна")
            except ExcelProcessingError as e:
                self.logger.error(f"BATCH_VALIDATION_ERROR - Ошибка валидации пакета: {str(e)}")
                raise
            
            results = []
            successful_files = 0
            failed_files = 0
            total_offers_created = 0
            
            for index, file in enumerate(files):
                file_start_time = time.time()
                
                self.logger.info(
                    f"FILE_START - Начало обработки файла | "
                    f"file_index={index + 1}/{len(files)} | filename={file.name} | "
                    f"size_mb={file.size / (1024 * 1024):.2f}"
                )
                
                try:
                    result = self.process_single_file(file, index)
                    results.append(result)
                    
                    file_duration = time.time() - file_start_time
                    
                    if result['success']:
                        successful_files += 1
                        offers_created = result.get('offers_created', 0)
                        total_offers_created += offers_created
                        
                        self.logger.info(
                            f"FILE_SUCCESS - Файл обработан успешно | "
                            f"filename={file.name} | company={result.get('company_name', 'N/A')} | "
                            f"offers_created={offers_created} | duration={file_duration:.2f}s"
                        )
                    else:
                        failed_files += 1
                        error_type = result.get('error_type', 'unknown')
                        
                        self.logger.warning(
                            f"FILE_ERROR - Ошибка обработки файла | "
                            f"filename={file.name} | error_type={error_type} | "
                            f"error_message={result.get('error_message', 'N/A')} | "
                            f"duration={file_duration:.2f}s"
                        )
                        
                except Exception as e:
                    failed_files += 1
                    file_duration = time.time() - file_start_time
                    
                    # Обработка неожиданных ошибок для отдельного файла
                    error_result = self._create_file_result(
                        file_name=file.name,
                        file_index=index,
                        success=False,
                        error_message=f"Неожиданная ошибка: {str(e)}",
                        error_type="processing_error"
                    )
                    results.append(error_result)
                    
                    self.logger.error(
                        f"FILE_EXCEPTION - Неожиданная ошибка при обработке файла | "
                        f"filename={file.name} | error={str(e)} | duration={file_duration:.2f}s",
                        exc_info=True
                    )
            
            batch_duration = time.time() - batch_start_time
            success_rate = (successful_files / len(files)) * 100 if files else 0
            
            # Логирование завершения обработки пакета с итоговой статистикой
            self.logger.info(
                f"BATCH_END - Обработка пакета завершена | "
                f"summary_id={self.summary.id} | total_files={len(files)} | "
                f"successful={successful_files} | failed={failed_files} | "
                f"success_rate={success_rate:.1f}% | total_offers_created={total_offers_created} | "
                f"duration={batch_duration:.2f}s | avg_file_time={batch_duration/len(files):.2f}s"
            )
            
            return results
    
    def process_single_file(self, file: UploadedFile, index: int) -> Dict[str, Any]:
        """
        Обработка одного файла
        
        Args:
            file: Загруженный файл
            index: Индекс файла в списке
            
        Returns:
            Результат обработки файла
        """
        import time
        
        start_time = time.time()
        
        self.logger.debug(
            f"SINGLE_FILE_START - Начало обработки отдельного файла | "
            f"filename={file.name} | file_index={index} | size_bytes={file.size}"
        )
        
        try:
            # Валидация отдельного файла
            validation_error = self.validate_file(file)
            if validation_error:
                self.logger.warning(
                    f"SINGLE_FILE_VALIDATION_ERROR - Ошибка валидации файла | "
                    f"filename={file.name} | error={validation_error}"
                )
                return self._create_file_result(
                    file_name=file.name,
                    file_index=index,
                    success=False,
                    error_message=validation_error,
                    error_type="validation_error"
                )
            
            # Проверка дубликатов перед обработкой
            duplicate_check_result = self._check_for_duplicates_before_processing(file)
            if duplicate_check_result:
                self.logger.warning(
                    f"SINGLE_FILE_DUPLICATE_ERROR - Обнаружены дубликаты | "
                    f"filename={file.name} | conflicts={duplicate_check_result['conflicts']}"
                )
                return self._create_file_result(
                    file_name=file.name,
                    file_index=index,
                    success=False,
                    error_message=duplicate_check_result['error_message'],
                    error_type="duplicate_offer",
                    duplicate_conflicts=duplicate_check_result['conflicts']
                )
            
            # Обработка файла через существующий процессор с блокировкой БД
            self.logger.debug(f"SINGLE_FILE_PROCESSING - Передача файла в ExcelResponseProcessor | filename={file.name}")
            
            # Используем блокировку для предотвращения параллельных записей в БД
            processing_result = self._process_file_with_retry(file)
            
            processing_time = time.time() - start_time
            
            self.logger.info(
                f"SINGLE_FILE_SUCCESS - Файл успешно обработан | "
                f"filename={file.name} | company={processing_result['company_name']} | "
                f"offers_created={processing_result['offers_created']} | "
                f"years={processing_result['years']} | processing_time={processing_time:.2f}s"
            )
            
            # Формирование успешного результата
            return self._create_file_result(
                file_name=file.name,
                file_index=index,
                success=True,
                company_name=processing_result['company_name'],
                offers_created=processing_result['offers_created'],
                years_processed=processing_result['years'],
                processed_rows=processing_result.get('processed_rows', []),
                skipped_rows=processing_result.get('skipped_rows', [])
            )
            
        except DuplicateOfferError as e:
            # Обработка ошибок дубликатов
            processing_time = time.time() - start_time
            conflict_message = f"{e.company_name} - {e.insurance_year} год"
            detailed_error_message = (
                f"Предложение от компании '{e.company_name}' для {e.insurance_year} года "
                f"уже существует в данном своде. Файл отклонен."
            )
            
            self.logger.warning(
                f"SINGLE_FILE_DUPLICATE_EXCEPTION - Исключение дубликата при обработке | "
                f"filename={file.name} | company={e.company_name} | year={e.insurance_year} | "
                f"processing_time={processing_time:.2f}s"
            )
            
            return self._create_file_result(
                file_name=file.name,
                file_index=index,
                success=False,
                error_message=detailed_error_message,
                error_type="duplicate_offer",
                duplicate_conflicts=[conflict_message]
            )
            
        except (ExcelProcessingError, InvalidFileFormatError) as e:
            # Обработка известных ошибок обработки
            processing_time = time.time() - start_time
            
            self.logger.error(
                f"SINGLE_FILE_PROCESSING_ERROR - Ошибка обработки файла | "
                f"filename={file.name} | error_type={type(e).__name__} | "
                f"error_message={str(e)} | processing_time={processing_time:.2f}s"
            )
            
            return self._create_file_result(
                file_name=file.name,
                file_index=index,
                success=False,
                error_message=str(e),
                error_type="processing_error"
            )
    
    def validate_file(self, file: UploadedFile) -> Optional[str]:
        """
        Валидация файла перед обработкой
        
        Args:
            file: Загруженный файл
            
        Returns:
            Сообщение об ошибке или None если файл валиден
        """
        # Проверка расширения файла
        if not any(file.name.lower().endswith(ext) for ext in self.ALLOWED_EXTENSIONS):
            return f"Неподдерживаемый формат файла. Разрешены только файлы: {', '.join(self.ALLOWED_EXTENSIONS)}"
        
        # Проверка размера файла
        max_size_bytes = self.MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size > max_size_bytes:
            return f"Файл слишком большой ({file.size / (1024*1024):.1f}MB). Максимальный размер: {self.MAX_FILE_SIZE_MB}MB"
        
        # Проверка на пустой файл
        if file.size == 0:
            return "Файл пуст"
        
        return None
    
    def _validate_files_batch(self, files: List[UploadedFile]) -> None:
        """
        Валидация общих ограничений для пакета файлов
        
        Args:
            files: Список файлов для валидации
            
        Raises:
            ExcelProcessingError: При нарушении ограничений
        """
        self.logger.debug(f"BATCH_VALIDATION_START - Начало валидации пакета | files_count={len(files)}")
        
        # Проверка количества файлов
        if len(files) > self.MAX_FILES_PER_UPLOAD:
            error_msg = (
                f"Слишком много файлов ({len(files)}). "
                f"Максимальное количество файлов за раз: {self.MAX_FILES_PER_UPLOAD}"
            )
            self.logger.error(f"BATCH_VALIDATION_COUNT_ERROR - {error_msg}")
            raise ExcelProcessingError(error_msg)
        
        if len(files) == 0:
            error_msg = "Не выбрано ни одного файла для загрузки"
            self.logger.error(f"BATCH_VALIDATION_EMPTY_ERROR - {error_msg}")
            raise ExcelProcessingError(error_msg)
        
        # Проверка общего размера
        total_size = sum(file.size for file in files)
        max_total_size_bytes = self.MAX_TOTAL_SIZE_MB * 1024 * 1024
        
        if total_size > max_total_size_bytes:
            error_msg = (
                f"Общий размер файлов слишком большой ({total_size / (1024*1024):.1f}MB). "
                f"Максимальный общий размер: {self.MAX_TOTAL_SIZE_MB}MB"
            )
            self.logger.error(f"BATCH_VALIDATION_SIZE_ERROR - {error_msg}")
            raise ExcelProcessingError(error_msg)
        
        # Логирование деталей каждого файла
        for i, file in enumerate(files):
            self.logger.debug(
                f"BATCH_VALIDATION_FILE_DETAIL - Файл {i+1} | "
                f"name={file.name} | size_mb={file.size / (1024*1024):.2f} | "
                f"content_type={getattr(file, 'content_type', 'unknown')}"
            )
        
        self.logger.info(
            f"BATCH_VALIDATION_SUCCESS - Валидация пакета успешна | "
            f"files_count={len(files)} | total_size_mb={total_size / (1024*1024):.2f} | "
            f"avg_file_size_mb={total_size / len(files) / (1024*1024):.2f}"
        )
    
    def _check_for_duplicates_before_processing(self, file: UploadedFile) -> Optional[Dict[str, Any]]:
        """
        Проверка на потенциальные дубликаты перед обработкой файла
        
        Эта функция пытается извлечь базовую информацию из файла
        и проверить существующие предложения в базе данных
        
        Args:
            file: Файл для проверки
            
        Returns:
            Словарь с информацией о конфликтах или None если дубликатов нет
        """
        self.logger.debug(f"DUPLICATE_CHECK_START - Начало проверки дубликатов | filename={file.name}")
        
        try:
            # Пытаемся извлечь базовую информацию из файла для проверки дубликатов
            file_info = self._extract_basic_file_info(file)
            if not file_info:
                # Если не удалось извлечь информацию, пропускаем предварительную проверку
                # Дубликаты будут обнаружены при полной обработке
                self.logger.debug(f"DUPLICATE_CHECK_SKIP - Не удалось извлечь информацию для проверки | filename={file.name}")
                return None
            
            self.logger.debug(
                f"DUPLICATE_CHECK_INFO_EXTRACTED - Информация извлечена | "
                f"filename={file.name} | company={file_info['company_name']} | years={file_info['years']}"
            )
            
            # Проверяем существующие предложения
            conflicts = self._check_existing_offers(file_info['company_name'], file_info['years'])
            
            if conflicts:
                conflict_messages = [f"{conflict['company_name']} - {conflict['year']} год" for conflict in conflicts]
                error_message = (
                    f"Предложение от компании '{file_info['company_name']}' "
                    f"для {', '.join(str(c['year']) for c in conflicts)} года уже существует в данном своде"
                )
                
                self.logger.warning(
                    f"DUPLICATE_CHECK_CONFLICTS_FOUND - Обнаружены конфликты | "
                    f"filename={file.name} | company={file_info['company_name']} | "
                    f"conflicts_count={len(conflicts)} | conflicts={conflict_messages}"
                )
                
                return {
                    'error_message': error_message,
                    'conflicts': conflict_messages
                }
            
            self.logger.debug(f"DUPLICATE_CHECK_SUCCESS - Дубликаты не найдены | filename={file.name}")
            return None
            
        except Exception as e:
            # Если произошла ошибка при предварительной проверке,
            # логируем её и продолжаем обработку (дубликаты будут обнаружены позже)
            self.logger.warning(
                f"DUPLICATE_CHECK_ERROR - Ошибка при предварительной проверке дубликатов | "
                f"filename={file.name} | error={str(e)}"
            )
            return None
    
    def _create_file_result(self, file_name: str, file_index: int, success: bool, **kwargs) -> Dict[str, Any]:
        """
        Создание результата обработки файла
        
        Args:
            file_name: Имя файла
            file_index: Индекс файла в списке
            success: Успешность обработки
            **kwargs: Дополнительные параметры результата
            
        Returns:
            Словарь с результатом обработки файла
        """
        result = {
            'file_name': file_name,
            'file_index': file_index,
            'success': success,
        }
        
        if success:
            result.update({
                'company_name': kwargs.get('company_name'),
                'offers_created': kwargs.get('offers_created', 0),
                'years_processed': kwargs.get('years_processed', []),
                'processed_rows': kwargs.get('processed_rows', []),
                'skipped_rows': kwargs.get('skipped_rows', []),
            })
        else:
            result.update({
                'error_message': kwargs.get('error_message'),
                'error_type': kwargs.get('error_type'),
                'duplicate_conflicts': kwargs.get('duplicate_conflicts', []),
            })
        
        return result

    def _extract_basic_file_info(self, file: UploadedFile) -> Optional[Dict[str, Any]]:
        """
        Извлекает базовую информацию из файла для проверки дубликатов
        
        Args:
            file: Загруженный файл
            
        Returns:
            Словарь с информацией о компании и годах или None при ошибке
        """
        self.logger.debug(f"FILE_INFO_EXTRACTION_START - Начало извлечения информации | filename={file.name}")
        
        try:
            import openpyxl
            from io import BytesIO
            
            # Читаем файл в память
            file.seek(0)  # Убеждаемся, что читаем с начала
            file_content = file.read()
            file.seek(0)  # Возвращаем указатель в начало для последующего использования
            
            self.logger.debug(f"FILE_INFO_EXTRACTION_READ - Файл прочитан | filename={file.name} | size_bytes={len(file_content)}")
            
            # Открываем Excel файл
            workbook = openpyxl.load_workbook(BytesIO(file_content), read_only=True)
            worksheet = workbook.active
            
            # Пытаемся найти название компании (обычно в ячейке B2)
            company_name = None
            company_cell = worksheet['B2']
            if company_cell.value:
                company_name = str(company_cell.value).strip()
            
            if not company_name:
                self.logger.debug(f"FILE_INFO_EXTRACTION_NO_COMPANY - Не удалось извлечь название компании | filename={file.name}")
                workbook.close()
                return None
            
            # Пытаемся найти годы страхования (обычно в строках с данными)
            years = []
            
            # Проверяем строки с 6 по 15 (типичное расположение данных)
            for row_num in range(6, 16):
                try:
                    year_cell = worksheet.cell(row=row_num, column=1)  # Колонка A
                    if year_cell.value and str(year_cell.value).strip().isdigit():
                        year = int(year_cell.value)
                        if 1 <= year <= 10:  # Годы страхования обычно от 1 до 10
                            years.append(year)
                except (ValueError, TypeError):
                    continue
            
            workbook.close()
            
            if not years:
                self.logger.debug(f"FILE_INFO_EXTRACTION_NO_YEARS - Не удалось извлечь годы страхования | filename={file.name}")
                return None
            
            self.logger.debug(
                f"FILE_INFO_EXTRACTION_SUCCESS - Информация успешно извлечена | "
                f"filename={file.name} | company={company_name} | years={years}"
            )
            
            return {
                'company_name': company_name,
                'years': years
            }
            
        except Exception as e:
            self.logger.debug(
                f"FILE_INFO_EXTRACTION_ERROR - Ошибка при извлечении информации | "
                f"filename={file.name} | error={str(e)}"
            )
            return None

    def _check_existing_offers(self, company_name: str, years: List[int]) -> List[Dict[str, Any]]:
        """
        Проверяет существующие предложения в базе данных
        
        Args:
            company_name: Название компании
            years: Список лет страхования
            
        Returns:
            Список конфликтующих предложений
        """
        self.logger.debug(
            f"EXISTING_OFFERS_CHECK_START - Начало проверки существующих предложений | "
            f"company={company_name} | years={years} | summary_id={self.summary.id}"
        )
        
        conflicts = []
        
        try:
            for year in years:
                existing_offer = InsuranceOffer.objects.filter(
                    summary=self.summary,
                    company_name=company_name,
                    insurance_year=year
                ).first()
                
                if existing_offer:
                    conflicts.append({
                        'company_name': company_name,
                        'year': year,
                        'offer_id': existing_offer.id
                    })
                    
                    self.logger.debug(
                        f"EXISTING_OFFERS_CONFLICT_FOUND - Найден конфликт | "
                        f"company={company_name} | year={year} | existing_offer_id={existing_offer.id}"
                    )
            
            if conflicts:
                self.logger.warning(
                    f"EXISTING_OFFERS_CHECK_CONFLICTS - Обнаружены конфликты | "
                    f"company={company_name} | conflicts_count={len(conflicts)} | "
                    f"conflicting_years={[c['year'] for c in conflicts]}"
                )
            else:
                self.logger.debug(
                    f"EXISTING_OFFERS_CHECK_SUCCESS - Конфликты не найдены | "
                    f"company={company_name} | checked_years={years}"
                )
            
        except Exception as e:
            self.logger.error(
                f"EXISTING_OFFERS_CHECK_ERROR - Ошибка при проверке существующих предложений | "
                f"company={company_name} | years={years} | error={str(e)}"
            )
            # Возвращаем пустой список, чтобы не блокировать обработку
            return []
        
        return conflicts

    def _process_file_with_retry(self, file: UploadedFile, max_retries: int = 3) -> Dict[str, Any]:
        """
        Обработка файла с повторными попытками при блокировке БД
        
        Args:
            file: Загруженный файл
            max_retries: Максимальное количество попыток
            
        Returns:
            Результат обработки файла
        """
        import time
        
        for attempt in range(max_retries + 1):
            try:
                # Блокировка уже применена на уровне process_files, используем только транзакцию
                with transaction.atomic():
                    return self.excel_processor.process_excel_file(file, self.summary)
                        
            except OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries:
                    wait_time = (attempt + 1) * 0.1  # Увеличиваем время ожидания
                    self.logger.warning(
                        f"DATABASE_LOCK_RETRY - База данных заблокирована, повтор через {wait_time}s | "
                        f"filename={file.name} | attempt={attempt + 1}/{max_retries + 1}"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    # Если все попытки исчерпаны или другая ошибка
                    raise e
            except Exception as e:
                # Для других исключений не делаем повторы
                raise e
        
        # Этот код не должен выполняться, но на всякий случай
        raise Exception(f"Не удалось обработать файл {file.name} после {max_retries + 1} попыток")


def get_multiple_file_processor(summary: InsuranceSummary) -> MultipleFileProcessor:
    """
    Фабричная функция для создания экземпляра MultipleFileProcessor
    
    Args:
        summary: Свод предложений для обработки
        
    Returns:
        MultipleFileProcessor: Экземпляр процессора
    """
    return MultipleFileProcessor(summary)
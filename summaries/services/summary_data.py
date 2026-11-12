"""Shared validation, company data and numeric formatting for summary exports."""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from ..exceptions import ExcelExportServiceError, InvalidSummaryDataError
from ..models import InsuranceSummary, InsurerResponse

logger = logging.getLogger(__name__)


class SummaryDataService:
    """Prepare summary data without loading a workbook template."""

    FIRST_DATA_ROW = 10  # Первая строка для данных компаний
    MAX_ROWS_LIMIT = 1000  # Максимальное количество строк для предотвращения зависания
    MAX_COMPANIES_LIMIT = 100  # Максимальное количество компаний
    MAX_YEARS_PER_COMPANY = 10  # Максимальное количество лет на компанию
    MAX_COVERAGE_TERRITORY_LENGTH = 32767  # Максимум текста в ячейке Excel
    MISSING_COVERAGE_TERRITORY = 'Не указано страховщиком'
    LEGACY_COVERAGE_TERRITORY = 'Нет данных: территория ранее не собиралась'
    MIN_INSURANCE_SUM = Decimal('1')  # Минимальная страховая сумма
    MAX_INSURANCE_SUM = Decimal('1000000000')  # Максимальная страховая сумма (1 млрд)
    DECLINED_TEXT = 'Отказ от страхования'
    FRANCHISE_APPROVAL_ADDITIONAL_NOTE = 'Требуется согласование франшизы с ГО.'

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

            if not request.object_summary or request.object_summary.strip() == '':
                missing_fields.append("объект страхования (object_summary)")

            if not request.client_name or request.client_name.strip() == '':
                missing_fields.append("название клиента (client_name)")

        if missing_fields:
            error_msg = f"Отсутствуют обязательные данные: {', '.join(missing_fields)}"
            logger.error(f"Валидация данных свода ID {summary.id} не пройдена: {error_msg}")
            raise InvalidSummaryDataError(error_msg)

        logger.debug(f"Валидация данных свода ID {summary.id} успешно пройдена")

    def _determine_template_type(self, summary: InsuranceSummary) -> str:
        """
        Определяет тип шаблона на основе анализа предложений в своде

        Args:
            summary: Объект свода предложений

        Returns:
            str: 'full' если есть хотя бы одно предложение с премией-2,
                 'simplified' если нет ни одного предложения с премией-2
        """
        try:
            logger.debug(f"Анализируем предложения свода ID: {summary.id} для определения типа шаблона")

            # Получаем все предложения свода
            offers = summary.offers.all()
            total_offers = offers.count()

            # Проверяем наличие хотя бы одного предложения с премией-2
            offers_with_premium_2 = offers.filter(
                premium_with_franchise_2__isnull=False,
                premium_with_franchise_2__gt=0
            ).count()

            # Логируем статистику
            logger.info(f"Свод ID: {summary.id} - всего предложений: {total_offers}, с премией-2: {offers_with_premium_2}")

            if offers_with_premium_2 > 0:
                logger.info(f"Найдено {offers_with_premium_2} предложений с премией-2, используем полный шаблон")
                return 'full'
            else:
                logger.info("Предложений с премией-2 не найдено, используем упрощенный шаблон")
                return 'simplified'

        except Exception as e:
            logger.error(f"Ошибка при анализе предложений для определения типа шаблона: {e}")
            raise

    def _determine_template_type_safe(self, summary: InsuranceSummary) -> str:
        """
        Безопасное определение типа шаблона с fallback к полному шаблону

        Args:
            summary: Объект свода предложений

        Returns:
            str: Тип шаблона ('full' или 'simplified')
        """
        try:
            template_type = self._determine_template_type(summary)
            self._log_template_selection(template_type, summary)
            return template_type
        except Exception as e:
            logger.error(f"Ошибка при определении типа шаблона для свода ID {summary.id}: {e}")
            logger.info("Используем полный шаблон по умолчанию")
            return 'full'  # Fallback к полному шаблону

    def _log_template_selection(self, template_type: str, summary: InsuranceSummary) -> None:
        """
        Логирует информацию о выборе шаблона

        Args:
            template_type: Выбранный тип шаблона
            summary: Объект свода предложений
        """
        try:
            total_offers = summary.offers.count()
            offers_with_premium_2 = summary.offers.filter(
                premium_with_franchise_2__isnull=False,
                premium_with_franchise_2__gt=0
            ).count()

            logger.info(f"=== ВЫБОР ШАБЛОНА ДЛЯ СВОДА ID: {summary.id} ===")
            logger.info(f"Выбран тип шаблона: {template_type}")
            logger.info(f"Всего предложений в своде: {total_offers}")
            logger.info(f"Предложений с премией-2: {offers_with_premium_2}")

            if template_type == 'simplified':
                logger.info("Будет использован упрощенный шаблон без колонок для второго предложения")
                logger.info("Блок колонок второго предложения будет отсутствовать")
                logger.info("Территория страховщика будет в колонке J")
                logger.info("Примечания будут в колонке K вместо Q")
            else:
                logger.info("Будет использован полный шаблон с колонками для обоих предложений")
                logger.info("Все колонки A-Q будут присутствовать")

            logger.info("=" * 50)

        except Exception as e:
            logger.warning(f"Ошибка при логировании выбора шаблона: {e}")

    def _get_installment_text_for_tech_info(self, has_installment: bool) -> str:
        """
        Возвращает текст о рассрочке для технического листа

        Args:
            has_installment: Наличие рассрочки

        Returns:
            str: Соответствующий текст для технического листа
        """
        if has_installment:
            return 'Запрос тарифа с рассрочкой'
        else:
            return 'Запрос тарифа без рассрочки'

    def _get_insurance_description_for_tech_info(self, request) -> str:
        """
        Формирует описание страхования для технического листа (аналог ins_type + casco_type_ce)

        Args:
            request: Объект заявки

        Returns:
            str: Описание типа страхования с дополнительными рисками
        """
        # Маппинг типов страхования (аналогично core/templates.py)
        insurance_type_descriptions = {
            'КАСКО': 'Стандартный запрос по КАСКО. ',
            'страхование спецтехники': (
                'Запрос по страхованию спецтехники (максимальный пакет с транспортировкой (погрузкой/выгрузкой) на весь срок '
                'страхования).\n Запрашивались:\n - риск кражи / угона в ночное время с неохраняемой стоянки.\n - риск просадки '
                'грунта, провала дорог или мостов, обвала тоннелей\n - риск провала под лед, затопления специальной техники, '
                'дополнительного оборудования.'
            ),
            'страхование имущества': (
                'Запрос по страхованию имущества ("полный пакет рисков").\nОтдельно запрашивались:\n'
                '1. Риски РНПК\n'
                '2. Ограничения по выплате страхового возмещения в той степени, в которой предоставление '
                'такого покрытия, возмещение такого убытка или предоставление такой компенсации подвергло бы Страховщика '
                'действиям любых санкций, запретов или ограничений установленных (резолюциями Организации Объединенных '
                'Наций; законами или правилами Европейского союза, Соединенного Королевства Великобритании или Соединенных '
                'Штатов Америки; законодательством РФ, указами Президента РФ и/или иными нормативными подзаконными актами '
                'РФ, принятыми в соответствии с резолюциями СБ ООН, указами Президента РФ и/или иными нормативными '
                'подзаконными актами РФ).\n'
                '3. Наличие рисков:\n а) Бой стекол \n б) Риск повреждения животными'
            ),
            'другое': 'Иной запрос по страхованию предмета лизинга.'
        }

        # Получаем базовое описание типа страхования
        insurance_type = request.insurance_type or 'КАСКО'
        base_description = insurance_type_descriptions.get(insurance_type, insurance_type)

        # Добавляем информацию о КАСКО C/E если необходимо
        casco_ce_text = ''
        if request.has_casco_ce:
            casco_ce_text = (
                'Также запрашивались доп. риски для категории C/E: \n'
                '- страхование вне дорог общего пользования, \n'
                '- провал грунта, \n'
                '- переворот \n'
                '- опрокидывание.'
            )

        # Объединяем описания
        result = base_description
        if casco_ce_text:
            result += casco_ce_text

        return result.strip()

    def _get_companies_sorted_data(self, summary: InsuranceSummary) -> Dict[str, List]:
        """
        Получает данные компаний, отсортированные по алфавиту

        Args:
            summary: Объект свода предложений

        Returns:
            Dict: Словарь с компаниями и их предложениями, отсортированными по алфавиту
            Формат: {'Компания': [offer_year1, offer_year2, ...], ...}

        Raises:
            ExcelExportServiceError: При ошибках получения данных
        """
        try:
            logger.debug(f"Получаем отсортированные данные компаний для свода ID: {summary.id}")

            # Используем существующий метод модели для получения сгруппированных данных
            companies_data = summary.get_offers_grouped_by_company()
            self._apply_company_fields(summary, companies_data)

            logger.info(f"Найдено {len(companies_data)} компаний для свода ID: {summary.id}")

            # Логируем информацию о каждой компании
            for company_name, offers in companies_data.items():
                years = [offer.insurance_year for offer in offers]
                logger.debug(f"Компания '{company_name}': {len(offers)} предложений для лет {years}")

            return companies_data

        except Exception as e:
            error_msg = f"Ошибка при получении данных компаний для свода ID {summary.id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ExcelExportServiceError(error_msg) from e

    @staticmethod
    def _apply_company_fields(summary, companies_data) -> None:
        """Территория и примечание — одни на СК в своде, хранятся в «Ответе СК». Код выгрузки читает их
        у предложений (offer.coverage_territory / offer.notes), поэтому они подставляются в загруженные для
        выгрузки объекты в памяти — не сохраняются; поля годовых строк — архив и не читаются.
        Примечание — только у первого года компании (как и было в данных: 660 из 661 — только в 1-м году)."""
        if not isinstance(summary, InsuranceSummary):
            return
        responses = {r.company_name: r for r in InsurerResponse.objects.filter(summary=summary)}
        for company_name, offers in companies_data.items():
            response = responses.get(company_name)
            for index, offer in enumerate(sorted(offers, key=lambda o: o.insurance_year)):
                offer.coverage_territory = response.coverage_territory if response else None
                offer.notes = (response.notes if response and index == 0 else '') or ''

    @staticmethod
    def _sanitize_excel_text(value: Any, max_length: Optional[int] = None) -> str:
        """Нормализует текст и удаляет все запрещенные Excel/XML символы."""
        if value is None:
            return ''

        sanitized = str(value).replace('\r\n', '\n').replace('\r', '\n')
        sanitized = ILLEGAL_CHARACTERS_RE.sub('', sanitized).strip()
        if max_length is not None and len(sanitized) > max_length:
            suffix = '...' if max_length >= 3 else ''
            sanitized = sanitized[:max_length - len(suffix)] + suffix
        return sanitized

    def _combine_additional_notes(self, *notes: Optional[str]) -> Optional[str]:
        """
        Объединяет системные примечания в одну строку без дублей.

        Args:
            notes: Последовательность системных примечаний

        Returns:
            Optional[str]: Объединенный текст или None
        """
        unique_notes = []

        for note in notes:
            if not note:
                continue

            normalized_note = ' '.join(str(note).split())
            if not normalized_note:
                continue

            if not any(existing.lower() == normalized_note.lower() for existing in unique_notes):
                unique_notes.append(normalized_note)

        return ' '.join(unique_notes) if unique_notes else None

    def _is_non_zero_franchise_value(self, value) -> bool:
        """
        Проверяет, что значение франшизы задано и не равно нулю.

        Args:
            value: Проверяемое значение франшизы

        Returns:
            bool: True если значение ненулевое
        """
        if value is None:
            return False

        try:
            return Decimal(str(value)) != Decimal('0')
        except (InvalidOperation, TypeError, ValueError):
            logger.debug(f"Некорректное значение франшизы '{value}', считаем как 0")
            return False

    def _get_franchise_approval_note_for_company(self, offers: List, company_name: str) -> Optional[str]:
        """
        Определяет необходимость системного комментария о согласовании франшизы для компании.

        Args:
            offers: Список предложений компании
            company_name: Название компании (для логирования)

        Returns:
            Optional[str]: Системный комментарий или None
        """
        for offer in offers:
            franchise_1 = getattr(offer, 'franchise_1', None)
            franchise_2 = getattr(offer, 'franchise_2', None)

            if self._is_non_zero_franchise_value(franchise_1) or self._is_non_zero_franchise_value(franchise_2):
                logger.info(
                    f"Компания '{company_name}': найдена ненулевая франшиза, "
                    "добавляем системный комментарий о согласовании"
                )
                return self.FRANCHISE_APPROVAL_ADDITIONAL_NOTE

        return None

    def _get_declined_companies(self, summary: InsuranceSummary) -> List[str]:
        """Отказавшие СК свода по алфавиту. У сводов до запуска статусов СК — пусто (отказы в примечании C5)."""
        from .company_statuses import declined_company_names

        try:
            return declined_company_names(summary)
        except Exception as e:  # отказы не должны ломать выгрузку предложений
            logger.error(f"Не удалось получить отказы СК для свода ID {summary.id}: {e}", exc_info=True)
            return []

    def _validate_companies_data(self, companies_data: Dict[str, List]) -> Dict[str, List]:
        """
        Валидирует данные компаний и применяет ограничения для предотвращения проблем

        Обрабатывает граничные случаи:
        - Отсутствие предложений от компаний
        - Превышение лимитов по количеству компаний и лет
        - Компании с одним годом страхования

        Args:
            companies_data: Словарь с данными компаний

        Returns:
            Dict: Валидированные и ограниченные данные компаний

        Raises:
            InvalidSummaryDataError: При критических проблемах с данными
        """
        try:
            logger.debug(f"Начинаем валидацию данных {len(companies_data)} компаний")

            # Обработка случая отсутствия предложений от компаний (требование 7.1)
            if not companies_data:
                logger.warning("Нет предложений от компаний для обработки")
                return {}

            # Применяем ограничение на количество компаний
            if len(companies_data) > self.MAX_COMPANIES_LIMIT:
                logger.warning(f"Количество компаний ({len(companies_data)}) превышает лимит ({self.MAX_COMPANIES_LIMIT}), обрезаем")
                # Берем первые N компаний по алфавиту
                sorted_companies = sorted(companies_data.keys())[:self.MAX_COMPANIES_LIMIT]
                companies_data = {name: companies_data[name] for name in sorted_companies}

            validated_data = {}
            total_rows_estimated = 0

            for company_name, offers in companies_data.items():
                # Валидация названия компании
                if not company_name or not company_name.strip():
                    logger.warning(f"Пропускаем компанию с пустым названием")
                    continue

                # Обработка компаний с одним годом страхования (требование 7.2)
                if len(offers) == 1:
                    logger.info(f"Компания '{company_name}' имеет только один год страхования - это нормально")

                # Применяем ограничение на количество лет на компанию
                if len(offers) > self.MAX_YEARS_PER_COMPANY:
                    logger.warning(f"Компания '{company_name}' имеет {len(offers)} лет, ограничиваем до {self.MAX_YEARS_PER_COMPANY}")
                    offers = offers[:self.MAX_YEARS_PER_COMPANY]

                # Валидируем каждое предложение
                valid_offers = []
                for offer in offers:
                    if self._validate_offer_data(offer, company_name):
                        valid_offers.append(offer)

                # Добавляем компанию только если есть валидные предложения
                if valid_offers:
                    validated_data[company_name] = valid_offers
                    # Оцениваем количество строк (предложения + разделители)
                    total_rows_estimated += len(valid_offers) + 1  # +1 для разделителя
                else:
                    logger.warning(f"Компания '{company_name}' не имеет валидных предложений, пропускаем")

            # Проверяем общее ограничение на количество строк (требование 7.4)
            if total_rows_estimated > self.MAX_ROWS_LIMIT:
                logger.warning(f"Оценочное количество строк ({total_rows_estimated}) превышает лимит ({self.MAX_ROWS_LIMIT})")
                # Обрезаем данные до достижения лимита
                validated_data = self._limit_data_by_rows(validated_data)

            logger.info(f"Валидация завершена: {len(validated_data)} компаний прошли проверку")
            return validated_data

        except Exception as e:
            error_msg = f"Ошибка при валидации данных компаний: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise InvalidSummaryDataError(error_msg) from e

    def _validate_offer_data(self, offer, company_name: str) -> bool:
        """
        Валидирует данные отдельного предложения

        Проверяет:
        - Наличие обязательных данных
        - Корректность числовых значений
        - Обработка отсутствующих данных по франшизе или премии (требование 7.3)

        Args:
            offer: Объект предложения InsuranceOffer
            company_name: Название компании для логирования

        Returns:
            bool: True если предложение валидно, False если нужно пропустить
        """
        try:
            # Проверяем наличие года страхования
            if not hasattr(offer, 'insurance_year') or offer.insurance_year is None:
                logger.warning(f"Компания '{company_name}': предложение без года страхования, пропускаем")
                return False

            # Проверяем корректность года
            if not isinstance(offer.insurance_year, int) or offer.insurance_year < 1 or offer.insurance_year > 20:
                logger.warning(f"Компания '{company_name}': некорректный год страхования {offer.insurance_year}, пропускаем")
                return False

            # Проверяем страховую сумму
            insurance_sum = getattr(offer, 'insurance_sum', None)
            if insurance_sum is None or insurance_sum <= 0:
                logger.warning(f"Компания '{company_name}', год {offer.insurance_year}: отсутствует или некорректная страховая сумма, пропускаем")
                return False

            # Валидируем числовые данные перед записью в Excel (требование 7.3)
            premium_1 = getattr(offer, 'premium_with_franchise_1', None)
            franchise_1 = getattr(offer, 'franchise_1', None)

            # Для первого варианта премия обязательна
            if premium_1 is None or premium_1 <= 0:
                logger.warning(f"Компания '{company_name}', год {offer.insurance_year}: отсутствует премия-1, пропускаем предложение")
                return False

            # Франшиза может отсутствовать (будет 0 по умолчанию)
            if franchise_1 is None:
                logger.debug(f"Компания '{company_name}', год {offer.insurance_year}: франшиза-1 отсутствует, будет использован 0")

            # Проверяем второй вариант если он есть
            if offer.has_second_franchise_variant():
                premium_2 = getattr(offer, 'premium_with_franchise_2', None)
                franchise_2 = getattr(offer, 'franchise_2', None)

                if premium_2 is None or premium_2 <= 0:
                    logger.warning(f"Компания '{company_name}', год {offer.insurance_year}: некорректная премия-2, второй вариант будет пропущен")

                if franchise_2 is None:
                    logger.debug(f"Компания '{company_name}', год {offer.insurance_year}: франшиза-2 отсутствует")

            logger.debug(f"Компания '{company_name}', год {offer.insurance_year}: предложение прошло валидацию")
            return True

        except Exception as e:
            logger.error(f"Ошибка при валидации предложения компании '{company_name}': {str(e)}")
            return False

    def _limit_data_by_rows(self, companies_data: Dict[str, List]) -> Dict[str, List]:
        """
        Ограничивает данные компаний по количеству строк для предотвращения превышения лимитов

        Args:
            companies_data: Данные компаний

        Returns:
            Dict: Ограниченные данные компаний
        """
        try:
            limited_data = {}
            current_rows = self.FIRST_DATA_ROW

            logger.info(f"Применяем ограничение по строкам, лимит: {self.MAX_ROWS_LIMIT}")

            for company_name, offers in companies_data.items():
                # Рассчитываем сколько строк займет эта компания
                company_rows = len(offers) + 1  # +1 для разделителя

                # Проверяем, поместится ли компания в лимит
                if current_rows + company_rows > self.MAX_ROWS_LIMIT:
                    logger.warning(f"Компания '{company_name}' не помещается в лимит строк, останавливаем обработку")
                    break

                limited_data[company_name] = offers
                current_rows += company_rows

                logger.debug(f"Компания '{company_name}': {len(offers)} предложений, текущая строка: {current_rows}")

            logger.info(f"Ограничение применено: {len(limited_data)} компаний, ожидаемая строка: {current_rows}")
            return limited_data

        except Exception as e:
            logger.error(f"Ошибка при ограничении данных по строкам: {str(e)}")
            return companies_data  # Возвращаем исходные данные при ошибке

    def _format_installment_payments(self, offer, variant: int = 1) -> int:
        """
        Форматирует количество платежей в год для указанного варианта рассрочки

        Логика определения:
        - 1 если рассрочки нет (единовременный платеж)
        - Фактическое количество платежей в год если есть рассрочка (2, 3, 4, 12 и т.д.)

        Args:
            offer: Объект предложения InsuranceOffer
            variant: Номер варианта (1 или 2)

        Returns:
            int: Количество платежей в год (1 если нет рассрочки, иначе фактическое количество)

        Raises:
            ValueError: Если variant не равен 1 или 2
        """
        try:
            # Валидация входного параметра
            if variant not in [1, 2]:
                logger.error(f"Некорректный номер варианта: {variant}. Ожидается 1 или 2")
                raise ValueError(f"Номер варианта должен быть 1 или 2, получен: {variant}")

            # Получаем данные для соответствующего варианта
            if variant == 1:
                payments_per_year = getattr(offer, 'payments_per_year_variant_1', 1)
                has_installment = getattr(offer, 'installment_variant_1', False)
                logger.debug(f"Вариант 1: платежей в год={payments_per_year}, рассрочка={has_installment}")
            else:  # variant == 2
                payments_per_year = getattr(offer, 'payments_per_year_variant_2', 1)
                has_installment = getattr(offer, 'installment_variant_2', False)
                logger.debug(f"Вариант 2: платежей в год={payments_per_year}, рассрочка={has_installment}")

            # Проверяем валидность данных
            if payments_per_year is None:
                payments_per_year = 1
                logger.warning(f"Количество платежей в год для варианта {variant} равно None, используем 1")

            # Если рассрочки нет или только один платеж в год - возвращаем 1
            if not has_installment or payments_per_year <= 1:
                logger.debug(f"Рассрочка недоступна для варианта {variant}: has_installment={has_installment}, payments_per_year={payments_per_year}")
                return 1

            # Возвращаем фактическое количество платежей в год без преобразований
            logger.debug(f"Рассрочка вариант {variant}: {payments_per_year} платежей в год")

            return payments_per_year

        except ValueError:
            # Переброс ошибок валидации
            raise
        except Exception as e:
            error_msg = f"Ошибка при форматировании рассрочки для варианта {variant}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # В случае ошибки возвращаем 1 (единовременный платеж)
            return 1

    def _format_numeric_value(self, value, field_name: str = "значение") -> Optional[Decimal]:
        """
        Форматирует числовое значение для записи в Excel

        Обеспечивает корректное форматирование премий, франшиз и страховых сумм.
        Обрабатывает различные типы входных данных и валидирует их.

        Args:
            value: Числовое значение (может быть Decimal, float, int, str или None)
            field_name: Название поля для логирования (для отладки)

        Returns:
            Optional[Decimal]: Отформатированное значение или None если значение пустое/некорректное
        """
        try:
            # Если значение None или пустое - возвращаем None
            if value is None:
                logger.debug(f"Поле '{field_name}': значение None, возвращаем None")
                return None

            # Если это строка - пытаемся преобразовать
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    logger.debug(f"Поле '{field_name}': пустая строка, возвращаем None")
                    return None

                # Нормализуем числовое значение с учетом разных форматов разделителей
                original_value = value
                value = self._normalize_decimal_separator(value)

                if original_value != value:
                    logger.debug(f"Поле '{field_name}': нормализовано '{original_value}' → '{value}'")

                try:
                    value = Decimal(value)
                except (ValueError, InvalidOperation) as e:
                    logger.warning(f"Поле '{field_name}': не удалось преобразовать строку '{original_value}' в число: {e}")
                    return None

            # Преобразуем в Decimal для точности
            if isinstance(value, (int, float)):
                value = Decimal(str(value))
            elif not isinstance(value, Decimal):
                logger.warning(f"Поле '{field_name}': неподдерживаемый тип данных {type(value)}, пытаемся преобразовать")
                value = Decimal(str(value))

            # Валидация: проверяем, что значение не отрицательное
            if value < 0:
                logger.warning(f"Поле '{field_name}': отрицательное значение {value}, возвращаем 0")
                return Decimal('0')

            # Валидация: проверяем разумные пределы
            if value > self.MAX_INSURANCE_SUM:
                logger.warning(f"Поле '{field_name}': значение {value} превышает максимальный лимит {self.MAX_INSURANCE_SUM}")
                return self.MAX_INSURANCE_SUM

            # Проверяем минимальные пределы
            if value < self.MIN_INSURANCE_SUM and value > 0:
                logger.warning(f"Поле '{field_name}': значение {value} меньше минимального лимита {self.MIN_INSURANCE_SUM}")
                return self.MIN_INSURANCE_SUM

            # Округляем до 2 знаков после запятой для денежных значений
            result = value.quantize(Decimal('0.01'))

            logger.debug(f"Поле '{field_name}': успешно отформатировано значение {result}")
            return result

        except Exception as e:
            error_msg = f"Ошибка при форматировании числового значения для поля '{field_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None

    def _normalize_decimal_separator(self, value_str: str) -> str:
        """
        Нормализует десятичные разделители в числовой строке

        Обрабатывает различные форматы чисел:
        - "43000" → "43000" (без изменений)
        - "43030,78" → "43030.78" (запятая как десятичный разделитель)
        - "43030.78" → "43030.78" (без изменений)
        - "1,234.56" → "1234.56" (запятая как разделитель тысяч)
        - "1 234,56" → "1234.56" (европейский формат)
        - "1.234,56" → "1234.56" (немецкий формат)

        Args:
            value_str: Строковое представление числа

        Returns:
            str: Нормализованная строка, готовая для преобразования в Decimal
        """
        try:
            # Убираем все пробелы
            normalized = value_str.replace(' ', '')

            # Если нет ни запятых, ни точек - возвращаем как есть
            if ',' not in normalized and '.' not in normalized:
                return normalized

            # Если есть и запятая, и точка
            if ',' in normalized and '.' in normalized:
                comma_pos = normalized.rfind(',')
                dot_pos = normalized.rfind('.')

                # Если точка после запятой - точка десятичный разделитель, запятая - разделитель тысяч
                if dot_pos > comma_pos:
                    # Формат: "1,234.56" → "1234.56"
                    return normalized.replace(',', '')
                else:
                    # Если запятая после точки - запятая десятичный разделитель, точка - разделитель тысяч
                    # Формат: "1.234,56" → "1234.56"
                    return normalized.replace('.', '').replace(',', '.')

            # Если только запятая
            if ',' in normalized and '.' not in normalized:
                # Определяем, является ли запятая десятичным разделителем
                comma_pos = normalized.rfind(',')

                # Если после запятой 1-3 цифры и это последняя запятая - скорее всего десятичный разделитель
                after_comma = normalized[comma_pos + 1:]
                if len(after_comma) <= 3 and after_comma.isdigit():
                    # Проверяем, нет ли других запятых (разделителей тысяч)
                    comma_count = normalized.count(',')
                    if comma_count == 1:
                        # Одна запятая - проверяем длину части после запятой
                        if len(after_comma) <= 2:
                            # 1-2 цифры после запятой - скорее всего десятичный разделитель
                            return normalized.replace(',', '.')
                        elif len(after_comma) == 3:
                            # 3 цифры после запятой - может быть разделитель тысяч
                            # Проверяем, есть ли цифры до запятой
                            before_comma = normalized[:comma_pos]
                            if len(before_comma) <= 3:
                                # Короткая часть до запятой - скорее всего разделитель тысяч
                                return normalized.replace(',', '')
                            else:
                                # Длинная часть до запятой - скорее всего десятичный разделитель
                                return normalized.replace(',', '.')
                    else:
                        # Несколько запятых - последняя может быть десятичным разделителем
                        if len(after_comma) <= 2:  # Обычно десятичная часть 1-2 цифры
                            # Заменяем все запятые кроме последней на пустоту, последнюю на точку
                            parts = normalized.split(',')
                            if len(parts) >= 2:
                                integer_part = ''.join(parts[:-1])
                                decimal_part = parts[-1]
                                return f"{integer_part}.{decimal_part}"

                # Если не подходит под десятичный разделитель - убираем все запятые (разделители тысяч)
                return normalized.replace(',', '')

            # Если только точка
            if '.' in normalized and ',' not in normalized:
                # Аналогичная логика для точки
                dot_pos = normalized.rfind('.')
                after_dot = normalized[dot_pos + 1:]

                if len(after_dot) <= 3 and after_dot.isdigit():
                    dot_count = normalized.count('.')
                    if dot_count == 1:
                        # Одна точка - проверяем длину части после точки
                        if len(after_dot) <= 2:
                            # 1-2 цифры после точки - скорее всего десятичный разделитель
                            return normalized
                        elif len(after_dot) == 3:
                            # 3 цифры после точки - может быть разделитель тысяч
                            before_dot = normalized[:dot_pos]
                            if len(before_dot) <= 3:
                                # Короткая часть до точки - скорее всего разделитель тысяч
                                return normalized.replace('.', '')
                            else:
                                # Длинная часть до точки - скорее всего десятичный разделитель
                                return normalized
                    else:
                        # Несколько точек - все разделители тысяч кроме возможно последней
                        if len(after_dot) <= 2:
                            # Последняя точка с 1-2 цифрами - десятичный разделитель
                            parts = normalized.split('.')
                            if len(parts) >= 2:
                                integer_part = ''.join(parts[:-1])
                                decimal_part = parts[-1]
                                return f"{integer_part}.{decimal_part}"

                # Если не подходит под десятичный разделитель - убираем все точки (разделители тысяч)
                return normalized.replace('.', '')

            # Если нет разделителей - возвращаем как есть
            return normalized

        except Exception as e:
            logger.warning(f"Ошибка при нормализации числового значения '{value_str}': {e}")
            # В случае ошибки возвращаем исходное значение без пробелов
            return value_str.replace(' ', '')

    def _format_insurance_sum(self, offer) -> Optional[Decimal]:
        """
        Форматирует страховую сумму для записи в Excel

        Args:
            offer: Объект предложения InsuranceOffer

        Returns:
            Optional[Decimal]: Отформатированная страховая сумма
        """
        try:
            insurance_sum = getattr(offer, 'insurance_sum', None)
            return self._format_numeric_value(insurance_sum, 'страховая сумма')
        except Exception as e:
            logger.error(f"Ошибка при форматировании страховой суммы: {str(e)}")
            return None

    def _format_premium(self, offer, variant: int = 1) -> Optional[Decimal]:
        """
        Форматирует премию для указанного варианта

        Args:
            offer: Объект предложения InsuranceOffer
            variant: Номер варианта (1 или 2)

        Returns:
            Optional[Decimal]: Отформатированная премия
        """
        try:
            if variant == 1:
                premium = getattr(offer, 'premium_with_franchise_1', None)
                field_name = 'премия-1'
            else:
                premium = getattr(offer, 'premium_with_franchise_2', None)
                field_name = 'премия-2'

            return self._format_numeric_value(premium, field_name)
        except Exception as e:
            logger.error(f"Ошибка при форматировании премии для варианта {variant}: {str(e)}")
            return None

    def _format_franchise(self, offer, variant: int = 1) -> Optional[Decimal]:
        """
        Форматирует франшизу для указанного варианта

        Args:
            offer: Объект предложения InsuranceOffer
            variant: Номер варианта (1 или 2)

        Returns:
            Optional[Decimal]: Отформатированная франшиза
        """
        try:
            if variant == 1:
                franchise = getattr(offer, 'franchise_1', None)
                field_name = 'франшиза-1'
            else:
                franchise = getattr(offer, 'franchise_2', None)
                field_name = 'франшиза-2'

            # Для франшизы 0 - это валидное значение, не None
            formatted_value = self._format_numeric_value(franchise, field_name)

            # Если франшиза None - возвращаем 0 (по умолчанию).
            # Для варианта 2 вызов уже выполняется внутри has_second_franchise_variant(),
            # поэтому None здесь означает "вариант существует, но франшиза не задана = 0".
            if formatted_value is None:
                logger.debug(f"{field_name.capitalize()} равна None, используем значение по умолчанию 0")
                return Decimal('0')

            return formatted_value
        except Exception as e:
            logger.error(f"Ошибка при форматировании франшизы для варианта {variant}: {str(e)}")
            return Decimal('0')

    def _calculate_premium_sum(self, offers: List, premium_type: int) -> Optional[Decimal]:
        """
        Вычисляет сумму премий по всем годам страхования для указанного типа

        Args:
            offers: Список предложений компании
            premium_type: Тип премии (1 или 2)

        Returns:
            Optional[Decimal]: Сумма премий или None если нет валидных данных
        """
        try:
            logger.debug(f"Вычисляем сумму премий типа {premium_type} для {len(offers)} предложений")

            total_sum = Decimal('0')
            valid_premiums_count = 0

            for offer in offers:
                try:
                    if premium_type == 1:
                        premium = self._format_premium(offer, 1)
                    else:
                        premium = self._format_premium(offer, 2)

                    if premium is not None and premium > 0:
                        total_sum += premium
                        valid_premiums_count += 1
                        logger.debug(f"Добавлена премия-{premium_type}: {premium}, текущая сумма: {total_sum}")
                    else:
                        logger.debug(f"Премия-{premium_type} отсутствует или равна 0 для года {getattr(offer, 'insurance_year', 'неизвестно')}")

                except Exception as offer_error:
                    logger.warning(f"Ошибка при обработке премии-{premium_type} для года {getattr(offer, 'insurance_year', 'неизвестно')}: {offer_error}")
                    continue

            if valid_premiums_count == 0:
                logger.debug(f"Не найдено валидных премий типа {premium_type}")
                return None

            logger.debug(f"Сумма премий-{premium_type}: {total_sum} (из {valid_premiums_count} валидных значений)")
            return total_sum

        except Exception as e:
            logger.error(f"Ошибка при вычислении суммы премий типа {premium_type}: {e}")
            return None

    def _get_export_coverage_territory(self, offer) -> str:
        """Готовит подтвержденную страховщиком территорию для Excel."""
        raw_value = getattr(offer, 'coverage_territory', '')
        if raw_value is None:
            return self.LEGACY_COVERAGE_TERRITORY

        value = self._sanitize_excel_text(
            raw_value,
            self.MAX_COVERAGE_TERRITORY_LENGTH,
        )
        if not value:
            return self.MISSING_COVERAGE_TERRITORY
        return value

    def _consolidate_notes(self, offers: List, additional_note: Optional[str] = None,
                           leading_note: Optional[str] = None) -> Optional[str]:
        """
        Объединяет все примечания по годам в единый текст с разделением пробелом

        Пример:
        - Год 1: "тест1"
        - Год 2: "тест2"
        - Год 3: "" (пустое)
        Результат: "тест1 тест2"

        Args:
            offers: Список предложений компании
            additional_note: Дополнительное примечание для экспорта

        Returns:
            Optional[str]: Объединенный текст примечаний или None если нет примечаний
        """
        try:
            logger.debug(f"Консолидируем примечания из {len(offers)} предложений")

            consolidated_parts = []

            # Сортируем предложения по годам для правильного порядка
            sorted_offers = sorted(offers, key=lambda x: getattr(x, 'insurance_year', 0))

            for offer in sorted_offers:
                try:
                    # Получаем примечания из предложения
                    notes = getattr(offer, 'notes', None)

                    if notes:
                        # Преобразуем в строку и очищаем от лишних пробелов
                        notes_str = str(notes).strip()

                        if notes_str:  # Пропускаем пустые примечания
                            # Удаляем потенциально проблемные символы для Excel
                            notes_str = self._sanitize_excel_text(notes_str)
                            notes_str = notes_str.replace('\n', ' ').replace('\r', ' ')

                            # Убираем множественные пробелы
                            notes_str = ' '.join(notes_str.split())

                            if notes_str:  # Проверяем, что после очистки что-то осталось
                                consolidated_parts.append(notes_str)
                                logger.debug(f"Добавлены примечания для года {getattr(offer, 'insurance_year', 'неизвестно')}: {notes_str[:30]}...")
                            else:
                                logger.debug(f"Примечания для года {getattr(offer, 'insurance_year', 'неизвестно')} пусты после очистки")
                        else:
                            logger.debug(f"Примечания для года {getattr(offer, 'insurance_year', 'неизвестно')} пусты")
                    else:
                        logger.debug(f"Примечания отсутствуют для года {getattr(offer, 'insurance_year', 'неизвестно')}")

                except Exception as offer_error:
                    logger.warning(f"Ошибка при обработке примечаний для года {getattr(offer, 'insurance_year', 'неизвестно')}: {offer_error}")
                    continue

            if additional_note:
                additional_note_str = str(additional_note).strip()
                if additional_note_str:
                    additional_note_str = self._sanitize_excel_text(additional_note_str)
                    additional_note_str = additional_note_str.replace('\n', ' ').replace('\r', ' ')
                    additional_note_str = ' '.join(additional_note_str.split())

                    if additional_note_str:
                        has_duplicate = any(part.lower() == additional_note_str.lower() for part in consolidated_parts)
                        if not has_duplicate:
                            consolidated_parts.append(additional_note_str)
                            logger.debug("Добавлено дополнительное примечание по году выпуска в консолидированный текст")

            # Ответы блоков шаблона V2 — первыми, перед примечаниями страховщика
            if leading_note and str(leading_note).strip():
                consolidated_parts.insert(0, ' '.join(self._sanitize_excel_text(leading_note).split()))

            # Объединяем все части с разделением пробелом
            if consolidated_parts:
                consolidated_text = ' '.join(consolidated_parts)

                # Ограничиваем длину для Excel (максимум 32767 символов)
                max_excel_length = 32767
                if len(consolidated_text) > max_excel_length:
                    consolidated_text = consolidated_text[:max_excel_length - 3] + "..."
                    logger.warning(f"Консолидированные примечания обрезаны до {max_excel_length} символов")

                logger.debug(f"Консолидированы примечания: {len(consolidated_parts)} частей, итоговая длина: {len(consolidated_text)}")
                return consolidated_text
            else:
                logger.debug("Нет примечаний для консолидации")
                return None

        except Exception as e:
            logger.error(f"Ошибка при консолидации примечаний: {e}")
            return None

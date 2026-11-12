"""Shared summary data tests retained when retiring the V1 workbook layout."""
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch, call

from django.test import TestCase
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer
from summaries.services.summary_data import SummaryDataService
from summaries.exceptions import ExcelExportServiceError, InvalidSummaryDataError



class SummaryDataValidationTests(TestCase):
    def setUp(self):
        self.service = SummaryDataService()

    def test_validate_summary_data_valid_data(self):
            """Тест валидации корректных данных свода"""
            # Создаем заявку с полными данными
            request = InsuranceRequest.objects.create(
                client_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
                inn='1234567890',
                object_description='б/у грузовой тягач седельный SCANIA R440A4X2NA',
                dfa_number='ТС-19827-ГА-ВН'
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            # Валидация должна пройти без исключений
            try:
                self.service._validate_summary_data(summary)
            except InvalidSummaryDataError:
                self.fail("Валидация корректных данных не должна вызывать исключение")

    def test_validate_summary_data_missing_request(self):
            """Тест валидации свода без связанной заявки"""
            # Создаем мок объекта свода без связанной заявки
            summary = Mock()
            summary.request = None
            summary.id = 999

            with self.assertRaises(InvalidSummaryDataError) as context:
                self.service._validate_summary_data(summary)

            self.assertIn('связанная заявка', str(context.exception))

    def test_validate_summary_data_missing_dfa_number(self):
            """Тест валидации заявки без номера ДФА"""
            request = InsuranceRequest.objects.create(
                client_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
                inn='1234567890',
                object_description='б/у грузовой тягач седельный SCANIA R440A4X2NA',
                dfa_number=''  # Пустой номер ДФА
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            with self.assertRaises(InvalidSummaryDataError) as context:
                self.service._validate_summary_data(summary)

            self.assertIn('номер заявки (dfa_number)', str(context.exception))

    def test_validate_summary_data_missing_vehicle_info(self):
            """Тест валидации заявки без информации о предмете лизинга"""
            request = InsuranceRequest.objects.create(
                client_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
                inn='1234567890',
                object_description='',  # Пустая информация о предмете лизинга
                dfa_number='ТС-19827-ГА-ВН'
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            with self.assertRaises(InvalidSummaryDataError) as context:
                self.service._validate_summary_data(summary)

            self.assertIn('объект страхования (object_summary)', str(context.exception))

    def test_validate_summary_data_accepts_structured_object_without_vehicle_info(self):
            request = InsuranceRequest.objects.create(
                client_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
                inn='1234567890',
                object_description='',
                brand='SCANIA',
                model='R440A4X2NA',
                condition='used',
                dfa_number='ТС-19827-ГА-ВН',
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            self.service._validate_summary_data(summary)

    def test_validate_summary_data_missing_client_name(self):
            """Тест валидации заявки без названия клиента"""
            request = InsuranceRequest.objects.create(
                client_name='',  # Пустое название клиента
                inn='1234567890',
                object_description='б/у грузовой тягач седельный SCANIA R440A4X2NA',
                dfa_number='ТС-19827-ГА-ВН'
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            with self.assertRaises(InvalidSummaryDataError) as context:
                self.service._validate_summary_data(summary)

            self.assertIn('название клиента (client_name)', str(context.exception))

    def test_validate_summary_data_multiple_missing_fields(self):
            """Тест валидации заявки с несколькими отсутствующими полями"""
            request = InsuranceRequest.objects.create(
                client_name='',  # Пустое название клиента
                inn='1234567890',
                object_description='',  # Пустая информация о предмете лизинга
                dfa_number='ТС-19827-ГА-ВН'
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            with self.assertRaises(InvalidSummaryDataError) as context:
                self.service._validate_summary_data(summary)

            error_message = str(context.exception)
            self.assertIn('название клиента (client_name)', error_message)
            self.assertIn('объект страхования (object_summary)', error_message)

    def test_validate_summary_data_whitespace_only_fields(self):
            """Тест валидации заявки с полями, содержащими только пробелы"""
            request = InsuranceRequest.objects.create(
                client_name='   ',  # Только пробелы
                inn='1234567890',
                object_description='б/у грузовой тягач седельный SCANIA R440A4X2NA',
                dfa_number='ТС-19827-ГА-ВН'
            )

            summary = InsuranceSummary.objects.create(
                request=request,
                status='ready'
            )

            with self.assertRaises(InvalidSummaryDataError) as context:
                self.service._validate_summary_data(summary)

            self.assertIn('название клиента (client_name)', str(context.exception))



class SummaryPremiumDataTests(TestCase):
    def setUp(self):
        self.service = SummaryDataService()
        self.offers = []
        for i in range(3):
                    offer = Mock()
                    offer.insurance_year = i + 1
                    offer.premium_with_franchise_1 = Decimal(f'{1000 + i * 100}')  # 1000, 1100, 1200
                    offer.premium_with_franchise_2 = Decimal(f'{500 + i * 50}') if i < 2 else None  # 500, 550, None
                    offer.has_second_franchise_variant.return_value = i < 2  # Только первые два
                    self.offers.append(offer)

    def test_calculate_premium_sum_type_1(self):
            """Тест вычисления суммы премий типа 1"""
            result = self.service._calculate_premium_sum(self.offers, 1)

            # Ожидаем сумму: 1000 + 1100 + 1200 = 3300
            expected = Decimal('3300')
            self.assertEqual(result, expected)

    def test_calculate_premium_sum_type_2(self):
            """Тест вычисления суммы премий типа 2"""
            result = self.service._calculate_premium_sum(self.offers, 2)

            # Ожидаем сумму: 500 + 550 = 1050 (третье предложение не имеет премии-2)
            expected = Decimal('1050')
            self.assertEqual(result, expected)

    def test_calculate_premium_sum_no_valid_premiums(self):
            """Тест вычисления суммы когда нет валидных премий"""
            # Создаем предложения без премий-2
            offers_no_premium_2 = []
            for i in range(2):
                offer = Mock()
                offer.premium_with_franchise_2 = None
                offer.has_second_franchise_variant.return_value = False
                offers_no_premium_2.append(offer)

            with patch.object(self.service, '_format_premium', return_value=None):
                result = self.service._calculate_premium_sum(offers_no_premium_2, 2)

            self.assertIsNone(result)

    def test_calculate_premium_sum_with_errors(self):
            """Тест вычисления суммы с ошибками в данных"""
            # Создаем предложения с ошибками
            offers_with_errors = []
            for i in range(3):
                offer = Mock()
                offer.insurance_year = i + 1
                offers_with_errors.append(offer)

            # Мокаем _format_premium чтобы возвращать ошибки для некоторых предложений
            def mock_format_premium(offer, variant):
                if offer.insurance_year == 2:  # Второе предложение с ошибкой
                    raise Exception("Format error")
                return Decimal('1000') if offer.insurance_year in [1, 3] else None

            with patch.object(self.service, '_format_premium', side_effect=mock_format_premium):
                result = self.service._calculate_premium_sum(offers_with_errors, 1)

            # Ожидаем сумму только валидных предложений: 1000 + 1000 = 2000
            expected = Decimal('2000')
            self.assertEqual(result, expected)



class SummaryCompanyDataTests(TestCase):
    def setUp(self):
        self.service = SummaryDataService()
        self.insurance_request = InsuranceRequest.objects.create(client_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"', inn='1234567890', object_description='б/у грузовой тягач седельный SCANIA R440A4X2NA', dfa_number='ТС-19827-ГА-ВН')
        self.insurance_summary = InsuranceSummary.objects.create(request=self.insurance_request, status='ready')
        self.offer1 = InsuranceOffer.objects.create(summary=self.insurance_summary, company_name='Абсолют', insurance_year=1, insurance_sum=Decimal('1000000'), premium_with_franchise_1=Decimal('50000'), franchise_1=Decimal('10000'), payments_per_year_variant_1=1, installment_variant_1=False)
        self.offer2 = InsuranceOffer.objects.create(summary=self.insurance_summary, company_name='Абсолют', insurance_year=2, insurance_sum=Decimal('800000'), premium_with_franchise_1=Decimal('40000'), franchise_1=Decimal('8000'), premium_with_franchise_2=Decimal('45000'), franchise_2=Decimal('5000'), payments_per_year_variant_1=4, installment_variant_1=True, payments_per_year_variant_2=2, installment_variant_2=True)
        self.offer3 = InsuranceOffer.objects.create(summary=self.insurance_summary, company_name='ВСК', insurance_year=1, insurance_sum=Decimal('1000000'), premium_with_franchise_1=Decimal('55000'), franchise_1=Decimal('15000'), payments_per_year_variant_1=12, installment_variant_1=True, notes='Специальные условия')

    def test_get_companies_sorted_data_success(self):
        """Тест успешного получения отсортированных данных компаний"""
        expected_data = {'Абсолют': [self.offer1, self.offer2], 'ВСК': [self.offer3]}
        with patch.object(self.insurance_summary, 'get_offers_grouped_by_company', return_value=expected_data):
            result = self.service._get_companies_sorted_data(self.insurance_summary)
        self.assertEqual(result, expected_data)

    def test_get_companies_sorted_data_empty_result(self):
        """Тест получения пустых данных компаний"""
        with patch.object(self.insurance_summary, 'get_offers_grouped_by_company', return_value={}):
            result = self.service._get_companies_sorted_data(self.insurance_summary)
        self.assertEqual(result, {})

    def test_get_companies_sorted_data_exception_handling(self):
        """Тест обработки исключений при получении данных компаний"""
        with patch.object(self.insurance_summary, 'get_offers_grouped_by_company', side_effect=Exception('Database error')):
            with self.assertRaises(ExcelExportServiceError) as context:
                self.service._get_companies_sorted_data(self.insurance_summary)
        self.assertIn('Ошибка при получении данных компаний', str(context.exception))

    def test_format_installment_payments_variant_1_no_installment(self):
        """Тест форматирования рассрочки для варианта 1 без рассрочки"""
        offer = Mock()
        offer.payments_per_year_variant_1 = 1
        offer.installment_variant_1 = False
        result = self.service._format_installment_payments(offer, 1)
        self.assertEqual(result, 1)

    def test_format_installment_payments_variant_1_with_installment(self):
        """Тест форматирования рассрочки для варианта 1 с рассрочкой"""
        offer = Mock()
        offer.payments_per_year_variant_1 = 4
        offer.installment_variant_1 = True
        result = self.service._format_installment_payments(offer, 1)
        self.assertEqual(result, 4)

    def test_format_installment_payments_variant_2_with_installment(self):
        """Тест форматирования рассрочки для варианта 2 с рассрочкой"""
        offer = Mock()
        offer.payments_per_year_variant_2 = 12
        offer.installment_variant_2 = True
        result = self.service._format_installment_payments(offer, 2)
        self.assertEqual(result, 12)

    def test_format_installment_payments_none_payments(self):
        """Тест обработки None в количестве платежей"""
        offer = Mock()
        offer.payments_per_year_variant_1 = None
        offer.installment_variant_1 = True
        result = self.service._format_installment_payments(offer, 1)
        self.assertEqual(result, 1)

    def test_format_installment_payments_invalid_variant(self):
        """Тест обработки некорректного номера варианта"""
        offer = Mock()
        with self.assertRaises(ValueError) as context:
            self.service._format_installment_payments(offer, 3)
        self.assertIn('Номер варианта должен быть 1 или 2', str(context.exception))

    def test_format_installment_payments_exception_handling(self):
        """Тест обработки исключений при форматировании рассрочки"""
        offer = Mock()
        offer.payments_per_year_variant_1 = Mock(side_effect=Exception('Attribute error'))
        result = self.service._format_installment_payments(offer, 1)
        self.assertEqual(result, 1)

    def test_validate_companies_data_empty_input(self):
        """Тест обработки пустых данных компаний"""
        result = self.service._validate_companies_data({})
        self.assertEqual(result, {})

    def test_validate_companies_data_company_limit(self):
        """Тест ограничения количества компаний"""
        companies_data = {}
        for i in range(self.service.MAX_COMPANIES_LIMIT + 10):
            company_name = f'Компания_{i:03d}'
            companies_data[company_name] = [Mock()]
        result = self.service._validate_companies_data(companies_data)
        self.assertLessEqual(len(result), self.service.MAX_COMPANIES_LIMIT)

    def test_validate_companies_data_years_limit(self):
        """Тест ограничения количества лет на компанию"""
        offers = []
        for i in range(self.service.MAX_YEARS_PER_COMPANY + 5):
            offer = Mock()
            offer.insurance_year = i + 1
            offers.append(offer)
        companies_data = {'Тест Компания': offers}
        with patch.object(self.service, '_validate_offer_data', return_value=True):
            result = self.service._validate_companies_data(companies_data)
        self.assertLessEqual(len(result['Тест Компания']), self.service.MAX_YEARS_PER_COMPANY)

    def test_validate_offer_data_missing_year(self):
        """Тест валидации предложения без года страхования"""
        offer = Mock()
        offer.insurance_year = None
        result = self.service._validate_offer_data(offer, 'Тест Компания')
        self.assertFalse(result)

    def test_validate_offer_data_invalid_year_range(self):
        """Тест валидации предложения с некорректным годом"""
        offer = Mock()
        offer.insurance_year = 25
        result = self.service._validate_offer_data(offer, 'Тест Компания')
        self.assertFalse(result)

    def test_validate_offer_data_missing_insurance_sum(self):
        """Тест валидации предложения без страховой суммы"""
        offer = Mock()
        offer.insurance_year = 1
        offer.insurance_sum = None
        result = self.service._validate_offer_data(offer, 'Тест Компания')
        self.assertFalse(result)

    def test_validate_offer_data_missing_premium(self):
        """Тест валидации предложения без премии"""
        offer = Mock()
        offer.insurance_year = 1
        offer.insurance_sum = Decimal('1000000')
        offer.premium_with_franchise_1 = None
        result = self.service._validate_offer_data(offer, 'Тест Компания')
        self.assertFalse(result)

    def test_validate_offer_data_valid_offer(self):
        """Тест валидации корректного предложения"""
        offer = Mock()
        offer.insurance_year = 1
        offer.insurance_sum = Decimal('1000000')
        offer.premium_with_franchise_1 = Decimal('50000')
        offer.franchise_1 = Decimal('10000')
        offer.has_second_franchise_variant.return_value = False
        result = self.service._validate_offer_data(offer, 'Тест Компания')
        self.assertTrue(result)

    def test_format_numeric_value_valid_decimal(self):
        """Тест форматирования корректного Decimal значения"""
        result = self.service._format_numeric_value(Decimal('50000.123'), 'премия')
        self.assertEqual(result, Decimal('50000.12'))

    def test_format_numeric_value_string_input(self):
        """Тест форматирования строкового числового значения"""
        result = self.service._format_numeric_value('50 000.50', 'премия')
        self.assertEqual(result, Decimal('50000.50'))

    def test_format_numeric_value_none_input(self):
        """Тест форматирования None значения"""
        result = self.service._format_numeric_value(None, 'премия')
        self.assertIsNone(result)

    def test_format_numeric_value_empty_string(self):
        """Тест форматирования пустой строки"""
        result = self.service._format_numeric_value('', 'премия')
        self.assertIsNone(result)

    def test_format_numeric_value_negative_to_zero(self):
        """Тест преобразования отрицательного значения в ноль"""
        result = self.service._format_numeric_value(Decimal('-1000'), 'премия')
        self.assertEqual(result, Decimal('0'))

    def test_format_numeric_value_excessive_to_max(self):
        """Тест ограничения чрезмерно большого значения"""
        excessive_value = Decimal('2000000000')
        result = self.service._format_numeric_value(excessive_value, 'премия')
        self.assertEqual(result, self.service.MAX_INSURANCE_SUM)

    def test_format_numeric_value_below_minimum(self):
        """Тест обработки значения ниже минимума"""
        small_value = Decimal('0.5')
        result = self.service._format_numeric_value(small_value, 'премия')
        self.assertEqual(result, self.service.MIN_INSURANCE_SUM)

    def test_format_insurance_sum(self):
        """Тест форматирования страховой суммы"""
        offer = Mock()
        offer.insurance_sum = Decimal('1000000')
        result = self.service._format_insurance_sum(offer)
        self.assertEqual(result, Decimal('1000000.00'))

    def test_format_premium_variant_1(self):
        """Тест форматирования премии для варианта 1"""
        offer = Mock()
        offer.premium_with_franchise_1 = Decimal('50000')
        result = self.service._format_premium(offer, 1)
        self.assertEqual(result, Decimal('50000.00'))

    def test_format_premium_variant_2(self):
        """Тест форматирования премии для варианта 2"""
        offer = Mock()
        offer.premium_with_franchise_2 = Decimal('45000')
        result = self.service._format_premium(offer, 2)
        self.assertEqual(result, Decimal('45000.00'))

    def test_format_franchise_variant_1_none_to_zero(self):
        """Тест форматирования франшизы варианта 1: None -> 0"""
        offer = Mock()
        offer.franchise_1 = None
        result = self.service._format_franchise(offer, 1)
        self.assertEqual(result, Decimal('0'))

    def test_format_franchise_variant_2_none_to_zero(self):
        """Тест форматирования франшизы варианта 2: None -> 0.

            Вызов _format_franchise(offer, 2) выполняется только под охраной
            has_second_franchise_variant(), поэтому None во франшизе-2 трактуется
            как 0 (по аналогии с variant 1).
            """
        offer = Mock()
        offer.franchise_2 = None
        result = self.service._format_franchise(offer, 2)
        self.assertEqual(result, Decimal('0'))

    def test_format_franchise_valid_value(self):
        """Тест форматирования корректного значения франшизы"""
        offer = Mock()
        offer.franchise_1 = Decimal('10000')
        result = self.service._format_franchise(offer, 1)
        self.assertEqual(result, Decimal('10000.00'))

    def test_get_franchise_approval_note_for_company_with_non_zero_franchise(self):
        """Для компании с ненулевой франшизой добавляется системный комментарий"""
        result = self.service._get_franchise_approval_note_for_company([self.offer3], 'ВСК')
        self.assertEqual(result, self.service.FRANCHISE_APPROVAL_ADDITIONAL_NOTE)

    def test_get_franchise_approval_note_for_company_with_zero_franchise_only(self):
        """Для компании с нулевой франшизой системный комментарий не добавляется"""
        offer = Mock()
        offer.franchise_1 = Decimal('0')
        offer.franchise_2 = None
        result = self.service._get_franchise_approval_note_for_company([offer], 'Тест')
        self.assertIsNone(result)

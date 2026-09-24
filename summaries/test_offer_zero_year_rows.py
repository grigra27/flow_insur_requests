"""
Строки лет с нулями в ответе страховщика.

Страховщики оставляют номер года, но ставят 0 (или ничего) в сумме и премии
для лет, которые не предлагают. Раньше такой год доходил до create_offers,
Decimal('0.00') превращался в None, и весь файл падал с
"insurance_sum: Это поле не может иметь значение NULL".
"""
from decimal import Decimal

from django.test import TestCase

from insurance_requests.models import InsuranceRequest
from summaries.exceptions import MissingDataError
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from summaries.services.excel_services import ExcelResponseProcessor


class MockCell:
    def __init__(self, value=None):
        self.value = value


class MockWorksheet:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, cell_address):
        return MockCell(self.values.get(cell_address))


def _year_row(row, year, insurance_sum, premium):
    return {
        f'A{row}': year,
        f'B{row}': insurance_sum,
        f'D{row}': premium,
        f'E{row}': 0,
        f'F{row}': 1,
    }


class ZeroYearRowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        InsuranceCompany.objects.get_or_create(
            name='Ингосстрах',
            defaults={'display_name': 'Ингосстрах', 'sort_order': 1, 'is_active': True},
        )
        request = InsuranceRequest.objects.create(
            client_name='ООО Тест',
            inn='1234567890',
            dfa_number='ТЕСТ-0',
            vehicle_info='Полуприцеп',
        )
        cls.summary = InsuranceSummary.objects.create(request=request, status='collecting')

    def _worksheet(self, *rows):
        values = {'B2': 'Ингосстрах'}
        for row in rows:
            values.update(row)
        return MockWorksheet(values)

    def _import(self, worksheet):
        processor = ExcelResponseProcessor()
        data = processor.extract_company_data(worksheet)
        processor.validate_extracted_data(data)
        return processor.create_offers(data, self.summary)

    def test_year_with_zero_sum_and_premium_is_skipped(self):
        # Реальный кейс с прода (сводка 303): 3-й год заполнен нулями
        worksheet = self._worksheet(
            _year_row(6, 1, 5_790_000, 91_193),
            _year_row(7, 2, 4_632_000, 91_193),
            _year_row(8, 3, 0, 0),
        )

        offers = self._import(worksheet)

        self.assertEqual(sorted(o.insurance_year for o in offers), [1, 2])
        self.assertEqual(InsuranceOffer.objects.filter(summary=self.summary).count(), 2)

    def test_zero_as_text_is_treated_as_zero(self):
        worksheet = self._worksheet(
            _year_row(6, 1, '1 000 000,00', '50 000,00'),
            _year_row(7, 2, '0,00', '0'),
        )

        offers = self._import(worksheet)

        self.assertEqual([o.insurance_year for o in offers], [1])

    def test_year_with_empty_sum_and_premium_is_skipped(self):
        worksheet = self._worksheet(
            _year_row(6, 1, 1_000_000, 50_000),
            _year_row(7, 2, None, None),
        )

        processor = ExcelResponseProcessor()
        data = processor.extract_company_data(worksheet)

        self.assertEqual([y['year'] for y in data['years']], [1])
        self.assertEqual(data['processing_info']['processing_errors'], [])

    def test_zero_premium_with_nonzero_sum_is_row_error(self):
        worksheet = self._worksheet(
            _year_row(6, 1, 1_000_000, 50_000),
            _year_row(7, 2, 900_000, 0),
        )

        processor = ExcelResponseProcessor()
        data = processor.extract_company_data(worksheet)

        self.assertEqual([y['year'] for y in data['years']], [1])
        errors = data['processing_info']['processing_errors']
        self.assertEqual(len(errors), 1)
        self.assertIn('D7', errors[0])
        self.assertIn('нулевое значение', errors[0])

    def test_zero_sum_with_nonzero_premium_is_row_error(self):
        worksheet = self._worksheet(
            _year_row(6, 1, 1_000_000, 50_000),
            _year_row(7, 2, 0, 45_000),
        )

        processor = ExcelResponseProcessor()
        data = processor.extract_company_data(worksheet)

        self.assertEqual([y['year'] for y in data['years']], [1])
        self.assertIn('B7', data['processing_info']['processing_errors'][0])

    def test_all_years_zero_reports_missing_data(self):
        worksheet = self._worksheet(
            _year_row(6, 1, 0, 0),
            _year_row(7, 2, 0, 0),
        )

        with self.assertRaises(MissingDataError):
            ExcelResponseProcessor().extract_company_data(worksheet)

    def test_offer_values_are_preserved(self):
        worksheet = self._worksheet(
            _year_row(6, 1, 5_790_000, 91_193),
            _year_row(7, 2, 0, 0),
        )

        offer = self._import(worksheet)[0]

        self.assertEqual(offer.insurance_sum, Decimal('5790000.00'))
        self.assertEqual(offer.premium_with_franchise_1, Decimal('91193.00'))

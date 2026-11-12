"""Regression: percent-formatted rates must store a fraction, with cached values."""
from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from summaries.services.summary_export_v2 import SummaryExportV2Service


class RateExportInvariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        InsuranceCompany.objects.get_or_create(name='Абсолют', defaults={'display_name': 'Абсолют', 'sort_order': 1, 'is_active': True})
        request = InsuranceRequest.objects.create(client_name='ООО Тариф', inn='1234567890', dfa_number='ТС-20276-ЛА-ПС', object_description='Haval F7X')
        cls.summary = InsuranceSummary.objects.create(request=request, status='ready')
        for (year, insurance_sum) in ((1, '3549000'), (2, '3016650'), (3, '2564153')):
            InsuranceOffer.objects.create(summary=cls.summary, company_name='Абсолют', insurance_year=year, insurance_sum=Decimal(insurance_sum), franchise_1=Decimal('0'), premium_with_franchise_1=Decimal('70980'), franchise_2=Decimal('50000'), premium_with_franchise_2=Decimal('60000'))

    def _assert_rates(self):
        for client in (False, True):
            data = SummaryExportV2Service().generate(self.summary, is_client_version=client).getvalue()
            formulas = load_workbook(BytesIO(data))
            values = load_workbook(BytesIO(data), data_only=True)
            rates = []
            for sheet in formulas:
                for row in sheet:
                    for cell in row:
                        if not (isinstance(cell.value, str) and cell.value.startswith('=') and '%' in cell.number_format):
                            continue
                        self.assertNotIn('*100', cell.value.replace(' ', ''))
                        cached = values[sheet.title][cell.coordinate].value
                        self.assertIsInstance(cached, (float, int))
                        self.assertGreater(cached, 0)
                        self.assertLess(cached, 1)
                        rates.append(cached)
            self.assertGreaterEqual(len(rates), 3)
            self.assertTrue(any(abs(rate - 0.02) < 1e-12 for rate in rates))

    def test_two_variants_client_and_full_rates(self):
        self._assert_rates()

    def test_single_variant_client_and_full_rates(self):
        InsuranceOffer.objects.filter(summary=self.summary).update(
            premium_with_franchise_2=None, franchise_2=None)
        self._assert_rates()

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.forms import AddOfferToSummaryForm, OfferForm
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from summaries.services.excel_services import ExcelExportService, ExcelResponseProcessor


class MockCell:
    def __init__(self, value=None):
        self.value = value


class MockWorksheet:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, cell_address):
        return MockCell(self.values.get(cell_address))


class OfferCoverageTerritoryImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        InsuranceCompany.objects.get_or_create(
            name='Абсолют',
            defaults={
                'display_name': 'Абсолют',
                'sort_order': 1,
                'is_active': True,
            },
        )
        request = InsuranceRequest.objects.create(
            client_name='ООО Тест',
            inn='1234567890',
            dfa_number='ТЕСТ-1',
            vehicle_info='Тестовый объект',
        )
        cls.summary = InsuranceSummary.objects.create(request=request, status='collecting')

    def _worksheet(self, territory=None):
        return MockWorksheet({
            'B2': 'Абсолют',
            'B3': territory,
            'A6': 1,
            'B6': 1_000_000,
            'D6': 50_000,
            'E6': 0,
            'F6': 1,
            'A7': 2,
            'B7': 900_000,
            'D7': 45_000,
            'E7': 0,
            'F7': 1,
        })

    def test_import_copies_common_territory_to_every_year(self):
        processor = ExcelResponseProcessor()
        data = processor.extract_company_data(
            self._worksheet('Российская Федерация, кроме новых территорий')
        )

        offers = processor.create_offers(data, self.summary)

        self.assertEqual(len(offers), 2)
        self.assertEqual(
            {offer.coverage_territory for offer in offers},
            {'Российская Федерация, кроме новых территорий'},
        )

    def test_old_response_without_territory_remains_supported(self):
        processor = ExcelResponseProcessor()

        data = processor.extract_company_data(self._worksheet())

        self.assertEqual(data['coverage_territory'], '')
        offers = processor.create_offers(data, self.summary)
        self.assertTrue(all(offer.coverage_territory == '' for offer in offers))


class OfferCoverageTerritoryExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        request = InsuranceRequest.objects.create(
            client_name='ООО Экспорт',
            inn='1234567890',
            dfa_number='ТЕСТ-2',
            vehicle_info='Складской комплекс',
            insurance_type='страхование имущества',
            insurance_territory='Российская Федерация',
        )
        cls.summary = InsuranceSummary.objects.create(request=request, status='ready')
        cls.offer1 = InsuranceOffer.objects.create(
            summary=cls.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000'),
            franchise_2=Decimal('50000'),
            premium_with_franchise_2=Decimal('45000'),
            coverage_territory='Российская Федерация',
        )
        cls.offer2 = InsuranceOffer.objects.create(
            summary=cls.summary,
            company_name='Абсолют',
            insurance_year=2,
            insurance_sum=Decimal('900000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('45000'),
            franchise_2=Decimal('50000'),
            premium_with_franchise_2=Decimal('40000'),
            coverage_territory='Российская Федерация',
        )

    def setUp(self):
        self.service = ExcelExportService(
            Path(settings.BASE_DIR) / 'templates' / 'summary_template.xlsx'
        )

    def _generate(self, is_client_version=False):
        return load_workbook(
            self.service.generate_summary_excel(
                self.summary,
                is_client_version=is_client_version,
            )
        )

    def test_all_four_exports_contain_coverage_territory(self):
        for is_client_version in (False, True):
            workbook = self._generate(is_client_version)
            sheet = workbook['summary_template_sheet']
            self.assertEqual(sheet['P10'].value, 'Российская Федерация')
            self.assertIn('P10:P11', {str(cell_range) for cell_range in sheet.merged_cells.ranges})
            if not is_client_version:
                self.assertEqual(
                    workbook['tech_info']['A27'].value,
                    'Территория по исходной заявке:',
                )
                self.assertEqual(workbook['tech_info']['B27'].value, 'Российская Федерация')

        InsuranceOffer.objects.filter(summary=self.summary).update(
            premium_with_franchise_2=None,
            franchise_2=None,
        )
        for is_client_version in (False, True):
            workbook = self._generate(is_client_version)
            sheet = workbook['summary_template_sheet']
            self.assertEqual(sheet['J10'].value, 'Российская Федерация')
            self.assertIn('J10:J11', {str(cell_range) for cell_range in sheet.merged_cells.ranges})

    def test_different_territories_are_not_merged(self):
        self.offer2.coverage_territory = 'Российская Федерация и Республика Беларусь'
        self.offer2.save(update_fields=['coverage_territory'])

        sheet = self._generate()['summary_template_sheet']

        self.assertNotIn('P10:P11', {str(cell_range) for cell_range in sheet.merged_cells.ranges})
        self.assertEqual(sheet['P10'].value, 'Российская Федерация')
        self.assertEqual(
            sheet['P11'].value,
            'Российская Федерация и Республика Беларусь',
        )

    def test_missing_territory_is_explicit_in_export(self):
        InsuranceOffer.objects.filter(summary=self.summary).update(coverage_territory='')

        sheet = self._generate()['summary_template_sheet']

        self.assertEqual(sheet['P10'].value, 'Не указано страховщиком')
        self.assertIn('P10:P11', {str(cell_range) for cell_range in sheet.merged_cells.ranges})


class OfferCoverageTerritoryInterfaceAndTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        group = Group.objects.create(name='Пользователи')
        cls.user = User.objects.create_user(username='territory-user', password='testpass')
        cls.user.groups.add(group)
        request = InsuranceRequest.objects.create(
            client_name='ООО Интерфейс',
            inn='1234567890',
            dfa_number='ТЕСТ-3',
            vehicle_info='Тестовый объект',
            created_by=cls.user,
        )
        cls.summary = InsuranceSummary.objects.create(request=request, status='collecting')
        cls.offer = InsuranceOffer.objects.create(
            summary=cls.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000'),
        )

    def test_forms_expose_optional_coverage_territory(self):
        for form in (OfferForm(), AddOfferToSummaryForm()):
            self.assertIn('coverage_territory', form.fields)
            self.assertFalse(form.fields['coverage_territory'].required)

    def test_summary_page_warns_when_territory_is_missing(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Не указано страховщиком')

    def test_real_templates_have_new_cells_and_safe_rate_formulas(self):
        templates_dir = Path(settings.BASE_DIR) / 'templates'
        response_template = load_workbook(templates_dir / 'flow_answer_template.xlsx')
        response_sheet = response_template['1']
        self.assertEqual(response_sheet['A3'].value, 'Территория страхования')
        self.assertIn('B3:C3', {str(cell_range) for cell_range in response_sheet.merged_cells.ranges})
        self.assertIsNone(response_sheet['B3'].value)

        expected = (
            ('summary_template.xlsx', 'P'),
            ('client_summary_template.xlsx', 'P'),
            ('summary_template_simplified.xlsx', 'J'),
            ('client_summary_template_simplified.xlsx', 'J'),
        )
        for filename, territory_column in expected:
            workbook = load_workbook(templates_dir / filename, data_only=False)
            sheet = workbook['summary_template_sheet']
            self.assertEqual(
                sheet[f'{territory_column}8'].value,
                'Территория страхования',
            )
            self.assertEqual(
                sheet['E10'].value,
                '=IF(AND(C10<>0,F10<>0),F10/C10*100,"")',
            )

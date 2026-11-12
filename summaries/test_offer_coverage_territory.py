from decimal import Decimal
from io import BytesIO
import importlib
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.forms import AddOfferToSummaryForm, OfferForm
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary, InsurerResponse
from summaries.exceptions import MissingDataError
from summaries.services.excel_services import ExcelResponseProcessor
from summaries.services.summary_export_v2 import SummaryExportV2Service


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
            object_description='Тестовый объект',
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

    def test_import_keeps_common_territory_once_per_company(self):
        from summaries.services.insurer_response import save_upload_company_fields

        processor = ExcelResponseProcessor()
        data = processor.extract_company_data(
            self._worksheet('Российская Федерация, кроме новых территорий')
        )

        offers = processor.create_offers(data, self.summary)
        save_upload_company_fields(self.summary.pk, data['company_name'], data['coverage_territory'], '')

        self.assertEqual(len(offers), 2)
        response = InsurerResponse.objects.get(summary=self.summary, company_name='Абсолют')
        self.assertEqual(response.coverage_territory, 'Российская Федерация, кроме новых территорий')
        # годовые строки — архив, территория в них не пишется
        self.assertEqual({offer.coverage_territory for offer in offers}, {''})

    def test_response_without_territory_is_rejected(self):
        processor = ExcelResponseProcessor()
        for territory in (None, '', '   ', '-', '—'):
            with self.subTest(territory=territory):
                with self.assertRaises(MissingDataError) as ctx:
                    processor.extract_company_data(self._worksheet(territory))
                message = str(ctx.exception)
                self.assertIn('не заполнена территория страхования (ячейка B3)', message)
                self.assertIn('Абсолют', message)
                self.assertIn('Запросите у страховой компании корректное предложение', message)
        self.assertFalse(InsuranceOffer.objects.filter(summary=self.summary).exists())


class OfferCoverageTerritoryExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        request = InsuranceRequest.objects.create(
            client_name='ООО Экспорт',
            inn='1234567890',
            dfa_number='ТЕСТ-2',
            object_description='Складской комплекс',
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
        )
        cls._territory('Российская Федерация')

    @classmethod
    def _territory(cls, value, **fields):
        InsurerResponse.objects.filter(summary=cls.summary, company_name='Абсолют').update(
            coverage_territory=value, **fields)

    def setUp(self):
        self.service = SummaryExportV2Service()

    def _generate(self, is_client_version=False):
        return load_workbook(self.service.generate(self.summary, is_client_version=is_client_version))

    def test_all_four_exports_contain_coverage_territory(self):
        for dual in (True, False):
            if not dual:
                InsuranceOffer.objects.filter(summary=self.summary).update(premium_with_franchise_2=None, franchise_2=None)
            for client in (False, True):
                with self.subTest(dual=dual, client=client):
                    workbook = self._generate(client)
                    sheet = workbook['Свод']
                    column = 'N' if dual else 'I'
                    self.assertEqual(sheet[f'{column}11'].value, 'Российская Федерация')
                    self.assertIn(f'{column}11:{column}12', {str(r) for r in sheet.merged_cells.ranges})
                    self.assertEqual(workbook.sheetnames, ['Свод'] if client else ['Свод', 'Параметры запроса'])

    def test_company_territory_is_one_merged_cell(self):
        # Территория одна на СК в своде («Ответ СК») — одна объединённая ячейка на все годы
        self._territory('Российская Федерация и Республика Беларусь')

        sheet = self._generate()['Свод']

        self.assertIn('N11:N12', {str(cell_range) for cell_range in sheet.merged_cells.ranges})
        self.assertEqual(sheet['N11'].value, 'Российская Федерация и Республика Беларусь')

    def test_missing_territory_is_explicit_in_export(self):
        self._territory('')

        sheet = self._generate()['Свод']

        self.assertEqual(sheet['N11'].value, 'Не указано страховщиком')
        self.assertIn('N11:N12', {str(cell_range) for cell_range in sheet.merged_cells.ranges})

    def test_legacy_territory_is_distinct_from_explicitly_missing(self):
        self._territory(None)

        sheet = self._generate()['Свод']

        self.assertEqual(sheet['N11'].value, '—')
        self.assertIn('N11:N12', {str(cell_range) for cell_range in sheet.merged_cells.ranges})

    def test_notes_once_per_company_in_first_year_row(self):
        self._territory('РФ', notes='Осмотр обязателен')

        sheet = self._generate()['Свод']

        notes_column = next(cell.column_letter for cell in sheet[9] if cell.value == 'Комментарии')
        self.assertTrue(sheet[f'{notes_column}11'].value.startswith('Осмотр обязателен'))
        self.assertNotIn('Осмотр обязателен', sheet[f'{notes_column}12'].value or '')

    def test_export_sanitizes_illegal_characters_and_preserves_long_text(self):
        self.offer2.delete()
        self._territory('Россия\x03\x08\x0b\x0e\x1f\r\n' + 'А' * 2500,
                        notes='Комментарий\x03\x08\x0b\x0e\x1f ' + 'Б' * 1100)
        sheet = self._generate()['Свод']
        text = '\n'.join(str(c.value) for row in sheet for c in row if c.value is not None)
        self.assertIn('Россия\n', text)
        self.assertIn('А' * 2500, text)
        self.assertIn('Б' * 1100, text)
        self.assertNotRegex(text, r'[\x00-\x08\x0b-\x0c\x0e-\x1f]')



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
            object_description='Тестовый объект',
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
        InsurerResponse.objects.filter(summary=self.summary).update(coverage_territory=None)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Нет данных: предложение создано до сбора территории')
        self.assertContains(response, 'Скачать актуальный шаблон ответа')

    def test_summary_page_distinguishes_explicitly_missing_territory(self):
        InsurerResponse.objects.filter(summary=self.summary).update(coverage_territory='')
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        )

        self.assertContains(response, 'Не указано страховщиком')

    def test_data_migration_marks_old_blank_values_as_legacy_only(self):
        from django.apps import apps as django_apps

        migration = importlib.import_module(
            'summaries.migrations.0020_insuranceoffer_legacy_coverage_territory'
        )
        migration.mark_legacy_territory_as_unknown(django_apps, None)
        self.offer.refresh_from_db()
        self.assertIsNone(self.offer.coverage_territory)

        new_offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=6,
            insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000'),
        )
        self.assertEqual(new_offer.coverage_territory, '')

    def test_current_response_template_can_be_downloaded(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('summaries:download_company_response_template')
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ))
        self.assertIn('flow_answer_template.xlsx', response['Content-Disposition'])
        workbook = load_workbook(BytesIO(b''.join(response.streaming_content)))
        sheet = workbook.active
        self.assertEqual(sheet['A3'].value, 'Территория страхования')
        self.assertIn('B3:J3', {str(cell_range) for cell_range in sheet.merged_cells.ranges})

    def test_response_template_download_requires_authentication(self):
        response = self.client.get(
            reverse('summaries:download_company_response_template')
        )

        self.assertEqual(response.status_code, 302)

    def _offer_form_data(self, insurance_year, territory):
        return {
            'company_name': 'Абсолют',
            'insurance_year': insurance_year,
            'insurance_sum': '1000000',
            'franchise_1': '0',
            'premium_with_franchise_1': '50000',
            'franchise_2': '',
            'premium_with_franchise_2': '',
            'payments_per_year_variant_1': '1',
            'payments_per_year_variant_2': '1',
            'coverage_territory': territory,
            'notes': '',
        }

    def _response_file(self, year, territory):
        workbook = load_workbook(
            Path(settings.BASE_DIR) / 'templates' / 'flow_answer_template.xlsx'
        )
        sheet = workbook.active
        sheet['B2'] = 'Абсолют'
        sheet['B3'] = territory
        sheet['A6'] = year
        sheet['B6'] = 1_000_000
        sheet['D6'] = 50_000
        sheet['E6'] = 0
        sheet['F6'] = 1
        output = BytesIO()
        workbook.save(output)
        return SimpleUploadedFile(
            f'absolute-{year}.xlsx',
            output.getvalue(),
            content_type=(
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ),
        )

    def test_manual_add_edit_and_copy_preserve_territory(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse('summaries:add_offer', args=[self.summary.pk]),
            self._offer_form_data(2, 'Россия и Беларусь'),
        )
        self.assertEqual(add_response.status_code, 302)
        added_offer = InsuranceOffer.objects.get(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=2,
        )
        def territory():
            return InsurerResponse.objects.get(summary=self.summary, company_name='Абсолют').coverage_territory

        self.assertEqual(territory(), 'Россия и Беларусь')

        edit_response = self.client.post(
            reverse('summaries:edit_offer', args=[added_offer.pk]),
            self._offer_form_data(2, 'Российская Федерация'),
        )
        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(territory(), 'Российская Федерация')

        copy_response = self.client.post(
            reverse('summaries:copy_offer', args=[added_offer.pk]),
            self._offer_form_data(3, 'Российская Федерация, кроме Крыма'),
        )
        self.assertEqual(copy_response.status_code, 302)
        self.assertTrue(InsuranceOffer.objects.filter(summary=self.summary, company_name='Абсолют',
                                                      insurance_year=3).exists())
        self.assertEqual(territory(), 'Российская Федерация, кроме Крыма')
        # годовые строки — архив: формы его не пишут
        self.assertFalse(InsuranceOffer.objects.filter(summary=self.summary).exclude(coverage_territory='').exists())

    def test_multiple_upload_endpoint_returns_territory_metadata(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                'summaries:upload_multiple_company_responses',
                args=[self.summary.pk],
            ),
            {'excel_files': [self._response_file(4, 'Российская Федерация')]},
        )

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content)['results'][0]
        self.assertTrue(result['success'])
        self.assertEqual(result['coverage_territory'], 'Российская Федерация')
        self.assertNotIn('coverage_territory_missing', result)
        self.assertEqual(
            InsurerResponse.objects.get(summary=self.summary, company_name='Абсолют').coverage_territory,
            'Российская Федерация',
        )

        missing_response = self.client.post(
            reverse(
                'summaries:upload_multiple_company_responses',
                args=[self.summary.pk],
            ),
            {'excel_files': [self._response_file(5, None)]},
        )
        missing_result = json.loads(missing_response.content)['results'][0]
        self.assertFalse(missing_result['success'])
        self.assertIn('не заполнена территория страхования', missing_result['error_message'])
        self.assertFalse(InsuranceOffer.objects.filter(
            summary=self.summary, company_name='Абсолют', insurance_year=5,
        ).exists())

    def test_insurer_response_template_has_coverage_territory(self):
        templates_dir = Path(settings.BASE_DIR) / 'templates'
        response_template = load_workbook(templates_dir / 'flow_answer_template.xlsx')
        response_sheet = response_template.active
        self.assertEqual(response_sheet['A3'].value, 'Территория страхования')
        self.assertIn('B3:J3', {str(cell_range) for cell_range in response_sheet.merged_cells.ranges})
        self.assertIsNone(response_sheet['B3'].value)

"""Монтаж/демонтаж самой спецтехники: независимый от СМР сквозной блок V2.

Только синтетические заявки. Дата фиксирована, проверки не зависят от времени запуска тестов.
"""
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from core.templates import EmailTemplateGenerator
from insurance_requests.models import InsuranceRequest
from summaries.equipment_assembly import FIELDS, EquipmentAssemblyError, clean_values
from summaries.exceptions import MissingDataError
from summaries.models import InsuranceOffer, InsuranceSummary, InsurerResponse
from summaries.response_sections import EQUIPMENT_ASSEMBLY, EQUIPMENT_ASSEMBLY_CHOICES, SMR, required_sections
from summaries.response_template import build_v1, build_v2
from summaries.services.excel_services import ExcelResponseProcessor
from summaries.services.insurer_response import display_lines, save_response, update_from_form, v2_strict
from summaries.services.summary_export_v2 import SummaryExportV2Service

SINCE = '2026-11-10'
AFTER = timezone.make_aware(datetime(2026, 11, 10, 12))
BEFORE = timezone.make_aware(datetime(2026, 11, 9, 12))
TYPE = 'страхование спецтехники'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _cell(wb, field):
    sheet, ref = next(wb.defined_names[f'resp_{field}'].destinations)
    return wb[sheet][ref.replace('$', '')]


def _values(status='included', **extra):
    return {'equipment_assembly_status': status, **{f'equipment_assembly_{k}': v for k, v in extra.items()}}


@override_settings(EQUIPMENT_ASSEMBLY_SINCE=SINCE)
class AssemblyRulesTests(SimpleTestCase):
    def test_required_for_exact_type_since_release(self):
        for kind in (TYPE, 'КАСКО', 'страхование имущества', 'другое', TYPE + ' '):
            for created in (BEFORE, AFTER, None):
                with self.subTest(kind=kind, created=created):
                    req = SimpleNamespace(insurance_type=kind, created_at=created)
                    self.assertEqual(EQUIPMENT_ASSEMBLY.is_required(req), kind == TYPE and created != BEFORE)

    def test_date_boundary_uses_moscow_date(self):
        req = SimpleNamespace(insurance_type=TYPE, created_at=datetime(2026, 11, 9, 21, tzinfo=dt_timezone.utc))
        self.assertTrue(EQUIPMENT_ASSEMBLY.is_required(req))
        req.created_at = datetime(2026, 11, 9, 20, 59, tzinfo=dt_timezone.utc)
        self.assertFalse(EQUIPMENT_ASSEMBLY.is_required(req))

    @override_settings(EQUIPMENT_ASSEMBLY_SINCE='2026-11-11')
    def test_date_is_configurable(self):
        self.assertFalse(EQUIPMENT_ASSEMBLY.is_required(SimpleNamespace(insurance_type=TYPE, created_at=AFTER)))

    def test_independent_of_smr(self):
        req = SimpleNamespace(insurance_type=TYPE, created_at=AFTER, has_construction_work=False)
        self.assertIn(EQUIPMENT_ASSEMBLY, required_sections(req))
        self.assertNotIn(SMR, required_sections(req))
        req.has_construction_work = True
        self.assertIn(EQUIPMENT_ASSEMBLY, required_sections(req))
        self.assertIn(SMR, required_sections(req))

    def test_choice_labels_safe_for_xlsx(self):
        labels = [label for _, label in EQUIPMENT_ASSEMBLY_CHOICES]
        self.assertLessEqual(len(','.join(labels)), 255)
        self.assertTrue(all(',' not in label for label in labels))


class AssemblyEmailTests(SimpleTestCase):
    def test_all_new_equipment_letters_request_coverage_without_input_flag(self):
        for v2 in (False, True):
            with self.subTest(v2=v2), override_settings(RESPONSE_TEMPLATE_V2_FOR_ALL=v2):
                body = EmailTemplateGenerator().generate_email_body({'insurance_type': TYPE})
                self.assertIn('Монтаж/демонтаж спецтехники.', body)
                self.assertIn('повреждения или гибели застрахованной спецтехники', body)
                self.assertIn('монтажа, демонтажа, сборки и разборки', body)
                self.assertIn('тариф или размер дополнительной страховой премии', body)
                self.assertEqual('«Ответ страховщика»' in body, v2)

    def test_other_types_have_no_new_requirement(self):
        for kind in ('КАСКО', 'страхование имущества', 'другое', TYPE + ' '):
            with self.subTest(kind=kind):
                self.assertNotIn('Монтаж/демонтаж спецтехники', EmailTemplateGenerator().generate_email_body({'insurance_type': kind}))

    def test_repeated_generation_has_one_paragraph_and_leaves_smr_intact(self):
        generator = EmailTemplateGenerator()
        data = {'insurance_type': TYPE, 'has_construction_work': True, 'has_transportation': True}
        first = generator.generate_email_body(data)
        self.assertEqual(first, generator.generate_email_body(data))
        self.assertEqual(first.count('Монтаж/демонтаж спецтехники.'), 1)
        self.assertIn('требуется страхование монтажных (строительно-монтажных) работ', first)
        self.assertIn('с погрузкой, выгрузкой', first)

    def test_custom_old_template_also_gets_requirement_once(self):
        generator = EmailTemplateGenerator()
        generator.template = 'Коллеги!\nЗаранее благодарим.'
        self.assertEqual(generator.generate_email_body({'insurance_type': TYPE}).count('Монтаж/демонтаж спецтехники.'), 1)


@override_settings(EQUIPMENT_ASSEMBLY_SINCE=SINCE)
class AssemblyTemplateTests(SimpleTestCase):
    def _request(self, kind=TYPE, created=AFTER):
        return SimpleNamespace(insurance_type=kind, created_at=created)

    def test_equipment_template_has_required_unlocked_block(self):
        wb = load_workbook(BytesIO(build_v2(self._request())))
        ws = wb['Ответ СК']
        row = next(c.row for row in ws for c in row if c.value == EQUIPMENT_ASSEMBLY.title)
        self.assertIn('ЗАПОЛНИТЕ', ws[f'G{row}'].value)
        for name in FIELDS:
            self.assertIsNone(_cell(wb, name).value)
            self.assertFalse(_cell(wb, name).protection.locked)
        status = _cell(wb, FIELDS[0])
        dv = next(d for d in ws.data_validations.dataValidation if status.coordinate in d)
        self.assertEqual(dv.formula1.strip('"').split(','), [label for _, label in EQUIPMENT_ASSEMBLY_CHOICES])
        self.assertIn('%', _cell(wb, 'equipment_assembly_rate').number_format)
        self.assertEqual(wb['_meta']['B1'].value, 2)

    def test_non_equipment_and_old_request_do_not_require_block(self):
        for req in (self._request('КАСКО'), self._request('страхование имущества'), self._request(created=BEFORE)):
            with self.subTest(req=req):
                wb = load_workbook(BytesIO(build_v2(req)))
                cell = _cell(wb, FIELDS[0])
                self.assertEqual(cell.value, '—')
                self.assertTrue(cell.protection.locked)

    def test_generic_template_contains_condition_and_open_inputs(self):
        wb = load_workbook(BytesIO(build_v2()))
        text = ' '.join(str(c.value) for row in wb['Ответ СК'] for c in row if c.value)
        self.assertIn(EQUIPMENT_ASSEMBLY.condition_text, text)
        self.assertIn('порядок/база начисления', text)
        self.assertFalse(_cell(wb, FIELDS[0]).protection.locked)

    def test_base_addresses_and_v1_stay_compatible(self):
        old = load_workbook(BytesIO(build_v1())).active
        new = load_workbook(BytesIO(build_v2(self._request()))).active
        for row in range(2, 11):
            for col in range(1, 11):
                self.assertEqual(old.cell(row, col).value, new.cell(row, col).value)
        self.assertEqual({str(r) for r in old.merged_cells.ranges if r.max_row <= 10},
                         {str(r) for r in new.merged_cells.ranges if r.max_row <= 10})


class AssemblyValidationTests(SimpleTestCase):
    def test_separate_rate_and_basis(self):
        result = clean_values(_values('separate', rate='0,125%', cost_basis='От страховой суммы за год'))
        self.assertEqual(result['equipment_assembly_rate'], Decimal('0.125'))

    def test_separate_premium_and_basis(self):
        result = clean_values(_values('separate', cost='15 000,25 ₽', cost_basis='За одну операцию'))
        self.assertEqual(result['equipment_assembly_cost'], Decimal('15000.25'))

    def test_both_prices_retained(self):
        result = clean_values(_values('separate', rate='0.15', cost='15000', cost_basis='За год от СС 10 млн'))
        self.assertEqual((result['equipment_assembly_rate'], result['equipment_assembly_cost']), (Decimal('.15'), Decimal('15000')))

    def test_separate_requires_positive_number(self):
        for values in (_values('separate'), _values('separate', rate=0, cost=0, cost_basis='За год')):
            with self.subTest(values=values), self.assertRaisesMessage(EquipmentAssemblyError, 'положительный'):
                clean_values(values)

    def test_separate_requires_basis(self):
        with self.assertRaisesMessage(EquipmentAssemblyError, 'порядок и базу'):
            clean_values(_values('separate', cost=15000))

    def test_not_applicable_requires_reason(self):
        for terms in ('', '—', '...'):
            with self.subTest(terms=terms), self.assertRaisesMessage(EquipmentAssemblyError, 'причину'):
                clean_values(_values('not_applicable', terms=terms))

    def test_other_statuses_clear_old_cost_and_basis(self):
        for status in ('included', 'declined', 'not_applicable'):
            with self.subTest(status=status):
                result = clean_values(_values(status, rate='.15', cost='15000', cost_basis='За год', terms='Причина / условия'))
                self.assertIsNone(result['equipment_assembly_rate'])
                self.assertIsNone(result['equipment_assembly_cost'])
                self.assertEqual(result['equipment_assembly_cost_basis'], '')

    def test_invalid_status_rejected(self):
        for status in ('maybe', '—', '123', 0, False):
            with self.subTest(status=status), self.assertRaises(EquipmentAssemblyError):
                clean_values(_values(status))

    def test_negative_nonfinite_and_oversized_numbers_rejected(self):
        for field in ('rate', 'cost'):
            for raw in ('-0.001', '-1', 'NaN', 'Infinity', '1e999', '1e9999999', True, '=1+1', 'дорого'):
                with self.subTest(field=field, raw=raw), self.assertRaises(EquipmentAssemblyError):
                    clean_values(_values('separate', **{field: raw}, cost_basis='За год'))

    def test_empty_history_remains_valid(self):
        self.assertEqual(clean_values({}), dict(zip(FIELDS, ('', None, None, '', ''))))
        with self.assertRaises(EquipmentAssemblyError):
            clean_values({}, required=True)

    def test_model_clean_uses_same_rules_and_clears_prices(self):
        response = InsurerResponse(**_values('separate', cost=15000))
        with self.assertRaises(ValidationError):
            response.clean()
        response.equipment_assembly_status = 'included'
        response.clean()
        self.assertIsNone(response.equipment_assembly_cost)


@override_settings(RESPONSE_TEMPLATE_V2_FOR_ALL=True, RESPONSE_TEMPLATE_V2_SINCE='2026-10-08', EQUIPMENT_ASSEMBLY_SINCE=SINCE)
class AssemblyFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('assembly-staff', password='test')
        cls.staff.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        cls.req = InsuranceRequest.objects.create(client_name='ООО Тестовый кран', inn='1234567890',
                                                  dfa_number='СТ-ТЕСТ-1', insurance_type=TYPE, object_description='Тестовый кран')
        InsuranceRequest.objects.filter(pk=cls.req.pk).update(created_at=AFTER)
        cls.req.refresh_from_db()
        cls.summary = InsuranceSummary.objects.create(request=cls.req, status='collecting')

    def _workbook(self, values=None, *, year=1, old=False, remove_names=False):
        wb = load_workbook(BytesIO(build_v1() if old else build_v2(self.req, self.summary.pk)))
        ws = wb.active
        ws['B2'], ws['B3'] = 'Согаз', 'РФ'
        for col, value in zip('BDEF', (10000000, 200000, 0, 1)):
            ws[f'{col}{year + 5}'] = value
        if not old:
            _cell(wb, 'inspection_status').value = 'Осмотр не требуется'
            _cell(wb, 'rnpk_status').value = 'Будут прописаны в полисе'
            for name, value in (values or {}).items():
                _cell(wb, name).value = value
            if remove_names:
                for name in FIELDS:
                    del wb.defined_names[f'resp_{name}']
        return wb

    def _process(self, values=None, **kwargs):
        wb = self._workbook(values, **kwargs)
        out = BytesIO()
        wb.save(out)
        file = SimpleUploadedFile('synthetic-response.xlsx', out.getvalue(), content_type=XLSX)
        return ExcelResponseProcessor().process_excel_file(file, self.summary, user=self.staff)

    def _response(self):
        return InsurerResponse.objects.get(summary=self.summary, company_name='Согаз')

    def _offer(self, company='Согаз', year=1):
        return InsuranceOffer.objects.create(summary=self.summary, company_name=company, insurance_year=year,
                                              insurance_sum=10000000, franchise_1=0, premium_with_franchise_1=200000)

    def _post(self, **values):
        self.client.force_login(self.staff)
        return self.client.post(reverse('summaries:set_insurer_response', args=[self.summary.pk]),
                                {'company': 'Согаз', **values})

    def _export(self, client=True, data_only=False):
        output = SummaryExportV2Service().generate(self.summary, is_client_version=client)
        return load_workbook(output, data_only=data_only)

    def test_import_included(self):
        self._process(_values())
        self.assertEqual(self._response().equipment_assembly_status, 'included')

    def test_import_declined(self):
        self._process(_values('declined'))
        self.assertEqual(self._response().equipment_assembly_status, 'declined')

    def test_import_not_applicable(self):
        self._process(_values('not_applicable', terms='Монтаж не предусмотрен конструкцией'))
        self.assertEqual(self._response().equipment_assembly_status, 'not_applicable')

    def test_import_separate_text_rate(self):
        self._process(_values('separate', rate='0,15%', cost_basis='От страховой суммы за год'))
        self.assertEqual(self._response().equipment_assembly_rate, Decimal('.15'))

    def test_import_separate_numeric_percent_cell(self):
        self._process(_values('separate', rate=.0015, cost_basis='От страховой суммы за год'))
        self.assertEqual(self._response().equipment_assembly_rate, Decimal('.15'))

    def test_import_general_numeric_rate_cell(self):
        wb = self._workbook(_values('separate', rate=.125, cost_basis='От СС за год'))
        _cell(wb, 'equipment_assembly_rate').number_format = 'General'
        parsed = ExcelResponseProcessor().extract_response_sections(wb, self.summary, 'Согаз', strict=True)
        self.assertEqual(parsed['values']['equipment_assembly_rate'], Decimal('.125'))

    def test_import_separate_premium_and_basis(self):
        self._process(_values('separate', cost=15000.25, cost_basis='За одну операцию', terms='Франшиза 10 000 ₽'))
        response = self._response()
        self.assertEqual(response.equipment_assembly_cost, Decimal('15000.25'))
        self.assertEqual(response.equipment_assembly_cost_basis, 'За одну операцию')
        self.assertEqual(response.equipment_assembly_terms, 'Франшиза 10 000 ₽')

    def test_invalid_imports_rejected_before_database_writes(self):
        invalid = ({}, _values('separate'), _values('separate', cost=15000), _values('not_applicable'),
                   _values('unknown'), _values('separate', cost=-1, cost_basis='За год'),
                   _values('included', rate='-0,15%'))
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(MissingDataError):
                self._process(values)
            self.assertFalse(self.summary.offers.exists())
            self.assertFalse(self.summary.insurer_responses.exists())

    def test_new_request_rejects_early_v2_without_named_cells(self):
        with self.assertRaisesMessage(MissingDataError, 'Монтаж/демонтаж'):
            self._process(remove_names=True)

    def test_new_request_rejects_v1_in_strict_mode(self):
        with self.assertRaises(MissingDataError):
            self._process(old=True)

    def test_old_request_accepts_early_v2(self):
        InsuranceRequest.objects.filter(pk=self.req.pk).update(created_at=BEFORE)
        self.req.refresh_from_db()
        self.summary.request = self.req
        self._process(remove_names=True)
        self.assertEqual(self._response().equipment_assembly_status, '')

    def test_pre_v2_request_accepts_v1(self):
        InsuranceRequest.objects.filter(pk=self.req.pk).update(created_at=timezone.make_aware(datetime(2026, 10, 1, 12)))
        self.req.refresh_from_db()
        self.summary.request = self.req
        self.assertFalse(v2_strict(self.staff, self.req))
        self._process(old=True)
        self.assertEqual(self._response().equipment_assembly_status, '')

    def test_other_type_ignores_block_even_in_generic_template(self):
        self.req.insurance_type = 'страхование имущества'
        self.req.save(update_fields=['insurance_type'])
        wb = load_workbook(BytesIO(build_v2()))
        _cell(wb, 'inspection_status').value = 'not_required'
        _cell(wb, 'rnpk_status').value = 'included'
        _cell(wb, 'equipment_assembly_status').value = 'unknown'
        parsed = ExcelResponseProcessor().extract_response_sections(wb, self.summary, 'Согаз', strict=True)
        save_response(self.summary, 'Согаз', parsed['values'], parsed['version'], user=self.staff)
        self.assertEqual(self._response().equipment_assembly_status, '')

    def test_reupload_new_year_updates_same_response_and_clears_cost(self):
        self._process(_values('separate', rate='0,15%', cost=15000, cost_basis='От СС за год'))
        response_pk = self._response().pk
        self._process(_values('declined', rate='0,15%', cost=15000, cost_basis='Прежний расчёт'), year=2)
        response = self._response()
        self.assertEqual(response.pk, response_pk)
        self.assertEqual(response.equipment_assembly_status, 'declined')
        self.assertIsNone(response.equipment_assembly_rate)
        self.assertIsNone(response.equipment_assembly_cost)
        self.assertEqual(self.summary.offers.count(), 2)

    def test_manual_edit_saves_and_switching_status_clears_previous_cost(self):
        self._offer()
        response = self._post(**_values('separate', rate='0,15%', cost='15000,25', cost_basis='От СС за год'))
        self.assertEqual(response.status_code, 200, response.content)
        response = self._post(**_values('included'))
        self.assertEqual(response.status_code, 200, response.content)
        saved = self._response()
        self.assertEqual(saved.equipment_assembly_status, 'included')
        self.assertIsNone(saved.equipment_assembly_rate)
        self.assertIsNone(saved.equipment_assembly_cost)
        self.assertEqual(saved.equipment_assembly_cost_basis, '')

    def test_partial_manual_price_edit_validates_with_saved_status(self):
        self._offer()
        update_from_form(self.summary, 'Согаз', _values('separate', rate='.15', cost_basis='За год'))
        response = self._post(equipment_assembly_rate='0,125%')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._response().equipment_assembly_rate, Decimal('.125'))

    def test_invalid_manual_edits_leave_previous_response_untouched(self):
        self._process(_values('included'))
        for values in (_values('separate'), _values('not_applicable'), _values('maybe'), _values('included', cost='-1'), _values('')):
            with self.subTest(values=values):
                response = self._post(**values)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self._response().equipment_assembly_status, 'included')

    def test_card_displays_data_and_edit_fields(self):
        self._process(_values('separate', rate='0,15%', cost=15000.25, cost_basis='От СС за год', terms='Франшиза 10 000'))
        self.client.force_login(self.staff)
        page = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        for text in (EQUIPMENT_ASSEMBLY.title, 'Доп. тариф 0,15%', 'Доп. премия 15 000,25 ₽', 'От СС за год', 'Франшиза 10 000'):
            self.assertContains(page, text)
        self.assertContains(page, 'name="equipment_assembly_rate"')
        self.assertContains(page, 'name="equipment_assembly_cost" value="15 000,25"')
        line = next(line for line in display_lines(self.summary, ['Согаз'])['Согаз']['lines'] if line['label'] == EQUIPMENT_ASSEMBLY.title)
        self.assertEqual(line['note'], 'не включено в ИТОГО')

    def test_manual_offer_requires_new_block_before_saving(self):
        self.client.force_login(self.staff)
        data = dict(company_name='Согаз', coverage_territory='РФ', insurance_year='1', insurance_sum='10000000',
                    franchise_1='0', premium_with_franchise_1='200000', payments_per_year_variant_1='1',
                    inspection_status='not_required', rnpk_status='included')
        url = reverse('summaries:add_offer', args=[self.summary.pk])
        page = self.client.post(url, data, follow=True)
        self.assertContains(page, 'Монтаж/демонтаж спецтехники')
        self.assertFalse(self.summary.offers.exists())
        page = self.client.post(url, {**data, **_values('separate', cost='15000', cost_basis='За одну операцию')}, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.summary.offers.count(), 1)
        self.assertEqual(self._response().equipment_assembly_cost, Decimal('15000'))

    def test_saved_historical_email_not_regenerated_on_view(self):
        text = 'Ранее сохранённое письмо, исправленное сотрудником.'
        InsuranceRequest.objects.filter(pk=self.req.pk).update(email_body=text, email_subject='Ранее')
        self.client.force_login(self.staff)
        for route in ('request_detail', 'preview_email'):
            self.assertEqual(self.client.get(reverse(f'insurance_requests:{route}', args=[self.req.pk])).status_code, 200)
            self.req.refresh_from_db()
            self.assertEqual(self.req.email_body, text)

    @override_settings(RESPONSE_TEMPLATE_V2_FOR_ALL=False)
    def test_email_links_block_in_superuser_v2_contour(self):
        root = User.objects.create_superuser('assembly-root', password='test')
        root.groups.add(Group.objects.get_or_create(name='Администраторы')[0])
        self.client.force_login(root)
        for route in ('generate_email', 'preview_email'):
            with self.subTest(route=route):
                InsuranceRequest.objects.filter(pk=self.req.pk).update(email_body='')
                self.assertIn(self.client.get(reverse(f'insurance_requests:{route}', args=[self.req.pk])).status_code, (200, 302))
                self.req.refresh_from_db()
                self.assertIn('«Ответ страховщика»', self.req.email_body)

    def test_smr_and_assembly_imported_independently(self):
        self.req.has_construction_work = True
        self.req.save(update_fields=['has_construction_work'])
        self._process({**_values('included'), 'smr_status': 'separate', 'smr_cost': 48500, 'smr_terms': 'Условия СМР'})
        saved = self._response()
        self.assertEqual((saved.smr_status, saved.smr_cost, saved.equipment_assembly_status), ('separate', Decimal('48500'), 'included'))

    def test_both_exports_show_prices_basis_terms_and_do_not_add_to_totals(self):
        self._process(_values('separate', rate='0,15%', cost=15000, cost_basis='От СС за одну операцию', terms='Франшиза 10 000'))
        self._offer(year=2)
        for client in (True, False):
            with self.subTest(client=client):
                wb = self._export(client=client, data_only=True)
                ws = wb['Свод']
                headers = [c.value for c in ws[9]]
                self.assertIn('Монтаж/демонтаж', headers)
                self.assertEqual(ws.cell(11, headers.index('Монтаж/демонтаж') + 1).value, 'Доп. тариф 0,15%\nДоп. премия 15 000 ₽')
                notes = ws.cell(11, headers.index('Комментарии') + 1).value
                for text in ('От СС за одну операцию', 'Франшиза 10 000', 'не включена в ИТОГО'):
                    self.assertIn(text, notes)
                self.assertEqual(ws['B11'].value, 400000)
                self.assertEqual(wb.sheetnames, ['Свод'] if client else ['Свод', 'Параметры запроса'])

    def test_export_all_statuses_and_no_answer(self):
        self._offer()
        for status, terms, expected in (('included', '', 'Включено'), ('declined', '', 'Не страхуем'),
                                         ('not_applicable', 'Технически не требуется', 'Не применимо'), ('', '', 'Нет данных')):
            with self.subTest(status=status):
                save_response(self.summary, 'Согаз', _values(status, terms=terms), 2)
                ws = self._export()['Свод']
                headers = [c.value for c in ws[9]]
                self.assertEqual(ws.cell(11, headers.index('Монтаж/демонтаж') + 1).value, expected)

    def test_export_rate_only_and_cost_only(self):
        self._offer()
        for values, expected in ((_values('separate', rate='.15', cost_basis='От СС за год'), 'Доп. тариф 0,15%'),
                                 (_values('separate', cost=15000, cost_basis='За одну операцию'), 'Доп. премия 15 000 ₽')):
            with self.subTest(values=values):
                save_response(self.summary, 'Согаз', values, 2)
                ws = self._export()['Свод']
                headers = [c.value for c in ws[9]]
                self.assertEqual(ws.cell(11, headers.index('Монтаж/демонтаж') + 1).value, expected)

    def test_one_two_and_many_companies_with_all_extra_blocks(self):
        self.req.has_construction_work = self.req.has_transportation = self.req.has_casco_ce = True
        self.req.branch = 'Краснодар'
        self.req.save()
        for count in (1, 2, 5):
            for index in range(self.summary.offers.count(), count):
                self._offer(company=('Согаз', 'ВСК', 'Альфа', 'Пари', 'РЕСО')[index])
            with self.subTest(companies=count):
                ws = self._export()['Свод']
                for title in ('СМР', 'Монтаж/демонтаж', 'Риски РНПК', 'Доп. риски C/E', 'ОСВР'):
                    self.assertIn(title, [c.value for c in ws[9]])
                self.assertEqual(ws.page_setup.fitToWidth, 1)
                self.assertEqual(ws.page_setup.orientation, 'landscape')
                self.assertEqual(ws.freeze_panes, 'C11')
                col = next(c.column_letter for c in ws[9] if c.value == 'Монтаж/демонтаж')
                self.assertGreaterEqual(ws.column_dimensions[col].width, 18)
                self.assertTrue(ws[f'{col}11'].alignment.wrap_text)

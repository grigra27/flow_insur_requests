from decimal import Decimal
from io import BytesIO
import os
import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from .forms import DEFAULT_BRANCH, ParserV2PreviewForm
from .models import InsuranceRequest, RequestAttachment
from .parsers.excel_v2 import ExcelRequestParserV2
from .parsers.excel_v2.parser import (
    classify_equipment_or_power,
    extract_quantity,
    extract_serial_number,
    extract_vin,
    normalize_condition,
    normalize_currency,
    parse_cost_value,
    split_brand_model,
)


class ObjectRowHelpersTests(TestCase):
    """Stage 3.1: low-level extractors used while parsing an object row."""

    def test_normalize_currency_recognises_common_variants(self):
        self.assertEqual(normalize_currency('руб'), 'RUB')
        self.assertEqual(normalize_currency('руб.'), 'RUB')
        self.assertEqual(normalize_currency('РУБ'), 'RUB')
        self.assertEqual(normalize_currency('рублей'), 'RUB')
        self.assertEqual(normalize_currency('₽'), 'RUB')
        self.assertEqual(normalize_currency('USD'), 'USD')
        self.assertEqual(normalize_currency('$'), 'USD')
        self.assertEqual(normalize_currency('долл'), 'USD')
        self.assertEqual(normalize_currency('EUR'), 'EUR')
        self.assertEqual(normalize_currency('евро'), 'EUR')
        self.assertEqual(normalize_currency('€'), 'EUR')
        self.assertIsNone(normalize_currency('XXX'))
        self.assertIsNone(normalize_currency(''))
        self.assertIsNone(normalize_currency(None))

    def test_normalize_condition_recognises_common_variants(self):
        self.assertEqual(normalize_condition('новое'), 'new')
        self.assertEqual(normalize_condition('Новый'), 'new')
        self.assertEqual(normalize_condition('НОВАЯ'), 'new')
        self.assertEqual(normalize_condition('б/у'), 'used')
        self.assertEqual(normalize_condition('БУ'), 'used')
        self.assertEqual(normalize_condition('б-у'), 'used')
        self.assertIsNone(normalize_condition('неизвестно'))
        self.assertIsNone(normalize_condition(None))

    def test_extract_vin_only_matches_valid_iso_3779(self):
        self.assertEqual(extract_vin('XTAKS045LP0001234'), 'XTAKS045LP0001234')
        # I/O/Q are not allowed in a VIN.
        self.assertIsNone(extract_vin('XTAIO0Q9876543210'))
        self.assertIsNone(extract_vin('TOO SHORT VIN'))
        self.assertIsNone(extract_vin(None))

    def test_parse_cost_value_strips_separators(self):
        self.assertEqual(parse_cost_value('1490000'), Decimal('1490000'))
        self.assertEqual(parse_cost_value('1 490 000'), Decimal('1490000'))
        self.assertEqual(parse_cost_value('1490000,00'), Decimal('1490000.00'))
        self.assertEqual(parse_cost_value('147.51'), Decimal('147.51'))
        self.assertIsNone(parse_cost_value('abc'))
        self.assertIsNone(parse_cost_value(''))
        self.assertIsNone(parse_cost_value(None))

    def test_classify_equipment_or_power_separates_text_from_number(self):
        self.assertEqual(classify_equipment_or_power('колесная'), ('колесная', None))
        self.assertEqual(classify_equipment_or_power('гусеничная'), ('гусеничная', None))
        self.assertEqual(classify_equipment_or_power('78.05'), (None, '78.05'))
        self.assertEqual(classify_equipment_or_power('147,51'), (None, '147,51'))
        self.assertEqual(classify_equipment_or_power('8 700'), (None, '8 700'))
        self.assertEqual(classify_equipment_or_power(''), (None, None))
        self.assertEqual(classify_equipment_or_power(None), (None, None))

    def test_split_brand_model_preserves_short_model_numbers(self):
        self.assertEqual(
            split_brand_model('LADA Largus KS045L 2024 б/у 78.05 1490000 руб', '2024'),
            ('LADA', 'Largus KS045L'),
        )
        # Short numerics inside model name (Mercedes G 400, BMW X5, Audi A4)
        # must survive — only prices (4+ digits) and fractional numbers are dropped.
        self.assertEqual(split_brand_model('Mercedes-Benz G 400 2024', '2024'),
                         ('Mercedes-Benz', 'G 400'))
        self.assertEqual(split_brand_model('Toyota Land Cruiser Prado 250 2024', '2024'),
                         ('Toyota', 'Land Cruiser Prado 250'))
        self.assertEqual(split_brand_model('Haval H7 2025 новое', '2025'),
                         ('Haval', 'H7'))
        # Single token → brand=None, all in model.
        self.assertEqual(split_brand_model('Mining', None), (None, 'Mining'))
        self.assertEqual(split_brand_model('', None), (None, None))
        self.assertEqual(split_brand_model(None, None), (None, None))

    def test_extract_quantity_only_with_marker(self):
        self.assertEqual(extract_quantity('15 шт.'), Decimal('15'))
        self.assertEqual(extract_quantity('Автобус ГАЗ 15шт'), Decimal('15'))
        # Without «шт» marker we do not guess.
        self.assertIsNone(extract_quantity('Toyota Camry 2024'))
        self.assertIsNone(extract_quantity(None))

    def test_extract_serial_number_pattern(self):
        self.assertEqual(extract_serial_number('Заводской номер ABC1234'), 'ABC1234')
        self.assertEqual(extract_serial_number('Серийный № XYZ-9876'), 'XYZ-9876')
        self.assertIsNone(extract_serial_number('просто текст без маркера'))


class ObjectRowPayloadIntegrationTests(TestCase):
    """Stage 3.1: insured_objects[] entries must carry structured fields."""

    def _build_minimal_workbook_with_object_row(self):
        wb = Workbook()
        sheet = wb.active
        # Minimal headers so that V2 detects an object table starting at row 41.
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '7707083893'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        # Object table header.
        sheet['C41'] = 'Наименование и описание имущества'
        sheet['J41'] = 'Год выпуска'
        sheet['L41'] = 'Мощность'
        sheet['M41'] = 'Стоимость на момент приобретения'
        sheet['N41'] = 'Валюта'
        # Object row.
        sheet['C43'] = 'LADA Largus KS045L'
        sheet['J43'] = 2024
        sheet['K43'] = 'б/у'
        sheet['L43'] = '78.05'
        sheet['M43'] = 1490000
        sheet['N43'] = 'руб'
        return wb

    def _parse_workbook(self, workbook):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        try:
            temp_file.close()
            workbook.save(temp_file.name)
            return ExcelRequestParserV2().parse(temp_file.name, original_filename='object-row.xlsx')
        finally:
            os.unlink(temp_file.name)

    def test_object_payload_contains_structured_fields(self):
        result = self._parse_workbook(self._build_minimal_workbook_with_object_row())
        objects = result.data['parser_v2_payload']['insured_objects']
        self.assertEqual(len(objects), 1)
        obj = objects[0]
        self.assertEqual(obj['brand'], 'LADA')
        self.assertEqual(obj['model'], 'Largus KS045L')
        self.assertEqual(obj['year'], '2024')
        self.assertEqual(obj['condition'], 'used')
        self.assertEqual(obj['power_or_capacity'], '78.05')
        self.assertEqual(obj['acquisition_cost_value'], '1490000')
        self.assertEqual(obj['acquisition_cost_currency'], 'RUB')
        # VIN не задан в synthetic-файле — должно быть None, без ложного срабатывания.
        self.assertIsNone(obj['vin'])

    def test_object_payload_normalises_alternative_currency_synonyms(self):
        wb = self._build_minimal_workbook_with_object_row()
        wb.active['N43'] = 'USD'
        wb.active['M43'] = 25000
        result = self._parse_workbook(wb)
        obj = result.data['parser_v2_payload']['insured_objects'][0]
        self.assertEqual(obj['acquisition_cost_currency'], 'USD')
        self.assertEqual(obj['acquisition_cost_value'], '25000')


class ParserV2UploadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')

        self.superuser = User.objects.create_superuser(
            username='parser_v2_root',
            email='root@example.com',
            password='pwd',
        )
        self.superuser.groups.add(admin_group)

        self.regular_user = User.objects.create_user(
            username='parser_v2_user',
            email='user@example.com',
            password='pwd',
        )
        self.regular_user.groups.add(user_group)

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _xlsx_upload(self, filename='заявка 20213-ЛТ-КЗ.xlsx'):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D6'] = '20213-ЛТ-КЗ'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['B14'] = 'Страхователь'
        sheet['D14'] = 'ЛизингоДАТЕЛЬ'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['B24'] = 'Предмет лизинга'
        sheet['B25'] = 'Мини-погрузчик Sunward SWL 4028, 2024 г.в.'
        sheet['D29'] = 'Без франшизы'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            filename,
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _xlsx_upload_with_template_object_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['A39'] = 'СВЕДЕНИЯ ОБ ОБЪЕКТЕ СТРАХОВАНИЯ'
        sheet['A41'] = '№ п/п'
        sheet['B41'] = 'Наименование и описание имущества  (марка модель комплектация)'
        sheet['C41'] = 'Год выпуска'
        sheet['A42'] = 'Транспортные средства категории B'
        sheet['A43'] = '1'
        sheet['B43'] = 'Lixiang L9 (пробег 13 000 км)'
        sheet['C43'] = '2024'
        sheet['D43'] = 'б/у'
        sheet['E43'] = '9 000 000'
        sheet['A45'] = 'Противоугонные системы и оборудование (отметьте знаком "Х")'
        sheet['B45'] = 'Штатная'
        sheet['C45'] = 'Установленная дополнительно'
        sheet['D45'] = 'название, модель'
        sheet['A46'] = 'Сигнализация'
        sheet['A47'] = 'Иммобилайзер'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'заявка object-template.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _xlsx_upload_with_unknown_branch(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Неизвестный филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['B24'] = 'Предмет лизинга'
        sheet['B25'] = 'Мини-погрузчик Sunward SWL 4028, 2024 г.в.'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'заявка unknown-branch.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _xlsx_upload_with_telematics_template_header(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['B24'] = 'Предмет лизинга'
        sheet['B25'] = 'Мини-погрузчик Sunward SWL 4028, 2024 г.в.'
        sheet['A53'] = 'Телематический комплекс'
        sheet['B53'] = 'Наименование'
        sheet['C53'] = 'StarLine M96'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'заявка telematics-template.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _parse_workbook_v2(self, workbook):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        try:
            temp_file.close()
            workbook.save(temp_file.name)
            return ExcelRequestParserV2().parse(temp_file.name, original_filename='franchise-test.xlsx')
        finally:
            os.unlink(temp_file.name)

    def _post_data_from_preview(self, form):
        data = {}
        checkbox_fields = {
            'has_installment',
            'has_autostart',
            'has_casco_ce',
            'has_transportation',
            'has_construction_work',
        }
        for field in form.fields:
            if field in checkbox_fields:
                if form.initial.get(field):
                    data[field] = 'on'
            else:
                data[field] = form.initial.get(field, '')
        return data

    def test_parser_v2_access_is_superuser_only(self):
        url = reverse('insurance_requests:upload_excel_v2')

        anonymous_response = self.client.get(url)
        self.assertEqual(anonymous_response.status_code, 302)

        self.client.login(username='parser_v2_user', password='pwd')
        regular_response = self.client.get(url)
        self.assertEqual(regular_response.status_code, 403)

        self.client.logout()
        self.client.login(username='parser_v2_root', password='pwd')
        superuser_response = self.client.get(url)
        self.assertEqual(superuser_response.status_code, 200)
        self.assertTemplateUsed(superuser_response, 'insurance_requests/upload_excel_v2.html')

    def test_parser_v2_link_is_visible_only_for_superuser_on_request_list(self):
        request_list_url = reverse('insurance_requests:request_list')
        parser_v2_url = reverse('insurance_requests:upload_excel_v2')

        self.client.login(username='parser_v2_user', password='pwd')
        regular_response = self.client.get(request_list_url)
        self.assertEqual(regular_response.status_code, 200)
        self.assertNotContains(regular_response, parser_v2_url)

        self.client.logout()
        self.client.login(username='parser_v2_root', password='pwd')
        superuser_response = self.client.get(request_list_url)
        self.assertEqual(superuser_response.status_code, 200)
        self.assertContains(superuser_response, parser_v2_url)

    def test_parser_v2_upload_renders_editable_preview(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'insurance_requests/upload_excel_v2_preview.html')
        self.assertContains(response, 'ООО Ромашка')
        self.assertContains(response, 'Мини-погрузчик Sunward SWL 4028')
        self.assertIn('draft_id', response.context)
        self.assertEqual(response.context['form'].initial['client_name'], 'ООО Ромашка')
        self.assertEqual(response.context['form'].initial['manager_name'], 'Иванов Иван')

    def test_parser_v2_branch_defaults_to_spb_when_not_recognized(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_unknown_branch()},
        )

        form = response.context['form']
        self.assertEqual(form.initial['branch'], DEFAULT_BRANCH)
        self.assertEqual(form.fields['branch'].widget.__class__.__name__, 'Select')

    def test_parser_v2_branch_accepts_only_known_choices(self):
        form = ParserV2PreviewForm(data={'draft_id': 'draft', 'branch': 'Неизвестный филиал'})

        self.assertFalse(form.is_valid())
        self.assertIn('branch', form.errors)

    def test_parser_v2_does_not_take_template_rows_as_vehicle_info(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_template_object_rows()},
        )

        vehicle_info = response.context['form'].initial['vehicle_info']
        self.assertIn('Lixiang L9', vehicle_info)
        self.assertNotIn('Транспортные средства категории B', vehicle_info)
        self.assertNotIn('Противоугонные системы', vehicle_info)
        self.assertNotIn('Сигнализация', vehicle_info)

    def test_parser_v2_does_not_take_name_header_as_telematics_complex(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_telematics_template_header()},
        )

        telematics_complex = response.context['form'].initial['telematics_complex']
        self.assertEqual(telematics_complex, 'StarLine M96')
        self.assertNotEqual(telematics_complex, 'Наименование')

    def test_parser_v2_franchise_uses_marked_column_not_all_template_labels(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['D28'] = 'Без франшизы'
        sheet['E28'] = 'Франшиза в процентах от страховой суммы'
        sheet['F28'] = 'Абсолютная сумма'
        sheet['D29'] = 'X'

        result = self._parse_workbook_v2(workbook)

        self.assertEqual(result.data['franchise_type'], 'none')
        self.assertIn('D29', result.source_map['franchise_type'])
        self.assertNotEqual(result.data['franchise_type'], 'both_variants')

    def test_parser_v2_franchise_ignores_unmarked_template_labels(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['D28'] = 'Без франшизы'
        sheet['E28'] = 'Франшиза в процентах от страховой суммы'
        sheet['F28'] = 'Абсолютная сумма'

        result = self._parse_workbook_v2(workbook)

        self.assertEqual(result.data['franchise_type'], 'none')
        self.assertNotIn('franchise_type', result.source_map)

    def test_parser_v2_franchise_detects_percent_and_absolute_columns(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['D28'] = 'Без франшизы'
        sheet['E28'] = 'Франшиза в процентах от страховой суммы'
        sheet['F28'] = 'Абсолютная сумма'
        sheet['E29'] = 'X'

        percent_result = self._parse_workbook_v2(workbook)
        self.assertEqual(percent_result.data['franchise_type'], 'with_franchise')
        self.assertIn('E29', percent_result.source_map['franchise_type'])

        sheet['E29'] = None
        sheet['F29'] = '50 000'

        absolute_result = self._parse_workbook_v2(workbook)
        self.assertEqual(absolute_result.data['franchise_type'], 'with_franchise')
        self.assertIn('F29', absolute_result.source_map['franchise_type'])

    def test_parser_v2_franchise_detects_both_variants(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['D28'] = 'Без франшизы'
        sheet['F28'] = 'Абсолютная сумма'
        sheet['D29'] = 'X'
        sheet['F29'] = '50 000'

        result = self._parse_workbook_v2(workbook)

        self.assertEqual(result.data['franchise_type'], 'both_variants')
        self.assertIn('D29', result.source_map['franchise_type'])
        self.assertIn('F29', result.source_map['franchise_type'])

    def test_parser_v2_franchise_uses_shifted_row_for_individual_entrepreneur(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['A1'] = 'Заявка от ИП Иванов И.И.'
        sheet['D29'] = 'Без франшизы'
        sheet['E29'] = 'Франшиза в процентах от страховой суммы'
        sheet['F29'] = 'Абсолютная сумма'
        sheet['E30'] = 'X'

        result = self._parse_workbook_v2(workbook)

        self.assertEqual(result.data['franchise_type'], 'with_franchise')
        self.assertIn('E30', result.source_map['franchise_type'])
        self.assertEqual(result.data['parser_v2_payload']['franchise_details']['value_row'], 30)

    def test_parser_v2_creates_request_from_preview_and_keeps_original_attachment(self):
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload()},
        )
        form = upload_response.context['form']
        post_data = self._post_data_from_preview(form)
        post_data['client_name'] = 'ООО Ромашка Проверено'

        create_response = self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        created_request = InsuranceRequest.objects.get()
        self.assertRedirects(
            create_response,
            reverse('insurance_requests:request_detail', kwargs={'pk': created_request.pk}),
        )
        self.assertEqual(created_request.client_name, 'ООО Ромашка Проверено')
        self.assertEqual(created_request.manager_name, 'Иванов Иван')
        self.assertEqual(created_request.branch, 'Казань')
        self.assertEqual(created_request.additional_data['parser_version'], 'v2')
        self.assertEqual(created_request.additional_data['parser_v2']['version'], '2.0.0')
        self.assertTrue(RequestAttachment.objects.filter(request=created_request).exists())

    def test_parser_v2_can_create_minimal_request_after_unreadable_file(self):
        self.client.login(username='parser_v2_root', password='pwd')
        unreadable_file = SimpleUploadedFile(
            'broken.xlsx',
            b'not an excel file',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': unreadable_file},
        )

        self.assertEqual(upload_response.status_code, 200)
        self.assertContains(upload_response, 'Файл не удалось прочитать')

        post_data = self._post_data_from_preview(upload_response.context['form'])
        create_response = self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        created_request = InsuranceRequest.objects.get()
        self.assertRedirects(
            create_response,
            reverse('insurance_requests:request_detail', kwargs={'pk': created_request.pk}),
        )
        self.assertEqual(created_request.client_name, 'Клиент не указан')
        self.assertEqual(created_request.dfa_number, 'Номер ДФА не указан')
        self.assertTrue(created_request.additional_data['parser_v2']['warnings'])

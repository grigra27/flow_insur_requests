from datetime import date
from decimal import Decimal
from io import BytesIO
import os
import shutil
import tempfile

from django import forms as forms_module
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
    normalize_condition,
    normalize_currency,
    normalize_insured_party,
    normalize_insured_sum_type,
    normalize_premium_frequency_label,
    normalize_property_location_right_holder,
    parse_cost_value,
    parse_date_value,
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


class CustomerDealHelpersTests(TestCase):
    """Stages 3.2 / 3.3: low-level extractors for customer and deal fields."""

    def test_parse_date_handles_common_formats(self):
        self.assertEqual(parse_date_value('17.04.2026'), date(2026, 4, 17))
        self.assertEqual(parse_date_value('12.06.80'), date(1980, 6, 12))
        self.assertEqual(parse_date_value('1982-12-12'), date(1982, 12, 12))
        self.assertEqual(parse_date_value('1982-12-12 00:00:00'), date(1982, 12, 12))
        self.assertEqual(parse_date_value(date(2024, 1, 1)), date(2024, 1, 1))
        self.assertIsNone(parse_date_value(''))
        self.assertIsNone(parse_date_value(None))
        self.assertIsNone(parse_date_value('not a date'))

    def test_normalize_insured_party(self):
        self.assertEqual(normalize_insured_party('ЛизингоДАТЕЛЬ'), 'lessor')
        self.assertEqual(normalize_insured_party('ЛИЗИНГОПОЛУЧАТЕЛЬ'), 'lessee')
        self.assertEqual(normalize_insured_party('Лизингополучатель'), 'lessee')
        self.assertIsNone(normalize_insured_party('Оба'))
        self.assertIsNone(normalize_insured_party('что-то другое'))
        self.assertIsNone(normalize_insured_party(None))

    def test_normalize_insured_sum_type_handles_substring_collision(self):
        # «неагрегатная» содержит «агрегатная» как подстроку — нельзя путать.
        self.assertEqual(normalize_insured_sum_type('Неагрегатная'), 'non_aggregate')
        self.assertEqual(normalize_insured_sum_type('агрегатная'), 'aggregate')
        self.assertIsNone(normalize_insured_sum_type('что-то'))

    def test_normalize_property_location_right_holder(self):
        self.assertEqual(
            normalize_property_location_right_holder('собственность лизингополучателя'),
            'lessee_owner',
        )
        self.assertEqual(
            normalize_property_location_right_holder('Стороннее лицо'),
            'third_party_owner',
        )
        self.assertIsNone(normalize_property_location_right_holder('—'))

    def test_normalize_premium_frequency_label(self):
        self.assertEqual(normalize_premium_frequency_label('Единовременно'), 'single')
        self.assertEqual(normalize_premium_frequency_label('ежеквартально'), 'quarterly')
        self.assertEqual(normalize_premium_frequency_label('Поквартально'), 'quarterly')
        self.assertEqual(normalize_premium_frequency_label('ежегодно'), 'annual')
        # «2 раза в год» и «прочее» — вне нашего enum.
        self.assertIsNone(normalize_premium_frequency_label('2 раза в год'))
        self.assertIsNone(normalize_premium_frequency_label('прочее (укажите)'))
        self.assertIsNone(normalize_premium_frequency_label(None))


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

    def test_object_payload_normalises_alternative_currency_synonyms(self):
        wb = self._build_minimal_workbook_with_object_row()
        wb.active['N43'] = 'USD'
        wb.active['M43'] = 25000
        result = self._parse_workbook(wb)
        obj = result.data['parser_v2_payload']['insured_objects'][0]
        self.assertEqual(obj['acquisition_cost_currency'], 'USD')
        self.assertEqual(obj['acquisition_cost_value'], '25000')


class CustomerDealPayloadIntegrationTests(TestCase):
    """Stages 3.2 / 3.3: customer + deal fields must surface in parse() result."""

    def _build_workbook(self):
        wb = Workbook()
        sheet = wb.active
        # Header / customer block. Submission date sits in M2 with a «дата
        # подачи» label one cell to the left, just like the real corpus.
        sheet['L2'] = 'дата подачи'
        sheet['M2'] = '17.04.2026'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['B8'] = 'Юридический адрес:'
        sheet['D8'] = '194354, Санкт-Петербург г, Северный пр-кт, дом № 11'
        sheet['D9'] = '7707083893'
        sheet['B10'] = 'Почтовый адрес:'
        sheet['D10'] = '194354, Санкт-Петербург г, Северный пр-кт, дом № 11'
        sheet['B11'] = 'Основной вид деятельности:'
        sheet['D11'] = 'Строительство автомобильных дорог'
        # Deal / insurance block. Two label cells + an «Х» under one of them
        # is the canonical layout in the real corpus.
        sheet['B14'] = 'Страхователь'
        sheet['D14'] = 'ЛизингоДАТЕЛЬ'
        sheet['E14'] = 'ЛизингоПОЛУЧАТЕЛЬ'
        sheet['D15'] = 'Х'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['D24'] = 'страховая сумма'
        sheet['E24'] = 'Неагрегатная'
        sheet['D26'] = 'условия по охране (день/ночь)'
        sheet['E26'] = 'без ограничений'
        # Property-location right holder block: two labels in one row + «Х»
        # under one of them (same crosshair layout as the «Страхователь» block).
        sheet['B27'] = 'Правообладатель места расположения'
        sheet['D27'] = 'собственность лизингополучателя'
        sheet['F27'] = 'собственность третьего лица'
        sheet['D28'] = 'Х'
        # Premium frequency block: «Х» next to «ежеквартально».
        sheet['B31'] = 'Порядок уплаты страховой премии'
        sheet['D31'] = 'Единовременно'
        sheet['E31'] = 'В рассрочку'
        sheet['E32'] = 'ежеквартально'
        sheet['F32'] = 'Х'
        sheet['E33'] = '2 раза в год'
        sheet['E34'] = 'ежегодно'
        return wb

    def _parse_workbook(self, workbook):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        try:
            temp_file.close()
            workbook.save(temp_file.name)
            return ExcelRequestParserV2().parse(temp_file.name, original_filename='customer-deal.xlsx')
        finally:
            os.unlink(temp_file.name)

    def test_customer_fields_surface_in_parse_result(self):
        result = self._parse_workbook(self._build_workbook())
        self.assertEqual(result.data.get('legal_address'),
                         '194354, Санкт-Петербург г, Северный пр-кт, дом № 11')
        self.assertEqual(result.data.get('postal_address'),
                         '194354, Санкт-Петербург г, Северный пр-кт, дом № 11')
        self.assertEqual(result.data.get('business_activity'),
                         'Строительство автомобильных дорог')
        self.assertEqual(result.data.get('submission_date'), '2026-04-17')

    def test_deal_fields_surface_in_parse_result(self):
        result = self._parse_workbook(self._build_workbook())
        self.assertEqual(result.data.get('insured_party'), 'lessor')
        self.assertEqual(result.data.get('insured_sum_type'), 'non_aggregate')
        self.assertEqual(result.data.get('guard_conditions'), 'без ограничений')
        self.assertEqual(result.data.get('property_location_right_holder'), 'lessee_owner')

    def test_insured_party_x_marker_picks_lessee_when_marked(self):
        wb = self._build_workbook()
        sheet = wb.active
        # Move the «Х» from under lessor (D15) to under lessee (E15).
        sheet['D15'] = None
        sheet['E15'] = 'Х'
        result = self._parse_workbook(wb)
        self.assertEqual(result.data.get('insured_party'), 'lessee')

    def test_insured_party_warns_when_no_mark_is_present(self):
        wb = self._build_workbook()
        sheet = wb.active
        # Strip every X-mark candidate cell below the label row.
        for coord in ('D15', 'E15'):
            sheet[coord] = None
        result = self._parse_workbook(wb)
        self.assertIsNone(result.data.get('insured_party'))
        self.assertTrue(
            any(
                w.get('field') == 'insured_party' and w.get('level') == 'manual_required'
                for w in result.warnings
            ),
            f"Expected a manual_required insured_party warning, got: {result.warnings}",
        )

    def test_insured_party_ambiguous_when_both_columns_marked(self):
        wb = self._build_workbook()
        sheet = wb.active
        sheet['D15'] = 'Х'
        sheet['E15'] = 'Х'
        result = self._parse_workbook(wb)
        self.assertIsNone(result.data.get('insured_party'))
        self.assertEqual(result.data.get('premium_frequency'), 'quarterly')

    def test_plrh_x_marker_picks_third_party_when_marked(self):
        wb = self._build_workbook()
        sheet = wb.active
        sheet['D28'] = None
        sheet['F28'] = 'Х'
        result = self._parse_workbook(wb)
        self.assertEqual(result.data.get('property_location_right_holder'), 'third_party_owner')

    def test_plrh_warns_only_for_property_insurance(self):
        # No mark + insurance_type = «страхование имущества» → warning fires.
        wb = self._build_workbook()
        sheet = wb.active
        sheet['D21'] = 'страхование имущества'
        sheet['D28'] = None
        sheet['F28'] = None
        result = self._parse_workbook(wb)
        self.assertIsNone(result.data.get('property_location_right_holder'))
        self.assertTrue(
            any(
                w.get('field') == 'property_location_right_holder'
                and w.get('level') == 'manual_required'
                for w in result.warnings
            ),
            f"Expected a manual_required PLRH warning, got: {result.warnings}",
        )

    def test_plrh_warning_suppressed_for_casco(self):
        # No mark + default КАСКО → no PLRH warning (field is irrelevant for CASCO).
        wb = self._build_workbook()
        sheet = wb.active
        sheet['D28'] = None
        sheet['F28'] = None
        result = self._parse_workbook(wb)
        self.assertIsNone(result.data.get('property_location_right_holder'))
        self.assertFalse(
            any(w.get('field') == 'property_location_right_holder' for w in result.warnings),
            f"Did not expect a PLRH warning for CASCO, got: {result.warnings}",
        )

    def test_plrh_ambiguous_when_both_columns_marked(self):
        wb = self._build_workbook()
        sheet = wb.active
        sheet['D28'] = 'Х'
        sheet['F28'] = 'Х'
        result = self._parse_workbook(wb)
        self.assertIsNone(result.data.get('property_location_right_holder'))

    def test_empty_template_does_not_pick_neighbour_labels(self):
        # Build a "template only" workbook — labels present, values empty.
        wb = Workbook()
        sheet = wb.active
        sheet['L2'] = 'дата подачи'
        sheet['M2'] = '17.04.2026'
        sheet['B8'] = 'Юридический адрес:'
        sheet['B10'] = 'Почтовый адрес:'
        sheet['B11'] = 'Основной вид деятельности:'
        sheet['B12'] = 'ПАРАМЕТРЫ СТРАХОВОЙ СДЕЛКИ'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '7707083893'
        result = self._parse_workbook(wb)
        # No value -> field stays absent (or None), never the next label.
        for field in ('legal_address', 'postal_address', 'business_activity'):
            value = result.data.get(field)
            self.assertNotIn('Почтовый адрес', value or '')
            self.assertNotIn('Основной вид деятельности', value or '')
            self.assertNotIn('ПАРАМЕТРЫ', value or '')


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
        sheet['E14'] = 'ЛизингоПОЛУЧАТЕЛЬ'
        sheet['D15'] = 'Х'
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

    def _post_data_from_preview(self, source):
        """Build POST data that mirrors what the operator would submit.

        Accepts either an HttpResponse from the upload step (preferred —
        also collects the object formset) or a bare ParserV2PreviewForm
        for back-compat with tests that don't deal with the formset.
        """
        if hasattr(source, 'context') and source.context is not None:
            form = source.context['form']
            object_formset = source.context.get('object_formset')
        else:
            form = source
            object_formset = None

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
                value = form.initial.get(field, '')
                data[field] = '' if value is None else value

        if object_formset is not None:
            prefix = object_formset.prefix or 'form'
            data[f'{prefix}-TOTAL_FORMS'] = str(object_formset.total_form_count())
            data[f'{prefix}-INITIAL_FORMS'] = str(object_formset.initial_form_count())
            data[f'{prefix}-MIN_NUM_FORMS'] = '0'
            data[f'{prefix}-MAX_NUM_FORMS'] = '1000'
            for index, obj_form in enumerate(object_formset.forms):
                for field_name, field in obj_form.fields.items():
                    initial = obj_form.initial.get(field_name, '')
                    key = f'{prefix}-{index}-{field_name}'
                    if isinstance(field, forms_module.BooleanField):
                        if initial:
                            data[key] = 'on'
                    else:
                        data[key] = '' if initial is None else initial
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

    def test_parser_v2_unrecognized_branch_preserves_raw_value_and_warns(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_unknown_branch()},
        )

        form = response.context['form']
        self.assertEqual(form.initial['branch'], 'Неизвестный филиал')
        self.assertEqual(form.fields['branch'].widget.__class__.__name__, 'Select')
        warnings = response.context['warnings']
        self.assertTrue(
            any(w.get('field') == 'branch' and w.get('level') == 'manual_required' for w in warnings),
            f"Expected a manual_required branch warning, got: {warnings}",
        )

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
        post_data = self._post_data_from_preview(upload_response)
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

    def _xlsx_upload_with_multiple_objects(self, object_count=3, filename='partia.xlsx'):
        """Build a synthetic xlsx with several object rows so the parser
        finds an N-object batch."""
        wb = Workbook()
        sheet = wb.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['B14'] = 'Страхователь'
        sheet['D14'] = 'ЛизингоДАТЕЛЬ'
        sheet['E14'] = 'ЛизингоПОЛУЧАТЕЛЬ'
        sheet['D15'] = 'Х'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        # Object table header.
        sheet['C41'] = 'Наименование и описание имущества'
        sheet['J41'] = 'Год выпуска'
        sheet['L41'] = 'Мощность'
        sheet['M41'] = 'Стоимость на момент приобретения'
        sheet['N41'] = 'Валюта'
        # Object rows at 43, 45, 47, 49 — stop at the requested count.
        descriptions = [
            ('LADA Largus KS045L', 2024, 'б/у', '78.05', 1490000),
            ('Toyota Camry XV70', 2023, 'новое', '249', 4500000),
            ('Haval H7', 2025, 'новое', '170', 3649000),
            ('Mercedes-Benz Sprinter', 2022, 'б/у', '170', 5200000),
        ]
        for idx, (desc, year, cond, power, cost) in enumerate(descriptions[:object_count]):
            row = 43 + idx * 2
            sheet[f'C{row}'] = desc
            sheet[f'J{row}'] = year
            sheet[f'K{row}'] = cond
            sheet[f'L{row}'] = power
            sheet[f'M{row}'] = cost
            sheet[f'N{row}'] = 'руб'
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            filename,
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_parser_v2_splits_multi_object_file_into_sibling_requests(self):
        """Stage 4.1: 3 objects → 3 requests sharing one source_batch_id."""
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_multiple_objects(object_count=3)},
        )

        # Preview must announce a batch and the submit button must reflect it.
        self.assertContains(upload_response, 'Партия объектов')
        self.assertContains(upload_response, 'Создать партию из 3 заявок')

        post_data = self._post_data_from_preview(upload_response)

        create_response = self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        # Three sibling rows must be created.
        siblings = InsuranceRequest.objects.order_by('item_no')
        self.assertEqual(siblings.count(), 3)

        # Common fields are duplicated.
        for s in siblings:
            self.assertEqual(s.client_name, 'ООО Ромашка')
            self.assertEqual(s.inn, '1234567890')
            self.assertEqual(s.branch, 'Казань')
            self.assertEqual(s.insured_party, 'lessor')

        # Batch identity is consistent across siblings.
        batch_ids = {s.source_batch_id for s in siblings}
        self.assertEqual(len(batch_ids), 1)
        self.assertIsNotNone(siblings.first().source_batch_id)
        item_nos = [s.item_no for s in siblings]
        self.assertEqual(item_nos, [1, 2, 3])
        for s in siblings:
            self.assertEqual(s.item_count, 3)

        # Per-object fields differ.
        first, second, third = siblings
        self.assertEqual(first.brand, 'LADA')
        self.assertEqual(second.brand, 'Toyota')
        self.assertEqual(third.brand, 'Haval')
        self.assertEqual(first.acquisition_cost_value, Decimal('1490000'))
        self.assertEqual(second.acquisition_cost_value, Decimal('4500000'))
        self.assertEqual(third.acquisition_cost_value, Decimal('3649000'))
        for s in siblings:
            self.assertEqual(s.acquisition_cost_currency, 'RUB')

        # Original Excel is attached to every sibling.
        self.assertEqual(RequestAttachment.objects.count(), 3)
        for s in siblings:
            self.assertTrue(RequestAttachment.objects.filter(request=s).exists())

        # The view redirects to the first request of the batch.
        self.assertRedirects(
            create_response,
            reverse('insurance_requests:request_detail', kwargs={'pk': first.pk}),
        )

    def test_parser_v2_single_object_file_keeps_batch_fields_null(self):
        """Stage 4.1: 1 object → 1 request, source_batch_id stays NULL."""
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_multiple_objects(object_count=1)},
        )
        # No "Партия объектов" block for single-object uploads.
        self.assertNotContains(upload_response, 'Партия объектов')
        self.assertContains(upload_response, 'Создать заявку')

        post_data = self._post_data_from_preview(upload_response)
        self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        created = InsuranceRequest.objects.get()
        self.assertIsNone(created.source_batch_id)
        self.assertIsNone(created.item_no)
        self.assertIsNone(created.item_count)
        # Object fields are still filled (single-object stage 4.1 still uses the payload).
        self.assertEqual(created.brand, 'LADA')
        self.assertEqual(created.acquisition_cost_value, Decimal('1490000'))
        self.assertEqual(RequestAttachment.objects.count(), 1)

    def test_parser_v2_can_skip_a_sibling_in_the_formset(self):
        """Stage 4.2: marking one card as skip removes it from the created batch."""
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_multiple_objects(object_count=3)},
        )
        post_data = self._post_data_from_preview(upload_response)
        # Drop the middle sibling.
        post_data['objects-1-skip'] = 'on'

        self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        siblings = list(InsuranceRequest.objects.order_by('item_no'))
        self.assertEqual(len(siblings), 2)
        # Both surviving siblings share the same batch and have item_count=2.
        self.assertEqual({s.source_batch_id for s in siblings}, {siblings[0].source_batch_id})
        self.assertIsNotNone(siblings[0].source_batch_id)
        self.assertEqual([s.item_no for s in siblings], [1, 2])
        for s in siblings:
            self.assertEqual(s.item_count, 2)
        # First and third objects survive, second (Toyota) was skipped.
        brands = [s.brand for s in siblings]
        self.assertIn('LADA', brands)
        self.assertIn('Haval', brands)
        self.assertNotIn('Toyota', brands)
        self.assertEqual(RequestAttachment.objects.count(), 2)

    def test_parser_v2_skipping_all_siblings_blocks_creation(self):
        """Stage 4.2: if every card is skipped, nothing is created."""
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_multiple_objects(object_count=3)},
        )
        post_data = self._post_data_from_preview(upload_response)
        for index in range(3):
            post_data[f'objects-{index}-skip'] = 'on'

        response = self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        self.assertEqual(InsuranceRequest.objects.count(), 0)
        self.assertEqual(RequestAttachment.objects.count(), 0)
        # User is shown the preview again with an explicit error.
        self.assertContains(response, 'Все объекты партии отмечены к пропуску')

    def test_parser_v2_operator_edits_propagate_into_created_sibling(self):
        """Stage 4.2: edits in the formset overwrite parser payload defaults."""
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_multiple_objects(object_count=2)},
        )
        post_data = self._post_data_from_preview(upload_response)
        post_data['objects-0-brand'] = 'LADA (исправлено)'
        post_data['objects-0-acquisition_cost_value'] = '2500000'

        self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        first = InsuranceRequest.objects.get(item_no=1)
        self.assertEqual(first.brand, 'LADA (исправлено)')
        self.assertEqual(first.acquisition_cost_value, Decimal('2500000'))
        # Second sibling untouched.
        second = InsuranceRequest.objects.get(item_no=2)
        self.assertEqual(second.brand, 'Toyota')

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

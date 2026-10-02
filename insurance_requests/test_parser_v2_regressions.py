"""Регрессионный набор парсера V2 по реальным случаям ручных правок.

docs/improvement_plans/analytics_redesign_2026_09.md, задача 5.5 (аудит — §4.5).

Бланки собираются в коде и повторяют раскладку ячеек реальных заявок лизинговой
компании (строки и столбцы — как в файлах, по которым сотрудники правили значения),
но без данных клиентов. Два вида тестов:

- «фиксация» — случаи, где парсер уже прав; не должны сломаться при исправлениях;
- «цель» — случаи, где парсер сейчас ошибается (`expectedFailure` со ссылкой на задачу
  этапа 6). Исправление в задаче 6.x снимает декоратор — тест становится обычной проверкой.

Проверка на всём реальном корпусе (исходные файлы на сервере) — команда
`python manage.py parser_corpus_check`.
"""
import os
import shutil
import tempfile
import unittest
from datetime import date

from django.test import SimpleTestCase, TestCase
from openpyxl import Workbook

from .parsers.excel_v2 import ExcelRequestParserV2

MARK = 'Х'  # кириллическая «Х», как в бланках


def build_casco_application(
    *,
    dfa='ТС-20842',  # None — ячейка номера пустая
    period_one_year_mark=None,
    period_whole_term_value=MARK,
    autostart_value='',
    single_payment_mark=None,
    quarterly_mark=None,
    applicant_type='legal_entity',
    birth_date_text=None,
    object_description='1 Автомобиль GWM WEY 80 2026 новое 7900000 руб',
):
    """Бланк «Заявка на страхование» КАСКО, юрлицо, раскладка как в реальных файлах 2026 г."""
    wb = Workbook()
    sheet = wb.active
    sheet['B2'] = 'Заявка на страхование №'
    if dfa is not None:
        sheet['H2'] = dfa
    sheet['M2'] = '26.08.2026'
    sheet['B5'] = 'Менеджер'
    sheet['C5'] = 'Тестов Т.Т. (менеджер УКО)'
    sheet['B7'] = 'Наименование лизингополучателя' if applicant_type == 'legal_entity' else 'ФИО лизингополучателя'
    sheet['D7'] = 'ООО «Тестовая компания»' if applicant_type == 'legal_entity' else 'ИП Тестов Тест Тестович'
    if birth_date_text is not None:
        sheet['B8'] = 'дата рождения'
        sheet['D8'] = birth_date_text
    sheet['B9'] = 'Юридический адрес'
    sheet['D9'] = '100000, г. Тестовск, ул. Проверочная, д. 1'
    sheet['B10'] = 'ИНН'
    sheet['D10'] = '7707083893' if applicant_type == 'legal_entity' else '770708389312'

    # Необходимый период страхования: «1 [год]» и «на весь срок лизинга», отметка — в столбце N.
    sheet['I17'] = 'Необходимый период страхования'
    sheet['M17'] = '1'
    if period_one_year_mark:
        sheet['N17'] = period_one_year_mark
    sheet['M18'] = 'на весь срок лизинга'
    if period_whole_term_value:
        sheet['N18'] = period_whole_term_value

    sheet['B20'] = 'Вид страхования (отметьте знаком "Х")'
    sheet['B21'] = 'КАСКО'
    sheet['D21'] = MARK
    sheet['I21'] = 'Территория страхования'
    sheet['L21'] = 'Россия'

    # Функция «Автозапуск»: значение из выпадающего списка в M24.
    sheet['B24'] = 'Условия страхования'
    sheet['L24'] = 'функция "Автозапуск"'
    if autostart_value:
        sheet['M24'] = autostart_value

    # Порядок уплаты: D31 «Единовременно» | E31 «В рассрочку»; варианты рассрочки — E32…E35.
    sheet['B31'] = 'Порядок уплаты страховой премии (отметьте)'
    sheet['D31'] = 'Единовременно'
    sheet['E31'] = 'В рассрочку'
    if single_payment_mark:
        sheet['D32'] = single_payment_mark
    sheet['E32'] = 'ежеквартально'
    if quarterly_mark:
        sheet['F32'] = quarterly_mark
    sheet['E33'] = '2 раза в год'
    sheet['E34'] = 'ежегодно'
    sheet['E35'] = 'прочее (укажите)'

    # Таблица объектов.
    sheet['C41'] = 'Наименование и описание имущества'
    sheet['J41'] = 'Год выпуска'
    sheet['M41'] = 'Стоимость на момент приобретения'
    sheet['N41'] = 'Валюта'
    sheet['C43'] = object_description
    sheet['J43'] = 2026
    sheet['K43'] = 'новое'
    sheet['M43'] = 7900000
    sheet['N43'] = 'руб'
    return wb


def parse_result(workbook, filename='Заявка ТС 20842.xlsx'):
    handle = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    try:
        handle.close()
        workbook.save(handle.name)
        return ExcelRequestParserV2().parse(handle.name, original_filename=filename)
    finally:
        os.unlink(handle.name)


def parse(workbook, filename='Заявка ТС 20842.xlsx'):
    return parse_result(workbook, filename).data


class InsurancePeriodRegressionTests(SimpleTestCase):
    """Срок страхования (§4.5: 15 правок, 4 скрытые ошибки; задача 6.1)."""

    def test_whole_term_marked(self):
        self.assertEqual(parse(build_casco_application())['insurance_period'], 'на весь срок лизинга')

    def test_one_year_marked(self):  # исправлено в 6.1
        data = parse(build_casco_application(period_one_year_mark=MARK, period_whole_term_value=None))
        self.assertEqual(data['insurance_period'], '1 год')

    def test_explicit_term_instead_of_mark(self):  # исправлено в 6.1
        # Поле допускает только «1 год» / «на весь срок лизинга»; явный срок — пояснение на превью.
        result = parse_result(build_casco_application(period_whole_term_value='4 года'))
        self.assertEqual(result.data['insurance_period'], 'на весь срок лизинга')
        self.assertEqual(result.data['parser_v2_payload']['insurance_period_term'], '4 года')
        self.assertIn('В бланке указан срок: 4 года', ' '.join(w['message'] for w in result.warnings))

    def test_no_mark_leaves_period_empty(self):
        data = parse(build_casco_application(period_whole_term_value=None))
        self.assertEqual(data['insurance_period'], '')


class AutostartRegressionTests(SimpleTestCase):
    """Автозапуск (§4.5: 11 правок, 2 скрытые ошибки; задача 6.2)."""

    def test_empty_value_means_no(self):
        self.assertFalse(parse(build_casco_application())['has_autostart'])

    def test_explicit_net_means_no(self):
        self.assertFalse(parse(build_casco_application(autostart_value='нет'))['has_autostart'])

    def test_dropdown_value_autostart_means_yes(self):  # исправлено в 6.2
        self.assertTrue(parse(build_casco_application(autostart_value='автозапуск'))['has_autostart'])

    def test_detailed_autostart_value_means_yes(self):
        value = 'автозапуск с 1-м ключом (размещение 2-ого ключа в ТС)'
        self.assertTrue(parse(build_casco_application(autostart_value=value))['has_autostart'])

    def test_without_autostart_means_no(self):
        self.assertFalse(parse(build_casco_application(autostart_value='без автозапуска'))['has_autostart'])


class PremiumFrequencyRegressionTests(SimpleTestCase):
    """Порядок уплаты и рассрочка (§4.5: 7 + 7 правок, 1 скрытая ошибка; задача 6.3)."""

    def test_annual_mark_next_to_option(self):
        wb = build_casco_application()
        wb.active['F34'] = MARK  # «ежегодно» — самая частая раскладка в корпусе (101 из 120)
        data = parse(wb)
        self.assertEqual(data['premium_frequency'], 'annual')
        self.assertFalse(data['has_installment'])

    def test_quarterly_mark_next_to_option(self):
        data = parse(build_casco_application(quarterly_mark=MARK))
        self.assertEqual(data['premium_frequency'], 'quarterly')
        self.assertTrue(data['has_installment'])

    def test_mark_under_single_payment_header(self):  # исправлено в 6.3
        data = parse(build_casco_application(single_payment_mark=MARK))
        self.assertEqual(data['premium_frequency'], 'single')
        self.assertFalse(data['has_installment'])


class BirthDateRegressionTests(SimpleTestCase):
    """Дата рождения ИП с двузначным годом (§4.5: скрытые ошибки 2061, 2063; задача 6.4)."""

    def test_four_digit_year(self):
        data = parse(build_casco_application(applicant_type='individual', birth_date_text='20.02.1961'))
        self.assertEqual(data.get('birth_date'), date(1961, 2, 20).isoformat())

    def test_two_digit_year_is_not_in_future(self):  # исправлено в 6.4
        data = parse(build_casco_application(applicant_type='individual', birth_date_text='20.02.61'))
        self.assertEqual(data.get('birth_date'), date(1961, 2, 20).isoformat())

    def test_two_digit_year_of_recent_birth_stays_in_2000s(self):
        from .parsers.excel_v2.parser import parse_birth_date_value

        self.assertEqual(parse_birth_date_value('05.03.01', today=date(2026, 9, 26)), date(2001, 3, 5))
        self.assertEqual(parse_birth_date_value('29.02.64', today=date(2026, 9, 26)), date(1964, 2, 29))


class DfaNumberRegressionTests(SimpleTestCase):
    """Номер ДФА (§4.5, §4.6; задача 6.5)."""

    def test_number_in_header_cell(self):
        self.assertEqual(parse(build_casco_application(dfa='ТС-20842'))['dfa_number'], 'ТС-20842')

    def test_full_number_with_suffix(self):
        self.assertEqual(parse(build_casco_application(dfa='ТС-20842-ГА-МН'))['dfa_number'], 'ТС-20842-ГА-МН')

    def test_preliminary_application_is_not_a_year(self):  # исправлено в 6.5
        result = parse_result(build_casco_application(dfa='ПРЕДВАРИТЕЛЬНАЯ'))
        self.assertEqual(result.data['dfa_number'], 'ПРЕДВАРИТЕЛЬНАЯ')
        self.assertIn('Номер ДФА ещё не присвоен', ' '.join(w['message'] for w in result.warnings))

    def test_iso_date_is_not_a_number(self):
        # Реальный случай: «2026-06-09» из даты заявки становился номером ДФА.
        wb = build_casco_application(dfa=None)
        wb.active['M2'] = '2026-06-09 00:00:00'
        self.assertNotIn('2026', parse(wb, filename='заявка б-н от 09.06.26 - TANK 500.xls')['dfa_number'])

    def test_suffix_completed_from_filename(self):
        data = parse(build_casco_application(dfa='ТС-20784'), filename='заявка 20784-ЛТ-КР - Фронт. погрузчик.xls')
        self.assertEqual(data['dfa_number'], 'ТС-20784-ЛТ-КР')

    def test_branch_from_dfa_code_when_form_has_none(self):
        data = parse(build_casco_application(dfa='ТС-20842-ГА-МН'))
        self.assertEqual(data['branch'], 'Мурманск')

    def test_kind_code_mismatch_with_insurance_type_warns(self):
        # КАСКО в бланке, а в номере «ЛТ» (спецтехника).
        result = parse_result(build_casco_application(dfa='ТС-20842-ЛТ-МН'))
        checks = [w for w in result.warnings if w['level'] == 'check']
        self.assertTrue(any('вид «ЛТ»' in w['message'] for w in checks))

    def test_kind_suggestion_for_special_vehicle_on_gaz_chassis(self):
        from .parsers.excel_v2.parser import suggest_dfa_kind

        objects = [{'description': 'спец. для нанесения дорожной разметки Шмель 11А (на базе ГАЗ 3302)',
                    'vehicle_category': 'B'}]
        self.assertEqual(suggest_dfa_kind('КАСКО', objects), 'ГА')
        self.assertEqual(suggest_dfa_kind('КАСКО', [{'description': 'HAVAL Jolion', 'vehicle_category': 'B'}]), 'ЛА')
        self.assertEqual(suggest_dfa_kind('страхование спецтехники', []), 'ЛТ')

    def test_full_number_suggested_but_not_applied(self):
        wb = build_casco_application(dfa='ТС-20842', object_description='1 фургон изотермический 278856 2024 новое 2800000 руб')
        wb.active['B3'] = 'Филиал'
        wb.active['C3'] = 'Мурманский филиал'
        result = parse_result(wb, filename='Заявка 20842 - фургон изотермический.xls')
        self.assertEqual(result.data['dfa_number'], 'ТС-20842')  # молча не подставляем
        self.assertEqual(result.data['parser_v2_payload']['dfa_suggestion'], 'ТС-20842-ГА-МН')


class ParserCorpusCheckCommandTests(TestCase):
    """Команда сверки парсера с итоговыми значениями на исходных файлах (5.5 / 6.9)."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def _v2_request_with_file(self, workbook, *, final, file_name='Заявка ТС 20842.xlsx'):
        from django.core.files.base import ContentFile
        from io import BytesIO

        from .models import InsuranceRequest, RequestAttachment

        buffer = BytesIO()
        workbook.save(buffer)
        handle = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        handle.write(buffer.getvalue())
        handle.close()
        upload_data = ExcelRequestParserV2().parse(handle.name, original_filename=file_name).data
        os.unlink(handle.name)

        insurance_request = InsuranceRequest.objects.create(
            client_name='ООО «Тестовая компания»', inn='7707083893', parser_confidence=1.0,
            additional_data={'parser_version': 'v2', 'parser_v2': {
                'source_file_name': file_name, 'original_data': upload_data, 'tracking': {},
            }},
            **final,
        )
        RequestAttachment.objects.create(
            request=insurance_request, file=ContentFile(buffer.getvalue(), name='source.xlsx'),
            original_filename=file_name, file_type='.xlsx',
        )
        return insurance_request

    def test_reports_fields_where_operator_changed_the_value(self):
        from io import StringIO

        from django.core.management import call_command

        with self.settings(MEDIA_ROOT=self.media):
            # В бланке отмечен весь срок, а сотрудник поставил 1 год (бизнес-решение) — расхождение.
            self._v2_request_with_file(
                build_casco_application(),
                final={'insurance_period': '1 год', 'dfa_number': 'ТС-20842', 'insurance_type': 'КАСКО'},
            )
            self._v2_request_with_file(
                build_casco_application(), file_name='Заявка 19818 - ИЗЪЯТОЕ.xlsx',
                final={'insurance_period': '1 год', 'dfa_number': 'ТС-20842'},
            )
            out = StringIO()
            call_command('parser_corpus_check', '--field', 'insurance_period', stdout=out)

        report = out.getvalue()
        self.assertIn('Заявок проверено: 1', report)
        self.assertIn('исключено: «Изъятое»: 1', report)
        self.assertIn('insurance_period | 1 | 0 (расх. 1) | 0 (расх. 1) | 0', report)
        self.assertIn('на весь срок лизинга | на весь срок лизинга | 1 год', report)


class ObjectRegressionTests(SimpleTestCase):
    """Объект: модель, стоимость / мощность, КАСКО C/E (§4.5: ≈ 17 правок; задача 6.6)."""

    def test_model_without_mileage_year_and_vin(self):
        from .parsers.excel_v2.parser import clean_model_text

        self.assertEqual(clean_model_text('500 (Пробег 13 800 км)'), '500')
        self.assertEqual(clean_model_text('500 г.в.) пpобeг тыс.км.'), '500')  # «пробег» с латинскими буквами
        self.assertEqual(clean_model_text('FAW J7 CA4180P77K25E5 vinLFWNHXSDXP1H08100'), 'FAW J7 CA4180P77K25E5')
        for model in ('Largus KS045L', 'X5 xDrive30d', 'R260LC-9S'):
            self.assertEqual(clean_model_text(model), model)

    def test_swapped_capacity_and_cost_columns(self):
        # Реальный случай (автокран): в L грузоподъёмность 32 670, в M стоимость 12 100 000.
        wb = build_casco_application(object_description='1 автокран SANY STC250T5-5')
        wb.active['L43'] = '32670'
        wb.active['M43'] = 12100000
        obj = parse(wb)['parser_v2_payload']['insured_objects'][0]
        self.assertEqual(obj['acquisition_cost_value'], '12100000')
        self.assertEqual(obj['power_or_capacity'], '32670')

    def test_semitrailer_is_casco_ce(self):
        wb = build_casco_application(object_description='1 полуприцеп-цистерна СЕСПЕЛЬ 2024 новое 7900000 руб')
        self.assertTrue(parse(wb)['has_casco_ce'])

    def test_passenger_car_is_not_casco_ce(self):
        self.assertFalse(parse(build_casco_application())['has_casco_ce'])


class BusinessActivityRegressionTests(SimpleTestCase):
    """Вид деятельности: ответ, который сам начинается словами «Основным видом деятельности…».

    Реальный случай (ОБ-20852-ЛО-АР, отзыв сотрудника 30.09.2026): значение в D11 парсер принял
    за подпись, а затем взял заголовок варианта «ЛизингоДАТЕЛЬ» из D14.
    """

    def build(self, activity):
        wb = build_casco_application()
        sheet = wb.active
        sheet['B11'] = 'Основной вид деятельности:'
        sheet['D11'] = activity
        sheet['B12'] = 'ПАРАМЕТРЫ СТРАХОВОЙ СДЕЛКИ'
        sheet['B14'] = 'Страхователь'
        sheet['D14'] = 'ЛизингоДАТЕЛЬ'
        sheet['E14'] = 'ЛизингоПОЛУЧАТЕЛЬ'
        sheet['E15'] = MARK
        return wb

    def test_answer_starting_with_label_words(self):
        activity = ('Основным видом деятельности ООО «Тестовая компания» является производство '
                    'металлоконструкций и монтаж оборудования')
        result = parse_result(self.build(activity))
        self.assertEqual(result.data['business_activity'], activity)
        self.assertEqual(result.source_map['business_activity'], 'D11')

    def test_short_answer(self):
        self.assertEqual(parse(self.build('Разработка карьера'))['business_activity'], 'Разработка карьера')


class FranchiseAmountRegressionTests(SimpleTestCase):
    """Размеры франшизы: числа в отмеченной колонке «Абсолютная сумма» / «% от страховой суммы».

    Отзывы сотрудника 2026-10-01: в PDF было только «с франшизой», без сумм из бланка
    (в том числе «30 000, 50 000» — два варианта).
    """

    def build(self, without='', percent='', absolute=''):
        wb = build_casco_application()
        sheet = wb.active
        sheet['B27'] = 'Франшиза (отметьте знаком "Х" или укажите значение)'
        sheet['D28'] = 'Нет франшизы'
        sheet['E28'] = '% от страховой суммы'
        sheet['F28'] = 'Абсолютная сумма'
        for cell, value in (('D29', without), ('E29', percent), ('F29', absolute)):
            if value != '':
                sheet[cell] = value
        return wb

    def test_both_variants_with_absolute_amount(self):
        result = parse_result(self.build(without=MARK, absolute=30000))
        self.assertEqual(result.data['franchise_type'], 'both_variants')
        self.assertEqual(result.data['franchise_amounts'], ['30000'])
        self.assertEqual(result.data['franchise_unit'], 'rub')
        self.assertEqual(result.source_map['franchise_amounts'], 'F29')

    def test_two_amounts_are_two_variants(self):
        # Реальный случай (Псков, ИП Курников): «без франшизы» + «30 000, 50 000».
        data = parse(self.build(without=MARK, absolute='30 000, 50 000'))
        self.assertEqual(data['franchise_type'], 'both_variants')
        self.assertEqual(data['franchise_amounts'], ['30000', '50000'])

    def test_amount_written_as_text_with_currency(self):
        data = parse(self.build(absolute='150 000 руб.'))
        self.assertEqual(data['franchise_type'], 'with_franchise')
        self.assertEqual(data['franchise_amounts'], ['150000'])

    def test_percent_amount(self):
        data = parse(self.build(percent='1,5%'))
        self.assertEqual(data['franchise_amounts'], ['1.5'])
        self.assertEqual(data['franchise_unit'], 'percent')

    def test_mark_without_amount(self):
        data = parse(self.build(without=MARK, absolute=MARK))
        self.assertEqual(data['franchise_type'], 'both_variants')
        self.assertNotIn('franchise_amounts', data)


class FranchiseAmountsParsingTests(SimpleTestCase):
    """Разбор размеров франшизы из текста (ячейка бланка, поле формы)."""

    def test_parse_amounts(self):
        from .franchise import parse_amounts

        cases = {
            '30 000, 50 000': ['30000', '50000'],
            '30 000,50 000': ['30000', '50000'],
            '30000/50000': ['30000', '50000'],
            '30 000 и 50 000': ['30000', '50000'],
            '30 000 руб.': ['30000'],
            '30 000,00': ['30000'],
            '1,5%': ['1.5'],
            'Х': [],
            'не знаю': [],
        }
        for text, expected in cases.items():
            self.assertEqual([format(a.normalize(), 'f') for a in parse_amounts(text)], expected, text)


class FranchiseDisplayTests(SimpleTestCase):
    """Франшиза одной строкой и в письме."""

    def make(self, franchise_type, amounts=(), unit='rub'):
        from .models import InsuranceRequest

        return InsuranceRequest(franchise_type=franchise_type, franchise_amounts=list(amounts), franchise_unit=unit)

    def test_display(self):
        self.assertEqual(self.make('both_variants', ['30000']).franchise_display,
                         'Оба варианта: без франшизы и с франшизой 30 000 руб.')
        self.assertEqual(self.make('both_variants', ['30000', '50000']).franchise_display,
                         'Варианты: без франшизы; с франшизой 30 000 руб.; с франшизой 50 000 руб.')
        self.assertEqual(self.make('with_franchise', ['1.5'], 'percent').franchise_display,
                         'С франшизой 1,5 % от страховой суммы')
        self.assertEqual(self.make('both_variants').franchise_display,
                         'Оба варианта: без франшизы и с франшизой')
        self.assertEqual(self.make('none', ['30000']).franchise_display, 'Без франшизы')

    def email_text(self, request):
        from core.templates import EmailTemplateGenerator

        data = request.to_dict() if hasattr(request, 'pk') and request.pk else {
            'franchise_type': request.franchise_type, 'franchise_variants': request.franchise_variants,
            'insurance_type': 'КАСКО',
        }
        return EmailTemplateGenerator()._prepare_template_data(data)['franshiza_text']

    def test_email_text_lists_variants(self):
        text = self.email_text(self.make('both_variants', ['30000', '50000']))
        self.assertIn('требуется 3 варианта тарифа', text)
        self.assertIn('1) без франшизы;', text)
        self.assertIn('2) с франшизой = 30 000 руб.;', text)
        self.assertIn('3) с франшизой = 50 000 руб.', text)
        self.assertIn('2) с франшизой = 30 000 руб.', self.email_text(self.make('both_variants', ['30000'])))
        self.assertIn('тариф с франшизой = 30 000 руб.', self.email_text(self.make('with_franchise', ['30000'])))
        self.assertIn('тариф с франшизой и без франшизы', self.email_text(self.make('both_variants')))


class FranchiseBackfillMigrationTests(SimpleTestCase):
    """Миграция 0047: размеры франшизы из служебной записи source_map уже загруженных заявок."""

    def test_amounts_from_source(self):
        import importlib

        migration = importlib.import_module('insurance_requests.migrations.0047_backfill_franchise_amounts')
        parse = migration.amounts_from_source
        self.assertEqual(parse('D29=Х (D28: Нет франшизы); F29=30000 (F28: Абсолютная сумма)'), (['30000'], 'rub'))
        self.assertEqual(parse('F29=30 000, 50 000 (F28: Абсолютная сумма)'), (['30000', '50000'], 'rub'))
        self.assertEqual(parse('E29=1,5% (E28: % от страховой суммы)'), (['1.5'], 'percent'))
        self.assertEqual(parse('D29=Х (D28: Нет франшизы)'), ([], None))
        self.assertEqual(parse(''), ([], None))


class ObjectCategoryColumnLRegressionTests(SimpleTestCase):
    """Колонка L и разделы категорий (отзыв сотрудника 2026-10-01).

    Реальные случаи: автобус «53+1+1» (ТС-20826-2-ГА-КЗ) уходил в «Тип / категория» без категории D;
    «г/п 7,5 т.» (ТС-20838-ГА-МН) — так же; полуприцепы под разделом «Прицепы» получали категорию D.
    """

    def build(self, object_row, section_row=None, section_text=None, description='1 автобус Yutong ZK6128H',
              column_l=''):
        wb = build_casco_application()
        sheet = wb.active
        for cell in ('C43', 'J43', 'K43', 'M43', 'N43'):
            sheet[cell] = None
        sheet['L41'] = 'Мощность двигателя л.с. (для кат.B) Грузоподъемность (для кат.С) Кол-во мест (для кат.D)'
        sheet['B42'] = 'Транспортные средства категории B'
        sheet['B44'] = 'Транспортные средства категории C'
        sheet['B46'] = 'Транспортные средства категории D'
        if section_row:
            sheet[f'B{section_row}'] = section_text
        sheet[f'B{object_row}'] = 1
        sheet[f'C{object_row}'] = description
        sheet[f'J{object_row}'] = 2026
        sheet[f'K{object_row}'] = 'новое'
        if column_l:
            sheet[f'L{object_row}'] = column_l
        sheet[f'M{object_row}'] = 17000000
        sheet[f'N{object_row}'] = 'руб'
        return wb

    def obj(self, wb):
        return parse(wb)['parser_v2_payload']['insured_objects'][0]

    def test_bus_seats_go_to_column_l_value_and_category_d_kept(self):
        obj = self.obj(self.build(object_row=47, section_row=48, section_text='Специальная техника',
                                  column_l='53+1+1'))
        self.assertEqual(obj['power_or_capacity'], '53+1+1')
        self.assertEqual(obj['equipment_type'], 'Категория D')

    def test_load_capacity_with_units(self):
        obj = self.obj(self.build(object_row=45, description='1 Бортовой КАМАЗ-43118-48 с КМУ',
                                  column_l='г/п 7,5 т.'))
        self.assertEqual(obj['power_or_capacity'], 'г/п 7,5 т.')
        self.assertEqual(obj['equipment_type'], 'Категория C')

    def test_trailers_section_is_its_own_category(self):
        obj = self.obj(self.build(object_row=49, section_row=48, section_text='Прицепы',
                                  description='1 полуприцеп-цистерна СЕСПЕЛЬ'))
        self.assertEqual(obj['equipment_type'], 'Прицепы')

    def test_crawler_kind_still_kind(self):
        obj = self.obj(self.build(object_row=49, section_row=48, section_text='Специальная техника',
                                  description='1 экскаватор HYUNDAI R260LC-9S', column_l='гусеничная'))
        self.assertEqual(obj['equipment_type'], 'гусеничная')
        self.assertIsNone(obj.get('power_or_capacity'))


class PowerLabelTests(SimpleTestCase):
    """Подпись колонки L в PDF зависит от категории."""

    def test_labels(self):
        from .application_export import power_label
        from .models import InsuranceRequest

        cases = {
            'Категория B': 'Мощность, л.с.', 'Категория C': 'Грузоподъёмность', 'Категория D': 'Количество мест',
            'Прицепы': 'Грузоподъёмность', 'гусеничная': 'Мощность / производ.', '': 'Мощность / производ.',
        }
        for kind, label in cases.items():
            self.assertEqual(power_label(InsuranceRequest(equipment_type=kind)), label, kind)


def build_lease_application(start, end, shift=0):
    """Бланк с блоком «Сроки действия договора лизинга» (I14, подзаголовки M14/N14, даты M15/N15)."""
    wb = build_casco_application()
    sheet = wb.active
    row = 14 + shift
    sheet[f'I{row}'] = 'Сроки действия договора лизинга'
    sheet[f'M{row}'] = 'Дата начала'
    sheet[f'N{row}'] = 'Дата окончания'
    sheet[f'M{row + 1}'] = start
    sheet[f'N{row + 1}'] = end
    return wb


class LeaseDatesRegressionTests(SimpleTestCase):
    """«Сроки действия договора лизинга» (отзыв сотрудника 2026-10-02: в PDF не было дат договора)."""

    def build(self, start, end, shift=0):
        return build_lease_application(start, end, shift)

    def test_text_dates(self):
        result = parse_result(self.build('20.09.2024', '20.12.2028'))
        self.assertEqual(result.data['lease_start_date'], '2024-09-20')
        self.assertEqual(result.data['lease_end_date'], '2028-12-20')
        self.assertEqual(result.source_map['lease_start_date'], 'M15')

    def test_excel_serial_dates_and_ip_shift(self):
        data = parse(self.build('46299', '47394.0', shift=1))
        self.assertEqual(data['lease_start_date'], '2026-10-04')
        self.assertEqual(data['lease_end_date'], '2029-10-03')

    def test_no_block_no_dates(self):
        self.assertNotIn('lease_start_date', parse(build_casco_application()))


class LeaseTermDisplayTests(SimpleTestCase):
    def make(self, start=None, end=None):
        from datetime import date as d

        from .models import InsuranceRequest

        return InsuranceRequest(lease_start_date=d(*start) if start else None, lease_end_date=d(*end) if end else None)

    def test_display(self):
        self.assertEqual(self.make((2024, 9, 20), (2028, 12, 20)).lease_term_display,
                         '20.09.2024 — 20.12.2028 (4 г. 3 мес.)')
        self.assertEqual(self.make((2026, 1, 15), (2026, 12, 14)).lease_duration_label, '11 мес.')
        # ТС-19854-ЛТ: 04.10.2026 — 03.10.2027 — полный год (дата окончания включительно).
        self.assertEqual(self.make((2026, 10, 4), (2027, 10, 3)).lease_duration_label, '1 г.')
        self.assertEqual(self.make((2025, 3, 1), (2028, 2, 29)).lease_duration_label, '3 г.')
        self.assertEqual(self.make((2026, 1, 15), (2029, 1, 15)).lease_duration_label, '3 г.')
        self.assertEqual(self.make((2024, 9, 20)).lease_term_display, 'с 20.09.2024')
        self.assertEqual(self.make().lease_term_display, '')

    def test_email_line(self):
        from core.templates import EmailTemplateGenerator

        generator = EmailTemplateGenerator()
        self.assertEqual(
            generator._format_lease_term_text(
                {'lease_start_date': '20.09.2024', 'lease_end_date': '20.12.2028', 'lease_duration': '4 г. 3 мес.'}),
            'Срок договора лизинга: с 20.09.2024 по 20.12.2028 (4 г. 3 мес.).\n')
        self.assertEqual(generator._format_lease_term_text({}), '')


class BackfillLeaseDatesCommandTests(TestCase):
    """Команда backfill_lease_dates: даты из исходного Excel, только в пустые поля."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def make_request(self, **extra):
        from django.core.files.base import ContentFile

        from .models import InsuranceRequest, RequestAttachment

        wb = build_lease_application('20.09.2024', '20.12.2028')
        handle = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        handle.close()
        wb.save(handle.name)
        with open(handle.name, 'rb') as source:
            content = source.read()
        os.unlink(handle.name)
        request = InsuranceRequest.objects.create(
            client_name='ООО Тест', inn='7707083893', insurance_type='КАСКО', dfa_number='ТС-1',
            additional_data={'parser_v2': {'warnings': []}}, **extra)
        attachment = RequestAttachment(request=request, original_filename='Заявка ТС 1.xlsx', file_type='.xlsx')
        attachment.file.save('Заявка ТС 1.xlsx', ContentFile(content), save=True)
        return request

    def test_dry_run_then_write(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test.utils import override_settings

        with override_settings(MEDIA_ROOT=self.media):
            request = self.make_request()
            out = StringIO()
            call_command('backfill_lease_dates', '--dry-run', stdout=out)
            request.refresh_from_db()
            self.assertIsNone(request.lease_start_date)
            self.assertIn('заполнено: 1 (DRY-RUN', out.getvalue())

            call_command('backfill_lease_dates', stdout=StringIO())
            request.refresh_from_db()
            self.assertEqual(str(request.lease_start_date), '2024-09-20')
            self.assertEqual(str(request.lease_end_date), '2028-12-20')


def build_anti_theft_application(alarm=None, immobilizer=None, mechanical=None, satellite=None, telematics=None):
    """Блок «Противоугонные системы и оборудование» как в реальных бланках (строки 51–63)."""
    wb = build_casco_application()
    sheet = wb.active
    sheet['B51'] = 'Противоугонные системы и оборудование (отметьте знаком "Х")'
    sheet['D51'] = 'Штатная'
    sheet['E51'] = 'Установленная дополнительно'
    sheet['F51'] = 'название, модель'
    sheet['B52'] = 'Сигнализация'
    sheet['B53'] = 'Иммобилайзер'
    for row, values in ((52, alarm), (53, immobilizer)):
        for column, value in (values or {}).items():
            sheet[f'{column}{row}'] = value
    sheet['B55'] = 'Механические противоугонные устройства'
    sheet['D55'] = 'Капот'
    sheet['D56'] = 'рычаг КПП'
    sheet['D57'] = 'Прочее'
    for cell, value in (mechanical or {}).items():
        sheet[cell] = value
    sheet['B59'] = 'Спутниковая противоугонная система'
    sheet['D59'] = 'Марка'
    sheet['E59'] = 'Модель'
    sheet['F59'] = 'Конфигурация'
    for cell, value in (satellite or {}).items():
        sheet[cell] = value
    sheet['C62'] = 'Телематический комплекс'
    sheet['D62'] = 'Наименование'
    if telematics:
        sheet['D63'] = telematics
    return wb


class AntiTheftRegressionTests(SimpleTestCase):
    """Противоугонные системы (2026-10-02): раньше блок не распознавался вовсе."""

    def test_alarm_added_with_model_and_standard_immobilizer(self):
        # Реальные случаи: ТС-20914-ЛА-МН (E52=Х, F52=StarLine A93), ТС-20857-ЛА-МСК (D53=Х).
        result = parse_result(build_anti_theft_application(
            alarm={'E': 'Х', 'F': 'StarLine A93'}, immobilizer={'D': 'Х'}, telematics='АВО Pharos'))
        self.assertEqual(result.data['anti_theft_systems'],
                         'Сигнализация: установлена доп., StarLine A93; Иммобилайзер: штатный')
        self.assertEqual(result.data['telematics_complex'], 'АВО Pharos')

    def test_mechanical_and_satellite(self):
        data = parse(build_anti_theft_application(
            mechanical={'E56': 'Х', 'E57': 'блокиратор руля'},
            satellite={'D60': 'Цезарь Сателлит', 'E60': 'Pandora DX-91', 'F60': 'GSM/GPS'}))
        self.assertEqual(data['anti_theft_systems'],
                         'Механические: рычаг кпп, блокиратор руля; Спутниковая: Цезарь Сателлит Pandora DX-91 GSM/GPS')

    def test_empty_block(self):
        self.assertNotIn('anti_theft_systems', parse(build_anti_theft_application()))

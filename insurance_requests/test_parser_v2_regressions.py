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
    dfa='ТС-20842',
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

    @unittest.expectedFailure  # 6.5: вместо «ПРЕДВАРИТЕЛЬНАЯ» берётся год из даты заявки — «2026»
    def test_preliminary_application_is_not_a_year(self):
        data = parse(build_casco_application(dfa='ПРЕДВАРИТЕЛЬНАЯ'))
        self.assertNotEqual(data['dfa_number'], '2026')
        self.assertEqual(data['dfa_number'].lower(), 'предварительная')


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

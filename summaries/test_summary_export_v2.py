"""Свод V2 (бета): содержание, оформление, печать на A4 и доступ только суперпользователю."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary, SummaryCompanyStatus
from summaries.services.summary_export_v2 import SummaryExportV2Service

COMPANIES = ['Альфа', 'ВСК', 'Зетта', 'Согласие', 'Ингосстрах', 'Пари', 'Согаз', 'Ренессанс',
             'Абсолют', 'Росгосстрах', 'Энергогарант', 'Югория']


def _all_text(sheet):
    return ' '.join(str(c.value) for row in sheet.iter_rows() for c in row if c.value is not None)


class SummaryExportV2Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        for order, name in enumerate(COMPANIES, start=1):
            InsuranceCompany.objects.get_or_create(
                name=name, defaults={'display_name': name, 'sort_order': order, 'is_active': True})
        cls.request_obj = InsuranceRequest.objects.create(
            client_name='ООО "ПМК 77"', inn='7751199551', dfa_number='ТС-20848-ЛА-КЗ', branch='Казань',
            insurance_type='КАСКО', brand='Mercedes-Benz', model='V 300 D 4Matic', condition='new',
            acquisition_cost_value=Decimal('17600000'), acquisition_cost_currency='RUB',
            usage_purposes='представительские', anti_theft_systems='Сигнализация: штатная',
            lease_start_date=date(2026, 9, 11), lease_end_date=date(2028, 9, 10),
            franchise_type='both_variants',
        )
        cls.summary = InsuranceSummary.objects.create(request=cls.request_obj, status='collecting')
        # Ответы СК (по мотивам свода 304): ВСК дороже Альфы, у Зетты территория из B3
        cls._offer('ВСК', 1, 17_600_000, 534_670.70, 321_027.57, notes='территория страхования: РФ')
        cls._offer('ВСК', 2, 14_960_000, 534_670.70, 321_027.57)
        cls._offer('Альфа', 1, 17_600_000, 357_773, 285_120)
        cls._offer('Альфа', 2, 14_960_000, 357_773, 285_120)
        cls._offer('Зетта', 1, 17_600_000, 440_000, 352_000, territory='Российская Федерация')
        cls._offer('Зетта', 2, 14_960_000, 440_000, 352_000, territory='Российская Федерация')
        SummaryCompanyStatus.objects.update_or_create(
            summary=cls.summary, company=InsuranceCompany.objects.get(name='Согласие'),
            defaults={'status': SummaryCompanyStatus.DECLINED})

    @classmethod
    def _offer(cls, company, year, insurance_sum, premium_1, premium_2, territory=None, notes='',
               summary=None):
        return InsuranceOffer.objects.create(
            summary=summary or cls.summary, company_name=company, insurance_year=year,
            insurance_sum=Decimal(str(insurance_sum)),
            franchise_1=Decimal('0'), premium_with_franchise_1=Decimal(str(premium_1)),
            franchise_2=Decimal('100000') if premium_2 else None,
            premium_with_franchise_2=Decimal(str(premium_2)) if premium_2 else None,
            coverage_territory=territory, notes=notes,
        )

    def _workbook(self, summary=None, client=True):
        data = SummaryExportV2Service().generate(summary or self.summary, is_client_version=client)
        return load_workbook(BytesIO(data.getvalue()))


class SummaryExportV2ContentTests(SummaryExportV2Base):
    def test_client_has_only_summary_sheet_full_adds_request_parameters(self):
        self.assertEqual(self._workbook(client=True).sheetnames, ['Свод'])
        self.assertEqual(self._workbook(client=False).sheetnames, ['Свод', 'Параметры запроса'])

    def test_header_keeps_v1_fields_and_adds_date(self):
        ws = self._workbook()['Свод']
        self.assertTrue(ws['A1'].value.startswith('Свод котировок и условий от '))
        labels = [ws[f'A{r}'].value for r in range(2, 7)]
        self.assertEqual(labels, ['Заявка №', 'Объект страхования', 'Лизингополучатель',
                                  'Цели использования', 'Примечание'])
        self.assertEqual(ws['C2'].value, 'ТС-20848-ЛА-КЗ')
        self.assertEqual(ws['C4'].value, 'ООО "ПМК 77"')

    def test_companies_sorted_by_total_of_offer_1_and_declined_last(self):
        ws = self._workbook()['Свод']
        names = [ws[f'A{r}'].value for r in range(10, ws.max_row + 1) if ws[f'A{r}'].value]
        self.assertEqual(names, ['Альфа', 'Зетта', 'ВСК', 'Согласие'])
        self.assertEqual(ws['B16'].value, 'Отказ от страхования')

    def test_year_rows_rates_and_totals_are_live_formulas(self):
        ws = self._workbook()['Свод']
        self.assertEqual(ws['B10'].value, '1 год')
        self.assertEqual(ws['C10'].value, 17_600_000)
        self.assertEqual(ws['D10'].value, '=IF(AND(C10<>0,E10<>0),E10/C10,"")')
        self.assertEqual(ws['H10'].value, '=SUM(E10:E11)')
        self.assertEqual(ws['M10'].value, '=SUM(J10:J11)')
        self.assertEqual(ws['K10'].value, 100_000)
        self.assertIn('H10:H11', {str(r) for r in ws.merged_cells.ranges})

    def test_variant_captions_and_column_titles(self):
        ws = self._workbook()['Свод']
        self.assertEqual(ws['D8'].value, 'Предложение 1 · без франшизы')
        self.assertEqual(ws['I8'].value, 'Предложение 2 · франшиза 100 000')
        self.assertEqual([ws[f'{c}9'].value for c in 'DEFGH'],
                         ['Тариф', 'Премия', 'Франшиза', 'Платежей в год', 'ИТОГО за срок'])
        self.assertEqual(ws['N8'].value, 'Территория страхования')
        self.assertEqual(ws['O8'].value, 'Комментарии')

    def test_territory_and_notes_follow_v1_rules_without_service_placeholder(self):
        ws = self._workbook()['Свод']
        self.assertEqual(ws['N12'].value, 'Российская Федерация')  # Зетта
        self.assertEqual(ws['N10'].value, '—')  # Альфа: ответ до сбора территории
        self.assertNotIn('ранее не собиралась', _all_text(ws))
        # системный комментарий о франшизе — как в своде V1
        self.assertIn('Требуется согласование франшизы с ГО.', ws['O14'].value)
        self.assertTrue(ws['O14'].value.startswith('территория страхования: РФ'))

    def test_selection_fields_are_manual_yellow_with_lists_and_highlight(self):
        ws = self._workbook()['Свод']
        self.assertEqual(ws['A7'].value, 'Выбрана СК:')
        self.assertIsNone(ws['C7'].value)
        self.assertIsNone(ws['H7'].value)
        self.assertEqual(ws['C7'].fill.fgColor.rgb, '00FFF2B3')
        lists = {str(dv.sqref): dv.formula1 for dv in ws.data_validations.dataValidation}
        self.assertEqual(lists['C7'], '"Альфа,Зетта,ВСК"')
        self.assertEqual(lists['H7'], '"Предложение 1,Предложение 2"')
        rules = [rule.formula[0] for rng in ws.conditional_formatting for rule in rng.rules]
        self.assertIn('$C$7="Альфа"', rules)
        self.assertIn('AND($C$7="Альфа",$H$7="Предложение 2")', rules)

    def test_white_label(self):
        wb = self._workbook()
        self.assertFalse(wb.properties.creator)
        text = _all_text(wb['Свод']).lower()
        for brand in ('онлайн', 'брокер', 'insflow'):
            self.assertNotIn(brand, text)
        self.assertFalse(wb['Свод']._images)

    def test_request_parameters_sheet_has_v1_fields_and_new_ones(self):
        ws = self._workbook(client=False)['Параметры запроса']
        values = {ws[f'A{r}'].value: ws[f'B{r}'].value for r in range(1, ws.max_row + 1) if ws[f'A{r}'].value}
        self.assertEqual(values['ИНН'], '7751199551')
        self.assertEqual(values['Филиал'], 'Казань')
        self.assertEqual(values['Срок договора лизинга'], '11.09.2026 — 10.09.2028 (2 г.)')
        self.assertEqual(values['Противоугонные системы'], 'Сигнализация: штатная')
        self.assertIn('Запрашиваемые риски', values)
        self.assertNotIn('Доп. параметры имущества', values)

    def test_single_variant_summary_has_no_offer_2_columns(self):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='1', dfa_number='ТС-1',
                                                 vehicle_info='Экскаватор')
        summary = InsuranceSummary.objects.create(request=request, status='collecting')
        self._offer('Альфа', 1, 1_000_000, 50_000, None, summary=summary)
        ws = self._workbook(summary)['Свод']
        self.assertEqual(ws['I8'].value, 'Территория страхования')
        self.assertEqual(ws['J8'].value, 'Комментарии')
        lists = {str(dv.sqref): dv.formula1 for dv in ws.data_validations.dataValidation}
        self.assertEqual(lists['H7'], '"Предложение 1"')


class SummaryExportV2PrintTests(SummaryExportV2Base):
    def test_numbers_on_first_page_conditions_after_column_break(self):
        ws = self._workbook()['Свод']
        self.assertEqual([b.id for b in ws.col_breaks.brk], [13])  # после «ИТОГО» предложения 2 (M)
        self.assertEqual(ws.print_title_cols, '$A:$A')
        self.assertEqual(ws.print_title_rows, '$8:$9')
        self.assertEqual(str(ws.page_setup.paperSize), str(ws.PAPERSIZE_A4))
        self.assertFalse(ws.sheet_properties.pageSetUpPr.fitToPage)
        self.assertEqual(ws.page_setup.orientation, 'landscape')
        self.assertTrue(72 <= ws.page_setup.scale <= 100)
        self.assertEqual(list(ws.row_breaks.brk), [])

    def test_long_summary_breaks_only_between_company_blocks(self):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='2', dfa_number='ТС-2',
                                                 vehicle_info='Автомобиль HAVAL H3')
        summary = InsuranceSummary.objects.create(request=request, status='collecting')
        for i, company in enumerate(COMPANIES):
            for year in range(1, 6):
                self._offer(company, year, 3_000_000 - year * 100_000, 80_000 + i * 1_000, None,
                            notes='Требуется осмотр ТС. ' * 3, summary=summary)
        ws = self._workbook(summary)['Свод']
        breaks = [b.id for b in ws.row_breaks.brk]
        self.assertTrue(breaks)
        for row in breaks:
            # следующая за разрывом строка — первая строка блока СК
            self.assertIn(ws[f'A{row + 1}'].value, COMPANIES)
            self.assertEqual(ws[f'B{row + 1}'].value, '1 год')
        self.assertEqual([b.id for b in ws.col_breaks.brk], [8])


class SummaryExportV2AccessTests(SummaryExportV2Base):
    def setUp(self):
        self.superuser = User.objects.create_superuser('root', password='p')
        # страница свода открыта группам; суперпользователи на проде состоят в «Администраторах»
        self.superuser.groups.add(Group.objects.get_or_create(name='Администраторы')[0])
        self.admin = User.objects.create_user('admin', password='p')
        self.admin.groups.add(Group.objects.get_or_create(name='Администраторы')[0])

    def _url(self, version):
        return reverse('summaries:generate_summary_file_v2', args=[self.summary.pk, version])

    def test_superuser_downloads_both_versions_in_any_status(self):
        self.client.force_login(self.superuser)
        for version, sheets in (('client', ['Свод']), ('full', ['Свод', 'Параметры запроса'])):
            response = self.client.get(self._url(version))
            self.assertEqual(response.status_code, 200)
            self.assertIn(f'{version}_svod_v2_20848', response['Content-Disposition'])
            self.assertEqual(load_workbook(BytesIO(response.content)).sheetnames, sheets)

    def test_admin_group_without_superuser_is_denied(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self._url('client')).status_code, 403)

    def test_unknown_version_is_404(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(self._url('pdf')).status_code, 404)

    def test_v2_card_visible_only_to_superuser(self):
        detail = reverse('summaries:summary_detail', args=[self.summary.pk])
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(detail), 'Клиентский свод V2')
        self.client.force_login(self.admin)
        response = self.client.get(detail)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Клиентский свод V2')

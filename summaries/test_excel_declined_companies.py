"""Declined and legacy company statuses in the current summary export."""
from summaries.models import InsuranceOffer, SummaryCompanyStatus
from summaries.test_summary_export_v2 import SummaryExportV2Base, COMPANIES


class DeclinedCompaniesExportTests(SummaryExportV2Base):
    def _names(self, sheet):
        return [sheet[f'A{row}'].value for row in range(11, sheet.max_row + 1)
                if sheet[f'A{row}'].value in COMPANIES]

    def test_declined_company_follows_quoted_companies(self):
        for client in (True, False):
            sheet = self._workbook(client=client)['Свод']
            self.assertEqual(self._names(sheet), ['Альфа', 'Зетта', 'ВСК', 'Согласие'])
            self.assertEqual(sheet['B17'].value, 'Отказ от страхования')

    def test_single_variant_also_includes_declined_companies(self):
        InsuranceOffer.objects.filter(summary=self.summary).update(
            premium_with_franchise_2=None, franchise_2=None)
        for client in (True, False):
            sheet = self._workbook(client=client)['Свод']
            self.assertEqual(self._names(sheet)[-1], 'Согласие')
            self.assertIn('Отказ от страхования',
                          ' '.join(str(c.value) for row in sheet for c in row if c.value is not None))

    def test_only_declined_companies_still_produce_a_workbook(self):
        self.summary.offers.all().delete()
        for client in (True, False):
            sheet = self._workbook(client=client)['Свод']
            self.assertEqual(self._names(sheet), ['Согласие'])
            self.assertEqual(sheet['B11'].value, 'Отказ от страхования')

    def test_no_declined_status_does_not_invent_a_declined_row(self):
        SummaryCompanyStatus.objects.filter(summary=self.summary).delete()
        self.assertEqual(self._names(self._workbook()['Свод']), ['Альфа', 'Зетта', 'ВСК'])

    def test_legacy_free_text_note_is_preserved_without_fabricated_statuses(self):
        SummaryCompanyStatus.objects.filter(summary=self.summary).delete()
        self.summary.notes = 'Остальные СК — отказ'
        self.summary.save(update_fields=['notes'])
        sheet = self._workbook()['Свод']
        self.assertEqual(sheet['B8'].value, 'Остальные СК — отказ')
        self.assertEqual(self._names(sheet), ['Альфа', 'Зетта', 'ВСК'])

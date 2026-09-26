"""Восстановление статусов СК для старых сводов (analytics_redesign_2026_09, задача 2.5)."""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from insurance_requests.models import InsuranceRequest

from .management.commands.restore_company_statuses import _company_patterns, parse_notes
from .models import InsuranceOffer, InsuranceSummary, StatusEvent, SummaryCompanyStatus
from .services import company_statuses


class NotesParsingTests(TestCase):
    def parse(self, notes):
        declined, no_answer = parse_notes(notes, _company_patterns())
        return set(declined), set(no_answer)

    def test_real_note_formats(self):
        self.assertEqual(self.parse('СК Абсолют, Зетта - ОТКАЗ'), ({'Абсолют', 'Зетта'}, set()))
        self.assertEqual(
            self.parse('Зетта, ВСК - отказ от страхования.\nРенессанс тариф не предоставил.'),
            ({'ВСК', 'Зетта'}, {'Ренессанс'}),
        )
        self.assertEqual(self.parse('Срок страхования - 25 месяцев. СК Абсолют - ОТКАЗ. ОСАГО - 34 547 руб.'),
                         ({'Абсолют'}, set()))
        self.assertEqual(self.parse('СК ВСК, РГС, Альфа - ОТКАЗ')[0], {'ВСК', 'Росгосстрах', 'Альфа'})
        self.assertEqual(self.parse('СК ПСБ, Ренессанс - ОТКАЗ')[0], {'ПСБ-страхование', 'Ренессанс'})
        self.assertEqual(self.parse('отказы от Страховщиков\r\nРенессанс, СОГАЗ, Абсолют, РГС')[0],
                         {'Ренессанс', 'Согаз', 'Абсолют', 'Росгосстрах'})
        self.assertEqual(self.parse('Остальные СК - ОТКАЗ'), (set(), set()))
        self.assertEqual(self.parse('Страхование имущества на хранении'), (set(), set()))


class RestoreCommandTests(TestCase):
    def make_summary(self, notes, offers=()):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', dfa_number='ТС-1')
        summary = InsuranceSummary.objects.create(request=request, status='completed_accepted', notes=notes)
        for company in offers:
            InsuranceOffer.objects.create(
                summary=summary, company_name=company, insurance_year=1, insurance_sum=Decimal('1000000'),
                franchise_1=Decimal('0'), premium_with_franchise_1=Decimal('50000'),
            )
        SummaryCompanyStatus.objects.filter(summary=summary).delete()  # как у старых сводов: строк не было
        return summary

    def statuses(self, summary):
        return dict(summary.company_statuses.values_list('company__name', 'status'))

    def test_dry_run_writes_nothing(self):
        summary = self.make_summary('СК Зетта - ОТКАЗ', offers=['ВСК'])
        out = StringIO()
        call_command('restore_company_statuses', stdout=out)
        self.assertIn('Только отчёт', out.getvalue())
        self.assertEqual(self.statuses(summary), {})

    def test_apply_restores_offered_declined_requested_without_journal_or_blocking(self):
        summary = self.make_summary('Зетта, ВСК - отказ от страхования.\nРенессанс тариф не предоставил.',
                                    offers=['ВСК', 'Абсолют'])
        new = InsuranceSummary.objects.create(
            request=InsuranceRequest.objects.create(client_name='ООО Новый', inn='7707083893', dfa_number='ТС-2'),
            notes='СК Абсолют - ОТКАЗ',
        )
        company_statuses.init_for_summary(new)
        events_before = StatusEvent.objects.count()

        call_command('restore_company_statuses', '--apply', stdout=StringIO())

        self.assertEqual(self.statuses(summary), {
            'ВСК': 'offered', 'Абсолют': 'offered', 'Зетта': 'declined', 'Ренессанс': 'requested',
        })
        self.assertTrue(all(summary.company_statuses.values_list('restored', flat=True)))
        self.assertEqual(StatusEvent.objects.count(), events_before)
        summary.refresh_from_db()
        self.assertFalse(summary.company_statuses_required)
        self.assertEqual(company_statuses.missing_companies(summary), [])
        self.assertEqual(self.statuses(new)['Абсолют'], 'undefined')  # новые своды не трогаем

        call_command('restore_company_statuses', '--apply', stdout=StringIO())  # повторный запуск — без дублей
        self.assertEqual(summary.company_statuses.count(), 4)

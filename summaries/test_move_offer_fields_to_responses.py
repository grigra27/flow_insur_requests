"""Уборка данных: перенос территории, примечания и файла из годовых предложений в «Ответ СК»."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary, InsurerResponse


class MoveOfferFieldsToResponsesTests(TestCase):
    def setUp(self):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='1', dfa_number='ТС-1')
        self.summary = InsuranceSummary.objects.create(request=request)

    def _offer(self, company, year, **fields):
        offer = InsuranceOffer.objects.create(
            summary=self.summary, company_name=company, insurance_year=year, insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'), premium_with_franchise_1=Decimal('10000'), **fields)
        return offer

    def _run(self, *args):
        out = StringIO()
        call_command('move_offer_fields_to_responses', *args, stdout=out)
        return out.getvalue()

    def test_report_does_not_write(self):
        self._offer('Согаз', 1, coverage_territory='РФ', notes='Осмотр обязателен')
        InsurerResponse.objects.all().delete()
        report = self._run()
        self.assertIn('«Ответ СК» создать: 1, дополнить: 0', report)
        self.assertIn('Только отчёт', report)
        self.assertFalse(InsurerResponse.objects.exists())

    def test_apply_creates_responses_with_company_level_values(self):
        first = self._offer('Согаз', 1, coverage_territory='РФ, кроме новых территорий', notes='Осмотр обязателен',
                            attachment_file='offers/2026/10/01/sogaz.xlsx')
        self._offer('Согаз', 2, coverage_territory='РФ, кроме новых территорий', notes='  Осмотр   обязателен ')
        self._offer('Согаз', 3, coverage_territory='РФ, кроме новых территорий', notes='Скидка за 3 года')
        self._offer('Альфа', 1, coverage_territory=None)
        self._offer('ВСК', 1, coverage_territory='')
        InsurerResponse.objects.all().delete()
        InsuranceOffer.objects.filter(pk=first.pk).update(received_at=timezone.now() - timedelta(days=30))
        self._run('--apply')

        sogaz = InsurerResponse.objects.get(summary=self.summary, company_name='Согаз')
        self.assertEqual(sogaz.coverage_territory, 'РФ, кроме новых территорий')
        self.assertEqual(sogaz.notes, 'Осмотр обязателен\nСкидка за 3 года')  # повтор с пробелами не дублируется
        self.assertEqual(sogaz.source_file.name, 'offers/2026/10/01/sogaz.xlsx')
        self.assertEqual(sogaz.template_version, InsurerResponse.TEMPLATE_V1)
        self.assertLess(sogaz.received_at, timezone.now() - timedelta(days=29))  # дата первого предложения
        # NULL (до сбора территории) и пустая строка («не указано страховщиком») различаются
        self.assertIsNone(InsurerResponse.objects.get(company_name='Альфа').coverage_territory)
        self.assertEqual(InsurerResponse.objects.get(company_name='ВСК').coverage_territory, '')
        # годовые строки — архив, не тронуты
        self.assertEqual(InsuranceOffer.objects.get(company_name='Согаз', insurance_year=2).notes, '  Осмотр   обязателен ')

    def test_existing_response_only_empty_fields_filled(self):
        self._offer('Согаз', 1, coverage_territory='РФ', notes='из годовой строки')
        response, _ = InsurerResponse.objects.get_or_create(summary=self.summary, company_name='Согаз')
        InsurerResponse.objects.filter(pk=response.pk).update(
            coverage_territory=None, notes='уже в ответе', rnpk_status='included',
            source_file='responses/2026/10/01/a.xlsx')
        report = self._run('--apply')
        self.assertIn("уже другое значение (оставлено как есть): {'notes': 1}", report)
        response.refresh_from_db()
        self.assertEqual((response.coverage_territory, response.notes, response.rnpk_status),
                         ('РФ', 'уже в ответе', 'included'))
        self.assertEqual(response.source_file.name, 'responses/2026/10/01/a.xlsx')

    def test_second_run_has_nothing_to_do(self):
        self._offer('Согаз', 1, coverage_territory='РФ', notes='Примечание')
        InsurerResponse.objects.all().delete()
        self._run('--apply')
        self.assertIn('«Ответ СК» создать: 0, дополнить: 0', self._run())

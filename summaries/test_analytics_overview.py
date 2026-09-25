"""Обзор аналитики с цифрами (analytics_redesign_2026_09, задача 1.6)."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class AnalyticsOverviewTests(TestCase):
    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.admin = User.objects.create_user(username='overview_admin', password='testpass123')
        self.admin.groups.add(admin_group)
        self.client.login(username='overview_admin', password='testpass123')

        now = timezone.now()
        self.accepted = self._summary('DFA-1', 'completed_accepted', 'Абсолют', now - timedelta(days=5))
        self._offer(self.accepted, 'Абсолют', '10000.00')
        self._offer(self.accepted, 'Альфа', '12000.00')

        old = self._summary('DFA-2', 'completed_accepted', 'Альфа', now - timedelta(days=200))
        self._offer(old, 'Альфа', '9000.00')

        self._summary('DFA-3', 'collecting', '', now - timedelta(days=2))
        self._summary('DFA-4', 'sent', '', now - timedelta(days=3))
        self._summary('DFA-5', 'completed_rejected', '', now - timedelta(days=4))

    def _summary(self, dfa, status, company, created_at):
        insurance_request = InsuranceRequest.objects.create(
            created_by=self.admin, client_name=f'Клиент {dfa}', inn='1234567890',
            insurance_type='КАСКО', dfa_number=dfa, branch='Москва',
        )
        InsuranceRequest.objects.filter(pk=insurance_request.pk).update(created_at=created_at)
        summary = InsuranceSummary.objects.create(
            request=insurance_request, status=status, selected_company=company or None,
            selected_franchise_variant=1 if company else None,
        )
        InsuranceSummary.objects.filter(pk=summary.pk).update(created_at=created_at)
        return summary

    def _offer(self, summary, company, premium):
        InsuranceOffer.objects.create(
            summary=summary, company_name=company, insurance_year=1,
            insurance_sum=Decimal('1000000.00'), premium_with_franchise_1=Decimal(premium),
            franchise_1=Decimal('0'),
        )

    def test_overview_kpi_all_time(self):
        response = self.client.get(reverse('summaries:analytics'))

        self.assertEqual(response.status_code, 200)
        kpi = response.context['kpi']
        self.assertEqual(kpi['requests'], 5)
        self.assertEqual(kpi['deals'], 2)
        self.assertEqual(kpi['insured_sum_total'], Decimal('2000000.00'))
        self.assertEqual(kpi['premium_total'], Decimal('19000.00'))
        # Открытые своды — текущее состояние, без учёта периода.
        self.assertEqual(kpi['open_summaries'], 2)
        self.assertEqual(
            {item['label']: item['count'] for item in kpi['open_breakdown']},
            {'сбор': 1, 'готов': 0, 'отправлен': 1},
        )

    def test_overview_period_filter(self):
        response = self.client.get(reverse('summaries:analytics'), {'period': '30'})
        kpi = response.context['kpi']

        self.assertEqual(kpi['requests'], 4)
        self.assertEqual(kpi['deals'], 1)
        self.assertEqual(kpi['premium_total'], Decimal('10000.00'))
        self.assertEqual(kpi['open_summaries'], 2)
        self.assertEqual([row['company_name'] for row in response.context['top_companies']], ['Абсолют'])

    def test_overview_numbers_match_companies_page(self):
        overview = self.client.get(reverse('summaries:analytics'), {'period': '365'}).context
        companies = self.client.get(reverse('summaries:analytics_insurance_companies'), {'period': '365'}).context

        self.assertEqual(overview['kpi']['deals'], companies['kpi']['total_deals'])
        self.assertEqual(overview['kpi']['insured_sum_total'], companies['kpi']['insured_sum_total'])
        self.assertEqual(overview['kpi']['premium_total'], companies['kpi']['premium_total'])

    def test_overview_charts(self):
        charts = self.client.get(reverse('summaries:analytics')).context['charts']

        self.assertEqual(sum(charts['monthly']['requests']), 5)
        self.assertEqual(sum(charts['monthly']['deals']), 2)
        # Поровну сделок — выше СК с большим числом участий (Альфа участвовала в обеих).
        self.assertEqual(charts['shares']['labels'], ['Альфа', 'Абсолют'])
        self.assertEqual(charts['shares']['percents'], [50.0, 50.0])
        # Цвет закреплён за СК, а не за местом.
        self.assertEqual(charts['shares']['colors'], ['#eda100', '#2a78d6'])

    def test_overview_renders_sections_and_links(self):
        response = self.client.get(reverse('summaries:analytics'))

        self.assertContains(response, 'Заявки и сделки по месяцам')
        self.assertContains(response, 'Доли СК по сделкам')
        self.assertContains(response, reverse('summaries:analytics_insurance_companies'))
        self.assertContains(response, reverse('summaries:analytics_managers'))
        self.assertContains(response, reverse('summaries:analytics_parser_edits'))
        self.assertContains(response, reverse('summaries:analytics_post_creation'))

    def test_empty_period_renders(self):
        response = self.client.get(reverse('summaries:analytics'), {'start_date': '2001-01-01', 'end_date': '2001-01-31'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['kpi']['deals'], 0)
        self.assertContains(response, 'Нет данных за выбранный период.')

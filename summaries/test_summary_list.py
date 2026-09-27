from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class SummaryListRowInfoTests(TestCase):
    """Строка списка сводов: лучшее за срок, итог выбранной СК, ожидание решения, счётчики филиалов."""

    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.user = User.objects.create_user(username='summary_list_admin', password='testpass123')
        self.user.groups.add(admin_group)
        self.client.login(username='summary_list_admin', password='testpass123')

    def _create_summary(self, *, branch='Москва', status='collecting', selected_company='', **summary_fields):
        request_obj = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='ООО "Клиент"',
            inn='1234567890',
            insurance_type='страхование спецтехники',
            dfa_number=f'ТС-{InsuranceRequest.objects.count() + 1}',
            branch=branch,
        )
        return InsuranceSummary.objects.create(
            request=request_obj,
            status=status,
            selected_company=selected_company,
            selected_franchise_variant=1 if selected_company else None,
            **summary_fields,
        )

    def _add_offer(self, summary, company_name, premium, year=1):
        InsuranceOffer.objects.create(
            summary=summary,
            company_name=company_name,
            insurance_year=year,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal(premium),
        )

    def _row_info(self, response, summary):
        rows = {row.pk: row for row in response.context['summaries'].object_list}
        return rows[summary.pk].list_info

    def test_best_offer_is_minimal_total_over_all_years(self):
        summary = self._create_summary(status='completed_accepted', selected_company='ВСК')
        # Альфа дешевле в первый год, но дороже за весь срок
        self._add_offer(summary, 'Альфа', '100000.00', year=1)
        self._add_offer(summary, 'Альфа', '100000.00', year=2)
        self._add_offer(summary, 'Абсолют', '120000.00', year=1)
        self._add_offer(summary, 'Абсолют', '60000.00', year=2)
        self._add_offer(summary, 'ВСК', '110000.00', year=1)
        self._add_offer(summary, 'ВСК', '85000.00', year=2)

        response = self.client.get(reverse('summaries:summary_list'))

        info = self._row_info(response, summary)
        self.assertEqual(info['best_total'], Decimal('180000.00'))
        self.assertEqual(info['best_company_name'], 'Абсолют')
        self.assertEqual(info['selected_total'], Decimal('195000.00'))
        self.assertTrue(info['has_cheaper'])
        self.assertEqual(info['companies_count'], 3)
        self.assertEqual(info['years_label'], '2 года')
        self.assertEqual(info['type_label'], 'Спецтехника')
        self.assertContains(response, 'есть дешевле')
        self.assertContains(response, '180 000 ₽')

    def test_selected_cheapest_offer_has_no_cheaper_flag(self):
        summary = self._create_summary(status='completed_accepted', selected_company='Альфа')
        self._add_offer(summary, 'Альфа', '50000.00')
        self._add_offer(summary, 'ВСК', '70000.00')

        response = self.client.get(reverse('summaries:summary_list'))

        info = self._row_info(response, summary)
        self.assertFalse(info['has_cheaper'])
        self.assertNotContains(response, 'есть дешевле')

    def test_sent_summary_shows_days_waiting_for_decision(self):
        summary = self._create_summary(status='sent', sent_to_client_at=timezone.now() - timedelta(days=9))

        response = self.client.get(reverse('summaries:summary_list'))

        self.assertEqual(self._row_info(response, summary)['waiting_days'], 9)
        self.assertContains(response, 'ждёт решения 9 дн.')
        self.assertContains(response, 'sl-waiting is-late')

    def test_branch_tabs_show_counts_for_every_branch(self):
        self._create_summary(branch='Москва')
        self._create_summary(branch='Москва')
        self._create_summary(branch='Казань')

        response = self.client.get(reverse('summaries:summary_list'), {'branch': 'Казань'})

        self.assertEqual(response.context['branch_counts'], {'Москва': 2, 'Казань': 1})
        self.assertEqual(response.context['total_summaries_count'], 3)
        self.assertEqual(len(response.context['summaries'].object_list), 1)

    def test_row_info_does_not_query_per_summary(self):
        for _ in range(3):
            summary = self._create_summary(status='completed_accepted', selected_company='Альфа')
            self._add_offer(summary, 'Альфа', '50000.00')
            self._add_offer(summary, 'ВСК', '70000.00')

        with CaptureQueriesContext(connection) as three_rows:
            self.client.get(reverse('summaries:summary_list'))

        for _ in range(3):
            summary = self._create_summary(status='completed_accepted', selected_company='Альфа')
            self._add_offer(summary, 'Альфа', '50000.00')
            self._add_offer(summary, 'ВСК', '70000.00')

        with CaptureQueriesContext(connection) as six_rows:
            self.client.get(reverse('summaries:summary_list'))

        self.assertEqual(len(three_rows.captured_queries), len(six_rows.captured_queries))

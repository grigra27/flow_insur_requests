from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class DealAnalyticsMvpTests(TestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.admin_user = User.objects.create_user(
            username='analytics_mvp_admin',
            email='analytics_mvp_admin@example.com',
            password='testpass123',
        )
        self.admin_user.groups.add(self.admin_group)
        self.client.login(username='analytics_mvp_admin', password='testpass123')

    def _create_completed_summary(self, dfa_number, branch, selected_company):
        insurance_request = InsuranceRequest.objects.create(
            created_by=self.admin_user,
            client_name=f'Клиент {dfa_number}',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number=dfa_number,
            branch=branch,
        )
        return InsuranceSummary.objects.create(
            request=insurance_request,
            status='completed_accepted',
            selected_company=selected_company,
            selected_franchise_variant=1,
        )

    def _add_offer(self, summary, company_name, premium):
        InsuranceOffer.objects.create(
            summary=summary,
            company_name=company_name,
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            premium_with_franchise_1=Decimal(premium),
            franchise_1=Decimal('0'),
        )

    def test_analytics_calculates_rank_and_min_selection_metrics(self):
        summary = self._create_completed_summary(
            dfa_number='DFA-0001',
            branch='Москва',
            selected_company='Абсолют',
        )
        self._add_offer(summary, 'Альфа', '10000.00')
        self._add_offer(summary, 'Абсолют', '11000.00')
        self._add_offer(summary, 'ВСК', '13000.00')

        response = self.client.get(reverse('summaries:analytics_insurance_offers'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Абсолют')
        self.assertContains(response, '2 / 3')

        analytics_kpi = response.context['analytics_kpi']
        self.assertEqual(analytics_kpi['total_deals'], 1)
        self.assertEqual(analytics_kpi['min_selected_count'], 0)
        self.assertEqual(analytics_kpi['min_selected_rate'], Decimal('0'))

        row = response.context['rows'].object_list[0]
        self.assertEqual(row['selected_rank'], 2)
        self.assertFalse(row['is_min_selected'])
        self.assertEqual(row['delta_to_min_abs'], Decimal('1000.00'))
        self.assertContains(response, 'left: 33.33%;')

    def test_analytics_filters_deals_by_branch(self):
        moscow_summary = self._create_completed_summary(
            dfa_number='DFA-0002',
            branch='Москва',
            selected_company='Абсолют',
        )
        self._add_offer(moscow_summary, 'Альфа', '10000.00')
        self._add_offer(moscow_summary, 'Абсолют', '10500.00')
        self._add_offer(moscow_summary, 'ВСК', '12000.00')

        spb_summary = self._create_completed_summary(
            dfa_number='DFA-0003',
            branch='Санкт-Петербург',
            selected_company='Альфа',
        )
        self._add_offer(spb_summary, 'Альфа', '9000.00')
        self._add_offer(spb_summary, 'Абсолют', '9500.00')
        self._add_offer(spb_summary, 'ВСК', '9800.00')

        response = self.client.get(reverse('summaries:analytics_insurance_offers'), {'branch': 'Москва'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DFA-0002')
        self.assertNotContains(response, 'DFA-0003')

        rows = response.context['rows'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['summary'].id, moscow_summary.id)

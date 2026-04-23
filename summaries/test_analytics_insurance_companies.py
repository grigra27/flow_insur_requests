from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class InsuranceCompaniesAnalyticsTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.user_group, _ = Group.objects.get_or_create(name='Пользователи')

        self.admin_user = User.objects.create_user(
            username='analytics_companies_admin',
            email='analytics_companies_admin@example.com',
            password='testpass123',
            first_name='Алексей',
            last_name='Петров',
        )
        self.admin_user.groups.add(self.admin_group)

        self.regular_user = User.objects.create_user(
            username='analytics_companies_user',
            email='analytics_companies_user@example.com',
            password='testpass123',
        )
        self.regular_user.groups.add(self.user_group)

        self.client.login(username='analytics_companies_admin', password='testpass123')

        now = timezone.now()

        self.summary_moscow = self._create_completed_summary(
            dfa_number='DFA-COMP-001',
            branch='Москва',
            insurance_type='КАСКО',
            manager_name='Иванов И.И.',
            deal_status='new',
            selected_company='Абсолют',
            selected_variant=1,
            response_deadline=now - timedelta(days=7),
            request_created_at=now - timedelta(days=11),
            summary_created_at=now - timedelta(days=10),
            completed_at=now - timedelta(days=8),
        )
        self._add_offer(self.summary_moscow, 'Абсолют', '10000.00', received_at=now - timedelta(days=9))
        self._add_offer(self.summary_moscow, 'Альфа', '9000.00', received_at=now - timedelta(days=9))
        self._add_offer(self.summary_moscow, 'ВСК', '12000.00', received_at=now - timedelta(days=9))

        self.summary_spb = self._create_completed_summary(
            dfa_number='DFA-COMP-002',
            branch='Санкт-Петербург',
            insurance_type='страхование имущества',
            manager_name='',
            deal_status='prolongation',
            selected_company='Альфа',
            selected_variant=None,
            response_deadline=now - timedelta(days=4),
            request_created_at=now - timedelta(days=7),
            summary_created_at=now - timedelta(days=6),
            completed_at=now - timedelta(days=3),
        )
        self._add_offer(self.summary_spb, 'Альфа', '8000.00', received_at=now - timedelta(days=5))
        self._add_offer(self.summary_spb, 'Абсолют', '8500.00', received_at=now - timedelta(days=5))

    def _create_completed_summary(
        self,
        *,
        dfa_number,
        branch,
        insurance_type,
        manager_name,
        deal_status,
        selected_company,
        selected_variant,
        response_deadline,
        request_created_at,
        summary_created_at,
        completed_at,
    ):
        insurance_request = InsuranceRequest.objects.create(
            created_by=self.admin_user,
            client_name=f'Клиент {dfa_number}',
            inn='1234567890',
            insurance_type=insurance_type,
            insurance_period='1 год',
            dfa_number=dfa_number,
            branch=branch,
            manager_name=manager_name,
            deal_status=deal_status,
            response_deadline=response_deadline,
        )
        InsuranceRequest.objects.filter(pk=insurance_request.pk).update(created_at=request_created_at)
        insurance_request.refresh_from_db()

        summary = InsuranceSummary.objects.create(
            request=insurance_request,
            status='completed_accepted',
            selected_company=selected_company,
            selected_franchise_variant=selected_variant,
            completed_at=completed_at,
        )
        InsuranceSummary.objects.filter(pk=summary.pk).update(created_at=summary_created_at)
        summary.refresh_from_db()
        return summary

    def _add_offer(self, summary, company_name, premium, received_at):
        offer = InsuranceOffer.objects.create(
            summary=summary,
            company_name=company_name,
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            premium_with_franchise_1=Decimal(premium),
            franchise_1=Decimal('0'),
            installment_variant_1=True,
            payments_per_year_variant_1=2,
        )
        InsuranceOffer.objects.filter(pk=offer.pk).update(received_at=received_at)

    def test_access_for_admin_and_regular_user(self):
        admin_response = self.client.get(reverse('summaries:analytics_insurance_companies'))
        self.assertEqual(admin_response.status_code, 200)
        self.assertTemplateUsed(admin_response, 'summaries/analytics_insurance_companies.html')

        self.client.logout()
        self.client.login(username='analytics_companies_user', password='testpass123')
        user_response = self.client.get(reverse('summaries:analytics_insurance_companies'))
        self.assertEqual(user_response.status_code, 403)
        self.assertTemplateUsed(user_response, 'insurance_requests/access_denied.html')

    def test_navigation_item_visible_for_admin_only(self):
        analytics_companies_url = reverse('summaries:analytics_insurance_companies')

        admin_response = self.client.get(reverse('summaries:summary_list'))
        self.assertContains(admin_response, analytics_companies_url)

        self.client.logout()
        self.client.login(username='analytics_companies_user', password='testpass123')
        user_response = self.client.get(reverse('summaries:summary_list'))
        self.assertNotContains(user_response, analytics_companies_url)

    def test_page_renders_all_key_blocks(self):
        response = self.client.get(reverse('summaries:analytics_insurance_companies'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Рейтинг страховых компаний')
        self.assertContains(response, 'Ценовая конкурентность')
        self.assertContains(response, 'Конверсия в выбор клиента')
        self.assertContains(response, 'Разрезы по филиалам, менеджерам, типам и статусам')
        self.assertContains(response, 'Динамика по времени')
        self.assertContains(response, 'Data Quality')
        self.assertContains(response, 'Детализация сделок')

    def test_filters_by_branch(self):
        response = self.client.get(
            reverse('summaries:analytics_insurance_companies'),
            {'branch': 'Москва'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DFA-COMP-001')
        self.assertNotContains(response, 'DFA-COMP-002')

        rows = list(response.context['deals_page'].object_list)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['summary'].pk, self.summary_moscow.pk)

    def test_core_metrics_and_data_quality(self):
        response = self.client.get(reverse('summaries:analytics_insurance_companies'))
        self.assertEqual(response.status_code, 200)

        kpi = response.context['kpi']
        self.assertEqual(kpi['total_deals'], 2)
        self.assertEqual(kpi['comparable_deals'], 2)
        self.assertEqual(kpi['min_selected_count'], 1)
        self.assertEqual(kpi['min_selected_rate'], Decimal('50'))
        self.assertEqual(kpi['avg_rank'], 1.5)
        self.assertEqual(kpi['median_delta_abs'], Decimal('500.00'))

        quality_rows = {row['key']: row for row in response.context['data_quality_rows']}
        self.assertEqual(quality_rows['missing_selected_variant_count']['count'], 1)
        self.assertEqual(quality_rows['missing_manager_alliance_count']['count'], 1)

    def test_drilldown_links_exist_for_deals(self):
        response = self.client.get(reverse('summaries:analytics_insurance_companies'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('summaries:deal_summary', args=[self.summary_moscow.pk]))
        self.assertContains(response, reverse('summaries:summary_detail', args=[self.summary_moscow.pk]))

    def test_export_returns_valid_xlsx(self):
        response = self.client.get(
            reverse('summaries:export_analytics_insurance_companies_widget'),
            {'widget': 'rating'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('analytics_companies_rating_', response['Content-Disposition'])

        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active

        self.assertEqual(worksheet['A1'].value, 'Рейтинг страховых компаний')
        self.assertEqual(worksheet['A6'].value, 'Позиция')
        self.assertEqual(worksheet['B6'].value, 'СК')
        self.assertEqual(worksheet['C6'].value, 'Участвовала в сделках, шт.')

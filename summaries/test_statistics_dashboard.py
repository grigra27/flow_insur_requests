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


class StatisticsDashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='stats_admin',
            email='stats_admin@example.com',
            password='testpass123'
        )
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.user.groups.add(admin_group)
        self.client.login(username='stats_admin', password='testpass123')

        now = timezone.now()
        old_date = now - timedelta(days=45)

        recent_request = InsuranceRequest.objects.create(
            client_name='Recent Client',
            inn='1234567890',
            insurance_type='КАСКО',
            branch='Москва',
            created_by=self.user
        )
        old_request = InsuranceRequest.objects.create(
            client_name='Old Client',
            inn='0987654321',
            insurance_type='страхование имущества',
            branch='Санкт-Петербург',
            created_by=self.user
        )

        self.recent_summary = InsuranceSummary.objects.create(
            request=recent_request,
            status='ready',
            total_offers=1
        )
        self.old_summary = InsuranceSummary.objects.create(
            request=old_request,
            status='completed_rejected',
            total_offers=1
        )

        InsuranceSummary.objects.filter(pk=self.old_summary.pk).update(created_at=old_date)

        self.recent_offer = InsuranceOffer.objects.create(
            summary=self.recent_summary,
            company_name='другое',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00')
        )
        self.old_offer = InsuranceOffer.objects.create(
            summary=self.old_summary,
            company_name='другое',
            insurance_year=1,
            insurance_sum=Decimal('800000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('45000.00')
        )

        InsuranceOffer.objects.filter(pk=self.old_offer.pk).update(received_at=old_date)

    def test_statistics_page_respects_quick_period_filter(self):
        response = self.client.get(reverse('summaries:statistics'), {'period': '30'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['total_summaries'], 1)
        self.assertEqual(response.context['stats']['total_offers'], 1)
        self.assertContains(response, 'data-widget="statuses"')

    def test_export_statistics_widget_returns_xlsx(self):
        response = self.client.get(
            reverse('summaries:export_statistics_widget'),
            {'widget': 'statuses', 'period': '30'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('stats_statuses_', response['Content-Disposition'])

        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active

        self.assertEqual(worksheet['A1'].value, 'Статусы сводов')
        self.assertEqual(worksheet['A5'].value, 'Статус')
        self.assertEqual(worksheet['B5'].value, 'Количество')
        self.assertEqual(worksheet['A6'].value, 'Сбор')

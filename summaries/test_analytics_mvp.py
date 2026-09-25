from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary
from summaries.views import _build_deal_price_row


class DealAnalyticsMvpTests(TestCase):
    """Ценовая позиция сделки (_build_deal_price_row).

    Раньше проверялась через страницу «Страховые предложения»; страница удалена
    (analytics_redesign_2026_09, задача 1.2), а расчёт используется страницей СК
    и будет основой ценового разбора в карточке СК.
    """

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

    def test_price_row_calculates_rank_and_min_selection(self):
        summary = self._create_completed_summary(
            dfa_number='DFA-0001',
            branch='Москва',
            selected_company='Абсолют',
        )
        self._add_offer(summary, 'Альфа', '10000.00')
        self._add_offer(summary, 'Абсолют', '11000.00')
        self._add_offer(summary, 'ВСК', '13000.00')

        row = _build_deal_price_row(summary)

        self.assertEqual(row['selected_rank'], 2)
        self.assertEqual(row['comparable_companies_count'], 3)
        self.assertFalse(row['is_min_selected'])
        self.assertEqual(row['best_company_name'], 'Альфа')
        self.assertEqual(row['delta_to_min_abs'], Decimal('1000.00'))
        self.assertEqual(row['delta_to_min_pct'], Decimal('10'))
        selected_point = next(p for p in row['points'] if p['is_selected'])
        self.assertEqual(selected_point['position_pct'], 33.33)

    def test_price_row_marks_min_selection(self):
        summary = self._create_completed_summary(
            dfa_number='DFA-0002',
            branch='Москва',
            selected_company='Альфа',
        )
        self._add_offer(summary, 'Альфа', '9000.00')
        self._add_offer(summary, 'Абсолют', '9500.00')

        row = _build_deal_price_row(summary)

        self.assertEqual(row['selected_rank'], 1)
        self.assertTrue(row['is_min_selected'])
        self.assertEqual(row['delta_to_min_abs'], Decimal('0'))

    def test_price_row_needs_at_least_two_comparable_companies(self):
        summary = self._create_completed_summary(
            dfa_number='DFA-0003',
            branch='Москва',
            selected_company='Альфа',
        )
        self._add_offer(summary, 'Альфа', '9000.00')

        self.assertIsNone(_build_deal_price_row(summary))

    def test_removed_offers_page_redirects_to_companies(self):
        response = self.client.get('/summaries/analytics/insurance-offers/', {'branch': 'Москва'})

        self.assertRedirects(
            response,
            reverse('summaries:analytics_insurance_companies') + '?branch=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0',
            fetch_redirect_response=False,
        )

"""Таблица предложений на карточке свода (редизайн 2026-09): одна таблица, территория один раз на компанию."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest

from .models import InsuranceOffer, InsuranceSummary
from .views import _territory_lines, _year_ranges, _years_label


class Offer:
    def __init__(self, year, territory):
        self.insurance_year, self.coverage_territory = year, territory


class TerritoryLinesTests(SimpleTestCase):
    def test_same_territory_shown_once(self):
        lines = _territory_lines([Offer(year, 'РФ') for year in (1, 2, 3, 4)])
        self.assertEqual(lines, [{'label': 'Территория', 'kind': 'text', 'text': 'РФ'}])

    def test_first_year_only_and_missing_rest(self):
        lines = _territory_lines([Offer(1, 'РФ и СНГ'), Offer(2, ''), Offer(3, ''), Offer(4, '')])
        self.assertEqual([(line['label'], line['kind']) for line in lines],
                         [('Территория (1 год)', 'text'), ('Территория (2–4 год)', 'missing')])

    def test_legacy_offers_without_territory_field(self):
        self.assertEqual(_territory_lines([Offer(1, None)])[0]['kind'], 'legacy')

    def test_helpers(self):
        self.assertEqual(_year_ranges([1, 2, 3, 5]), '1–3, 5')
        self.assertEqual([_years_label(n) for n in (1, 2, 4, 5, 11, 21)],
                         ['1 год', '2 года', '4 года', '5 лет', '11 лет', '21 год'])


class OfferTableRenderingTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='table_user', password='pwd')
        user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.login(username='table_user', password='pwd')
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', dfa_number='ТС-1',
                                                  vehicle_info='Haval F7X')
        self.summary = InsuranceSummary.objects.create(request=request)
        for company, territory in (('Альфа', 'РФ'), ('ВСК', 'РФ, Европа и СНГ')):
            for year in (1, 2):
                InsuranceOffer.objects.create(summary=self.summary, company_name=company, insurance_year=year,
                                              insurance_sum=Decimal('3000000'), franchise_1=Decimal('0'),
                                              premium_with_franchise_1=Decimal('70000'), coverage_territory=territory)

    def page(self):
        return self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))

    def test_one_table_one_header_and_territory_once_per_company(self):
        content = self.page().content.decode()
        self.assertEqual(content.count('class="og-table'), 1)
        self.assertEqual(content.count('<thead>'), 1)
        self.assertEqual(content.count('<tr class="og-company-row">'), 2)
        self.assertEqual(content.count('РФ, Европа и СНГ'), 1)
        self.assertIn('2 года · итого <strong class="franchise-variant-1">140', content)

    def test_variant_2_columns_only_when_present(self):
        self.assertNotIn('<tr class="og-head-groups">', self.page().content.decode())
        InsuranceOffer.objects.filter(company_name='Альфа', insurance_year=1).update(
            franchise_2=Decimal('30000'), premium_with_franchise_2=Decimal('60000'))
        content = self.page().content.decode()
        self.assertIn('<tr class="og-head-groups">', content)
        self.assertIn('Вариант 2', content)

"""Таблица предложений на карточке свода (редизайн 2026-09): одна таблица, территория один раз на компанию."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest

from .models import InsuranceOffer, InsuranceSummary
from .services.insurer_response import set_offer_company_fields
from .views import _territory_lines, _years_label


class Response:
    def __init__(self, territory):
        self.coverage_territory = territory


class TerritoryLinesTests(SimpleTestCase):
    """Территория — одна на СК в своде, из «Ответа СК»."""

    def test_text_missing_and_legacy(self):
        self.assertEqual(_territory_lines(Response(' РФ ')), [{'label': 'Территория', 'kind': 'text', 'text': 'РФ'}])
        self.assertEqual(_territory_lines(Response(''))[0]['kind'], 'missing')
        self.assertEqual(_territory_lines(Response(None))[0]['kind'], 'legacy')
        self.assertEqual(_territory_lines(None)[0]['kind'], 'legacy')

    def test_helpers(self):
        self.assertEqual([_years_label(n) for n in (1, 2, 4, 5, 11, 21)],
                         ['1 год', '2 года', '4 года', '5 лет', '11 лет', '21 год'])


class OfferTableRenderingTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='table_user', password='pwd')
        user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.login(username='table_user', password='pwd')
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', dfa_number='ТС-1',
                                                  object_description='Haval F7X')
        self.summary = InsuranceSummary.objects.create(request=request)
        for company, territory in (('Альфа', 'РФ'), ('ВСК', 'РФ, Европа и СНГ')):
            for year in (1, 2):
                offer = InsuranceOffer.objects.create(summary=self.summary, company_name=company, insurance_year=year,
                                                      insurance_sum=Decimal('3000000'), franchise_1=Decimal('0'),
                                                      premium_with_franchise_1=Decimal('70000'))
            set_offer_company_fields(offer, territory)

    def page(self):
        return self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))

    def test_one_table_one_header_and_territory_once_per_company(self):
        content = self.page().content.decode()
        self.assertEqual(content.count('class="og-table'), 1)
        self.assertEqual(content.count('<thead>'), 1)
        self.assertEqual(content.count('<tr class="og-company-row">'), 2)
        self.assertEqual(content.count('<span class="og-territory-text">РФ, Европа и СНГ'), 1)
        self.assertIn('<small>итого за срок</small>', content)
        self.assertIn('<b>140 000 ₽</b>', content)

    def test_variant_2_columns_only_when_present(self):
        self.assertNotIn('<tr class="og-head-groups">', self.page().content.decode())
        InsuranceOffer.objects.filter(company_name='Альфа', insurance_year=1).update(
            franchise_2=Decimal('30000'), premium_with_franchise_2=Decimal('60000'))
        content = self.page().content.decode()
        self.assertIn('<tr class="og-head-groups">', content)
        self.assertIn('Вариант 2', content)

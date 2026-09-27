from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class OfferFormPageTests(TestCase):
    """Общая форма предложения (редизайн 2026-09): несколько лет, повторы «СК + год», суммы с пробелами."""

    def setUp(self):
        group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user = User.objects.create_user(username='offer_form_user', password='testpass123')
        self.user.groups.add(group)
        self.client.login(username='offer_form_user', password='testpass123')
        request_obj = InsuranceRequest.objects.create(
            created_by=self.user, client_name='ООО "Клиент"', inn='1234567890', dfa_number='ТС-1',
            insurance_type='КАСКО', insurance_period='на весь срок лизинга',
        )
        self.summary = InsuranceSummary.objects.create(request=request_obj, status='collecting')
        self.alfa_1 = InsuranceOffer.objects.create(
            summary=self.summary, company_name='Альфа', insurance_year=1,
            insurance_sum=Decimal('4160000.00'), franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('198016.00'), coverage_territory='Вся РФ',
        )
        InsuranceOffer.objects.create(
            summary=self.summary, company_name='Альфа', insurance_year=2,
            insurance_sum=Decimal('3536000.00'), franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('198016.00'), coverage_territory='Вся РФ',
        )
        self.add_url = reverse('summaries:add_offer', args=[self.summary.pk])

    def _rows(self, company, rows, **common):
        data = {'company_name': company, 'rows-TOTAL': str(len(rows)), 'coverage_territory': 'РФ', 'notes': ''}
        data.update(common)
        for index, row in enumerate(rows):
            for field, value in row.items():
                data[f'rows-{index}-{field}'] = value
        return data

    def test_add_several_years_at_once_with_spaced_numbers(self):
        response = self.client.post(self.add_url, self._rows('ВСК', [
            {'insurance_year': '1', 'insurance_sum': '4 160 000', 'franchise_1': '0', 'premium_with_franchise_1': '205 400,50'},
            {'insurance_year': '2', 'insurance_sum': '3 536 000', 'franchise_1': '0', 'premium_with_franchise_1': '186 900'},
        ], installment_variant_1='on', payments_per_year_variant_1='4'))

        self.assertRedirects(response, reverse('summaries:summary_detail', args=[self.summary.pk]))
        offers = list(InsuranceOffer.objects.filter(summary=self.summary, company_name='ВСК').order_by('insurance_year'))
        self.assertEqual([offer.insurance_year for offer in offers], [1, 2])
        self.assertEqual(offers[0].insurance_sum, Decimal('4160000'))
        self.assertEqual(offers[0].premium_with_franchise_1, Decimal('205400.50'))
        self.assertTrue(all(offer.installment_variant_1 and offer.payments_per_year_variant_1 == 4 for offer in offers))
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.total_offers, 2)

    def test_add_saves_nothing_when_one_year_is_invalid(self):
        response = self.client.post(self.add_url, self._rows('ВСК', [
            {'insurance_year': '1', 'insurance_sum': '1000000', 'franchise_1': '0', 'premium_with_franchise_1': '50000'},
            {'insurance_year': '2', 'insurance_sum': '1000000', 'franchise_1': '0', 'premium_with_franchise_1': '-5'},
        ]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(InsuranceOffer.objects.filter(company_name='ВСК').exists())
        self.assertContains(response, 'должна быть больше нуля')
        self.assertContains(response, 'name="rows-1-premium_with_franchise_1"')

    def test_add_rejects_existing_and_repeated_years(self):
        response = self.client.post(self.add_url, self._rows('Альфа', [
            {'insurance_year': '2', 'insurance_sum': '1000000', 'franchise_1': '0', 'premium_with_franchise_1': '50000'},
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже существует в данном своде')

        response = self.client.post(self.add_url, self._rows('ВСК', [
            {'insurance_year': '1', 'insurance_sum': '1000000', 'franchise_1': '0', 'premium_with_franchise_1': '50000'},
            {'insurance_year': '1', 'insurance_sum': '1000000', 'franchise_1': '0', 'premium_with_franchise_1': '50000'},
        ]))
        self.assertContains(response, '1 год указан в форме несколько раз')
        self.assertFalse(InsuranceOffer.objects.filter(company_name='ВСК').exists())

    def test_copy_suggests_first_free_year_and_shows_company_years(self):
        response = self.client.get(reverse('summaries:copy_offer', args=[self.alfa_1.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="insurance_year" value="3"')
        self.assertContains(response, 'value="4 160 000"')
        self.assertEqual(response.context['company_years'], {'Альфа': [1, 2]})

    def test_copy_to_taken_year_shows_duplicate_message(self):
        data = {
            'company_name': 'Альфа', 'insurance_year': '2', 'insurance_sum': '1 000 000', 'franchise_1': '0',
            'premium_with_franchise_1': '50 000', 'coverage_territory': 'Вся РФ', 'notes': '',
        }
        response = self.client.post(reverse('summaries:copy_offer', args=[self.alfa_1.pk]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже существует в данном своде')
        self.assertEqual(InsuranceOffer.objects.filter(company_name='Альфа').count(), 2)

    def test_edit_hides_own_year_from_company_years(self):
        response = self.client.get(reverse('summaries:edit_offer', args=[self.alfa_1.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['company_years'], {'Альфа': [2]})
        self.assertContains(response, 'Удалить предложение')
        self.assertContains(response, 'value="198 016"')

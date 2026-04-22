from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class DealSummaryOfferNotesTests(TestCase):
    """Тесты отображения комментариев выбранных предложений в резюме сделки."""

    def setUp(self):
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user = User.objects.create_user(
            username='deal_summary_user',
            password='testpass123'
        )
        self.user.groups.add(self.users_group)

        self.client = Client()
        self.client.login(username='deal_summary_user', password='testpass123')

        self.request_obj = InsuranceRequest.objects.create(
            dfa_number='DFA-001',
            client_name='ООО Тест Клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            branch='msk',
            status='uploaded',
            created_by=self.user,
        )

        self.summary = InsuranceSummary.objects.create(
            request=self.request_obj,
            status='completed_accepted',
            selected_company='Абсолют',
            selected_franchise_variant=1,
        )

        self.offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('50000.00'),
            notes='Точечный комментарий по предложению',
        )

    def test_deal_summary_shows_selected_offer_notes(self):
        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Комментарий предложения:')
        self.assertContains(response, 'Точечный комментарий по предложению')

    def test_deal_summary_merges_multiyear_notes_into_one_row(self):
        InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=2,
            insurance_sum=Decimal('900000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('48000.00'),
            notes='Комментарий по второму году',
        )

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Точечный комментарий по предложению')
        self.assertContains(response, 'Комментарий по второму году')
        self.assertContains(response, 'Точечный комментарий по предложению | Комментарий по второму году')
        self.assertEqual(response.content.decode('utf-8').count('Комментарий предложения:'), 1)

    def test_deal_summary_hides_offer_note_block_for_empty_notes(self):
        self.offer.notes = ''
        self.offer.save(update_fields=['notes'])

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Комментарий предложения:')

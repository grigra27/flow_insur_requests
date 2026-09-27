from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import date, datetime

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
        self.assertContains(response, 'Комментарий предложения</span>')
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
        self.assertEqual(response.content.decode('utf-8').count('Комментарий предложения</span>'), 1)

    def test_deal_summary_hides_offer_note_block_for_empty_notes(self):
        self.offer.notes = ''
        self.offer.save(update_fields=['notes'])

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Комментарий предложения</span>')

    def test_deal_summary_shows_deal_summary_note(self):
        self.summary.deal_summary_note = 'Срочно проверить особое условие перед выпуском полиса'
        self.summary.save(update_fields=['deal_summary_note'])

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Примечание к резюме')
        self.assertContains(response, 'Срочно проверить особое условие перед выпуском полиса')

    def test_deal_summary_hides_deal_summary_note_block_when_empty(self):
        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Примечание к резюме')


class DealSummaryDetailsTests(DealSummaryOfferNotesTests):
    """Резюме сделки (редизайн 2026-09): поля заявки из V2, территория выбранной СК, дата закрытия."""

    def test_deal_summary_shows_contract_object_and_client_fields(self):
        InsuranceRequest.objects.filter(pk=self.request_obj.pk).update(
            insured_party='lessee',
            insured_sum_type='non_aggregate',
            premium_frequency='quarterly',
            equipment_type='гусеничная',
            machine_kind='Экскаватор',
            guard_conditions='охраняемая стоянка',
            legal_address='119192, Москва, Мосфильмовская ул., 74Б',
            business_activity='Разработка карьера',
            submission_date=date(2026, 9, 23),
        )

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        for text in ('Лизингополучатель', 'Уплата премии: поквартально', 'Неагрегатная', 'гусеничная', 'Экскаватор',
                     'охраняемая стоянка', 'Мосфильмовская', 'Разработка карьера', 'Заявка подана', '23.09.2026'):
            self.assertContains(response, text)

    def test_deal_summary_hides_empty_v2_fields(self):
        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.status_code, 200)
        for text in ('Страхователь', 'Тип страховой суммы', 'Юридический адрес', 'Заявка подана', 'Территория страхования'):
            self.assertNotContains(response, text)

    def test_deal_summary_shows_selected_company_territory(self):
        self.offer.coverage_territory = 'Российская Федерация, кроме новых территорий'
        self.offer.save(update_fields=['coverage_territory'])

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertContains(response, 'Территория страхования')
        self.assertContains(response, 'Российская Федерация, кроме новых территорий')

    def test_deal_closed_date_comes_from_completed_at(self):
        completed_at = timezone.make_aware(datetime(2026, 9, 1, 12, 0))
        InsuranceSummary.objects.filter(pk=self.summary.pk).update(completed_at=completed_at)
        # правка свода после закрытия не должна сдвигать дату закрытия
        InsuranceSummary.objects.filter(pk=self.summary.pk).update(updated_at=timezone.now())

        response = self.client.get(reverse('summaries:deal_summary', args=[self.summary.pk]))

        self.assertEqual(response.context['deal_closed_at'], completed_at)
        self.assertContains(response, '01.09.2026')

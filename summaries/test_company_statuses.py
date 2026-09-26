"""Статусы страховых компаний в своде (analytics_redesign_2026_09, этап 2)."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest

from .models import InsuranceCompany, InsuranceOffer, InsuranceSummary, StatusEvent, SummaryCompanyStatus
from .services import company_statuses


def make_request(user=None, **extra):
    return InsuranceRequest.objects.create(
        client_name='ООО Тест', inn='7707083893', insurance_type='КАСКО', created_by=user,
        status='emails_sent', dfa_number='ТС-20842', **extra,
    )


def make_offer(summary, company_name, year=1):
    return InsuranceOffer.objects.create(
        summary=summary, company_name=company_name, insurance_year=year,
        insurance_sum=Decimal('1000000'), franchise_1=Decimal('0'), premium_with_franchise_1=Decimal('50000'),
    )


def statuses(summary):
    return dict(summary.company_statuses.values_list('company__name', 'status'))


class CompanyStatusServiceTests(TestCase):
    def setUp(self):
        self.summary = InsuranceSummary.objects.create(request=make_request())
        company_statuses.init_for_summary(self.summary)
        self.summary.refresh_from_db()
        self.active = set(InsuranceCompany.objects.filter(is_active=True, is_other=False).values_list('name', flat=True))

    def company(self, name):
        return InsuranceCompany.objects.get(name=name)

    def test_init_creates_undefined_rows_for_active_companies_except_other(self):
        self.assertTrue(self.summary.company_statuses_required)
        self.assertEqual(set(statuses(self.summary)), self.active)
        self.assertNotIn('другое', statuses(self.summary))
        self.assertEqual(set(statuses(self.summary).values()), {'undefined'})
        self.assertEqual(len(company_statuses.missing_companies(self.summary)), len(self.active))

    def test_offer_sets_offered_and_removing_last_offer_returns_requested(self):
        first = make_offer(self.summary, 'Абсолют', 1)
        second = make_offer(self.summary, 'Абсолют', 2)
        self.assertEqual(statuses(self.summary)['Абсолют'], 'offered')

        first.delete()
        self.assertEqual(statuses(self.summary)['Абсолют'], 'offered')  # остался второй год
        second.delete()
        self.assertEqual(statuses(self.summary)['Абсолют'], 'requested')

    def test_offer_for_other_creates_offered_row(self):
        make_offer(self.summary, 'другое')
        self.assertEqual(statuses(self.summary)['другое'], 'offered')

    def test_moving_offer_to_another_company_resyncs_both(self):
        offer = make_offer(self.summary, 'Абсолют')
        offer.company_name = 'Альфа'
        offer.save()
        self.assertEqual(statuses(self.summary)['Абсолют'], 'requested')
        self.assertEqual(statuses(self.summary)['Альфа'], 'offered')

    def test_manual_status_and_offered_is_locked(self):
        company_statuses.set_status(self.summary, self.company('Зетта').pk, 'declined')
        self.assertEqual(statuses(self.summary)['Зетта'], 'declined')

        make_offer(self.summary, 'Абсолют')
        with self.assertRaises(company_statuses.CompanyStatusError):
            company_statuses.set_status(self.summary, self.company('Абсолют').pk, 'declined')
        with self.assertRaises(company_statuses.CompanyStatusError):
            company_statuses.set_status(self.summary, self.company('Зетта').pk, 'offered')
        with self.assertRaises(company_statuses.CompanyStatusError):
            company_statuses.set_status(self.summary, self.company('Зетта').pk, 'undefined')

    def test_remaining_to_not_requested(self):
        make_offer(self.summary, 'Абсолют')
        company_statuses.set_status(self.summary, self.company('Зетта').pk, 'declined')

        changed = company_statuses.set_undefined_to(self.summary, 'not_requested')

        self.assertEqual(changed, len(self.active) - 2)
        self.assertEqual(company_statuses.missing_companies(self.summary), [])
        self.assertEqual(statuses(self.summary)['Абсолют'], 'offered')
        self.assertEqual(statuses(self.summary)['Зетта'], 'declined')
        self.assertEqual(company_statuses.declined_company_names(self.summary), ['Зетта'])

    def test_changes_are_journaled_but_initial_undefined_rows_are_not(self):
        row_type = ContentType.objects.get_for_model(SummaryCompanyStatus)
        self.assertEqual(StatusEvent.objects.filter(content_type=row_type).count(), 0)

        company_statuses.set_status(self.summary, self.company('Зетта').pk, 'requested')
        company_statuses.set_status(self.summary, self.company('Зетта').pk, 'declined')

        events = list(StatusEvent.objects.filter(content_type=row_type).order_by('changed_at', 'pk')
                      .values_list('from_status', 'to_status'))
        self.assertEqual(events, [('undefined', 'requested'), ('requested', 'declined')])

    def test_legacy_summary_is_not_blocked(self):
        legacy = InsuranceSummary.objects.create(request=make_request())
        make_offer(legacy, 'Абсолют')
        self.assertFalse(legacy.company_statuses_required)
        self.assertEqual(company_statuses.missing_companies(legacy), [])
        self.assertEqual(statuses(legacy), {'Абсолют': 'offered'})


class CompanyStatusViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cs_user', password='pwd')
        self.user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.login(username='cs_user', password='pwd')
        self.request_obj = make_request(self.user)

    def create_summary(self):
        response = self.client.post(reverse('summaries:create_summary', args=[self.request_obj.pk]))
        self.assertEqual(response.status_code, 302)
        return InsuranceSummary.objects.get(request=self.request_obj)

    def change_status(self, summary, status, **extra):
        return self.client.post(
            reverse('summaries:change_summary_status', args=[summary.pk]), {'status': status, **extra}
        ).json()

    def test_summary_created_in_ui_requires_statuses(self):
        summary = self.create_summary()
        self.assertTrue(summary.company_statuses_required)
        self.assertTrue(summary.company_statuses.exists())

    def test_any_status_change_blocked_until_every_company_has_status(self):
        summary = self.create_summary()
        make_offer(summary, 'Абсолют')

        for target in ('ready', 'sent', 'completed_rejected'):
            data = self.change_status(summary, target)
            self.assertFalse(data['success'])
            self.assertIn('Без статуса', data['error'])
            self.assertNotIn('Абсолют', data['missing_companies'])  # «предложение» уже стоит само
        data = self.change_status(summary, 'completed_accepted', selected_company='Абсолют')
        self.assertFalse(data['success'])
        summary.refresh_from_db()
        self.assertEqual(summary.status, 'collecting')

        zetta = InsuranceCompany.objects.get(name='Зетта')
        response = self.client.post(reverse('summaries:set_company_status', args=[summary.pk]),
                                    {'company_id': zetta.pk, 'status': 'requested'})
        self.assertTrue(response.json()['success'])
        response = self.client.post(reverse('summaries:set_remaining_company_statuses', args=[summary.pk]),
                                    {'status': 'not_requested'})
        self.assertEqual(response.json()['missing'], [])

        data = self.change_status(summary, 'ready')  # «запрошена» (нет ответа) допустима
        self.assertTrue(data['success'])
        summary.refresh_from_db()
        self.assertEqual(summary.status, 'ready')

    def test_resubmitting_current_status_is_not_blocked(self):
        summary = self.create_summary()
        self.assertTrue(self.change_status(summary, 'collecting')['success'])

    def test_set_company_status_rejects_offered_company(self):
        summary = self.create_summary()
        make_offer(summary, 'Абсолют')
        absolut = InsuranceCompany.objects.get(name='Абсолют')
        response = self.client.post(reverse('summaries:set_company_status', args=[summary.pk]),
                                    {'company_id': absolut.pk, 'status': 'declined'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('предложение', response.json()['error'])

    def test_detail_page_shows_statuses_and_declined_block(self):
        summary = self.create_summary()
        company_statuses.set_status(summary, InsuranceCompany.objects.get(name='Зетта').pk, 'declined')

        response = self.client.get(reverse('summaries:summary_detail', args=[summary.pk]))

        self.assertContains(response, 'Статусы страховых компаний')
        self.assertContains(response, 'id="status-blocked-alert"')
        self.assertEqual(response.context['declined_companies'], ['Зетта'])
        self.assertContains(response, 'Отказались от страхования')

    def test_auto_close_is_not_blocked(self):
        from datetime import timedelta
        from django.core.management import call_command
        from django.utils import timezone

        summary = self.create_summary()
        InsuranceSummary.objects.filter(pk=summary.pk).update(
            status='sent', created_at=timezone.now() - timedelta(days=45),
        )
        call_command('auto_close_stale_summaries', verbosity=0)
        summary.refresh_from_db()
        self.assertEqual(summary.status, 'completed_rejected')

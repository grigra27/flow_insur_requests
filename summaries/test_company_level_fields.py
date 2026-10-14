"""Территория и примечание — одни на СК в своде, хранятся в «Ответе СК» (уборка данных, 2026-10-14).

Годовые строки предложений (InsuranceOffer.coverage_territory / notes / attachment_file) — архив: код их не пишет.
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest

from .models import InsuranceOffer, InsuranceSummary, InsurerResponse
from .services.insurer_response import company_fields, merge_notes, set_company_fields


def offer(summary, company, year):
    return InsuranceOffer.objects.create(summary=summary, company_name=company, insurance_year=year,
                                         insurance_sum=Decimal('3000000'), franchise_1=Decimal('0'),
                                         premium_with_franchise_1=Decimal('70000'))


class CompanyLevelFieldsTests(TestCase):
    def setUp(self):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', dfa_number='ТС-1',
                                                  object_description='Haval F7X')
        self.summary = InsuranceSummary.objects.create(request=request, status='collecting')
        self.user = User.objects.create_user(username='cl_user', password='pwd')
        self.user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.force_login(self.user)

    def _form(self, year, territory='РФ', notes='', company='ВСК'):
        return {'company_name': company, 'insurance_year': year, 'insurance_sum': '3000000', 'franchise_1': '0',
                'premium_with_franchise_1': '70000', 'payments_per_year_variant_1': '1',
                'payments_per_year_variant_2': '1', 'coverage_territory': territory, 'notes': notes}

    def test_response_created_with_first_offer_and_shared_by_years(self):
        offer(self.summary, 'ВСК', 1)
        set_company_fields(self.summary.pk, 'ВСК', coverage_territory='РФ и СНГ')
        offer(self.summary, 'ВСК', 2)
        self.assertEqual(InsurerResponse.objects.filter(summary=self.summary).count(), 1)
        self.assertEqual(company_fields(self.summary.pk, 'ВСК')['coverage_territory'], 'РФ и СНГ')

    def test_offer_moved_to_new_company_takes_territory_and_notes(self):
        offer(self.summary, 'ВСК', 1)
        moved = offer(self.summary, 'ВСК', 2)
        set_company_fields(self.summary.pk, 'ВСК', coverage_territory='Вся РФ', notes='Осмотр')
        moved.company_name = 'Альфа'
        moved.save()
        self.assertEqual(company_fields(self.summary.pk, 'Альфа'), {'coverage_territory': 'Вся РФ', 'notes': 'Осмотр'})
        self.assertEqual(company_fields(self.summary.pk, 'ВСК')['coverage_territory'], 'Вся РФ')  # у ВСК остался год

    def test_offer_moved_to_existing_company_keeps_its_values(self):
        offer(self.summary, 'Альфа', 1)
        set_company_fields(self.summary.pk, 'Альфа', coverage_territory='Альфа: РФ')
        moved = offer(self.summary, 'ВСК', 1)
        moved.company_name, moved.insurance_year = 'Альфа', 2
        moved.save()
        self.assertEqual(company_fields(self.summary.pk, 'Альфа')['coverage_territory'], 'Альфа: РФ')
        self.assertFalse(InsurerResponse.objects.filter(summary=self.summary, company_name='ВСК').exists())

    def test_add_appends_notes_and_edit_replaces(self):
        add_url = reverse('summaries:add_offer', args=[self.summary.pk])
        self.client.post(add_url, self._form(1, notes='Осмотр обязателен'))
        self.client.post(add_url, self._form(2))  # пустое примечание прежнее не стирает
        self.assertEqual(company_fields(self.summary.pk, 'ВСК')['notes'], 'Осмотр обязателен')
        self.client.post(add_url, self._form(3, notes='Скидка за 3 года'))
        self.assertEqual(company_fields(self.summary.pk, 'ВСК')['notes'], 'Осмотр обязателен\nСкидка за 3 года')

        second = InsuranceOffer.objects.get(summary=self.summary, company_name='ВСК', insurance_year=2)
        page = self.client.get(reverse('summaries:edit_offer', args=[second.pk]))
        self.assertContains(page, 'Скидка за 3 года')  # форма правки показывает примечание СК
        self.client.post(reverse('summaries:edit_offer', args=[second.pk]), self._form(2, territory='РФ и РБ'))
        self.assertEqual(company_fields(self.summary.pk, 'ВСК'), {'coverage_territory': 'РФ и РБ', 'notes': ''})
        self.assertFalse(InsuranceOffer.objects.filter(summary=self.summary).exclude(notes='').exists())  # архив

    def test_set_territory_from_summary_card(self):
        offer(self.summary, 'ВСК', 1)
        offer(self.summary, 'ВСК', 2)
        url = reverse('summaries:set_company_territory', args=[self.summary.pk])
        response = self.client.post(url, {'company': 'ВСК', 'territory': '  РФ без исключений '})
        self.assertEqual(response.json(), {'success': True})
        self.assertEqual(company_fields(self.summary.pk, 'ВСК')['coverage_territory'], 'РФ без исключений')
        self.assertEqual(self.client.post(url, {'company': 'Зетта', 'territory': 'x'}).status_code, 400)
        page = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertContains(page, '<span class="og-territory-text">РФ без исключений', count=1)  # один раз на СК

    def test_merge_notes(self):
        self.assertEqual(merge_notes('', ' новое '), 'новое')
        self.assertEqual(merge_notes('Осмотр', ''), 'Осмотр')
        self.assertEqual(merge_notes('Осмотр  обязателен', 'Осмотр обязателен'), 'Осмотр  обязателен')
        self.assertEqual(merge_notes('Осмотр', 'Скидка'), 'Осмотр\nСкидка')

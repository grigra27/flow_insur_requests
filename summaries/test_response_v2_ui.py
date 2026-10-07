"""Шаблон ответа V2, этап 3: тестовая карточка, скачивание шаблона, блоки у компаний на карточке свода.

Всё видно только суперпользователю (контур V2), сотрудники карточку свода видят как раньше.
"""
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary, InsurerResponse
from summaries.response_template import META_SHEET, SHEET_TITLE


class ResponseV2UiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admins = Group.objects.get_or_create(name='Администраторы')[0]
        users = Group.objects.get_or_create(name='Пользователи')[0]
        cls.superuser = User.objects.create_superuser('root', password='p')
        cls.superuser.groups.add(admins)
        cls.admin = User.objects.create_user('admin', password='p')
        cls.admin.groups.add(admins)
        cls.staff = User.objects.create_user('staff', password='p')
        cls.staff.groups.add(users)
        request = InsuranceRequest.objects.create(
            client_name='ООО Тест', inn='1234567890', dfa_number='ОБ-20702-ЛО-КР', vehicle_info='GIANFRANCO',
            insurance_type='страхование имущества', has_transportation=True,
            transportation_departure='Москва', transportation_destination='Армавир',
        )
        cls.summary = InsuranceSummary.objects.create(request=request, status='collecting')
        for company in ('Согаз', 'ВСК'):
            InsuranceOffer.objects.create(
                summary=cls.summary, company_name=company, insurance_year=1,
                insurance_sum=Decimal('3000000'), franchise_1=Decimal('0'),
                premium_with_franchise_1=Decimal('90000'), coverage_territory='РФ',
            )
        InsurerResponse.objects.create(
            summary=cls.summary, company_name='Согаз', template_version=InsurerResponse.TEMPLATE_V2,
            rnpk_status='included', rnpk_comment='по правилам СК', transport_cost=Decimal('5330'),
        )

    def _detail(self, user):
        self.client.force_login(user)
        return self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))

    def test_test_card_visible_only_to_superuser(self):
        self.assertContains(self._detail(self.superuser), 'ТЕСТ · Шаблон ответа V2')
        for user in (self.admin, self.staff):
            response = self._detail(user)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'Шаблон ответа V2')

    def test_block_lines_for_superuser_with_missing_marked(self):
        content = self._detail(self.superuser).content.decode()
        self.assertIn('class="og-v2-lines"', content)
        self.assertIn('Включены в полис · по правилам СК', content)
        self.assertIn('5 330 ₽', content)
        self.assertIn('og-v2-line og-v2-line--missing', content)  # у ВСК ответа V2 нет
        self.assertNotIn('class="og-v2-lines"', self._detail(self.staff).content.decode())

    def test_personal_template_download(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('summaries:download_response_template_v2', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('otvet_strahovshika_v2_20702.xlsx', response['Content-Disposition'])
        wb = load_workbook(BytesIO(response.content))
        self.assertEqual(wb[META_SHEET]['B2'].value, self.summary.pk)
        self.assertEqual(wb[SHEET_TITLE]['A1'].value, 'Ответ страховой компании на запрос ОБ-20702-ЛО-КР')

    def test_generic_template_download(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('summaries:download_response_template_v2_generic'))
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        self.assertIsNone(wb[META_SHEET]['B2'].value)
        self.assertTrue(wb[SHEET_TITLE]['A12'].value.startswith('Общий шаблон.'))

    def test_downloads_denied_without_superuser(self):
        self.client.force_login(self.admin)
        for url in (reverse('summaries:download_response_template_v2', args=[self.summary.pk]),
                    reverse('summaries:download_response_template_v2_generic')):
            self.assertEqual(self.client.get(url).status_code, 403)

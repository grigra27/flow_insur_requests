"""Комплект для страховщика на странице заявки (шаблон ответа V2): заявка PDF + шаблон ответа.

docs/improvement_plans/insurer_response_v2.md. Виден, когда открыт шаблон V2; иначе —
прежняя красная кнопка «Скачать заявку (PDF)» в шапке.
"""
import uuid
from io import BytesIO
from unittest import mock
from urllib.parse import quote

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary


class InsurerKitTests(TestCase):
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
        cls.request_obj = InsuranceRequest.objects.create(
            client_name='ООО Тест', inn='1234567890', dfa_number='ОБ-20702-ЛО-КР', vehicle_info='Станок',
            insurance_type='страхование имущества', has_transportation=True,
        )
        batch_id = uuid.uuid4()
        cls.batch = [
            InsuranceRequest.objects.create(
                client_name='ООО Партия', inn='1', dfa_number='ТС-18022-2-3', vehicle_info=f'Автобус {n}',
                insurance_type='КАСКО', source_batch_id=batch_id, item_no=n, item_count=3,
            ) for n in (1, 2, 3)
        ]

    def _detail(self, user, obj):
        self.client.force_login(user)
        return self.client.get(reverse('insurance_requests:request_detail', args=[obj.pk]))

    def test_kit_card_for_superuser_with_two_files(self):
        response = self._detail(self.superuser, self.request_obj)
        self.assertContains(response, 'Отправка страховщику')
        kit = response.context['insurer_kit']
        self.assertFalse(kit['is_batch'])
        self.assertEqual([f['title'] for f in kit['files']],
                         ['Заявка — ОБ-20702-ЛО-КР.pdf', 'Ответ страховщика — ОБ-20702-ЛО-КР.xlsx'])
        self.assertEqual(kit['files'][1]['subtitle'], 'шаблон ответа · блоки: Осмотр, Риски РНПК, Перевозка')
        self.assertContains(response, 'Скачать оба файла')
        self.assertContains(response, 'rq-kit__btn--pdf')
        self.assertContains(response, 'rq-kit__btn--xlsx')
        self.assertNotContains(response, 'class="rq-pdf-btn"')  # кнопка PDF в шапке — только без комплекта

    def test_staff_sees_only_current_pdf_button(self):
        for user in (self.admin, self.staff):
            response = self._detail(user, self.request_obj)
            self.assertIsNone(response.context['insurer_kit'])
            self.assertNotContains(response, 'Отправка страховщику')
            self.assertContains(response, 'class="rq-pdf-btn"')

    def test_batch_kit_has_batch_pdf_and_template_per_object(self):
        kit = self._detail(self.superuser, self.batch[1]).context['insurer_kit']
        self.assertTrue(kit['is_batch'])
        titles = [f['title'] for f in kit['files']]
        self.assertEqual(titles[0], 'Заявка на партию — ТС-18022-2-3.pdf')
        self.assertEqual(titles[1:], [f'Ответ страховщика — ТС-18022-2-3 (объект {n} из 3).xlsx' for n in (1, 2, 3)])
        self.assertEqual([f.get('current', False) for f in kit['files'][1:]], [False, True, False])
        self.assertEqual(kit['template'], kit['files'][2])
        self.assertEqual([f['label'][:13] for f in kit['others']], ['Объект 1 из 3', 'Объект 3 из 3'])
        self.assertIn('?kit=1', kit['files'][0]['url'])

    def test_template_download_carries_request_and_summary(self):
        summary = InsuranceSummary.objects.create(request=self.request_obj, status='collecting')
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('insurance_requests:download_response_template',
                                           args=[self.request_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("filename*=UTF-8''" + quote('Ответ страховщика — ОБ-20702-ЛО-КР.xlsx'),
                      response['Content-Disposition'])
        meta = load_workbook(BytesIO(response.content))['_meta']
        self.assertEqual((meta['B2'].value, meta['B3'].value), (summary.pk, self.request_obj.pk))

    def test_template_download_superuser_only(self):
        self.client.force_login(self.admin)
        url = reverse('insurance_requests:download_response_template', args=[self.request_obj.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    @mock.patch('insurance_requests.views.render_application_pdf', return_value=b'%PDF-1.4')
    def test_pdf_kit_name_only_with_kit_flag(self, _render):
        self.client.force_login(self.staff)
        url = reverse('insurance_requests:export_request_application', args=[self.request_obj.pk])
        plain = self.client.get(url)['Content-Disposition']
        self.assertIn('application_', plain)  # прежнее имя для красной кнопки
        kit = self.client.get(url + '?kit=1')['Content-Disposition']
        self.assertIn("filename*=UTF-8''" + quote('Заявка — ОБ-20702-ЛО-КР.pdf'), kit)


class SummarySectionRefreshTests(TestCase):
    """После смены статуса без перезагрузки JS подменяет блок #summary-section свежей разметкой страницы."""

    def test_section_has_create_button_after_emails_sent(self):
        users = Group.objects.get_or_create(name='Пользователи')[0]
        staff = User.objects.create_user('s', password='p')
        staff.groups.add(users)
        obj = InsuranceRequest.objects.create(client_name='ООО', inn='1', dfa_number='ОБ-9', vehicle_info='Станок',
                                              status='email_generated')
        self.client.force_login(staff)
        url = reverse('insurance_requests:request_detail', args=[obj.pk])
        page = self.client.get(url)
        self.assertContains(page, 'id="summary-section"')
        self.assertContains(page, 'refreshSummarySection()')
        self.assertNotContains(page, 'create-summary-btn')
        self.client.post(reverse('insurance_requests:change_request_status', args=[obj.pk]),
                         {'status': 'emails_sent'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        fresh = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(fresh, 'create-summary-btn')

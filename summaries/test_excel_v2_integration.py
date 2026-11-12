"""Current Excel downloads and authenticated compatibility redirects."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import Client, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from summaries.exceptions import ExcelExportServiceError
from summaries.models import InsuranceSummary
from summaries.services.summary_export_v2 import SummaryExportV2Service
from summaries.test_summary_export_v2 import SummaryExportV2Base


class ExcelV2IntegrationTests(SummaryExportV2Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.employee = User.objects.create_user('excel-employee')
        cls.employee.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        cls.admin = User.objects.create_user('excel-admin', is_superuser=True, is_staff=True)
        cls.admin.groups.add(Group.objects.get_or_create(name='Администраторы')[0])
        cls.outsider = User.objects.create_user('excel-outsider')
        cls.summary.status = 'ready'
        cls.summary.save(update_fields=['status'])

    def setUp(self):
        self.client.force_login(self.employee)

    def _current_url(self, version, pk=None):
        return reverse('summaries:generate_summary_file_v2', args=[pk or self.summary.pk, version])

    def _legacy_url(self, version, pk=None):
        name = 'generate_client_summary_file' if version == 'client' else 'generate_summary_file'
        return reverse('summaries:' + name, args=[pk or self.summary.pk])

    def _assert_workbook(self, response, version):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ['Свод'] if version == 'client' else ['Свод', 'Параметры запроса'])
        self.assertEqual(workbook['Свод']['B4'].value, self.request_obj.dfa_number)
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_employee_downloads_current_client_and_full_workbooks(self):
        for version in ('client', 'full'):
            with self.subTest(version=version):
                self._assert_workbook(self.client.get(self._current_url(version)), version)

    def test_old_client_and_full_urls_redirect_to_matching_v2(self):
        for version in ('client', 'full'):
            with self.subTest(version=version):
                response = self.client.get(self._legacy_url(version))
                self.assertRedirects(response, self._current_url(version), fetch_redirect_response=False)
                self.assertIn('private', response['Cache-Control'])
                self.assertIn('no-store', response['Cache-Control'])

    def test_following_old_links_downloads_the_current_workbook(self):
        for version in ('client', 'full'):
            with self.subTest(version=version):
                response = self.client.get(self._legacy_url(version), follow=True)
                self.assertEqual(response.redirect_chain, [(self._current_url(version), 302)])
                self._assert_workbook(response, version)

    def test_card_only_offers_current_exports(self):
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertContains(response, self._current_url('client'))
        self.assertContains(response, self._current_url('full'))
        for removed in ('Клиентский V1', 'Полный V1', 'generateSummaryFile(', 'generateClientSummaryFile('):
            self.assertNotContains(response, removed)

    def test_anonymous_users_cannot_access_old_or_current_exports(self):
        self.client.logout()
        for version in ('client', 'full'):
            for url in (self._legacy_url(version), self._current_url(version)):
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn('/login/', response['Location'])

    def test_user_without_employee_group_is_denied_on_both_versions(self):
        self.client.force_login(self.outsider)
        for version in ('client', 'full'):
            for url in (self._legacy_url(version), self._current_url(version)):
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_employee_status_restriction_is_preserved_through_old_links(self):
        for status in ('collecting', 'sent', 'completed_accepted', 'completed_rejected'):
            InsuranceSummary.objects.filter(pk=self.summary.pk).update(status=status)
            for version in ('client', 'full'):
                with self.subTest(status=status, version=version):
                    response = self.client.get(self._legacy_url(version), follow=True)
                    self.assertEqual(response.redirect_chain, [
                        (self._current_url(version), 302),
                        (reverse('summaries:summary_detail', args=[self.summary.pk]), 302),
                    ])
                    self.assertNotEqual(response.get('Content-Type'),
                                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_superuser_can_download_through_old_links_in_any_status(self):
        self.client.force_login(self.admin)
        for status in ('collecting', 'ready', 'sent', 'completed_accepted', 'completed_rejected'):
            InsuranceSummary.objects.filter(pk=self.summary.pk).update(status=status)
            for version in ('client', 'full'):
                with self.subTest(status=status, version=version):
                    self._assert_workbook(self.client.get(self._legacy_url(version), follow=True), version)

    def test_missing_summary_still_returns_404_after_redirect(self):
        for version in ('client', 'full'):
            with self.subTest(version=version):
                response = self.client.get(self._legacy_url(version, pk=999999), follow=True)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.redirect_chain, [(self._current_url(version, pk=999999), 302)])

    def test_v2_works_without_the_old_template_directory(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)):
            for version in ('client', 'full'):
                with self.subTest(version=version):
                    self._assert_workbook(self.client.get(self._current_url(version)), version)

    def test_export_error_returns_to_card_through_old_link(self):
        with patch.object(SummaryExportV2Service, 'generate', side_effect=ExcelExportServiceError('fixture error')):
            response = self.client.get(self._legacy_url('client'), follow=True)
        self.assertEqual(response.redirect_chain, [
            (self._current_url('client'), 302),
            (reverse('summaries:summary_detail', args=[self.summary.pk]), 302),
        ])
        self.assertContains(response, 'fixture error')

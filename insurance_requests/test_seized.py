"""Сценарий «Изъятое имущество» (analytics_redesign_2026_09, задача 6.8)."""
import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .parsers.excel_v2.parser import ParserV2Result
from .seized import apply_seized_preset, is_seized_filename, seized_dfa_number
from . import test_parser_v2

xlsx_upload = test_parser_v2.ParserV2UploadTests._xlsx_upload  # импорт класса запустил бы его тесты повторно


class SeizedPresetTests(SimpleTestCase):
    def test_filename_marker(self):
        self.assertTrue(is_seized_filename('Заявка 20555-ЛТ-СТ ИЗЪЯТОЕ.xlsx'))
        self.assertTrue(is_seized_filename('изъятие экскаватор.xlsx'))
        self.assertFalse(is_seized_filename('Заявка ТС 20842.xlsx'))
        self.assertFalse(is_seized_filename(None))

    def test_dfa_suffix_added_once(self):
        self.assertEqual(seized_dfa_number('ТС-20555-ЛТ-СТ'), 'ТС-20555-ЛТ-СТ Изъятое')
        self.assertEqual(seized_dfa_number('ТС-20555 изъятое'), 'ТС-20555 изъятое')
        self.assertEqual(seized_dfa_number(''), 'Изъятое')

    def test_preset_replaces_lessee_data(self):
        result = ParserV2Result(data={
            'client_name': 'ООО Ромашка', 'inn': '1234567890', 'insured_party': 'lessee',
            'insurance_type': 'страхование спецтехники', 'insurance_period': 'на весь срок лизинга',
            'manager_name': 'Иванов Иван', 'dfa_number': 'ТС-20555-ЛТ-СТ',
            'legal_address': 'г. Казань', 'postal_address': 'г. Казань', 'business_activity': 'стройка',
            'birth_date': '1961-02-20', 'insurance_territory': '',
        }, warnings=[])

        apply_seized_preset(result)

        self.assertEqual(result.data['client_name'], 'ЗАО "Альянс-Лизинг"')
        self.assertEqual(result.data['inn'], '7825496985')
        self.assertEqual(result.data['insured_party'], 'lessor')
        self.assertEqual(result.data['insurance_type'], 'страхование имущества')
        self.assertEqual(result.data['insurance_period'], '1 год')
        self.assertEqual(result.data['manager_name'], 'Овдина Е.М.')
        self.assertEqual(result.data['dfa_number'], 'ТС-20555-ЛТ-СТ Изъятое')
        for field in ('legal_address', 'postal_address', 'business_activity', 'birth_date'):
            self.assertEqual(result.data[field], '')
        self.assertEqual(result.warnings[-1]['field'], 'seized')


class SeizedUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        user = User.objects.create_user(username='seized_user', password='pwd')
        user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.login(username='seized_user', password='pwd')

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _upload(self, filename, **extra):
        return self.client.post(
            reverse('insurance_requests:upload_excel'),
            {'excel_file': xlsx_upload(self, filename), **extra},
        )

    def test_checkbox_applies_preset(self):
        response = self._upload('заявка 20213-ЛТ-КЗ изъятое.xlsx', seized_mode='on')

        initial = response.context['form'].initial
        self.assertEqual(initial['client_name'], 'ЗАО "Альянс-Лизинг"')
        self.assertEqual(initial['insured_party'], 'lessor')
        self.assertEqual(initial['manager_name'], 'Овдина Е.М.')
        self.assertTrue(initial['dfa_number'].endswith(' Изъятое'))
        self.assertContains(response, 'Включён режим')
        self.assertNotContains(response, 'js-seized-apply')

    def test_seized_filename_offers_button_without_applying(self):
        response = self._upload('заявка 20213-ЛТ-КЗ изъятое.xlsx')

        self.assertEqual(response.context['form'].initial['client_name'], 'ООО Ромашка')
        self.assertContains(response, 'js-seized-apply')
        self.assertContains(response, 'id="seized-preset"')

    def test_regular_filename_has_no_banner(self):
        response = self._upload('заявка 20213-ЛТ-КЗ.xlsx')

        self.assertNotContains(response, 'js-seized-apply')
        self.assertNotContains(response, 'Включён режим')

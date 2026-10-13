"""Фаза D3: перенос vehicle_info/asset_status в object_description/condition (команда migrate_legacy_object_fields)."""
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from insurance_requests.management.commands.migrate_legacy_object_fields import condition_from_asset_status
from insurance_requests.models import InsuranceRequest, RequestFieldEdit


class ConditionMappingTests(SimpleTestCase):
    def test_values_seen_on_prod(self):
        for value in ('новое', 'Новое', 'новое новое', ' новое '):
            self.assertEqual(condition_from_asset_status(value), 'new', value)
        for value in ('б/у', 'БУ', 'б.у.', 'Б/У'):
            self.assertEqual(condition_from_asset_status(value), 'used', value)
        for value in ('', None, '2025 2025 2025', 'новое и б/у'):
            self.assertIsNone(condition_from_asset_status(value), value)


class MigrateLegacyObjectFieldsTests(TestCase):
    def setUp(self):
        self.v1 = InsuranceRequest.objects.create(client_name='ООО V1', inn='1', dfa_number='ТС-1',
                                                  vehicle_info='Haval Jolion 2024', asset_status='новое')
        self.v1_used = InsuranceRequest.objects.create(client_name='ООО V1 бу', inn='2', dfa_number='ТС-2',
                                                       vehicle_info='Экскаватор JCB', asset_status='БУ')
        self.v2 = InsuranceRequest.objects.create(client_name='ООО V2', inn='3', dfa_number='ТС-3',
                                                  vehicle_info='старый текст', object_description='Газель Next',
                                                  asset_status='б/у', condition='new')
        self.odd = InsuranceRequest.objects.create(client_name='ООО ?', inn='4', dfa_number='ТС-4',
                                                   vehicle_info='Компрессор', asset_status='2025 2025 2025')
        self.updated_at = {r.pk: r.updated_at for r in InsuranceRequest.objects.all()}

    def _run(self, *args):
        out = StringIO()
        call_command('migrate_legacy_object_fields', *args, stdout=out)
        return out.getvalue()

    def test_report_does_not_write(self):
        report = self._run()
        self.assertIn('Заявок к обновлению: 3', report)
        self.assertIn("object_description ← vehicle_info: 3", report)
        self.assertIn("'2025 2025 2025': 1", report)
        self.assertIn('Только отчёт', report)
        self.v1.refresh_from_db()
        self.assertFalse(self.v1.object_description)
        self.assertIsNone(self.v1.condition)

    def test_apply_copies_without_touching_legacy_fields_or_history(self):
        summary_before = self.v1.object_summary
        self._run('--apply')
        for request in InsuranceRequest.objects.all():
            request.refresh_from_db()
        v1, v1_used, v2, odd = (InsuranceRequest.objects.get(pk=r.pk) for r in (self.v1, self.v1_used, self.v2, self.odd))
        self.assertEqual((v1.object_description, v1.condition), ('Haval Jolion 2024', 'new'))
        self.assertEqual((v1_used.object_description, v1_used.condition), ('Экскаватор JCB', 'used'))
        # уже заполненные структурные поля не трогаются
        self.assertEqual((v2.object_description, v2.condition), ('Газель Next', 'new'))
        # неразобранное состояние остаётся пустым, описание переносится
        self.assertEqual((odd.object_description, odd.condition), ('Компрессор', None))
        # старые поля — как были (архив)
        self.assertEqual((v1.vehicle_info, v1.asset_status), ('Haval Jolion 2024', 'новое'))
        # без смены даты изменения и без записей в журнал правок
        for request in (v1, v1_used, v2, odd):
            self.assertEqual(request.updated_at, self.updated_at[request.pk])
        self.assertEqual(RequestFieldEdit.objects.count(), 0)
        # сводка объекта теперь из структуры и с состоянием
        self.assertEqual(summary_before, 'Haval Jolion 2024')
        self.assertEqual(v1.object_summary, 'Haval Jolion 2024, Новое')

    def test_second_run_has_nothing_to_do(self):
        self._run('--apply')
        self.assertIn('Заявок к обновлению: 0', self._run())

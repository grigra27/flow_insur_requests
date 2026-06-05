"""Тесты трекинга ручных правок оператора (фаза 1)."""
import datetime as dt
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from .edit_tracking import (
    build_edit_tracking,
    current_display_value,
    diff_fields,
    get_object_field_meta,
    get_scalar_field_meta,
    object_comparison_rows,
    scalar_comparison_rows,
)
from .models import InsuranceRequest


class DiffFieldsTests(SimpleTestCase):
    def setUp(self):
        self.meta = get_scalar_field_meta()

    def test_no_change_when_values_equal(self):
        before = {'client_name': 'ООО Ромашка'}
        after = {'client_name': 'ООО Ромашка'}
        self.assertEqual(diff_fields(before, after, ['client_name'], self.meta), [])

    def test_whitespace_difference_is_not_an_edit(self):
        before = {'client_name': 'ООО  Ромашка '}
        after = {'client_name': 'ООО Ромашка'}
        self.assertEqual(diff_fields(before, after, ['client_name'], self.meta), [])

    def test_changed_value_is_reported(self):
        before = {'client_name': 'ООО Ромашка'}
        after = {'client_name': 'ООО Лютик'}
        edits = diff_fields(before, after, ['client_name'], self.meta)
        self.assertEqual(len(edits), 1)
        edit = edits[0]
        self.assertEqual(edit['field'], 'client_name')
        self.assertEqual(edit['original'], 'ООО Ромашка')
        self.assertEqual(edit['modified'], 'ООО Лютик')
        self.assertEqual(edit['edit_type'], 'changed')
        self.assertEqual(edit['label'], 'Клиент')

    def test_filled_when_parser_empty(self):
        before = {'creditor_bank': ''}
        after = {'creditor_bank': 'Сбербанк'}
        edits = diff_fields(before, after, ['creditor_bank'], self.meta)
        self.assertEqual(edits[0]['edit_type'], 'filled')

    def test_cleared_when_operator_empties(self):
        before = {'creditor_bank': 'Сбербанк'}
        after = {'creditor_bank': ''}
        edits = diff_fields(before, after, ['creditor_bank'], self.meta)
        self.assertEqual(edits[0]['edit_type'], 'cleared')

    def test_none_treated_as_empty(self):
        before = {'creditor_bank': None}
        after = {'creditor_bank': None}
        self.assertEqual(diff_fields(before, after, ['creditor_bank'], self.meta), [])

    def test_inn_leading_zero_preserved(self):
        # ИНН — НЕ числовое поле, ведущий ноль не должен теряться при сравнении.
        before = {'inn': '0123456789'}
        after = {'inn': '123456789'}
        edits = diff_fields(before, after, ['inn'], self.meta)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]['original'], '0123456789')

    def test_numeric_field_normalized(self):
        # transportation_days — числовое поле, 5 == 5.0.
        before = {'transportation_days': '5'}
        after = {'transportation_days': 5}
        self.assertEqual(diff_fields(before, after, ['transportation_days'], self.meta), [])

    def test_boolean_change_reported_with_labels(self):
        before = {'has_installment': False}
        after = {'has_installment': True}
        edits = diff_fields(before, after, ['has_installment'], self.meta)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]['original'], 'Нет')
        self.assertEqual(edits[0]['modified'], 'Да')
        # Булево всегда «присутствует» (явное Нет), поэтому смена — исправление.
        self.assertEqual(edits[0]['edit_type'], 'changed')

    def test_choice_code_rendered_as_label(self):
        before = {'deal_status': 'new'}
        after = {'deal_status': 'prolongation'}
        edits = diff_fields(before, after, ['deal_status'], self.meta)
        self.assertEqual(edits[0]['original'], 'Новая сделка')
        self.assertEqual(edits[0]['modified'], 'Пролонгация')

    def test_object_decimal_cost_normalized(self):
        object_meta = get_object_field_meta()
        before = {'acquisition_cost_value': '1000000'}
        after = {'acquisition_cost_value': Decimal('1000000.00')}
        self.assertEqual(
            diff_fields(before, after, ['acquisition_cost_value'], object_meta), []
        )


class BuildEditTrackingTests(SimpleTestCase):
    def _parse_result(self, **data):
        return {'data': data}

    def test_scalar_edits_collected(self):
        parse_result = self._parse_result(client_name='ООО А', inn='111', branch='')
        scalar_after = {'client_name': 'ООО Б', 'inn': '111', 'branch': 'Москва'}
        tracking = build_edit_tracking(parse_result, scalar_after, [], has_objects=False)
        names = tracking['summary']['edited_field_names']
        self.assertIn('client_name', names)
        self.assertIn('branch', names)
        self.assertNotIn('inn', names)
        self.assertEqual(tracking['summary']['total_field_edits'], 2)

    def test_vehicle_info_skipped_at_scalar_level_when_objects(self):
        parse_result = self._parse_result(vehicle_info='старое', manufacturing_year='2020')
        scalar_after = {'vehicle_info': 'новое', 'manufacturing_year': '2021'}
        tracking = build_edit_tracking(parse_result, scalar_after, [], has_objects=True)
        self.assertEqual(tracking['summary']['total_field_edits'], 0)

    def test_vehicle_info_tracked_at_scalar_level_without_objects(self):
        parse_result = self._parse_result(vehicle_info='старое')
        scalar_after = {'vehicle_info': 'новое'}
        tracking = build_edit_tracking(parse_result, scalar_after, [], has_objects=False)
        self.assertEqual(tracking['summary']['total_field_edits'], 1)

    def test_object_edits_aligned_by_position(self):
        parse_result = self._parse_result()
        object_pairs = [
            ({'brand': 'КамАЗ'}, {'brand': 'КамАЗ'}),
            ({'brand': 'МАЗ'}, {'brand': 'МАН'}),
        ]
        tracking = build_edit_tracking(parse_result, {}, object_pairs, has_objects=True)
        self.assertEqual(len(tracking['object_edits']), 2)
        self.assertEqual(tracking['object_edits'][0], [])
        self.assertEqual(len(tracking['object_edits'][1]), 1)
        self.assertEqual(tracking['summary']['total_object_edits'], 1)


class FieldComparisonTests(SimpleTestCase):
    def test_scalar_comparison_excludes_object_level_fields_with_objects(self):
        original = {'client_name': 'ООО А', 'manufacturing_year': '2020'}
        fields = {row['field'] for row in scalar_comparison_rows(original, [], has_objects=True)}
        self.assertIn('client_name', fields)
        self.assertNotIn('manufacturing_year', fields)
        self.assertNotIn('vehicle_info', fields)

    def test_scalar_comparison_marks_changed_from_edits(self):
        original = {'client_name': 'ООО А'}
        edits = [{'field': 'client_name', 'label': 'Клиент', 'original': 'ООО А',
                  'modified': 'ООО Б', 'edit_type': 'changed'}]
        rows = scalar_comparison_rows(original, edits, has_objects=False)
        by_field = {row['field']: row for row in rows}
        self.assertTrue(by_field['client_name']['changed'])
        self.assertEqual(by_field['client_name']['modified'], 'ООО Б')
        # Прочие поля присутствуют и не отмечены изменёнными.
        self.assertFalse(by_field['inn']['changed'])

    def test_object_comparison_rows_cover_object_fields(self):
        original = {'brand': 'КамАЗ', 'model': '5490'}
        edits = [{'field': 'model', 'label': 'Модель', 'original': '5490',
                  'modified': '54901', 'edit_type': 'changed'}]
        rows = object_comparison_rows(original, edits)
        by_field = {row['field']: row for row in rows}
        self.assertFalse(by_field['brand']['changed'])
        self.assertEqual(by_field['brand']['original'], 'КамАЗ')
        self.assertTrue(by_field['model']['changed'])


class ModelComparisonMethodsTests(SimpleTestCase):
    def test_scalar_comparison_from_snapshot(self):
        req = InsuranceRequest(additional_data={
            'parser_version': 'v2',
            'parser_v2': {
                'original_data': {'client_name': 'ООО А'},
                'tracking': {
                    'field_edits': [{'field': 'client_name', 'label': 'Клиент',
                                     'original': 'ООО А', 'modified': 'ООО Б',
                                     'edit_type': 'changed'}],
                },
            },
        })
        rows = req.parser_v2_scalar_comparison()
        client_rows = [r for r in rows if r['field'] == 'client_name']
        self.assertEqual(len(client_rows), 1)
        self.assertTrue(client_rows[0]['changed'])
        self.assertEqual(client_rows[0]['modified'], 'ООО Б')
        self.assertTrue(req.parser_v2_has_original_snapshot)

    def test_object_comparison_reads_edits_and_snapshot(self):
        req = InsuranceRequest(
            additional_data={
                'parser_version': 'v2',
                'parser_v2': {
                    'original_data': {},
                    'tracking': {
                        'object_originals': [{'brand': 'LADA', 'model': 'Largus'}],
                        'object_edits': [[
                            {'field': 'brand', 'label': 'Марка', 'original': 'LADA',
                             'modified': 'LADA (исправлено)', 'edit_type': 'changed'}
                        ]],
                    },
                },
            },
        )
        rows = req.parser_v2_object_comparison()
        by_field = {r['field']: r for r in rows}
        self.assertTrue(by_field['brand']['changed'])
        self.assertEqual(by_field['brand']['original'], 'LADA')
        self.assertEqual(by_field['brand']['modified'], 'LADA (исправлено)')
        # Неизменённое поле показывается из снимка в обеих колонках.
        self.assertFalse(by_field['model']['changed'])
        self.assertEqual(by_field['model']['original'], 'Largus')
        self.assertEqual(by_field['model']['modified'], 'Largus')

    def test_no_snapshot_reports_false(self):
        req = InsuranceRequest(additional_data={'parser_version': 'v2', 'parser_v2': {}})
        self.assertFalse(req.parser_v2_has_original_snapshot)
        self.assertEqual(req.parser_v2_object_comparison(), [])


class ModelEditPropertiesTests(SimpleTestCase):
    def _request(self, tracking, **kwargs):
        return InsuranceRequest(
            additional_data={'parser_version': 'v2', 'parser_v2': {'tracking': tracking}},
            **kwargs,
        )

    def test_field_edits_exposed(self):
        tracking = {
            'field_edits': [{'field': 'client_name', 'label': 'Клиент',
                             'original': 'A', 'modified': 'B', 'edit_type': 'changed'}],
            'object_edits': [],
        }
        req = self._request(tracking)
        self.assertEqual(len(req.parser_v2_field_edits), 1)
        self.assertEqual(req.parser_v2_edit_count, 1)

    def test_object_edits_selected_by_item_no(self):
        tracking = {
            'field_edits': [],
            'object_edits': [
                [{'field': 'brand', 'label': 'Марка', 'original': 'A',
                  'modified': 'B', 'edit_type': 'changed'}],
                [],
            ],
        }
        req_first = self._request(tracking, item_no=1, item_count=2)
        req_second = self._request(tracking, item_no=2, item_count=2)
        self.assertEqual(len(req_first.parser_v2_object_edits), 1)
        self.assertEqual(len(req_second.parser_v2_object_edits), 0)

    def test_single_request_uses_first_object(self):
        tracking = {
            'field_edits': [],
            'object_edits': [
                [{'field': 'brand', 'label': 'Марка', 'original': 'A',
                  'modified': 'B', 'edit_type': 'changed'}],
            ],
        }
        req = self._request(tracking)  # item_no is None
        self.assertEqual(len(req.parser_v2_object_edits), 1)
        self.assertEqual(req.parser_v2_all_edits[0]['field'], 'brand')

    def test_no_tracking_is_safe(self):
        req = InsuranceRequest(additional_data={})
        self.assertEqual(req.parser_v2_field_edits, [])
        self.assertEqual(req.parser_v2_object_edits, [])
        self.assertEqual(req.parser_v2_edit_count, 0)


class CurrentDisplayValueTests(SimpleTestCase):
    """Точка 3: форматирование текущего значения поля модели для показа."""

    def setUp(self):
        self.meta = get_scalar_field_meta()

    def test_placeholder_neutralized_to_empty(self):
        # to_request_fields() кладёт плейсхолдеры в пустые обязательные поля —
        # в сравнении они должны читаться как пустота, а не как значение.
        self.assertEqual(current_display_value('client_name', 'Клиент не указан', self.meta), '')
        self.assertEqual(current_display_value('vehicle_info', 'Предмет лизинга не указан', self.meta), '')
        self.assertEqual(current_display_value('dfa_number', 'Номер ДФА не указан', self.meta), '')

    def test_datetime_localized_and_formatted(self):
        from django.utils import timezone as djtz
        value = djtz.make_aware(dt.datetime(2025, 1, 2, 9, 30), djtz.utc)
        # Europe/Moscow = UTC+3 → 12:30.
        self.assertEqual(current_display_value('response_deadline', value, self.meta), '02.01.2025 12:30')

    def test_date_formatted(self):
        self.assertEqual(current_display_value('birth_date', dt.date(1990, 5, 7), self.meta), '07.05.1990')

    def test_choice_code_rendered_as_label(self):
        self.assertEqual(current_display_value('deal_status', 'new', self.meta), 'Новая сделка')

    def test_plain_text_passthrough(self):
        self.assertEqual(current_display_value('manager_name', 'Иванов И.И.', self.meta), 'Иванов И.И.')


class PostCreationComparisonTests(TestCase):
    """Точка 3 в сравнении: правки после создания (из CRUDEvent)."""

    def _make_crud_update(self, req, changed_fields, *, user, when):
        from easyaudit.models import CRUDEvent
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(InsuranceRequest)
        ev = CRUDEvent.objects.create(
            event_type=CRUDEvent.UPDATE,
            object_id=str(req.pk),
            content_type=ct,
            object_repr='req',
            changed_fields=json.dumps(changed_fields),
            user=user,
        )
        # datetime — auto_now_add, выставляем явно: правка должна быть позже
        # создания заявки, иначе попадёт в «хвост создания».
        CRUDEvent.objects.filter(pk=ev.pk).update(datetime=when)
        return ev

    def test_changed_after_create_flagged_with_author(self):
        user = User.objects.create_user('operator1', last_name='Петров', first_name='Иван')
        req = InsuranceRequest.objects.create(
            client_name='ООО Текущее',
            inn='1234567890',
            insurance_type='КАСКО',
            status='uploaded',
            created_by=user,
            additional_data={
                'parser_version': 'v2',
                'parser_v2': {
                    'original_data': {'client_name': 'ООО Распознано'},
                    'tracking': {'field_edits': []},
                },
            },
        )
        self._make_crud_update(
            req, {'client_name': ['ООО Распознано', 'ООО Текущее']},
            user=user, when=req.created_at + dt.timedelta(hours=1),
        )

        rows = {r['field']: r for r in req.parser_v2_scalar_comparison()}
        client = rows['client_name']
        self.assertEqual(client['original'], 'ООО Распознано')   # точка 1
        self.assertEqual(client['current'], 'ООО Текущее')       # точка 3
        self.assertTrue(client['changed_after_create'])
        self.assertEqual(client['changed_by'], 'Петров Иван')
        # Поле, которое не трогали после создания, не подсвечено.
        self.assertFalse(rows['inn']['changed_after_create'])
        self.assertEqual(req.parser_v2_post_creation_count, 1)

    def test_creation_burst_not_counted_as_late_edit(self):
        user = User.objects.create_user('operator2')
        req = InsuranceRequest.objects.create(
            client_name='ООО А', inn='1', insurance_type='КАСКО',
            status='uploaded', created_by=user,
            additional_data={
                'parser_version': 'v2',
                'parser_v2': {'original_data': {'client_name': 'ООО А'}, 'tracking': {'field_edits': []}},
            },
        )
        # Правка «в момент создания» (в пределах эпсилона) — не считается поздней.
        self._make_crud_update(
            req, {'client_name': ['x', 'ООО А']},
            user=user, when=req.created_at + dt.timedelta(seconds=1),
        )
        self.assertEqual(req.parser_v2_post_creation_count, 0)
        rows = {r['field']: r for r in req.parser_v2_scalar_comparison()}
        self.assertFalse(rows['client_name']['changed_after_create'])

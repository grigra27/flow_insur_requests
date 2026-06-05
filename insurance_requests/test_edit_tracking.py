"""Тесты трекинга ручных правок оператора (фаза 1)."""
from decimal import Decimal

from django.test import SimpleTestCase

from .edit_tracking import (
    build_edit_tracking,
    diff_fields,
    get_object_field_meta,
    get_scalar_field_meta,
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

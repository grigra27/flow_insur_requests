"""Проверки правдоподобия значений заявки (analytics_redesign_2026_09, задача 5.4)."""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from .models import InsuranceRequest
from .plausibility import check_values, inn_checksum_ok

TODAY = date(2026, 9, 26)


def fields(values):
    return [warning['field'] for warning in check_values(values, today=TODAY)]


class PlausibilityRulesTests(SimpleTestCase):
    def test_plausible_values_pass(self):
        self.assertEqual(fields({
            'birth_date': date(1961, 2, 20), 'manufacturing_year': '2024',
            'acquisition_cost_value': Decimal('7900000'), 'acquisition_cost_currency': 'RUB',
            'power_or_capacity': '249', 'dfa_number': 'ТС-20842-ГА-МН', 'inn': '7707083893',
        }), [])

    def test_empty_values_are_not_checked(self):
        self.assertEqual(fields({'birth_date': None, 'acquisition_cost_value': '', 'inn': '', 'dfa_number': ''}), [])

    def test_birth_date_in_future_or_implausible_age(self):
        self.assertEqual(fields({'birth_date': date(2061, 2, 20)}), ['birth_date'])   # «20.02.61» → 2061
        self.assertEqual(fields({'birth_date': '2063-02-06'}), ['birth_date'])
        self.assertEqual(fields({'birth_date': date(2015, 1, 1)}), ['birth_date'])    # 11 лет
        self.assertEqual(fields({'birth_date': date(1900, 1, 1)}), ['birth_date'])

    def test_manufacturing_year(self):
        self.assertEqual(fields({'manufacturing_year': '2027'}), [])
        self.assertEqual(fields({'manufacturing_year': '2029'}), ['manufacturing_year'])
        self.assertEqual(fields({'manufacturing_year': '1900'}), ['manufacturing_year'])

    def test_capacity_in_kilograms_is_not_flagged(self):
        # Поле — «мощность / грузоподъёмность»: 32 670 кг у автокрана законно.
        self.assertEqual(fields({'power_or_capacity': '32670', 'acquisition_cost_value': '12100000'}), [])

    def test_swapped_power_and_cost(self):
        # Реальный случай: мощность 12 100 000, стоимость 32 670.
        self.assertEqual(
            fields({'acquisition_cost_value': '32670', 'power_or_capacity': '12100000'}),
            ['acquisition_cost_value', 'power_or_capacity'],
        )
        self.assertEqual(fields({'acquisition_cost_value': '32670', 'acquisition_cost_currency': 'USD'}), [])

    def test_dfa_number_that_is_a_year(self):
        self.assertEqual(fields({'dfa_number': '2026'}), ['dfa_number'])
        self.assertEqual(fields({'dfa_number': 'ТС-2026'}), [])

    def test_inn_checksum(self):
        self.assertTrue(inn_checksum_ok('7707083893'))
        self.assertTrue(inn_checksum_ok('500100732259'))
        self.assertFalse(inn_checksum_ok('7707083894'))
        self.assertEqual(fields({'inn': '7707083894'}), ['inn'])
        self.assertEqual(fields({'inn': '12345'}), [])  # неполный ИНН — отдельная проверка формы


class PreviewPlausibilityTests(SimpleTestCase):
    def test_preview_warnings_for_request_and_objects(self):
        from .views import _plausibility_warnings

        parse_result = {'data': {'birth_date': '2061-02-20', 'dfa_number': 'ТС-20842', 'inn': '7707083893'}}
        insured_objects = [
            {'brand': 'SANY', 'model': 'STC250T5-5', 'acquisition_cost_value': '32670', 'acquisition_cost_currency': 'RUB',
             'power_or_capacity': '12100000', 'year': '2024'},
            {'brand': 'GWM', 'model': 'WEY 80', 'acquisition_cost_value': '7900000', 'acquisition_cost_currency': 'RUB',
             'year': '2026'},
        ]

        warnings = _plausibility_warnings(parse_result, insured_objects)

        self.assertEqual([warning['field'] for warning in warnings],
                         ['Дата рождения', 'Объект 1: Стоимость', 'Объект 1: Мощность'])
        self.assertTrue(all(warning['level'] == 'check' for warning in warnings))


class PlausibilityPageTests(TestCase):
    def test_hits_on_saved_v2_requests(self):
        from summaries.services import analytics_parser_edits

        InsuranceRequest.objects.create(
            client_name='ИП Тестов', inn='470401291828', parser_confidence=1.0, dfa_number='ТС-20834',
            birth_date=date(2061, 2, 20), additional_data={'parser_version': 'v2'},
        )
        InsuranceRequest.objects.create(
            client_name='ООО Норма', inn='7707083893', parser_confidence=1.0, dfa_number='ТС-20842',
            additional_data={'parser_version': 'v2'},
        )

        plausibility = analytics_parser_edits.build_payload(analytics_parser_edits.parse_filters({}))['plausibility']

        self.assertEqual((plausibility['total'], plausibility['requests']), (1, 1))
        self.assertEqual(plausibility['rows'][0]['field'], 'birth_date')
        self.assertEqual(plausibility['by_field'], [('Дата рождения', 1)])

"""Подсказка филиала по истории менеджера (analytics_redesign_2026_09, задача 6.7)."""
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from .branch_hint import apply_branch_hint, manager_key, suggest_branch
from .models import InsuranceRequest


def _request(manager_name, branch):
    return InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', manager_name=manager_name, branch=branch)


class ManagerKeyTests(SimpleTestCase):
    def test_same_person_written_differently(self):
        self.assertEqual(manager_key('Бурак А.'), manager_key('Бурак А.В. (менеджер УКО)'))
        self.assertEqual(manager_key('УВОЛ. Таралов Э.В. (менеджер УКО)'), ('таралов', 'э'))
        self.assertIsNone(manager_key(''))


class SuggestBranchTests(TestCase):
    def test_single_branch_history(self):
        _request('Бурак А.В. (менеджер УКО)', 'Санкт-Петербург')
        _request('Бурак А.', 'Санкт-Петербург')
        self.assertEqual(suggest_branch('Бурак А.В. (менеджер УКО)'), ('Санкт-Петербург', 2))

    def test_head_office_manager_with_many_branches_gets_no_hint(self):
        _request('Овдина Е.М.', 'Краснодар')
        _request('Овдина Е.М', 'Казань')
        _request('Овдина Е.М.', 'Краснодар')
        self.assertIsNone(suggest_branch('Овдина Е.М.'))

    def test_not_enough_history(self):
        _request('Новиков И.И.', 'Псков')
        self.assertIsNone(suggest_branch('Новиков И.И.'))

    def test_other_person_with_same_surname_is_not_mixed(self):
        _request('Иванов А.А.', 'Псков')
        _request('Иванов А.А.', 'Псков')
        _request('Иванов Б.Б.', 'Москва')
        self.assertEqual(suggest_branch('Иванов А.А.'), ('Псков', 2))

    def test_apply_hint_only_when_branch_missing(self):
        _request('Бурак А.', 'Санкт-Петербург')
        _request('Бурак А.', 'Санкт-Петербург')
        result = SimpleNamespace(data={'manager_name': 'Бурак А.В. (менеджер УКО)', 'branch': ''}, source_map={}, warnings=[])
        apply_branch_hint(result)
        self.assertEqual(result.data['branch'], 'Санкт-Петербург')
        self.assertEqual(result.source_map['branch'], 'история менеджера')
        self.assertEqual(result.warnings[0]['level'], 'check')

        recognized = SimpleNamespace(data={'manager_name': 'Бурак А.', 'branch': 'Москва'}, source_map={}, warnings=[])
        apply_branch_hint(recognized)
        self.assertEqual(recognized.data['branch'], 'Москва')
        self.assertEqual(recognized.warnings, [])

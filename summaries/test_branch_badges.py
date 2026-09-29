from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core.branch_badges import BRANCH_BADGES
from core.excel_utils import AVAILABLE_BRANCHES
from insurance_requests.models import InsuranceRequest
from summaries.templatetags.summary_extras import branch_badge


class BranchBadgeFilterTests(TestCase):
    """Значок филиала: буквы из ДФА + код региона в цвете филиала."""

    def test_every_known_branch_has_badge(self):
        self.assertEqual(set(BRANCH_BADGES), set(AVAILABLE_BRANCHES))

    def test_badge_with_name(self):
        html = branch_badge('Казань')
        self.assertIn('<b>КЗ</b><i>16</i>', html)
        self.assertIn('title="Казань · 16 регион"', html)
        self.assertTrue(html.endswith('Казань</span>'))

    def test_badge_only(self):
        html = branch_badge('Санкт-Петербург', 'only')
        self.assertIn('<b>СПБ</b><i>78</i>', html)
        self.assertNotIn('brb-wrap', html)

    def test_unknown_and_empty_branch(self):
        self.assertEqual(branch_badge('Тверь'), 'Тверь')
        self.assertEqual(branch_badge('Тверь', 'only'), '')
        self.assertEqual(branch_badge(''), '')
        self.assertEqual(branch_badge(None), '')

    def test_request_list_shows_badge_but_branch_tabs_do_not(self):
        user = User.objects.create_user(username='badge_user', password='pwd')
        user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.login(username='badge_user', password='pwd')
        InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', insurance_type='КАСКО',
                                        dfa_number='ТС-1-МСК', branch='Москва')
        response = self.client.get(reverse('insurance_requests:request_list'))
        content = response.content.decode()
        self.assertEqual(content.count('<b>МСК</b><i>77</i>'), 1)

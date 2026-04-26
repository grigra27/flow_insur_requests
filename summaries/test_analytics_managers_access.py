"""Тест доступа к разделу «Аналитика по сотрудникам».

Все новые URL должны быть admin-only: для не-админа — 403,
для админа — 200 (или 501 для экспорт-заглушки в Phase 0).
"""
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse


class ManagerAnalyticsAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')

        self.admin = User.objects.create_user(
            username='managers_admin',
            email='managers_admin@example.com',
            password='pwd',
        )
        self.admin.groups.add(admin_group)

        self.regular = User.objects.create_user(
            username='managers_user',
            email='managers_user@example.com',
            password='pwd',
        )
        self.regular.groups.add(user_group)

    def _admin_endpoints(self):
        return [
            (reverse('summaries:analytics_managers'), 200),
            (reverse('summaries:analytics_managers_compare'), 200),
            (reverse('summaries:analytics_managers_leaderboard'), 200),
            (
                reverse('summaries:analytics_manager_detail', kwargs={'user_id': self.admin.pk}),
                200,
            ),
            (reverse('summaries:export_analytics_managers_widget'), 200),
            (
                reverse('summaries:export_analytics_manager_detail', kwargs={'user_id': self.admin.pk}),
                200,
            ),
        ]

    def test_admin_can_access_all_endpoints(self):
        self.client.login(username='managers_admin', password='pwd')
        for url, expected in self._admin_endpoints():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, expected, msg=url)

    def test_regular_user_gets_403_on_all_endpoints(self):
        self.client.login(username='managers_user', password='pwd')
        for url, _ in self._admin_endpoints():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403, msg=url)

    def test_anonymous_redirected_to_login(self):
        for url, _ in self._admin_endpoints():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, (302, 301), msg=url)

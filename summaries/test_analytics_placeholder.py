from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse


class AnalyticsPlaceholderAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.user_group, _ = Group.objects.get_or_create(name='Пользователи')

        self.admin_user = User.objects.create_user(
            username='analytics_admin',
            email='analytics_admin@example.com',
            password='testpass123',
        )
        self.admin_user.groups.add(self.admin_group)

        self.regular_user = User.objects.create_user(
            username='analytics_user',
            email='analytics_user@example.com',
            password='testpass123',
        )
        self.regular_user.groups.add(self.user_group)

    def test_analytics_page_available_for_admin_group(self):
        self.client.login(username='analytics_admin', password='testpass123')

        response = self.client.get(reverse('summaries:analytics'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/analytics_placeholder.html')
        self.assertContains(response, 'Аналитика')

    def test_analytics_page_forbidden_for_non_admin_group(self):
        self.client.login(username='analytics_user', password='testpass123')

        response = self.client.get(reverse('summaries:analytics'))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'insurance_requests/access_denied.html')

    def test_analytics_companies_page_available_for_admin(self):
        self.client.login(username='analytics_admin', password='testpass123')

        response = self.client.get(reverse('summaries:analytics_insurance_companies'))

        self.assertEqual(response.status_code, 200)

    def test_analytics_companies_page_forbidden_for_regular_user(self):
        self.client.login(username='analytics_user', password='testpass123')

        response = self.client.get(reverse('summaries:analytics_insurance_companies'))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'insurance_requests/access_denied.html')

    def test_removed_statistics_pages_redirect_to_analytics(self):
        # Старая «Статистика» удалена (analytics_redesign_2026_09, задача 1.3).
        self.client.login(username='analytics_admin', password='testpass123')

        for path in ('/summaries/statistics/', '/summaries/statistics/export/'):
            with self.subTest(path=path):
                response = self.client.get(path, {'period': '30'})
                self.assertRedirects(
                    response, reverse('summaries:analytics'), fetch_redirect_response=False,
                )

    def test_summary_list_has_no_statistics_button(self):
        self.client.login(username='analytics_user', password='testpass123')

        response = self.client.get(reverse('summaries:summary_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/summaries/statistics/')

    def test_top_menu_item_visible_only_for_admin_group(self):
        analytics_url = reverse('summaries:analytics')
        analytics_offers_url = '/summaries/analytics/insurance-offers/'
        analytics_companies_url = reverse('summaries:analytics_insurance_companies')

        self.client.login(username='analytics_admin', password='testpass123')
        admin_response = self.client.get(reverse('summaries:summary_list'))
        self.assertContains(admin_response, analytics_url)
        self.assertNotContains(admin_response, analytics_offers_url)
        self.assertContains(admin_response, analytics_companies_url)
        self.assertContains(admin_response, 'Аналитика')

        self.client.logout()
        self.client.login(username='analytics_user', password='testpass123')
        user_response = self.client.get(reverse('summaries:summary_list'))
        self.assertNotContains(user_response, analytics_url)
        self.assertNotContains(user_response, analytics_offers_url)
        self.assertNotContains(user_response, analytics_companies_url)

    def test_analytics_page_uses_its_own_navigation_section(self):
        self.client.login(username='analytics_admin', password='testpass123')

        response = self.client.get(reverse('summaries:analytics'))

        self.assertEqual(response.status_code, 200)
        app_navigation = response.context['app_navigation']
        self.assertEqual(app_navigation['current_section']['label'], 'Аналитика')
        self.assertEqual(app_navigation['current_context_label'], 'Аналитика')

        section_labels = [item['label'] for item in app_navigation['section_items']]
        self.assertIn('Обзор аналитики', section_labels)
        self.assertNotIn('Страховые предложения', section_labels)
        self.assertIn('Страховые компании', section_labels)
        self.assertNotIn('Статистика', section_labels)
        self.assertNotIn('Справка', section_labels)
        self.assertNotContains(response, 'Своды / Аналитика')

    def test_manager_analytics_pages_do_not_activate_summaries_menu(self):
        self.client.login(username='analytics_admin', password='testpass123')

        urls = [
            reverse('summaries:analytics_managers'),
            reverse('summaries:analytics_manager_detail', kwargs={'user_id': self.admin_user.pk}),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                main_items = {
                    item['label']: item['active']
                    for item in response.context['app_navigation']['main_items']
                }
                self.assertFalse(main_items['Своды'])
                self.assertTrue(main_items['Аналитика'])
                self.assertEqual(
                    response.context['app_navigation']['current_section']['label'],
                    'Аналитика',
                )

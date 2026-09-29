from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


class RequestHelpPageTests(TestCase):
    """Справка по разделу «Заявки»: доступ, ссылки из списка, футера и справки по сводам."""

    def setUp(self):
        self.user = User.objects.create_user(username='help_user', password='pwd')
        self.user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])

    def test_regular_user_sees_help(self):
        self.client.login(username='help_user', password='pwd')
        response = self.client.get(reverse('insurance_requests:help'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'insurance_requests/help.html')
        self.assertContains(response, 'Справка по работе с заявками')
        self.assertContains(response, reverse('summaries:help'))

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('insurance_requests:help'))
        self.assertEqual(response.status_code, 302)

    def test_user_without_group_denied(self):
        User.objects.create_user(username='nogroup', password='pwd')
        self.client.login(username='nogroup', password='pwd')
        response = self.client.get(reverse('insurance_requests:help'))
        self.assertEqual(response.status_code, 403)

    def test_links_from_request_list_footer_and_summary_help(self):
        self.client.login(username='help_user', password='pwd')
        help_url = reverse('insurance_requests:help')
        list_page = self.client.get(reverse('insurance_requests:request_list'))
        self.assertContains(list_page, f'href="{help_url}"')
        self.assertContains(list_page, 'Справка по заявкам')
        self.assertContains(list_page, 'Справка по сводам')
        summary_help = self.client.get(reverse('summaries:help'))
        self.assertContains(summary_help, f'href="{help_url}"')

    def test_breadcrumbs(self):
        self.client.login(username='help_user', password='pwd')
        response = self.client.get(reverse('insurance_requests:help'))
        crumbs = [crumb['label'] for crumb in response.context['app_navigation']['breadcrumbs']]
        self.assertEqual(crumbs, ['Заявки', 'Справка'])

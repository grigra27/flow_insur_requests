from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from onlineservice.context_processors import WORK_COUNTERS_CACHE_KEY, _plural
from summaries.models import InsuranceSummary


def make_request(status, dfa):
    return InsuranceRequest.objects.create(
        client_name='ООО Тест', inn='7707083893', insurance_type='КАСКО', status=status, dfa_number=dfa,
    )


class FooterWorkCountersTests(TestCase):
    """Футер «Сейчас в работе»: счётчики по всей системе и ссылки в отфильтрованные списки."""

    def setUp(self):
        cache.delete(WORK_COUNTERS_CACHE_KEY)
        self.user = User.objects.create_user(username='footer_user', password='pwd')
        self.user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.login(username='footer_user', password='pwd')
        make_request('email_generated', 'ТС-1')
        make_request('email_generated', 'ТС-2')
        make_request('uploaded', 'ТС-3')
        InsuranceSummary.objects.create(request=make_request('emails_sent', 'ТС-4'), status='sent')

    def tearDown(self):
        cache.delete(WORK_COUNTERS_CACHE_KEY)

    def test_footer_shows_counters_with_links(self):
        response = self.client.get(reverse('summaries:summary_list'))
        items = {item['url'].split('status=')[1]: item for item in response.context['app_work']}
        self.assertEqual(items['email_generated']['count'], 2)
        self.assertEqual(items['email_generated']['label'], 'письма ждут отправки')
        self.assertEqual(items['sent']['count'], 1)
        self.assertEqual(items['sent']['label'], 'ждёт решения клиента')
        self.assertEqual(items['collecting']['count'], 0)
        self.assertContains(response, 'Сейчас в работе')
        self.assertContains(response, f'href="{reverse("insurance_requests:request_list")}?status=email_generated"')
        self.assertContains(response, f'href="{reverse("summaries:summary_list")}?status=sent"')

    def test_request_list_status_filter(self):
        response = self.client.get(reverse('insurance_requests:request_list'), {'status': 'email_generated'})
        self.assertEqual(response.context['total_requests'], 2)
        self.assertContains(response, 'Письмо сгенерировано')
        unknown = self.client.get(reverse('insurance_requests:request_list'), {'status': 'nope'})
        self.assertEqual(unknown.context['total_requests'], 4)
        self.assertEqual(unknown.context['current_status'], '')

    def test_plural(self):
        self.assertEqual([_plural(n, 'а', 'б', 'в') for n in (1, 2, 5, 11, 21, 22, 25)], ['а', 'б', 'в', 'в', 'а', 'б', 'в'])

    def test_anonymous_has_no_counters(self):
        self.client.logout()
        response = self.client.get(reverse('login'))
        self.assertNotContains(response, 'Сейчас в работе')

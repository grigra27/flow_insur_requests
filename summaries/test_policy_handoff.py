from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from .models import InsuranceOffer, InsuranceSummary, InsurerResponse, PolicyHandoffCode, PolicyVariantDecision


@override_settings(FLOW_HANDOFF_ENABLED=True, FLOW_POLIS_BASE_URL='http://127.0.0.1:8901',
                   FLOW_SERVICE_TOKEN='service-test-key', FLOW_HANDOFF_GROUP='')
class PolicyHandoffTests(TestCase):
    auth = {'HTTP_AUTHORIZATION': 'Bearer service-test-key'}

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('flow-manager')
        group, _ = Group.objects.get_or_create(name='Пользователи')
        cls.user.groups.add(group)
        cls.req = InsuranceRequest.objects.create(
            client_name='Тест', inn='1234567890', dfa_number='0001-А', insurance_type='КАСКО',
            insurance_period='1 год', branch='Москва', object_description='Автомобиль', manufacturing_year='2025',
        )
        cls.summary = InsuranceSummary.objects.create(
            request=cls.req, status='completed_accepted', selected_company='Абсолют',
            completed_at=timezone.now() - timedelta(days=60),
        )
        cls.offer = InsuranceOffer.objects.create(summary=cls.summary, company_name='Абсолют', insurance_year=1,
            insurance_sum=Decimal('1000'), premium_with_franchise_1=Decimal('100'))
        cls.start = reverse('summaries:policy_start', args=[cls.summary.pk])
        cls.lookup = reverse('flow_current', args=[cls.summary.pk])
        cls.variant = reverse('summaries:policy_variant', args=[cls.summary.pk])

    def setUp(self):
        self.client.force_login(self.user)
        self.service = Client(enforce_csrf_checks=True)

    def snapshot(self):
        return self.service.get(self.lookup, **self.auth).json()['snapshot']

    def code(self):
        return parse_qs(urlsplit(self.client.post(self.start)['Location']).query)['code'][0]

    def exchange(self, code, **auth):
        return self.service.post(reverse('flow_exchange'), {'code':code}, content_type='application/json', **auth)

    @override_settings(FLOW_HANDOFF_GROUP='Пилот оформления')
    @patch('summaries.services.policy_handoff.requests.get')
    def test_ordinary_employee_pilot_access_is_independent_of_destination_account(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {'links': [], 'mode': None, 'total': 0}
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        url = reverse('summaries:summary_detail', args=[self.summary.pk])
        self.assertNotContains(self.client.get(url), 'Создать полис')
        self.assertEqual(self.client.post(self.start).status_code, 403)

        pilot = Group.objects.create(name='Пилот оформления')
        self.user.groups.add(pilot)
        self.assertContains(self.client.get(url), 'Создать полис')
        # The destination exchanges an opaque code without a browser session or user identifiers.
        code = self.code()
        self.assertEqual(PolicyHandoffCode.objects.get().issued_by, self.user)
        reply = self.exchange(code, **self.auth)
        self.assertEqual(reply.status_code, 200)
        self.assertNotIn(self.user.username, reply.content.decode())
        snapshot = reply.json()['snapshot']
        self.assertFalse({'user', 'user_id', 'username', 'issued_by'} & snapshot.keys())

        pending = self.code()
        self.user.groups.remove(pilot)
        self.assertEqual(self.exchange(pending, **self.auth).status_code, 403)

    def test_private_one_time_exchange_and_expiry(self):
        code = self.code()
        self.assertNotEqual(code, PolicyHandoffCode.objects.get().digest)
        self.assertEqual(self.service.get(self.lookup).status_code, 401)
        self.assertEqual(self.exchange(code).status_code, 401)
        ok = self.exchange(code, **self.auth)
        self.assertEqual(ok.status_code, 200)
        self.assertIn('no-store', ok['Cache-Control'])
        snapshot = ok.json()['snapshot']
        self.assertEqual(snapshot['offers'], [{'year': 1, 'premium': '100.00', 'franchise': '0.00',
                                               'insurance_sum': '1000.00', 'installments': 1}])
        self.assertEqual(snapshot['property_year'], 2025)
        self.assertEqual(self.exchange(code, **self.auth).status_code, 410)
        expired = self.code()
        PolicyHandoffCode.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.exchange(expired, **self.auth).status_code, 410)

    def test_legacy_choice_audited_without_changing_completion_date(self):
        InsuranceOffer.objects.filter(pk=self.offer.pk).update(premium_with_franchise_2=90,
            franchise_2=10, installment_variant_2=True, payments_per_year_variant_2=4)
        old = self.snapshot()
        self.assertIsNone(old['variant'])
        self.assertEqual(old['offers'], [])
        start = self.client.post(self.start)
        self.assertRedirects(start, self.variant, fetch_redirect_response=False)
        self.assertFalse(PolicyHandoffCode.objects.exists())
        revision = self.client.get(start['Location']).context['snapshot']['revision']
        InsuranceOffer.objects.filter(pk=self.offer.pk).update(premium_with_franchise_2=88)
        self.assertEqual(self.client.post(self.variant, {'variant':2, 'revision':revision}).status_code, 409)
        self.assertFalse(PolicyVariantDecision.objects.exists())
        response = self.client.post(self.variant, {'variant':2, 'revision':self.snapshot()['revision']})
        location = urlsplit(response['Location'])
        self.assertEqual(location.path, '/flow/from-zs/')
        code = parse_qs(location.query)['code'][0]
        accepted = self.exchange(code, **self.auth).json()['snapshot']
        self.assertEqual((accepted['variant'],accepted['offers'][0]['premium'],accepted['offers'][0]['installments']), (2,'88.00',4))
        self.assertEqual(PolicyVariantDecision.objects.get().user, self.user)
        self.assertEqual(InsuranceSummary.objects.get(pk=self.summary.pk).completed_at, self.summary.completed_at)

    @patch('summaries.services.policy_handoff.requests.post')
    def test_registries_show_all_linked_policies_for_any_employee(self, post):
        historical = InsuranceRequest.objects.create(client_name='Другой клиент', dfa_number='ДФА-2')
        InsuranceSummary.objects.create(request=historical, status='completed_accepted', selected_company='Абсолют')
        drafts = InsuranceRequest.objects.bulk_create([InsuranceRequest(client_name=f'Черновик {i}') for i in range(30)])
        InsuranceSummary.objects.bulk_create([InsuranceSummary(request=draft) for draft in drafts])
        # Для полиса, сохранённого сегодня и вступающего в силу завтра,
        # реестр сразу возвращает связь с in_force=False.
        issued = {'position': 1, 'policy_id': 7, 'policy_number': 'П-7', 'in_force': False}
        linked = {'mode': 'separate', 'total': 18, 'links': [issued]}
        def reply(url, *, json, **kwargs):
            self.assertEqual(url, 'http://127.0.0.1:8901/internal/flow/v1/summaries/links/')
            statuses = {str(pk): linked if pk == self.summary.pk else {'mode': None, 'total': 0, 'links': []}
                        for pk in json['summary_ids']}
            return Mock(status_code=200, json=lambda: {'summaries': statuses})
        post.side_effect = reply
        summary_page = self.client.get(reverse('summaries:summary_list'), {'page': 2})
        post.assert_called_once()
        page_ids = [s.pk for s in summary_page.context['summaries']]
        self.assertEqual(post.call_args.kwargs['json']['summary_ids'], page_ids)
        self.assertEqual(len(page_ids), 2)
        post.reset_mock()
        deals_page = self.client.get(reverse('summaries:deal_list'))
        post.assert_called_once()
        self.assertCountEqual(post.call_args.kwargs['json']['summary_ids'], page_ids)
        direct_url = 'http://127.0.0.1:8901/policies/7/'
        deal_url = reverse('summaries:deal_summary', args=[self.summary.pk])
        self.assertContains(deals_page, f'<a class="dl-number" href="{deal_url}" title="ИНН {self.req.inn}">{self.req.get_display_name()}</a>', html=True)
        for page in (summary_page, deals_page):
            self.assertContains(page, f'<a class="policy-list-link" href="{direct_url}">Полис <span aria-hidden="true">↗</span></a>', html=True)
            self.assertContains(page, 'class="policy-list-link"', count=1)
            self.assertNotContains(page, 'Проверить по ДФА')
            self.assertNotContains(page, self.start)
        linked['links'].extend([
            {'position': 2, 'policy_id': 8, 'policy_number': 'П-8', 'in_force': True},
            {'position': 3, 'policy_id': 9, 'policy_number': 'П-9', 'in_force': False},
        ])
        with self.settings(FLOW_HANDOFF_GROUP='Другая группа', FLOW_HANDOFF_ENABLED=False):
            for route, params in [('summary_list', {'page': 2}), ('deal_list', {})]:
                page = self.client.get(reverse('summaries:' + route), params)
                group_url = f'http://127.0.0.1:8901/policies/by-summary/{self.summary.pk}/'
                self.assertContains(page, f'<a class="policy-list-link" href="{group_url}">Полисы (3) <span aria-hidden="true">↗</span></a>', html=True)
        # Прежний API отдаёт достоверные связи без поля in_force.
        linked['links'] = [{'position': 1, 'policy_id': 7, 'policy_number': 'П-7'}]
        for route, params in [('summary_list', {'page': 2}), ('deal_list', {})]:
            page = self.client.get(reverse('summaries:' + route), params)
            self.assertContains(page, f'<a class="policy-list-link" href="{direct_url}">Полис <span aria-hidden="true">↗</span></a>', html=True)
        post.side_effect = None
        post.return_value = Mock(status_code=503)
        unavailable = self.client.get(reverse('summaries:deal_list'))
        self.assertNotContains(unavailable, 'class="policy-list-link"')
        self.assertNotContains(unavailable, 'Проверить по ДФА')

    def test_revision_tracks_selected_offer_and_request(self):
        initial = self.snapshot()['revision']
        InsuranceOffer.objects.filter(pk=self.offer.pk).update(insurance_sum=1111)
        changed = self.snapshot()['revision']
        self.assertNotEqual(initial, changed)
        InsuranceRequest.objects.filter(pk=self.req.pk).update(manager_name='Другой менеджер')
        self.assertNotEqual(changed, self.snapshot()['revision'])

    def test_multiyear_snapshot_uses_winner_and_separate_costs(self):
        # Вариант 2 не покрывает второй год и не может считаться принятым.
        InsuranceOffer.objects.filter(pk=self.offer.pk).update(premium_with_franchise_2=90)
        InsuranceOffer.objects.create(summary=self.summary, company_name='Абсолют', insurance_year=2,
                                     insurance_sum=900, premium_with_franchise_1=80)
        InsuranceOffer.objects.create(summary=self.summary, company_name='ВСК', insurance_year=1,
                                     insurance_sum=1000, premium_with_franchise_1=60)
        InsurerResponse.objects.update_or_create(summary=self.summary, company_name='Абсолют',
            defaults={'transport_cost':500, 'smr_status':'separate', 'smr_cost':100})
        snapshot = self.snapshot()
        self.assertEqual(snapshot['variant'], 1)
        self.assertEqual([row['premium'] for row in snapshot['offers']], ['100.00', '80.00'])
        self.assertEqual([row['year'] for row in snapshot['offers']], [1, 2])
        self.assertEqual(snapshot['extras']['transport_cost'], '500.00')
        self.assertTrue(snapshot['extras']['smr_status_display'])
        self.assertNotEqual(snapshot['extras']['smr_status_display'], 'separate')

    def test_revoked_acceptance_and_access(self):
        code = self.code()
        InsuranceSummary.objects.filter(pk=self.summary.pk).update(status='collecting')
        self.assertEqual(self.exchange(code, **self.auth).status_code, 409)
        self.assertEqual(self.client.post(self.start).status_code, 409)
        self.assertEqual(self.service.get(self.lookup, **self.auth).status_code, 409)
        with self.settings(FLOW_HANDOFF_GROUP='Пилот'):
            self.assertEqual(self.client.post(self.start).status_code, 403)
        with self.settings(FLOW_HANDOFF_ENABLED=False):
            self.assertEqual(self.service.get(self.lookup, **self.auth).status_code, 404)
        self.assertEqual(Client().post(self.start).status_code, 302)
        external = Client(enforce_csrf_checks=True)
        external.force_login(self.user)
        self.assertEqual(external.post(self.start).status_code, 403)

    @patch('summaries.services.policy_handoff.requests.get')
    def test_ui_distinguishes_incomplete_complete_and_unavailable(self, get):
        url = reverse('summaries:summary_detail', args=[self.summary.pk])
        get.return_value = Mock(status_code=200)
        data = {'links':[], 'mode':None,'total':0}
        get.return_value.json.return_value = data
        self.assertContains(self.client.get(url), 'Создать полис')
        InsuranceRequest.objects.filter(pk=self.req.pk).update(source_object_count=18)
        self.assertContains(self.client.get(url), 'Оформлено 0 из 18')
        data.update(mode='separate', total=4)
        self.assertContains(self.client.get(url), 'Оформлено 0 из 18')
        data.update(mode='separate', total=18, links=[
            {'policy_number': f'Тест-{i}', 'policy_id': i, 'position': i} for i in range(1, 16)
        ])
        partial = self.client.get(url)
        self.assertContains(partial, 'Оформлено 15 из 18')
        self.assertContains(partial, 'Осталось оформить 3 объекта.')
        self.assertContains(partial, 'Оформить оставшиеся 3')
        self.assertContains(partial, 'Открыть 15 полисов')
        group_url = f'http://127.0.0.1:8901/policies/by-summary/{self.summary.pk}/'
        self.assertContains(partial, f'href="{group_url}"')
        with self.settings(FLOW_HANDOFF_GROUP='Другая группа'):
            for route in ('summary_detail', 'deal_summary'):
                reader = self.client.get(reverse('summaries:' + route, args=[self.summary.pk]))
                self.assertContains(reader, f'href="{group_url}"')
                self.assertNotContains(reader, self.start)
        data.update(links=[{'policy_number':'Тест-78','policy_id':3,'position':1}],mode='separate',total=2)
        split = self.client.get(url)
        self.assertContains(split, 'Оформить последний объект')
        self.assertContains(split, 'Оформлено 1 из 2')
        self.assertContains(split, 'href="http://127.0.0.1:8901/policies/3/"')
        data['mode'] = 'common'
        common = self.client.get(url)
        self.assertContains(common, 'Общий полис на все объекты')
        self.assertContains(common, 'Полис № Тест-78')
        self.assertContains(common, 'Открыть полис')
        self.assertNotContains(common, self.start)
        data['mode'] = 'separate'
        with self.settings(FLOW_HANDOFF_ENABLED=False):
            disabled = self.client.get(url)
            self.assertContains(disabled, 'href="http://127.0.0.1:8901/policies/3/"')
            self.assertNotContains(disabled, self.start)
        InsuranceSummary.objects.filter(pk=self.summary.pk).update(status='collecting',selected_company=None)
        response = self.client.get(url)
        self.assertContains(response, 'href="http://127.0.0.1:8901/policies/3/"')
        self.assertNotContains(response,self.start)
        get.return_value.status_code=503
        unavailable = self.client.get(url)
        self.assertContains(unavailable,'Не удалось проверить связь')
        self.assertNotContains(unavailable, self.start)

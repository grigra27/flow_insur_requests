from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from insurance_requests.middleware import AuthenticationMiddleware
from insurance_requests.models import InsuranceRequest
from .models import InsuranceSummary
from .services.policy_search import search_summaries


@override_settings(FLOW_HANDOFF_ENABLED=True, FLOW_SERVICE_TOKEN='search-test-key')
class PolicySearchTests(TestCase):
    auth = {'HTTP_AUTHORIZATION': 'Bearer search-test-key'}

    def setUp(self):
        self.url = reverse('flow_summary_search')
        self.service = Client(enforce_csrf_checks=True)

    def source(self, dfa='ТС-12345/1', *, inn='1234567890', name='Пример',
               status='completed_accepted', company='Абсолют', age=0, **fields):
        source = InsuranceRequest.objects.create(
            dfa_number=dfa, inn=inn, client_name=name, insurance_type='КАСКО',
            object_description='Тестовый объект', **fields,
        )
        return InsuranceSummary.objects.create(
            request=source, status=status, selected_company=company,
            completed_at=timezone.now() - timedelta(days=age),
        )

    def find(self, **query):
        reply = self.service.get(self.url, query, **self.auth)
        self.assertEqual(reply.status_code, 200, reply.content)
        return reply.json()

    def test_only_the_service_can_search_and_reads_do_not_create_handoff(self):
        self.source()
        self.assertEqual(self.service.get(self.url, {'dfa': '12345-1'}).status_code, 401)
        self.assertEqual(self.service.get(self.url, HTTP_AUTHORIZATION='Bearer bad').status_code, 401)
        self.service.force_login(User.objects.create_superuser('admin', password='test-only-password'))
        self.assertEqual(self.service.get(self.url, {'dfa': '12345-1'}).status_code, 401)
        self.assertEqual(self.service.post(self.url, {}, **self.auth).status_code, 403)
        self.assertEqual(Client().post(self.url, {}, **self.auth).status_code, 405)
        reply = self.service.get(self.url, {'dfa': '12345-1'}, **self.auth)
        self.assertEqual(reply.status_code, 200)
        self.assertIn('no-store', reply['Cache-Control'])
        from .models import PolicyHandoffCode
        self.assertFalse(PolicyHandoffCode.objects.exists())

    @override_settings(FLOW_HANDOFF_ENABLED=False)
    def test_disabled_integration_returns_not_found(self):
        self.assertEqual(self.service.get(self.url, **self.auth).status_code, 404)

    def test_middleware_only_exempts_the_exact_service_route(self):
        middleware = AuthenticationMiddleware(lambda request: None)
        self.assertTrue(middleware._is_public_url(self.url))
        self.assertFalse(middleware._is_public_url(self.url + 'anything'))
        self.assertFalse(middleware._is_public_url('/internal/flow/v1/summaries/other/'))

    def test_accepted_sources_only_and_sparse_old_acceptances_are_searchable(self):
        eligible = self.source()
        self.source(status='collecting')
        self.source(status='completed_rejected')
        self.source(company='')
        self.source(company=None)
        result = self.find(dfa='12345-1')['results']
        self.assertEqual([row['summary_id'] for row in result], [eligible.pk])
        self.assertFalse(eligible.offers.exists())

    def test_structural_matching_preserves_suffix_boundaries_and_leading_zeroes(self):
        full = self.source('ТС-12345/1')
        exact = self.source('12345-1')
        base = self.source('TS-12345')
        for unrelated in ('12345-2', '123451', '1234-51', '012345-1', '12345-01',
                          '12345/1/2026', 'ТС-12345/1-X', 'ПРЕДВАРИТЕЛЬНЫЙ-12345-1'):
            self.source(unrelated)
        result = self.find(dfa='12345-1')['results']
        self.assertEqual([row['summary_id'] for row in result], [exact.pk, full.pk, base.pk])
        self.assertEqual([row['match_kind'] for row in result], ['exact', 'structure', 'base'])
        self.assertEqual(result[1]['dfa_number'], 'ТС-12345/1')

    def test_missing_suffix_candidates_are_distinct_from_different_suffixes(self):
        self.source('TS-12345-1')
        self.source('ТС-12345/2')
        results = self.find(dfa='12345')['results']
        self.assertEqual(len(results), 2)
        self.assertEqual({row['match_kind'] for row in results}, {'base'})

    def test_same_client_promotes_equal_quality_and_explains_dfa_mismatch(self):
        other_client = self.source('ТС-12345/1', inn='0987654321')
        same_client = self.source('TS-12345/1', age=2)
        different_suffix = self.source('12345-2')
        result = self.find(dfa='12345-1', inn='1234567890')['results']
        self.assertEqual([row['summary_id'] for row in result],
                         [same_client.pk, other_client.pk, different_suffix.pk])
        self.assertIn('Совпал ИНН', result[0]['match_label'])
        self.assertEqual(result[2]['match_kind'], 'client')
        self.assertIn('проверьте номер ДФА', result[2]['match_label'])

    def test_empty_and_preliminary_dfa_do_not_dump_sources(self):
        self.source('ПРЕДВАРИТЕЛЬНЫЙ-12345')
        self.source()
        self.assertEqual(self.find(), {'results': [], 'page': 1, 'has_next': False})
        self.assertEqual(self.find(dfa='ПРЕДВАРИТЕЛЬНЫЙ-12345')['results'], [])
        self.assertEqual(self.find(dfa='ТС')['results'], [])

    def test_final_dfa_group_hints_are_bounded_filtered_and_prioritized(self):
        exact = self.source('12345-1')
        hinted = self.source('Предварительный', inn='0987654321', age=10)
        rejected = self.source(status='completed_rejected')
        result = self.find(dfa='12345-1', summary_ids=f'{hinted.pk},{rejected.pk}')['results']
        self.assertEqual([row['summary_id'] for row in result], [hinted.pk, exact.pk])
        self.assertIn('группе ДФА', result[0]['match_label'])
        self.assertEqual(self.find(summary_ids=str(hinted.pk))['results'][0]['summary_id'], hinted.pk)
        # Policies derives hints from the manual final DFA, unknown to ZS.
        self.assertEqual(self.find(q='88888-1', summary_ids=str(hinted.pk))['results'][0]['summary_id'], hinted.pk)

    def test_manual_query_can_find_source_outside_initial_suggestions(self):
        wanted = self.source('ТС-54321/2', name='Другой клиент', inn='0987654321')
        self.source()
        for query in ('Другой клиент', '0987654321', '54321-2', str(wanted.pk)):
            with self.subTest(query=query):
                rows = self.find(dfa='12345-1', q=query)['results']
                self.assertIn(wanted.pk, [row['summary_id'] for row in rows])
        self.assertIn(wanted.pk, [row['summary_id'] for row in self.find(q=str(wanted.request_id))['results']])
        self.assertEqual(self.find(q='9' * 100)['results'], [])

    def test_source_payload_disambiguates_batch_and_same_object_group_without_offers(self):
        source = self.source(source_object_count=18, item_no=2, item_count=3, brand='Марка', model='Модель')
        with self.assertNumQueries(1):
            row = search_summaries(dfa='12345-1')['results'][0]
        self.assertEqual(row['request_id'], source.request_id)
        self.assertEqual((row['source_object_count'], row['item_no'], row['item_count']), (18, 2, 3))
        self.assertEqual(row['property_description'], 'Марка Модель')
        self.assertEqual(row['selected_company'], 'Абсолют')
        self.assertNotIn('offers', row)

    def test_pagination_has_no_duplicates_and_is_stable_with_equal_dates(self):
        rows = [self.source('ТС-12345/1') for _ in range(23)]
        InsuranceSummary.objects.update(completed_at=timezone.now())
        first, second = self.find(dfa='12345-1'), self.find(dfa='12345-1', page=2)
        self.assertTrue(first['has_next'])
        self.assertFalse(second['has_next'])
        self.assertEqual((len(first['results']), len(second['results'])), (20, 3))
        self.assertEqual(
            [row['summary_id'] for page in (first, second) for row in page['results']],
            [source.pk for source in reversed(rows)],
        )
        self.assertEqual(self.find(dfa='12345-1', page=3)['results'], [])

    def test_invalid_and_oversized_parameters(self):
        for query in ({'page': '0'}, {'page': '-1'}, {'page': '1.2'}, {'page': '10001'},
                      {'page': '١'}, {'page': '9' * 100}, {'q': 'x' * 101},
                      {'dfa': '1' * 101}, {'inn': '1' * 13}, {'inn': '12a'},
                      {'q': 'line\nbreak'}, {'q': ['one', 'two']}, {'page': ['1', '2']},
                      {'summary_ids': '1,1'}, {'summary_ids': '0'}, {'summary_ids': 'x'},
                      {'summary_ids': str(2**63)}, {'summary_ids': ','.join(str(i) for i in range(1, 22))},
                      {'summary_ids': ['1', '2']}, {'summary_ids': '1,'}):
            with self.subTest(query=query):
                reply = self.service.get(self.url, query, **self.auth)
                self.assertEqual(reply.status_code, 400)
        self.assertEqual(self.service.get(self.url + '?unknown=' + 'x' * 4096, **self.auth).status_code, 400)

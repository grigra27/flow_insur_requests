"""Тесты дашборда ручных правок распознавания (фаза 4)."""
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest, RequestFieldEdit
from summaries.services import analytics_parser_edits as service


def _make_request(branch='Казань', confidence=0.8, edits_count=0, created_by=None):
    return InsuranceRequest.objects.create(
        client_name='ООО Тест', inn='1', branch=branch,
        parser_confidence=confidence, manual_edits_count=edits_count,
        created_by=created_by, additional_data={'parser_version': 'v2'},
    )


class AnalyticsParserEditsServiceTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username='op', first_name='Иван', last_name='Петров', password='x'
        )

    def test_aggregates_counts_and_shares(self):
        req_a = _make_request(branch='Казань', confidence=0.7, edits_count=2,
                              created_by=self.operator)
        _make_request(branch='Москва', confidence=0.95, edits_count=0)
        RequestFieldEdit.objects.create(
            request=req_a, scope='common', field_name='client_name',
            field_label='Клиент', original_value='A', modified_value='B',
            edit_type='changed',
        )
        RequestFieldEdit.objects.create(
            request=req_a, scope='object', field_name='brand',
            field_label='Марка', original_value='', modified_value='LADA',
            edit_type='filled',
        )

        payload = service.build_payload(service.parse_filters({}))
        totals = payload['totals']
        self.assertEqual(totals['total_v2'], 2)
        self.assertEqual(totals['requests_with_edits'], 1)
        self.assertEqual(totals['edited_share_percent'], 50.0)
        self.assertEqual(totals['total_edits'], 2)
        # Средняя уверенность в процентах.
        self.assertAlmostEqual(totals['avg_confidence_percent'], 82.5, places=1)
        self.assertAlmostEqual(totals['avg_confidence_with_edits_percent'], 70.0, places=1)
        self.assertAlmostEqual(totals['avg_confidence_without_edits_percent'], 95.0, places=1)

    def test_breakdowns(self):
        req = _make_request(branch='Казань', edits_count=1, created_by=self.operator)
        RequestFieldEdit.objects.create(
            request=req, scope='common', field_name='inn', field_label='ИНН',
            original_value='1', modified_value='2', edit_type='changed',
        )
        RequestFieldEdit.objects.create(
            request=req, scope='common', field_name='inn', field_label='ИНН',
            original_value='3', modified_value='4', edit_type='changed',
        )
        payload = service.build_payload(service.parse_filters({}))

        top = {row['field_name']: row['count'] for row in payload['top_fields']}
        self.assertEqual(top['inn'], 2)
        by_branch = {row['branch']: row['count'] for row in payload['by_branch']}
        self.assertEqual(by_branch['Казань'], 2)
        by_operator = {row['operator']: row['count'] for row in payload['by_operator']}
        self.assertEqual(by_operator['Петров Иван'], 2)
        by_type = {row['type']: row['count'] for row in payload['by_type']}
        self.assertEqual(by_type['changed'], 2)

    def test_empty_period_is_safe(self):
        payload = service.build_payload(service.parse_filters({'days': '5'}))
        self.assertEqual(payload['totals']['total_v2'], 0)
        self.assertEqual(payload['totals']['edited_share_percent'], 0.0)
        self.assertEqual(payload['top_fields'], [])

    def test_top_field_accuracy(self):
        # inn правили в 1 из 2 V2-заявок → error_rate 50%.
        req = _make_request(edits_count=2, created_by=self.operator)
        _make_request(edits_count=0)
        RequestFieldEdit.objects.create(
            request=req, scope='common', field_name='inn', field_label='ИНН',
            original_value='1', modified_value='2', edit_type='changed',
        )
        RequestFieldEdit.objects.create(
            request=req, scope='common', field_name='inn', field_label='ИНН',
            original_value='2', modified_value='3', edit_type='changed',
        )
        payload = service.build_payload(service.parse_filters({}))
        inn = next(r for r in payload['top_fields'] if r['field_name'] == 'inn')
        self.assertEqual(inn['count'], 2)        # всего правок
        self.assertEqual(inn['requests'], 1)     # затронута 1 заявка
        self.assertEqual(inn['error_rate_percent'], 50.0)

    def test_segmentation_by_template(self):
        InsuranceRequest.objects.create(
            client_name='c', inn='1', parser_confidence=0.8, manual_edits_count=3,
            additional_data={'parser_version': 'v2', 'application_format': 'casco_equipment',
                             'application_type': 'legal_entity'},
        )
        InsuranceRequest.objects.create(
            client_name='c', inn='2', parser_confidence=0.9, manual_edits_count=0,
            additional_data={'parser_version': 'v2', 'application_format': 'property',
                             'application_type': 'individual_entrepreneur'},
        )
        payload = service.build_payload(service.parse_filters({}))
        by_format = {r['value']: r for r in payload['by_format']}
        self.assertEqual(by_format['casco_equipment']['error_rate_percent'], 100.0)
        self.assertEqual(by_format['casco_equipment']['avg_edits'], 3.0)
        self.assertEqual(by_format['property']['error_rate_percent'], 0.0)
        by_type = {r['value']: r for r in payload['by_app_type']}
        self.assertEqual(by_type['legal_entity']['requests'], 1)

    def test_field_drilldown_examples(self):
        req = _make_request(edits_count=1, created_by=self.operator)
        RequestFieldEdit.objects.create(
            request=req, scope='object', field_name='brand', field_label='Марка',
            original_value='ЛАДА', modified_value='LADA', edit_type='changed',
        )
        payload = service.build_payload(service.parse_filters({'field': 'brand'}))
        self.assertEqual(payload['selected_field'], 'brand')
        self.assertEqual(payload['selected_field_label'], 'Марка')
        self.assertEqual(len(payload['field_examples']), 1)
        example = payload['field_examples'][0]
        self.assertEqual(example['original_value'], 'ЛАДА')
        self.assertEqual(example['modified_value'], 'LADA')
        self.assertEqual(example['request_id'], req.id)


class AnalyticsParserEditsAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.admin = User.objects.create_user(username='a', password='x')
        self.admin.groups.add(admin_group)
        self.regular = User.objects.create_user(username='u', password='x')
        self.regular.groups.add(user_group)

    def test_admin_can_open_dashboard(self):
        self.client.login(username='a', password='x')
        response = self.client.get(reverse('summaries:analytics_parser_edits'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/analytics_parser_edits.html')
        self.assertContains(response, 'Ручные правки распознавания')

    def test_regular_user_forbidden(self):
        self.client.login(username='u', password='x')
        response = self.client.get(reverse('summaries:analytics_parser_edits'))
        self.assertEqual(response.status_code, 403)

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


class ParserVersionTests(TestCase):
    """Версия парсера и коммит сборки на заявке (analytics_redesign_2026_09, задача 5.2)."""

    def _request(self, version, edits, build=None):
        parser_v2 = {'version': version}
        if build:
            parser_v2['build'] = build
        return InsuranceRequest.objects.create(
            client_name='ООО Тест', inn='1', parser_confidence=1.0, manual_edits_count=edits,
            additional_data={'parser_version': 'v2', 'parser_v2': parser_v2},
        )

    def test_share_without_edits_by_version(self):
        self._request('2.0.0', 2)
        self._request('2.0.0', 0)
        self._request('2.1.0', 0, build='abc123')
        self._request('2.1.0', 0, build='def456')

        rows = {row['version']: row for row in service.build_payload(service.parse_filters({}))['by_version']}

        self.assertEqual((rows['2.0.0']['requests'], rows['2.0.0']['clean_percent'], rows['2.0.0']['builds']), (2, 50.0, 0))
        self.assertEqual((rows['2.1.0']['requests'], rows['2.1.0']['clean_percent'], rows['2.1.0']['builds']), (2, 100.0, 2))

    def test_new_request_stores_parser_version_and_build(self):
        from unittest import mock

        from insurance_requests.parsers.excel_v2.parser import PARSER_V2_VERSION
        from insurance_requests.views import _build_parser_v2_additional_data

        user = User.objects.create_user(username='uploader', password='x')
        draft = {'parse_result': {'parser_version': PARSER_V2_VERSION, 'data': {}}, 'file_name': 'f.xlsx'}
        with mock.patch.dict('os.environ', {'APP_BUILD_SHA': '0123456789abcdef'}):
            data = _build_parser_v2_additional_data(draft, {}, user)

        self.assertEqual(data['parser_v2']['version'], PARSER_V2_VERSION)
        self.assertEqual(data['parser_v2']['build'], '0123456789ab')


class EditReasonsTests(TestCase):
    """Правки по причинам и прогноз доли заявок без правок (задача 5.3)."""

    def _request(self, file_name='Заявка ТС 20842.xlsx', edits=()):
        request = InsuranceRequest.objects.create(
            client_name='ООО Тест', inn='1', parser_confidence=1.0, manual_edits_count=len(edits),
            additional_data={'parser_version': 'v2', 'parser_v2': {'version': '2.0.0', 'source_file_name': file_name}},
        )
        for field_name in edits:
            RequestFieldEdit.objects.create(
                request=request, scope='common', field_name=field_name, field_label=field_name,
                original_value='a', modified_value='b', edit_type='changed',
            )
        return request

    def test_classify(self):
        from summaries.services import parser_edit_reasons as reasons

        self.assertEqual(reasons.classify('insurance_period'), 'period')
        self.assertEqual(reasons.classify('has_installment'), 'payment')
        self.assertEqual(reasons.classify('model'), 'object')
        self.assertEqual(reasons.classify('guard_conditions'), 'other')
        # «Изъятое» по имени файла перекрывает поле.
        self.assertEqual(reasons.classify('insurance_period', 'Заявка 19818 - ИЗЪЯТОЕ.xls'), 'seized')

    def test_reasons_and_forecast(self):
        self._request(edits=['insurance_period', 'has_autostart'])        # только известные ошибки
        self._request(edits=['has_autostart', 'guard_conditions'])        # есть «прочее»
        self._request(file_name='Заявка 19818 - ИЗЪЯТОЕ.xls', edits=['client_name', 'inn'])
        self._request()                                                   # без правок

        payload = service.build_payload(service.parse_filters({}))
        forecast = payload['forecast']
        self.assertEqual((forecast['total'], forecast['clean_now']), (4, 1))
        self.assertEqual(forecast['clean_now_percent'], 25.0)
        self.assertEqual(forecast['clean_after_parser_percent'], 50.0)   # + первая заявка
        self.assertEqual(forecast['clean_after_all_percent'], 75.0)      # + «Изъятое»
        self.assertEqual(forecast['seized_requests'], 1)

        rows = {row['key']: row for row in payload['by_reason']}
        self.assertEqual((rows['autostart']['requests'], rows['autostart']['task']), (2, '6.2'))
        self.assertEqual((rows['seized']['edits'], rows['seized']['kind']), (2, 'scenario'))
        self.assertEqual(rows['other']['edits'], 1)
        self.assertEqual(payload['by_reason'][0]['kind'], 'parser')      # сначала ошибки парсера

    def test_post_creation_page_groups_by_reason(self):
        from summaries.services import analytics_post_creation

        request = self._request()
        RequestFieldEdit.objects.create(
            request=request, scope='post', field_name='dfa_number', field_label='Номер ДФА',
            original_value='ТС-20842', modified_value='ТС-20842-ГА-МН', edit_type='changed',
        )
        payload = analytics_post_creation.build_payload(analytics_post_creation.parse_filters({}))
        self.assertEqual([(row['key'], row['edits']) for row in payload['by_reason']], [('dfa', 1)])

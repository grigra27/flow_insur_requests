"""Тесты дашборда правок после создания (фаза 2: контроль операторов)."""
import datetime as dt
import json

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest, RequestFieldEdit
from summaries.services import analytics_post_creation as service


def _make_v2_request(**kwargs):
    defaults = dict(
        client_name='ООО Тест', inn='1', parser_confidence=0.8,
        additional_data={'parser_version': 'v2'},
    )
    defaults.update(kwargs)
    return InsuranceRequest.objects.create(**defaults)


def _crud_update(req, changed_fields, *, user, when):
    from easyaudit.models import CRUDEvent
    ct = ContentType.objects.get_for_model(InsuranceRequest)
    ev = CRUDEvent.objects.create(
        event_type=CRUDEvent.UPDATE, object_id=str(req.pk), content_type=ct,
        object_repr='req', changed_fields=json.dumps(changed_fields), user=user,
    )
    CRUDEvent.objects.filter(pk=ev.pk).update(datetime=when)
    return ev


class PostCreationServiceTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('op', last_name='Петров', first_name='Иван')

    def test_aggregates_and_suspected(self):
        req = _make_v2_request(created_by=self.operator)
        # Поле inn правили на входе — НЕ подозрение, даже если меняли позже.
        RequestFieldEdit.objects.create(
            request=req, scope='common', field_name='inn', field_label='ИНН',
            original_value='1', modified_value='2', edit_type='changed',
        )
        late = req.created_at + dt.timedelta(hours=2)
        _crud_update(req, {'inn': ['2', '3'], 'updated_at': ['a', 'b']},
                     user=self.operator, when=late)
        # client_name на входе не правили → подозрение на пропущенную ошибку.
        _crud_update(req, {'client_name': ['Старое', 'Новое']},
                     user=self.operator, when=late + dt.timedelta(minutes=5))

        payload = service.build_payload(service.parse_filters({}))
        self.assertTrue(payload['audit_available'])
        self.assertEqual(payload['totals']['requests_with_post_edits'], 1)
        # updated_at игнорируется, считаются inn + client_name.
        self.assertEqual(payload['totals']['total_post_edits'], 2)

        by_field = {r['field_name']: r for r in payload['by_field']}
        self.assertEqual(by_field['client_name']['edits'], 1)
        self.assertEqual(by_field['inn']['requests'], 1)

        by_editor = {r['editor']: r for r in payload['by_editor']}
        self.assertEqual(by_editor['Петров Иван']['edits'], 2)

        suspected = {s['field_name'] for s in payload['suspected']}
        self.assertIn('client_name', suspected)   # не правили на входе
        self.assertNotIn('inn', suspected)         # правили на входе
        self.assertEqual(payload['totals']['suspected_count'], 1)

    def test_creation_burst_excluded(self):
        req = _make_v2_request(created_by=self.operator)
        _crud_update(req, {'client_name': ['x', 'y']},
                     user=self.operator, when=req.created_at + dt.timedelta(seconds=1))
        payload = service.build_payload(service.parse_filters({}))
        self.assertEqual(payload['totals']['total_post_edits'], 0)
        self.assertEqual(payload['suspected'], [])

    def test_non_tracked_field_ignored(self):
        req = _make_v2_request(created_by=self.operator)
        _crud_update(req, {'some_internal_field': ['a', 'b']},
                     user=self.operator, when=req.created_at + dt.timedelta(hours=1))
        payload = service.build_payload(service.parse_filters({}))
        self.assertEqual(payload['totals']['total_post_edits'], 0)

    def test_empty_is_safe(self):
        payload = service.build_payload(service.parse_filters({'days': '5'}))
        self.assertEqual(payload['totals']['total_post_edits'], 0)
        self.assertEqual(payload['by_field'], [])


class PostCreationAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.admin = User.objects.create_user(username='a', password='x')
        self.admin.groups.add(admin_group)
        self.regular = User.objects.create_user(username='u', password='x')
        self.regular.groups.add(user_group)

    def test_admin_can_open(self):
        self.client.login(username='a', password='x')
        response = self.client.get(reverse('summaries:analytics_post_creation'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/analytics_post_creation.html')
        self.assertContains(response, 'Правки после создания')

    def test_regular_user_forbidden(self):
        self.client.login(username='u', password='x')
        response = self.client.get(reverse('summaries:analytics_post_creation'))
        self.assertEqual(response.status_code, 403)

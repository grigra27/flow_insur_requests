"""Правки после создания: сигнал, перенос истории, дашборд (analytics_redesign_2026_09, 5.1)."""
import datetime as dt
import json

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest, RequestFieldEdit
from summaries._current_user import set_current_user
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


def _age(req, **delta):
    """Сдвинуть created_at заявки в прошлое, чтобы правка не считалась хвостом создания."""
    InsuranceRequest.objects.filter(pk=req.pk).update(created_at=timezone.now() - dt.timedelta(**delta))
    req.refresh_from_db()
    return req


class PostCreationSignalTests(TestCase):
    """Сигнал пишет RequestFieldEdit(scope='post') при правке сохранённой V2-заявки (задача 5.1)."""

    def setUp(self):
        self.operator = User.objects.create_user('op', last_name='Петров', first_name='Иван')
        set_current_user(self.operator)
        self.addCleanup(set_current_user, None)

    def _post_edits(self, req):
        return list(RequestFieldEdit.objects.filter(request=req, scope='post').order_by('field_name'))

    def test_records_changed_parser_fields_with_editor(self):
        req = _age(_make_v2_request(created_by=self.operator, dfa_number='ТС-20842', has_autostart=False), hours=2)
        req.dfa_number = 'ТС-20842-ГА-МН'
        req.has_autostart = True
        req.save()

        edits = {edit.field_name: edit for edit in self._post_edits(req)}
        self.assertEqual(set(edits), {'dfa_number', 'has_autostart'})
        self.assertEqual(edits['dfa_number'].original_value, 'ТС-20842')
        self.assertEqual(edits['dfa_number'].modified_value, 'ТС-20842-ГА-МН')
        self.assertEqual((edits['has_autostart'].original_value, edits['has_autostart'].modified_value), ('Нет', 'Да'))
        self.assertEqual(edits['dfa_number'].edited_by, self.operator)
        self.assertEqual(edits['dfa_number'].edit_type, 'changed')

    def test_ignores_empty_to_empty_notes_status_and_creation_tail(self):
        req = _age(_make_v2_request(created_by=self.operator, legal_address=None), hours=2)
        req.legal_address = ''          # None → '' — не правка
        req.notes = 'служебная пометка'  # примечание не распознаётся парсером
        req.status = 'emails_sent'      # статус пишет StatusEvent
        req.save()
        self.assertEqual(self._post_edits(req), [])

        fresh = _make_v2_request(created_by=self.operator)
        fresh.client_name = 'Сразу после создания'
        fresh.save()
        self.assertEqual(self._post_edits(fresh), [])

    def test_v1_requests_not_tracked(self):
        req = _age(InsuranceRequest.objects.create(client_name='V1', inn='1'), hours=2)
        req.client_name = 'V1 правка'
        req.save()
        self.assertEqual(self._post_edits(req), [])

    def _form_data(self, req):
        from insurance_requests.forms import InsuranceRequestForm

        form = InsuranceRequestForm(instance=req)
        data = {}
        for name, field in form.fields.items():
            value = form[name].value()
            if isinstance(value, bool):
                if value:
                    data[name] = 'on'
                continue
            if value is None:
                value = ''
            data[name] = form[name].field.widget.format_value(value) if hasattr(form[name].field.widget, 'format_value') else value
            if data[name] is None:
                data[name] = ''
        return data

    def _realistic_v2(self):
        import datetime as _dt
        from decimal import Decimal

        return _age(_make_v2_request(
            created_by=self.operator, inn='470401291828', insurance_type='КАСКО', insurance_period='на весь срок лизинга',
            dfa_number='ТС-20842', branch='Москва', manager_name='Бурак А.В.', has_autostart=True,
            has_installment=False, franchise_type='none', brand='GWM', model='WEY 80', condition='new',
            acquisition_cost_value=Decimal('7900000.00'), acquisition_cost_currency='RUB', source_object_count=1,
            manufacturing_year='2026', legal_address=None, birth_date=_dt.date(1961, 2, 20),
            submission_date=_dt.date(2026, 8, 26), premium_frequency='annual', insured_party='lessee',
            response_deadline=timezone.now() + _dt.timedelta(days=2),
        ), hours=3)

    def _editor_client(self):
        users_group, _ = Group.objects.get_or_create(name='Пользователи')
        editor = User.objects.create_user('editor', password='p', last_name='Сергеева')
        editor.groups.add(users_group)
        client = Client()
        client.login(username='editor', password='p')
        return editor, client

    def test_saving_edit_form_unchanged_records_nothing(self):
        req = self._realistic_v2()
        _, client = self._editor_client()

        response = client.post(reverse('insurance_requests:edit_request', args=[req.pk]), self._form_data(req))

        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        self.assertEqual([(e.field_name, e.original_value, e.modified_value) for e in self._post_edits(req)], [])

    def test_edit_form_records_changed_field_and_editor(self):
        req = self._realistic_v2()
        editor, client = self._editor_client()
        data = self._form_data(req)
        data['dfa_number'] = 'ТС-20842-ГА-МС'

        response = client.post(reverse('insurance_requests:edit_request', args=[req.pk]), data)

        self.assertEqual(response.status_code, 302)
        edits = self._post_edits(req)
        self.assertEqual([edit.field_name for edit in edits], ['dfa_number'])
        self.assertEqual(edits[0].edited_by, editor)


class PostCreationServiceTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('op', last_name='Петров', first_name='Иван')

    def _post(self, req, field, label, old, new, when=None):
        edit = RequestFieldEdit.objects.create(
            request=req, scope='post', edited_by=self.operator, field_name=field, field_label=label,
            original_value=old, modified_value=new, edit_type='changed',
        )
        if when:
            RequestFieldEdit.objects.filter(pk=edit.pk).update(created_at=when)
        return edit

    def test_aggregates_and_suspected(self):
        req = _make_v2_request(created_by=self.operator)
        # Поле inn правили на входе — НЕ подозрение, даже если меняли позже.
        RequestFieldEdit.objects.create(
            request=req, scope='common', field_name='inn', field_label='ИНН',
            original_value='1', modified_value='2', edit_type='changed',
        )
        self._post(req, 'inn', 'ИНН', '2', '3')
        # client_name на входе не правили → подозрение на пропущенную ошибку.
        self._post(req, 'client_name', 'Клиент', 'Старое', 'Новое')

        payload = service.build_payload(service.parse_filters({}))
        self.assertEqual(payload['totals']['requests_with_post_edits'], 1)
        self.assertEqual(payload['totals']['total_post_edits'], 2)

        by_field = {r['field_name']: r for r in payload['by_field']}
        self.assertEqual(by_field['client_name']['edits'], 1)
        self.assertEqual(by_field['inn']['requests'], 1)

        by_editor = {r['editor']: r for r in payload['by_editor']}
        self.assertEqual(by_editor['Петров Иван']['edits'], 2)

        suspected = {s['field_name'] for s in payload['suspected']}
        self.assertIn('client_name', suspected)
        self.assertNotIn('inn', suspected)
        self.assertEqual(payload['totals']['suspected_count'], 1)

    def test_period_filter(self):
        req = _make_v2_request(created_by=self.operator)
        self._post(req, 'client_name', 'Клиент', 'a', 'b', when=timezone.now() - dt.timedelta(days=100))
        payload = service.build_payload(service.parse_filters({'days': '90'}))
        self.assertEqual(payload['totals']['total_post_edits'], 0)

    def test_intake_page_excludes_post_edits(self):
        from summaries.services import analytics_parser_edits

        req = _make_v2_request(created_by=self.operator, manual_edits_count=0)
        self._post(req, 'client_name', 'Клиент', 'a', 'b')
        payload = analytics_parser_edits.build_payload(analytics_parser_edits.parse_filters({}))
        self.assertEqual(payload['totals']['total_edits'], 0)

    def test_empty_is_safe(self):
        payload = service.build_payload(service.parse_filters({'days': '5'}))
        self.assertEqual(payload['totals']['total_post_edits'], 0)
        self.assertEqual(payload['by_field'], [])


class ImportPostCreationEditsTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('op', last_name='Петров', first_name='Иван')
        self.req = _age(_make_v2_request(created_by=self.operator), days=10)

    def test_imports_with_dedupe_and_skips_noise(self):
        late = self.req.created_at + dt.timedelta(hours=2)
        _crud_update(self.req, {'dfa_number': ['ТС-1', 'ТС-1-ГА-МН'], 'updated_at': ['a', 'b']},
                     user=self.operator, when=late)
        _crud_update(self.req, {'legal_address': ['None', '']}, user=self.operator, when=late)  # не правка
        _crud_update(self.req, {'client_name': ['x', 'y']}, user=self.operator,
                     when=self.req.created_at + dt.timedelta(seconds=1))  # хвост создания

        out = StringIO()
        call_command('import_post_creation_edits', stdout=out)
        self.assertEqual(RequestFieldEdit.objects.filter(scope='post').count(), 0)
        self.assertIn('Правок к переносу: 1', out.getvalue())

        call_command('import_post_creation_edits', '--apply', stdout=StringIO())
        call_command('import_post_creation_edits', '--apply', stdout=StringIO())  # повтор — без дублей

        rows = list(RequestFieldEdit.objects.filter(scope='post'))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].field_name, rows[0].original_value, rows[0].modified_value),
                         ('dfa_number', 'ТС-1', 'ТС-1-ГА-МН'))
        self.assertEqual(rows[0].edited_by, self.operator)
        self.assertEqual(rows[0].created_at, late)


class PostCreationAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.admin = User.objects.create_user(username='a', password='x')
        self.admin.groups.add(admin_group)
        self.regular = User.objects.create_user(username='u', password='x')
        self.regular.groups.add(user_group)

    def test_old_url_opens_post_tab(self):
        self.client.login(username='a', password='x')
        response = self.client.get(reverse('summaries:analytics_post_creation'), {'days': '30'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('summaries:analytics_parser_edits') + '?days=30&tab=post')

    def test_admin_can_open_post_tab(self):
        self.client.login(username='a', password='x')
        response = self.client.get(reverse('summaries:analytics_parser_edits'), {'tab': 'post'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/_recognition_post.html')
        self.assertTemplateNotUsed(response, 'summaries/_recognition_intake.html')
        self.assertContains(response, 'Какие поля меняют после создания')

    def test_default_tab_is_intake_without_removed_blocks(self):
        self.client.login(username='a', password='x')
        response = self.client.get(reverse('summaries:analytics_parser_edits'))
        self.assertTemplateUsed(response, 'summaries/_recognition_intake.html')
        for removed in ('Средняя уверенность', 'По филиалам', 'По операторам'):
            self.assertNotContains(response, removed)

    def test_regular_user_forbidden(self):
        self.client.login(username='u', password='x')
        response = self.client.get(reverse('summaries:analytics_post_creation'))
        self.assertEqual(response.status_code, 403)

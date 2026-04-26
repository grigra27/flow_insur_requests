"""Phase 5a — слияние easyaudit CRUDEvent и StatusEvent в timeline."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from easyaudit.models import CRUDEvent

from insurance_requests.models import InsuranceRequest

from .models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from .services import analytics_managers


class FieldFormattingTests(TestCase):
    def test_field_label_uses_verbose_name(self):
        label = analytics_managers._field_label(InsuranceRequest, 'dfa_number')
        self.assertEqual(label, 'Номер ДФА')

    def test_field_label_falls_back_to_raw(self):
        label = analytics_managers._field_label(InsuranceRequest, 'no_such_field')
        self.assertEqual(label, 'no_such_field')

    def test_truncate_long_value(self):
        out = analytics_managers._truncate_value('x' * 100)
        self.assertTrue(out.endswith('…'))
        self.assertEqual(len(out), analytics_managers.TIMELINE_VALUE_TRUNCATE + 1)

    def test_normalize_changed_fields_drops_status(self):
        raw = json.dumps({'status': ['uploaded', 'email_generated'], 'notes': ['', 'тест']})
        out = analytics_managers._normalize_changed_fields(InsuranceRequest, raw, drop_status=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['field'], 'notes')
        self.assertEqual(out[0]['new'], 'тест')

    def test_normalize_changed_fields_drops_noisy(self):
        raw = json.dumps({'updated_at': ['t1', 't2'], 'created_at': ['t1', 't2']})
        out = analytics_managers._normalize_changed_fields(InsuranceRequest, raw)
        self.assertEqual(out, [])

    def test_normalize_handles_invalid_json(self):
        self.assertEqual(
            analytics_managers._normalize_changed_fields(InsuranceRequest, 'not json'),
            [],
        )


@override_settings(TEST=True)
class TimelineMergerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='alice', password='p', first_name='Алиса')
        InsuranceCompany.objects.get_or_create(
            name='Альфа', defaults={'display_name': 'Альфа', 'sort_order': 10})

    def test_status_event_present(self):
        InsuranceRequest.objects.create(
            client_name='Test', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        timeline = analytics_managers._personal_timeline(self.user.pk)
        kinds = {e['kind'] for e in timeline}
        self.assertIn('status', kinds)

    def test_edit_event_after_field_change(self):
        req = InsuranceRequest.objects.create(
            client_name='Test', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        # Меняем не-status поле
        req.notes = 'добавил приоритет'
        req.save()

        timeline = analytics_managers._personal_timeline(self.user.pk)
        edit_events = [e for e in timeline if e['kind'] == 'edit']
        self.assertTrue(edit_events, msg='Ожидался edit-event при правке notes')
        # Проверим, что в changes есть поле notes
        changes = edit_events[0]['changes']
        notes_changes = [c for c in changes if c['field'] == 'notes']
        self.assertEqual(len(notes_changes), 1)
        self.assertEqual(notes_changes[0]['new'], 'добавил приоритет')

    def test_status_only_update_does_not_create_duplicate_edit(self):
        req = InsuranceRequest.objects.create(
            client_name='Test', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        # Меняем только статус — easyaudit запишет UPDATE с changed_fields={'status': [...]}
        req.status = 'email_generated'
        req.save()

        timeline = analytics_managers._personal_timeline(self.user.pk)
        # В timeline должны быть status-события, но НЕ должен появиться edit-событие
        # с пустыми changes (после dropping status), т.к. мы такие отбрасываем.
        for e in timeline:
            if e['kind'] == 'edit':
                self.assertTrue(e['changes'], msg='edit без changes не должен попадать в timeline')

    def test_create_event_for_offer(self):
        req = InsuranceRequest.objects.create(
            client_name='Test', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user, status='emails_sent',
        )
        sm = InsuranceSummary.objects.create(request=req)
        InsuranceOffer.objects.create(
            summary=sm, company_name='Альфа',
            insurance_sum=Decimal('500000'), insurance_year=1,
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal('25000'),
        )
        timeline = analytics_managers._personal_timeline(self.user.pk)
        create_kinds = [e for e in timeline if e['kind'] == 'create' and e['target_kind'] == 'offer']
        self.assertTrue(create_kinds, msg='Ожидался create-event для offer')

    def test_timeline_sorted_desc(self):
        # Создаём 3 заявки с задержкой
        InsuranceRequest.objects.create(
            client_name='1', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        r2 = InsuranceRequest.objects.create(
            client_name='2', inn='1234567890',
            insurance_type='КАСКО', created_by=self.user,
        )
        r2.notes = 'edit'
        r2.save()

        timeline = analytics_managers._personal_timeline(self.user.pk)
        for i in range(len(timeline) - 1):
            self.assertGreaterEqual(timeline[i]['changed_at'], timeline[i + 1]['changed_at'])


class DossierEndpointTests(TestCase):
    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.admin = User.objects.create_user(username='adm', password='p')
        self.admin.groups.add(admin_group)
        self.client = Client()
        self.client.login(username='adm', password='p')

    def test_dossier_renders_timeline_filters(self):
        target = User.objects.create_user(username='t', password='p', first_name='Тест')
        InsuranceRequest.objects.create(
            client_name='Test', inn='1234567890',
            insurance_type='КАСКО', created_by=target,
        )
        url = reverse('summaries:analytics_manager_detail', kwargs={'user_id': target.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Чекбоксы фильтров присутствуют
        self.assertContains(response, 'js-tl-filter')
        self.assertContains(response, 'tl-f-status')
        self.assertContains(response, 'tl-f-edit')

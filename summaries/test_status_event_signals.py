"""Smoke-тесты для аудита смен статусов через StatusEvent.

Проверяем, что pre_save/post_save сигналы:
- создают запись при создании InsuranceRequest;
- создают запись при смене status у InsuranceRequest;
- не создают повторных записей при save() без смены status;
- работают для InsuranceSummary;
- подхватывают current user из thread-local.
"""
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from insurance_requests.models import InsuranceRequest

from ._current_user import set_current_user
from .models import InsuranceSummary, StatusEvent


def _events_for(instance):
    ct = ContentType.objects.get_for_model(instance.__class__)
    return StatusEvent.objects.filter(content_type=ct, object_id=instance.pk)


class StatusEventOnInsuranceRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pwd')

    def test_creation_emits_event(self):
        req = InsuranceRequest.objects.create(
            client_name='ООО Тест',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user,
        )
        events = _events_for(req)
        self.assertEqual(events.count(), 1)
        evt = events.first()
        self.assertEqual(evt.from_status, '')
        self.assertEqual(evt.to_status, 'uploaded')

    def test_status_change_emits_event(self):
        req = InsuranceRequest.objects.create(
            client_name='ООО Тест',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user,
        )
        req.status = 'email_generated'
        req.save()

        events = list(_events_for(req).order_by('changed_at'))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].to_status, 'uploaded')
        self.assertEqual(events[1].from_status, 'uploaded')
        self.assertEqual(events[1].to_status, 'email_generated')

    def test_no_event_when_status_unchanged(self):
        req = InsuranceRequest.objects.create(
            client_name='ООО Тест',
            inn='1234567890',
            insurance_type='КАСКО',
            created_by=self.user,
        )
        # Меняем не-status поле
        req.notes = 'Что-то поменяли'
        req.save()
        self.assertEqual(_events_for(req).count(), 1)  # только создание

    def test_changed_by_picked_from_thread_local(self):
        try:
            set_current_user(self.user)
            req = InsuranceRequest.objects.create(
                client_name='ООО Тест',
                inn='1234567890',
                insurance_type='КАСКО',
                created_by=self.user,
            )
        finally:
            set_current_user(None)

        evt = _events_for(req).first()
        self.assertEqual(evt.changed_by, self.user)


class StatusEventOnInsuranceSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester2', password='pwd')
        self.request = InsuranceRequest.objects.create(
            client_name='ООО Тест-2',
            inn='1234567890',
            insurance_type='КАСКО',
            status='emails_sent',
            created_by=self.user,
        )

    def test_summary_creation_and_status_change(self):
        summary = InsuranceSummary.objects.create(request=self.request)
        events_create = _events_for(summary)
        self.assertEqual(events_create.count(), 1)
        self.assertEqual(events_create.first().to_status, 'collecting')

        summary.status = 'ready'
        summary.save()

        events = list(_events_for(summary).order_by('changed_at'))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].from_status, 'collecting')
        self.assertEqual(events[1].to_status, 'ready')

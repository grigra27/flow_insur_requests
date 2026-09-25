"""Дата закрытия у сводов «не будет» (analytics_redesign_2026_09, задача 1.7)."""
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, StatusEvent


class RejectedCompletedAtTests(TestCase):
    def setUp(self):
        group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user = User.objects.create_user(username='closer', password='testpass123')
        self.user.groups.add(group)
        self.client.login(username='closer', password='testpass123')
        self._counter = 0

    def _summary(self, status='sent', created_days_ago=1):
        self._counter += 1
        insurance_request = InsuranceRequest.objects.create(
            created_by=self.user, client_name=f'Клиент {self._counter}', inn='1234567890',
            insurance_type='КАСКО', dfa_number=f'DFA-{self._counter}',
        )
        summary = InsuranceSummary.objects.create(request=insurance_request, status=status)
        InsuranceSummary.objects.filter(pk=summary.pk).update(
            created_at=timezone.now() - timedelta(days=created_days_ago)
        )
        summary.refresh_from_db()
        return summary

    def _change_status(self, summary, status):
        return self.client.post(reverse('summaries:change_summary_status', args=[summary.pk]), {'status': status})

    def test_manual_rejection_sets_completed_at_and_reopening_clears_it(self):
        summary = self._summary()

        self.assertTrue(self._change_status(summary, 'completed_rejected').json()['success'])
        summary.refresh_from_db()
        self.assertIsNotNone(summary.completed_at)
        self.assertLess(timezone.now() - summary.completed_at, timedelta(minutes=1))

        self._change_status(summary, 'collecting')
        summary.refresh_from_db()
        self.assertIsNone(summary.completed_at)

    def test_repeated_rejection_keeps_first_close_time(self):
        summary = self._summary()
        self._change_status(summary, 'completed_rejected')
        summary.refresh_from_db()
        first_close = summary.completed_at

        self._change_status(summary, 'completed_rejected')
        summary.refresh_from_db()
        self.assertEqual(summary.completed_at, first_close)

    def test_auto_close_sets_completed_at_and_writes_status_event(self):
        stale = self._summary(status='sent', created_days_ago=31)

        call_command('auto_close_stale_summaries', stdout=StringIO())

        stale.refresh_from_db()
        self.assertEqual(stale.status, 'completed_rejected')
        self.assertIsNotNone(stale.completed_at)
        event = StatusEvent.objects.get(
            content_type=ContentType.objects.get_for_model(InsuranceSummary),
            object_id=stale.pk,
            to_status='completed_rejected',
        )
        self.assertEqual(event.from_status, 'sent')
        self.assertIsNone(event.changed_by)
        self.assertEqual(event.note, 'Автозакрытие: нет решения 30 дн.')

    def _legacy_rejected(self, updated_days_ago):
        summary = self._summary(status='completed_rejected', created_days_ago=60)
        updated_at = timezone.now() - timedelta(days=updated_days_ago)
        InsuranceSummary.objects.filter(pk=summary.pk).update(completed_at=None, updated_at=updated_at)
        summary.refresh_from_db()
        return summary

    def test_backfill_reports_without_writing_by_default(self):
        summary = self._legacy_rejected(updated_days_ago=10)
        out = StringIO()

        call_command('backfill_rejected_completed_at', stdout=out)

        summary.refresh_from_db()
        self.assertIsNone(summary.completed_at)
        self.assertIn('без записи', out.getvalue())

    def test_backfill_apply_prefers_status_event_then_updated_at(self):
        with_event = self._legacy_rejected(updated_days_ago=2)
        StatusEvent.objects.filter(object_id=with_event.pk).delete()
        event = StatusEvent.objects.create(
            content_type=ContentType.objects.get_for_model(InsuranceSummary),
            object_id=with_event.pk, from_status='sent', to_status='completed_rejected',
        )
        event_time = timezone.now() - timedelta(days=5)
        StatusEvent.objects.filter(pk=event.pk).update(changed_at=event_time)
        InsuranceSummary.objects.filter(pk=with_event.pk).update(completed_at=None)

        without_event = self._legacy_rejected(updated_days_ago=10)
        StatusEvent.objects.filter(object_id=without_event.pk).delete()
        updated_at_before = without_event.updated_at

        call_command('backfill_rejected_completed_at', '--apply', stdout=StringIO())

        with_event.refresh_from_db()
        without_event.refresh_from_db()
        self.assertEqual(with_event.completed_at, event_time)
        self.assertEqual(without_event.completed_at, updated_at_before)
        # Заполнение не должно сдвигать дату изменения свода.
        self.assertEqual(without_event.updated_at, updated_at_before)

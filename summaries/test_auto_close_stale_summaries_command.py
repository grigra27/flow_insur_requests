from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary


class AutoCloseStaleSummariesCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="autoclose_user",
            password="testpass123",
        )
        self._counter = 0

    def _create_summary(
        self,
        *,
        status="collecting",
        created_at=None,
        selected_company=None,
        selected_franchise_variant=None,
    ):
        self._counter += 1
        request = InsuranceRequest.objects.create(
            dfa_number=f"AUTO-{self._counter}",
            client_name=f"Client {self._counter}",
            inn=f"12345678{self._counter:02d}",
            insurance_type="КАСКО",
            insurance_period="1 год",
            created_by=self.user,
        )
        summary = InsuranceSummary.objects.create(
            request=request,
            status=status,
            selected_company=selected_company,
            selected_franchise_variant=selected_franchise_variant,
        )

        if created_at is not None:
            InsuranceSummary.objects.filter(pk=summary.pk).update(created_at=created_at)
            summary.refresh_from_db()

        return summary

    def test_closes_stale_summary(self):
        old_time = timezone.now() - timedelta(days=31)
        summary = self._create_summary(
            status="sent",
            created_at=old_time,
            selected_company="Тест СК",
            selected_franchise_variant=1,
        )

        call_command("auto_close_stale_summaries")

        summary.refresh_from_db()
        self.assertEqual(summary.status, "completed_rejected")
        self.assertIsNone(summary.selected_company)
        self.assertIsNone(summary.selected_franchise_variant)

    def test_does_not_touch_completed_accepted(self):
        old_time = timezone.now() - timedelta(days=45)
        summary = self._create_summary(
            status="completed_accepted",
            created_at=old_time,
            selected_company="Акцепт СК",
            selected_franchise_variant=2,
        )

        call_command("auto_close_stale_summaries")

        summary.refresh_from_db()
        self.assertEqual(summary.status, "completed_accepted")
        self.assertEqual(summary.selected_company, "Акцепт СК")
        self.assertEqual(summary.selected_franchise_variant, 2)

    def test_does_not_touch_recent_summary(self):
        recent_time = timezone.now() - timedelta(days=10)
        summary = self._create_summary(status="ready", created_at=recent_time)

        call_command("auto_close_stale_summaries")

        summary.refresh_from_db()
        self.assertEqual(summary.status, "ready")

    def test_dry_run_does_not_change_data(self):
        old_time = timezone.now() - timedelta(days=31)
        summary = self._create_summary(status="collecting", created_at=old_time)
        out = StringIO()

        call_command("auto_close_stale_summaries", "--dry-run", stdout=out)

        summary.refresh_from_db()
        self.assertEqual(summary.status, "collecting")
        self.assertIn("Dry-run mode", out.getvalue())

    def test_days_option_changes_threshold(self):
        old_time = timezone.now() - timedelta(days=15)
        summary = self._create_summary(status="collecting", created_at=old_time)

        call_command("auto_close_stale_summaries", "--days=10")

        summary.refresh_from_db()
        self.assertEqual(summary.status, "completed_rejected")

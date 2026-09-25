"""
Management command to auto-close stale summaries.

Rule:
- If summary is older than N days (default: 30),
- And summary is not completed with acceptance,
- Then move summary to "completed_rejected".

The close time is stored in completed_at and a StatusEvent with a note is
written for every closed summary: .update() bypasses the status signals, and
analytics needs to tell auto-closures apart from explicit "не будет".
"""

from datetime import timedelta
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from django.contrib.contenttypes.models import ContentType

from summaries.models import InsuranceSummary, StatusEvent


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Auto-close stale summaries: move collecting/ready/sent summaries older than "
        "N days to completed_rejected."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Age threshold in days (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many records would be updated without changing data.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        if days <= 0:
            raise CommandError("--days must be a positive integer")

        now = timezone.now()
        cutoff = now - timedelta(days=days)
        eligible_statuses = ["collecting", "ready", "sent"]

        stale_summaries = InsuranceSummary.objects.filter(
            status__in=eligible_statuses,
            created_at__lte=cutoff,
        )

        count = stale_summaries.count()
        self.stdout.write(
            f"Found {count} stale summaries older than {days} days "
            f"(cutoff: {cutoff:%Y-%m-%d %H:%M:%S %Z})."
        )

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No updates required."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode: no changes were applied."))
            return

        with transaction.atomic():
            previous_statuses = list(stale_summaries.values_list("pk", "status"))
            updated_count = InsuranceSummary.objects.filter(
                pk__in=[pk for pk, _ in previous_statuses]
            ).update(
                status="completed_rejected",
                selected_company=None,
                selected_franchise_variant=None,
                completed_at=now,
                updated_at=now,
            )
            content_type = ContentType.objects.get_for_model(InsuranceSummary)
            note = f"Автозакрытие: нет решения {days} дн."
            StatusEvent.objects.bulk_create([
                StatusEvent(
                    content_type=content_type,
                    object_id=pk,
                    from_status=old_status,
                    to_status="completed_rejected",
                    note=note,
                )
                for pk, old_status in previous_statuses
            ])

        logger.info(
            "Auto-closed stale summaries: updated=%s cutoff=%s days=%s",
            updated_count,
            cutoff.isoformat(),
            days,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated_count} summaries to 'completed_rejected'."
            )
        )

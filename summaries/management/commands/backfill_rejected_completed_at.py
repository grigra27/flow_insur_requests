"""
Заполняет completed_at у сводов «Завершен: не будет», закрытых до того, как дата
закрытия стала фиксироваться (docs/improvement_plans/analytics_redesign_2026_09.md,
задача 1.7).

Источник даты по приоритету:
1. последнее событие StatusEvent с переходом в completed_rejected;
2. updated_at свода (автозакрытие по cron и ручные закрытия до появления журнала
   статусов; после закрытия свод обычно не редактируют).

По умолчанию — только отчёт. Изменения записываются с флагом --apply.

Использование:
    python manage.py backfill_rejected_completed_at            # отчёт
    python manage.py backfill_rejected_completed_at --apply    # записать
"""

from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from summaries.models import InsuranceSummary, StatusEvent


class Command(BaseCommand):
    help = 'Заполняет дату закрытия у сводов «не будет», где она пуста (по журналу статусов или updated_at).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения (без флага — только отчёт)')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        summaries = list(
            InsuranceSummary.objects.filter(status='completed_rejected', completed_at__isnull=True)
            .only('pk', 'updated_at')
        )

        content_type = ContentType.objects.get_for_model(InsuranceSummary)
        event_times = {}
        for object_id, changed_at in (
            StatusEvent.objects.filter(
                content_type=content_type,
                object_id__in=[summary.pk for summary in summaries],
                to_status='completed_rejected',
            ).order_by('changed_at').values_list('object_id', 'changed_at')
        ):
            event_times[object_id] = changed_at  # последнее событие перезаписывает предыдущие

        sources = Counter()
        updates = []
        for summary in summaries:
            if summary.pk in event_times:
                closed_at = event_times[summary.pk]
                sources['журнал статусов'] += 1
            else:
                closed_at = summary.updated_at
                sources['дата изменения свода'] += 1
            updates.append((summary.pk, closed_at))

        self.stdout.write(f'Сводов «не будет» без даты закрытия: {len(summaries)}')
        for source, count in sources.most_common():
            self.stdout.write(f'  источник «{source}»: {count}')
        for pk, closed_at in updates[:10]:
            self.stdout.write(f'  свод #{pk}: {closed_at:%Y-%m-%d %H:%M %Z}')
        if len(updates) > 10:
            self.stdout.write(f'  … и ещё {len(updates) - 10}')

        if not apply_changes:
            self.stdout.write(self.style.WARNING('Отчёт без записи. Для записи запустите с --apply.'))
            return

        # QuerySet.update не трогает updated_at (auto_now срабатывает только в save()).
        with transaction.atomic():
            for pk, closed_at in updates:
                InsuranceSummary.objects.filter(pk=pk, completed_at__isnull=True).update(completed_at=closed_at)
        self.stdout.write(self.style.SUCCESS(f'Записана дата закрытия у {len(updates)} сводов.'))

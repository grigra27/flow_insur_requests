"""
Переносит правки уже созданных V2-заявок из журнала easy-audit (CRUDEvent, хранится
365 дней) в RequestFieldEdit(scope='post'), где они хранятся бессрочно.
docs/improvement_plans/analytics_redesign_2026_09.md, задача 5.1.

Отбор — как на странице «Правки после создания»: UPDATE по InsuranceRequest с
parser_confidence, позже 5 секунд после создания заявки, только поля, которые
распознаёт парсер; переходы «None → ''» не считаются правкой. Повторный запуск
не создаёт дублей (заявка + поле + время события).

Использование:
    python manage.py import_post_creation_edits            # отчёт
    python manage.py import_post_creation_edits --apply    # записать
"""
import json
from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from insurance_requests.edit_tracking import (
    POST_CREATE_GRACE_SECONDS,
    diff_model_values,
    get_post_creation_field_meta,
)
from insurance_requests.models import InsuranceRequest, RequestFieldEdit


class Command(BaseCommand):
    help = 'Переносит правки после создания V2-заявок из журнала easy-audit в RequestFieldEdit (scope=post).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать (без флага — только отчёт)')

    def handle(self, *args, **options):
        from easyaudit.models import CRUDEvent

        meta = get_post_creation_field_meta()
        created_at_by_id = dict(
            InsuranceRequest.objects.filter(parser_confidence__isnull=False).values_list('pk', 'created_at')
        )
        existing = set(
            RequestFieldEdit.objects.filter(scope='post').values_list('request_id', 'field_name', 'created_at')
        )
        events = CRUDEvent.objects.filter(
            content_type=ContentType.objects.get_for_model(InsuranceRequest),
            event_type=CRUDEvent.UPDATE,
        ).order_by('datetime')

        rows, skipped = [], Counter()
        for event in events.iterator():
            try:
                request_id = int(event.object_id)
            except (TypeError, ValueError):
                continue
            created_at = created_at_by_id.get(request_id)
            if created_at is None:
                skipped['не V2-заявка'] += 1
                continue
            if (event.datetime - created_at).total_seconds() <= POST_CREATE_GRACE_SECONDS:
                skipped['хвост создания'] += 1
                continue
            try:
                delta = json.loads(event.changed_fields) if event.changed_fields else {}
            except (TypeError, ValueError):
                continue
            if not isinstance(delta, dict):
                continue
            before, after = {}, {}
            for name, change in delta.items():
                if name in meta and isinstance(change, list) and len(change) == 2:
                    before[name], after[name] = change
            for edit in diff_model_values(before, after, meta):
                key = (request_id, edit['field'], event.datetime)
                if key in existing:
                    skipped['уже перенесено'] += 1
                    continue
                existing.add(key)
                rows.append((event, request_id, edit))

        by_field = Counter(edit['label'] for _, _, edit in rows)
        self.stdout.write(f'Правок к переносу: {len(rows)} (заявок: {len({request_id for _, request_id, _ in rows})})')
        for label, count in by_field.most_common(10):
            self.stdout.write(f'  {label}: {count}')
        for reason, count in skipped.items():
            self.stdout.write(f'  пропущено ({reason}): {count}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Отчёт без записи. Для записи запустите с --apply.'))
            return

        with transaction.atomic():
            for event, request_id, edit in rows:
                row = RequestFieldEdit.objects.create(
                    request_id=request_id,
                    scope='post',
                    edited_by_id=event.user_id,
                    field_name=edit['field'],
                    field_label=edit['label'],
                    original_value=edit['original'],
                    modified_value=edit['modified'],
                    edit_type=edit['edit_type'],
                )
                # created_at — auto_now_add: переписываем на время исходного события.
                RequestFieldEdit.objects.filter(pk=row.pk).update(created_at=event.datetime)
        self.stdout.write(self.style.SUCCESS(f'Перенесено правок: {len(rows)}.'))

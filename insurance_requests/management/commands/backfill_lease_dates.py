"""Заполнить даты договора лизинга у уже загруженных заявок из их исходных Excel.

Блок «Сроки действия договора лизинга» (дата начала / окончания) парсер читает с 2026-10-02;
у заявок, загруженных раньше, поля пустые, хотя даты есть в исходном файле во «Вложениях».
Команда разбирает этот файл тем же парсером и записывает ТОЛЬКО пустые поля дат.

    python manage.py backfill_lease_dates --dry-run          # отчёт без записи
    python manage.py backfill_lease_dates                    # записать
    python manage.py backfill_lease_dates --include-legacy   # и заявки старого загрузчика
"""
import logging
import os
from datetime import date

from django.core.management.base import BaseCommand

from insurance_requests.models import InsuranceRequest
from insurance_requests.parsers.excel_v2.parser import ExcelRequestParserV2

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Заполнить даты договора лизинга из исходных Excel уже загруженных заявок'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только отчёт, без записи')
        parser.add_argument('--include-legacy', action='store_true',
                            help='Также заявки старого загрузчика (до июня 2026)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        queryset = InsuranceRequest.objects.filter(lease_start_date__isnull=True, lease_end_date__isnull=True)
        if not options['include_legacy']:
            queryset = queryset.exclude(additional_data__parser_v2__isnull=True)

        parser = ExcelRequestParserV2()
        cache = {}
        stats = {'checked': 0, 'filled': 0, 'no_file': 0, 'no_dates': 0, 'errors': 0}
        for request in queryset.order_by('pk').iterator():
            stats['checked'] += 1
            attachment = request.attachments.first()
            path = attachment.file.path if attachment and attachment.file else ''
            if not path or not os.path.exists(path):
                stats['no_file'] += 1
                continue
            if path not in cache:
                try:
                    data = parser.parse(path, original_filename=attachment.original_filename or os.path.basename(path)).data
                    cache[path] = (data.get('lease_start_date'), data.get('lease_end_date'))
                except Exception as exc:  # noqa: BLE001 — один битый файл не должен останавливать прогон
                    logger.warning('backfill_lease_dates: cannot parse %s for request %s: %s', path, request.pk, exc)
                    cache[path] = None
            dates = cache[path]
            if dates is None:
                stats['errors'] += 1
                continue
            start, end = (date.fromisoformat(value) if value else None for value in dates)
            if not start and not end:
                stats['no_dates'] += 1
                continue
            stats['filled'] += 1
            self.stdout.write(f'{request.pk}\t{request.dfa_number}\t{start or "—"} — {end or "—"}')
            if not dry_run:
                InsuranceRequest.objects.filter(pk=request.pk).update(lease_start_date=start, lease_end_date=end)

        mode = 'DRY-RUN, ничего не записано' if dry_run else 'записано'
        self.stdout.write(
            f"Проверено: {stats['checked']} · заполнено: {stats['filled']} ({mode}) · "
            f"без дат в файле: {stats['no_dates']} · без файла: {stats['no_file']} · ошибки разбора: {stats['errors']}"
        )

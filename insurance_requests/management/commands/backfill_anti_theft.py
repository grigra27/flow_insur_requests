"""Заполнить «Противоугонные системы» у уже загруженных заявок из их исходных Excel.

Блок «Противоугонные системы и оборудование» парсер читает с 2026-10-02; у заявок, загруженных
раньше, поле пустое, хотя данные есть в исходном файле во «Вложениях». Команда разбирает файл тем
же парсером и записывает ТОЛЬКО пустое поле.

    python manage.py backfill_anti_theft --dry-run          # отчёт без записи
    python manage.py backfill_anti_theft                    # записать
    python manage.py backfill_anti_theft --include-legacy   # и заявки старого загрузчика
"""
import logging
import os

from django.core.management.base import BaseCommand

from insurance_requests.models import InsuranceRequest
from insurance_requests.parsers.excel_v2.parser import ExcelRequestParserV2

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Заполнить «Противоугонные системы» из исходных Excel уже загруженных заявок'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только отчёт, без записи')
        parser.add_argument('--include-legacy', action='store_true',
                            help='Также заявки старого загрузчика (до июня 2026)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        queryset = InsuranceRequest.objects.filter(anti_theft_systems='')
        if not options['include_legacy']:
            queryset = queryset.exclude(additional_data__parser_v2__isnull=True)

        parser = ExcelRequestParserV2()
        cache = {}
        stats = {'checked': 0, 'filled': 0, 'empty': 0, 'no_file': 0, 'errors': 0}
        for request in queryset.order_by('pk').iterator():
            stats['checked'] += 1
            attachment = request.attachments.first()
            path = attachment.file.path if attachment and attachment.file else ''
            if not path or not os.path.exists(path):
                stats['no_file'] += 1
                continue
            if path not in cache:
                try:
                    name = attachment.original_filename or os.path.basename(path)
                    cache[path] = parser.parse(path, original_filename=name).data.get('anti_theft_systems') or ''
                except Exception as exc:  # noqa: BLE001 — один битый файл не должен останавливать прогон
                    logger.warning('backfill_anti_theft: cannot parse %s for request %s: %s', path, request.pk, exc)
                    cache[path] = None
            value = cache[path]
            if value is None:
                stats['errors'] += 1
                continue
            if not value:
                stats['empty'] += 1
                continue
            stats['filled'] += 1
            self.stdout.write(f'{request.pk}\t{request.dfa_number}\t{value}')
            if not dry_run:
                InsuranceRequest.objects.filter(pk=request.pk).update(anti_theft_systems=value)

        mode = 'DRY-RUN, ничего не записано' if dry_run else 'записано'
        self.stdout.write(
            f"Проверено: {stats['checked']} · заполнено: {stats['filled']} ({mode}) · "
            f"блок пустой: {stats['empty']} · без файла: {stats['no_file']} · ошибки разбора: {stats['errors']}"
        )

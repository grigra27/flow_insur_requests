"""
Ротирует файловые логи приложения (BASE_DIR/logs/*.log) по размеру.

Почему не RotatingFileHandler: gunicorn запущен с несколькими воркерами, и
каждый процесс ротировал бы файл сам по себе — переименования наперегонки,
часть записей уходит в уже сдвинутый файл. Здесь схема copytruncate:
содержимое сжимается в <name>.log.1.gz, а сам файл обрезается до нуля.
FileHandler открывает файл в режиме append (O_APPEND), поэтому после
обрезки все процессы продолжают писать в начало того же файла.
Записи, попавшие между копированием и обрезкой, теряются — как и у
logrotate copytruncate; для этих логов это приемлемо.

Использование:
    python manage.py rotate_logs
    python manage.py rotate_logs --dry-run
    python manage.py rotate_logs --max-mb 20 --keep 3
"""
import gzip
import logging
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('backup.rotate_logs')


class Command(BaseCommand):
    help = (
        'Сжимает и обрезает логи в BASE_DIR/logs больше --max-mb (по умолчанию 10 МБ), '
        'хранит --keep архивов (по умолчанию 5).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--max-mb', type=float, default=10,
                            help='Ротировать файлы больше этого размера, МБ (default: 10)')
        parser.add_argument('--keep', type=int, default=5,
                            help='Сколько архивов .N.gz хранить на файл (default: 5)')
        parser.add_argument('--log-dir', default=None,
                            help='Папка с логами (default: BASE_DIR/logs)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать, что будет ротировано, ничего не меняя')

    def handle(self, *args, **options):
        max_bytes = int(options['max_mb'] * 1024 * 1024)
        keep = options['keep']
        if max_bytes < 1 or keep < 1:
            raise CommandError('--max-mb и --keep должны быть положительными')

        log_dir = Path(options['log_dir'] or Path(settings.BASE_DIR) / 'logs')
        if not log_dir.is_dir():
            raise CommandError(f'Папка логов не найдена: {log_dir}')

        rotated = 0
        for path in sorted(log_dir.glob('*.log')):
            size = path.stat().st_size
            if size < max_bytes:
                continue

            size_mb = size / 1024 / 1024
            if options['dry_run']:
                self.stdout.write(f'[dry-run] {path.name}: {size_mb:.1f} МБ — будет ротирован')
                continue

            self._rotate(path, keep)
            rotated += 1
            msg = f'{path.name}: {size_mb:.1f} МБ → {path.name}.1.gz, файл обрезан'
            self.stdout.write(self.style.SUCCESS(f'✓ {msg}'))
            logger.info(msg)

        if not options['dry_run']:
            msg = f'rotate_logs completed: rotated {rotated} file(s) in {log_dir}'
            self.stdout.write(msg)
            logger.info(msg)

    @staticmethod
    def _rotate(path, keep):
        # Сдвигаем архивы: .4.gz → .5.gz, ..., .1.gz → .2.gz; самый старый удаляется
        oldest = path.with_name(f'{path.name}.{keep}.gz')
        if oldest.exists():
            oldest.unlink()
        for n in range(keep - 1, 0, -1):
            src = path.with_name(f'{path.name}.{n}.gz')
            if src.exists():
                os.replace(src, path.with_name(f'{path.name}.{n + 1}.gz'))

        # Сначала пишем во временный файл, чтобы при сбое не оставить битый .1.gz
        target = path.with_name(f'{path.name}.1.gz')
        tmp = path.with_name(f'{path.name}.1.gz.tmp')
        with open(path, 'rb') as src, gzip.open(tmp, 'wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        os.replace(tmp, target)

        with open(path, 'r+b') as f:
            f.truncate(0)

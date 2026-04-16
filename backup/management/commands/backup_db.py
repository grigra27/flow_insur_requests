"""
Management-команда для создания резервной копии базы данных.

Использование:
    python manage.py backup_db
    python manage.py backup_db --output-dir /var/backups/app --format json
    python manage.py backup_db --format sqlite   # только для SQLite
    python manage.py backup_db --format pgdump   # только для PostgreSQL
    python manage.py backup_db --keep 7          # хранить последние 7 файлов

Для cron (ежедневный бекап в 3:00):
    0 3 * * * cd /path/to/project && python manage.py backup_db --format pgdump --keep 30
"""
import glob
import os
import shutil
import subprocess
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Создать резервную копию базы данных (JSON, SQLite-файл или pg_dump)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default='backups',
            help='Директория для сохранения резервных копий (default: backups/)',
        )
        parser.add_argument(
            '--format',
            choices=['json', 'sqlite', 'pgdump'],
            default='json',
            help=(
                'Формат резервной копии: '
                'json (универсальный, только данные приложений), '
                'sqlite (только для SQLite БД), '
                'pgdump (только для PostgreSQL, полный дамп через pg_dump)'
            ),
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=0,
            help='Сколько последних файлов оставлять (0 = хранить все)',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        fmt = options['format']
        keep = options['keep']

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if fmt == 'json':
            self._backup_json(output_dir, timestamp)
            pattern = os.path.join(output_dir, 'backup_*.json')
        elif fmt == 'sqlite':
            self._backup_sqlite(output_dir, timestamp)
            pattern = os.path.join(output_dir, 'db_backup_*.sqlite3')
        else:
            self._backup_pgdump(output_dir, timestamp)
            pattern = os.path.join(output_dir, 'pgdump_*.dump')

        if keep > 0:
            self._rotate(pattern, keep)

    # ------------------------------------------------------------------ helpers

    def _backup_json(self, output_dir, timestamp):
        filename = os.path.join(output_dir, f'backup_{timestamp}.json')
        with open(filename, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                '--natural-foreign',
                '--natural-primary',
                '--exclude', 'auth',
                '--exclude', 'contenttypes',
                '--exclude', 'sessions',
                '--exclude', 'admin',
                '--exclude', 'backup',
                '--indent', '2',
                stdout=f,
            )
        size = os.path.getsize(filename)
        self.stdout.write(
            self.style.SUCCESS(f'✓ JSON-бекап сохранён: {filename} ({size:,} байт)')
        )

    def _backup_sqlite(self, output_dir, timestamp):
        db_config = settings.DATABASES['default']
        engine = db_config.get('ENGINE', '')
        if 'sqlite3' not in engine:
            raise CommandError(
                f'Формат sqlite доступен только при использовании SQLite. '
                f'Текущий движок: {engine}'
            )

        db_path = str(db_config.get('NAME', ''))
        if not os.path.exists(db_path):
            raise CommandError(f'Файл БД не найден: {db_path}')

        filename = os.path.join(output_dir, f'db_backup_{timestamp}.sqlite3')
        shutil.copy2(db_path, filename)
        size = os.path.getsize(filename)
        self.stdout.write(
            self.style.SUCCESS(f'✓ SQLite-бекап сохранён: {filename} ({size:,} байт)')
        )

    def _backup_pgdump(self, output_dir, timestamp):
        db_config = settings.DATABASES['default']
        engine = db_config.get('ENGINE', '')
        if 'postgresql' not in engine and 'postgis' not in engine:
            raise CommandError(
                f'Формат pgdump доступен только при использовании PostgreSQL. '
                f'Текущий движок: {engine}'
            )

        if not shutil.which('pg_dump'):
            raise CommandError(
                'pg_dump не найден. Установите postgresql-client: '
                'apt install postgresql-client  или  brew install libpq'
            )

        host = str(db_config.get('HOST') or 'localhost')
        port = str(db_config.get('PORT') or '5432')
        user = str(db_config.get('USER') or '')
        password = str(db_config.get('PASSWORD') or '')
        dbname = str(db_config.get('NAME') or '')

        filename = os.path.join(output_dir, f'pgdump_{timestamp}.dump')

        cmd = ['pg_dump', '-h', host, '-p', port, '-F', 'c', '-f', filename]
        if user:
            cmd += ['-U', user]
        cmd.append(dbname)

        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password

        self.stdout.write(f'Запускаю pg_dump для базы "{dbname}" на {host}:{port}...')
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode != 0:
            # Убираем пароль из вывода на случай если он попал в stderr
            err = result.stderr.replace(password, '***') if password else result.stderr
            raise CommandError(f'pg_dump завершился с ошибкой:\n{err}')

        size = os.path.getsize(filename)
        self.stdout.write(
            self.style.SUCCESS(f'✓ pg_dump сохранён: {filename} ({size:,} байт)')
        )

    def _rotate(self, pattern, keep):
        """Удаляет старые файлы бекапа, оставляя последние `keep` штук."""
        files = sorted(glob.glob(pattern))
        to_delete = files[:-keep] if len(files) > keep else []
        for f in to_delete:
            os.unlink(f)
            self.stdout.write(self.style.WARNING(f'  удалён старый бекап: {f}'))
        if to_delete:
            self.stdout.write(f'Ротация: удалено {len(to_delete)}, оставлено {keep}.')

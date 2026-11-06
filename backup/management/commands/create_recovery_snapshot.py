"""Create a private verified DB/media snapshot for a separate delivery layer."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from backup.recovery_snapshot import RecoverySnapshotError, create_recovery_snapshot


class Command(BaseCommand):
    help = 'Создать согласованный снимок PostgreSQL и документов для внешнего резервирования'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='/app/backups/recovery')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        try:
            path = create_recovery_snapshot(options['output_dir'])
        except RecoverySnapshotError as error:
            raise CommandError(str(error)) from None
        if options['as_json']:
            self.stdout.write(json.dumps({
                'status': 'ready', 'snapshot_path': path,
                'manifest_path': str(Path(path) / 'manifest.json'),
            }))
            return None
        return path

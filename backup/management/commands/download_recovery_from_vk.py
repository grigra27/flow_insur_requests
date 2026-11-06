"""Read back one recovery document without reading or modifying VK messages."""
import json
from django.core.management.base import BaseCommand, CommandError
from backup.recovery_vk import RecoveryError, RecoveryVK


class Command(BaseCommand):
    help = 'Скачать и проверить зашифрованную копию VK по приватной квитанции'

    def add_arguments(self, parser):
        parser.add_argument('--receipt-file', required=True)
        parser.add_argument('--output-file', required=True)

    def handle(self, *args, **options):
        try:
            result = RecoveryVK().download(options['receipt_file'], options['output_file'])
            return json.dumps(result, ensure_ascii=False)
        except RecoveryError as error:
            raise CommandError(str(error)) from None
        except Exception:
            raise CommandError('recovery_download_failed') from None

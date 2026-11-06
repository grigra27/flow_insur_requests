"""Send only a validated owner-encrypted recovery archive through existing VK."""
import json
from django.core.management.base import BaseCommand, CommandError
from backup.recovery_vk import RecoveryError, RecoveryVK, RETRY_DEFAULTS


class Command(BaseCommand):
    help = 'Отправить полную зашифрованную копию InsFlow в существующий канал VK'

    def add_arguments(self, parser):
        parser.add_argument('--archive')
        parser.add_argument('--expected-sha256')
        parser.add_argument('--receipt-file')
        parser.add_argument('--no-notify', action='store_true')
        parser.add_argument('--notify-failure', action='store_true')
        parser.add_argument('--failure-code', choices=['snapshot', 'bundle', 'encryption', 'upload'])
        for key, default in RETRY_DEFAULTS.items():
            parser.add_argument('--' + key.replace('_', '-'), default=default,
                                type=int if key == 'upload_attempts' else float)

    def handle(self, *args, **options):
        try:
            retry = {key: options[key] for key in RETRY_DEFAULTS}
            if not options['notify_failure'] and not all(options[key] for key in ('archive', 'expected_sha256', 'receipt_file')):
                raise RecoveryError('archive_hash_and_receipt_required')
            client = RecoveryVK(retry)
            if options['notify_failure']:
                client.notify_failure(options.get('failure_code'))
                result = {'status': 'failure_notified', 'failure_code': options['failure_code']}
            else:
                result = client.send(options['archive'], options['expected_sha256'], options['receipt_file'], options['no_notify'])
            return json.dumps(result, ensure_ascii=False)
        except RecoveryError as error:
            raise CommandError(str(error)) from None
        except Exception:
            raise CommandError('recovery_delivery_failed') from None

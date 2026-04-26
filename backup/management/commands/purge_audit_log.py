"""
Удаляет старые записи django-easy-audit (LoginEvent, CRUDEvent, RequestEvent).

Зачем разные сроки: RequestEvent растёт быстро (одна запись на каждый
HTTP-запрос пользователя) — хранить долго бессмысленно. LoginEvent и CRUDEvent
нужны для разбора инцидентов и аудита, поэтому хранятся 90 дней.

Использование:
    python manage.py purge_audit_log
    python manage.py purge_audit_log --dry-run
    python manage.py purge_audit_log --login-days 180 --crud-days 180 --request-days 7
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger('backup.purge_audit_log')


class Command(BaseCommand):
    help = (
        'Чистит старые записи django-easy-audit: LoginEvent и CRUDEvent старше '
        '90 дней (по умолчанию), RequestEvent старше 1 дня.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--login-days', type=int, default=90,
                            help='Срок хранения LoginEvent (default: 90)')
        parser.add_argument('--crud-days', type=int, default=90,
                            help='Срок хранения CRUDEvent (default: 90)')
        parser.add_argument('--request-days', type=int, default=1,
                            help='Срок хранения RequestEvent (default: 1)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать сколько будет удалено, но не удалять')

    def handle(self, *args, **options):
        from easyaudit.models import CRUDEvent, LoginEvent, RequestEvent

        dry = options['dry_run']
        now = timezone.now()

        targets = [
            ('LoginEvent', LoginEvent, 'datetime', options['login_days']),
            ('CRUDEvent', CRUDEvent, 'datetime', options['crud_days']),
            ('RequestEvent', RequestEvent, 'datetime', options['request_days']),
        ]

        total_deleted = 0
        for name, model, dt_field, days in targets:
            cutoff = now - timedelta(days=days)
            qs = model.objects.filter(**{f'{dt_field}__lt': cutoff})
            count = qs.count()

            if dry:
                msg = f'[dry-run] {name}: было бы удалено {count} (старше {days}д, до {cutoff:%Y-%m-%d %H:%M})'
                self.stdout.write(msg)
                logger.info(msg)
                continue

            if count == 0:
                msg = f'{name}: нечего удалять (порог {days}д)'
                self.stdout.write(msg)
                logger.info(msg)
                continue

            qs.delete()
            total_deleted += count
            msg = f'{name}: удалено {count} записей старше {days}д'
            self.stdout.write(self.style.SUCCESS(f'✓ {msg}'))
            logger.info(msg)

        if not dry:
            logger.info('purge_audit_log completed: deleted %d records total', total_deleted)

"""
Удаляет старые записи django-easy-audit (LoginEvent, CRUDEvent, RequestEvent).

Зачем разные сроки: RequestEvent растёт быстро (одна запись на каждый
HTTP-запрос пользователя) — хранить долго бессмысленно. LoginEvent и CRUDEvent
нужны для разбора инцидентов, аудита и аналитики сотрудников и правок
(раздел «Аналитика»), поэтому хранятся 365 дней. Объём небольшой:
~1 000 CRUD и ~120 входов в месяц.

Перед удалением вчерашний день сворачивается в дневной агрегат активности
сотрудников (summaries.UserDailyActivity): просмотры страниц хранятся 1 день,
и без агрегата история присутствия терялась бы. Если сборка агрегата упала,
RequestEvent в этот раз не удаляется — лучше лишний день журнала, чем потерянный.

Удаление идёт партиями: easy-audit подписан на post_delete, поэтому Django не
может сделать быстрый DELETE и загружает удаляемые объекты в память. Одним
qs.delete() на сотнях тысяч RequestEvent легко съесть всю RAM сервера.

Использование:
    python manage.py purge_audit_log
    python manage.py purge_audit_log --dry-run
    python manage.py purge_audit_log --login-days 180 --crud-days 180 --request-days 7
    python manage.py purge_audit_log --batch-size 2000
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger('backup.purge_audit_log')


class Command(BaseCommand):
    help = (
        'Чистит старые записи django-easy-audit: LoginEvent и CRUDEvent старше '
        '365 дней (по умолчанию), RequestEvent старше 1 дня.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--login-days', type=int, default=365,
                            help='Срок хранения LoginEvent (default: 365)')
        parser.add_argument('--crud-days', type=int, default=365,
                            help='Срок хранения CRUDEvent (default: 365)')
        parser.add_argument('--request-days', type=int, default=1,
                            help='Срок хранения RequestEvent (default: 1)')
        parser.add_argument('--batch-size', type=int, default=5000,
                            help='Сколько записей удалять за один запрос (default: 5000)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать сколько будет удалено, но не удалять')

    def handle(self, *args, **options):
        from easyaudit.models import CRUDEvent, LoginEvent, RequestEvent

        dry = options['dry_run']
        batch_size = options['batch_size']
        if batch_size < 1:
            raise CommandError('--batch-size должен быть положительным')
        now = timezone.now()

        aggregate_ok = True
        if not dry:
            aggregate_ok = self._aggregate_user_activity()

        targets = [
            ('LoginEvent', LoginEvent, 'datetime', options['login_days']),
            ('CRUDEvent', CRUDEvent, 'datetime', options['crud_days']),
            ('RequestEvent', RequestEvent, 'datetime', options['request_days']),
        ]

        total_deleted = 0
        for name, model, dt_field, days in targets:
            if name == 'RequestEvent' and not aggregate_ok:
                msg = 'RequestEvent: не удаляем — дневной агрегат активности не собран (см. ошибку выше)'
                self.stdout.write(self.style.WARNING(msg))
                logger.warning(msg)
                continue
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

            deleted = self._delete_in_batches(model, qs, batch_size)
            total_deleted += deleted
            msg = f'{name}: удалено {deleted} записей старше {days}д'
            self.stdout.write(self.style.SUCCESS(f'✓ {msg}'))
            logger.info(msg)

        if not dry:
            logger.info('purge_audit_log completed: deleted %d records total', total_deleted)

    def _aggregate_user_activity(self):
        from summaries.services import user_activity

        day = user_activity.yesterday()
        try:
            report = user_activity.aggregate_day(day)
        except Exception:  # noqa: BLE001 — чистку журнала не роняем, но просмотры сохраняем
            logger.exception('purge_audit_log: не удалось собрать UserDailyActivity за %s', day)
            self.stdout.write(self.style.ERROR(f'Агрегат активности за {day} не собран'))
            return False
        self.stdout.write(f"Агрегат активности за {day}: сотрудников {report.get('users', 0)}")
        return True

    @staticmethod
    def _delete_in_batches(model, qs, batch_size):
        deleted = 0
        while True:
            pks = list(qs.order_by('pk').values_list('pk', flat=True)[:batch_size])
            if not pks:
                return deleted
            model.objects.filter(pk__in=pks).delete()
            deleted += len(pks)

"""
Собирает дневной агрегат активности сотрудников (UserDailyActivity) из журналов
easy-audit. Идемпотентно: день можно пересобрать повторно.

Каждую ночь вызывается из purge_audit_log перед чисткой журнала (вчерашний день).
Вручную — для истории по входам и изменениям (хранятся 365 дней).

Использование:
    python manage.py aggregate_user_activity                      # вчера
    python manage.py aggregate_user_activity --date 2026-09-24
    python manage.py aggregate_user_activity --from 2026-06-29 --to 2026-09-24
    python manage.py aggregate_user_activity --backfill           # с первого дня журнала по вчера
"""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from summaries.services import user_activity


def _parse(value, label):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as error:
        raise CommandError(f'Некорректная дата в {label}: {value!r} (нужен формат ГГГГ-ММ-ДД)') from error


class Command(BaseCommand):
    help = 'Собирает дневной агрегат активности сотрудников (UserDailyActivity) из журналов easy-audit.'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Один день, ГГГГ-ММ-ДД (по умолчанию — вчера)')
        parser.add_argument('--from', dest='date_from', help='Начало периода, ГГГГ-ММ-ДД')
        parser.add_argument('--to', dest='date_to', help='Конец периода, ГГГГ-ММ-ДД (по умолчанию — вчера)')
        parser.add_argument('--backfill', action='store_true', help='С первого дня журнала по вчера')

    def handle(self, *args, **options):
        yesterday = user_activity.yesterday()
        if options['backfill']:
            first_day = user_activity.earliest_audit_day()
            if first_day is None:
                self.stdout.write('Журнал пуст — собирать нечего.')
                return
            last_day = yesterday
        elif options['date_from']:
            first_day = _parse(options['date_from'], '--from')
            last_day = _parse(options['date_to'], '--to') if options['date_to'] else yesterday
        else:
            first_day = last_day = _parse(options['date'], '--date') if options['date'] else yesterday

        if first_day > last_day:
            raise CommandError('Начало периода позже конца')

        reports = user_activity.aggregate_range(first_day, last_day)
        for report in reports:
            source = 'просмотры + входы + изменения' if report.get('with_request_data') else 'только входы и изменения'
            self.stdout.write(
                f"{report['date']:%Y-%m-%d}: сотрудников {report.get('users', 0)}, "
                f"новых {report.get('created', 0)}, обновлено {report.get('updated', 0)} ({source})"
            )
        self.stdout.write(self.style.SUCCESS(f'Готово: дней {len(reports)}.'))

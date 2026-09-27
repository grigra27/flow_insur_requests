"""Пересчитать марку, класс и вид машины по справочнику техники (tariffs_analytics_2026_09, шаг 1).

Запускать после пополнения словаря в `insurance_requests/object_catalog.py`. По умолчанию — отчёт,
запись — с --apply. Пишет через bulk_update: журнал правок и сигналы не затрагиваются (это вычисляемые поля).
"""
from collections import Counter

from django.core.management.base import BaseCommand

from insurance_requests.models import InsuranceRequest
from insurance_requests.object_catalog import OBJECT_CLASS_LABELS, classify_request

FIELDS = ('object_brand', 'object_class', 'machine_kind')


class Command(BaseCommand):
    help = 'Пересчитать марку, класс и вид машины заявок по справочнику техники (по умолчанию — только отчёт).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения.')
        parser.add_argument('--show', type=int, default=20, help='Сколько изменений и нераспознанных показать.')

    def handle(self, *args, **options):
        changed, unknown, classes = [], [], Counter()
        requests = list(InsuranceRequest.objects.all().order_by('pk'))
        for insurance_request in requests:
            info = classify_request(insurance_request)
            classes[info.object_class] += 1
            new = (info.brand, info.object_class, info.machine_kind)
            old = tuple(getattr(insurance_request, field) for field in FIELDS)
            if new != old:
                changed.append((insurance_request, old, new))
                insurance_request.object_brand, insurance_request.object_class, insurance_request.machine_kind = new
            if not info.brand:
                unknown.append(insurance_request)

        self.stdout.write(f'Заявок: {len(requests)}; марка узнана: {len(requests) - len(unknown)}; изменится: {len(changed)}')
        self.stdout.write('Классы: ' + ', '.join(f'{OBJECT_CLASS_LABELS[key]} {count}' for key, count in classes.most_common()))
        for insurance_request, old, new in changed[:options['show']]:
            self.stdout.write(f'  #{insurance_request.pk}: {old} → {new}')
        self.stdout.write('Марка не узнана (пополните словарь, если это техника):')
        for insurance_request in unknown[:options['show']]:
            self.stdout.write(f'  #{insurance_request.pk} [{insurance_request.insurance_type}] {insurance_request.object_summary[:90]}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Только отчёт. Для записи запустите с --apply.'))
            return
        InsuranceRequest.objects.bulk_update([item[0] for item in changed], FIELDS, batch_size=200)
        self.stdout.write(self.style.SUCCESS(f'Обновлено заявок: {len(changed)}'))

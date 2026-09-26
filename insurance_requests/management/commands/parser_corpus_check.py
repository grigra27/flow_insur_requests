"""
Проверка парсера V2 на реальном корпусе заявок — только чтение.
docs/improvement_plans/analytics_redesign_2026_09.md, задачи 5.5 и 6.9.

Для каждой V2-заявки с исходным Excel-файлом заново разбирает файл текущим
парсером и сравнивает по полям три значения:
- «при загрузке» — что парсер выдал тогда (снимок additional_data.parser_v2);
- «сейчас» — что выдаёт текущий код на том же файле;
- «итог» — значение в заявке после правок сотрудников.

Совпадение с итогом «при загрузке» и «сейчас» показывает, сколько ручных правок
убрало бы текущее состояние парсера. Поля объекта сравниваются по номеру объекта;
если текущий парсер выделяет в файле другое число объектов, чем при загрузке,
поля объекта этой заявки пропускаются (иначе сравнивались бы разные объекты). Сценарий «Изъятое» (слово в имени файла)
по умолчанию исключён — там расхождения ожидаемы (задача 6.8).

Использование:
    python manage.py parser_corpus_check
    python manage.py parser_corpus_check --field insurance_period   # расхождения по полю
    python manage.py parser_corpus_check --include-seized
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from insurance_requests.edit_tracking import _post_canonical, get_object_field_meta, get_scalar_field_meta
from insurance_requests.forms import parser_v2_object_initial_from_payload
from insurance_requests.models import InsuranceRequest
from insurance_requests.parsers.excel_v2 import ExcelRequestParserV2
from insurance_requests.seized import is_seized_filename

# Не сравниваем: служебное примечание (парсер пишет туда предупреждения), поля объекта
# старого формата и срок ответа (выставляется по умолчанию, не распознаётся).
EXCLUDED_FIELDS = {'notes', 'draft_id', 'skip', 'vehicle_info', 'asset_status', 'response_deadline'}


class Command(BaseCommand):
    help = 'Сверяет парсер V2 с итоговыми значениями заявок на реальных исходных файлах (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--field', help='Показать расхождения по полю (имя поля модели)')
        parser.add_argument('--limit', type=int, default=30, help='Сколько расхождений показать (default: 30)')
        parser.add_argument('--include-seized', action='store_true', help='Включить заявки «Изъятое»')

    def handle(self, *args, **options):
        scalar_meta = {k: v for k, v in get_scalar_field_meta().items() if k not in EXCLUDED_FIELDS}
        object_meta = {k: v for k, v in get_object_field_meta().items() if k not in EXCLUDED_FIELDS}
        meta = {**scalar_meta, **object_meta}

        stats = defaultdict(Counter)
        mismatches = []
        requests_total = Counter()
        parsed_cache = {}

        queryset = InsuranceRequest.objects.filter(parser_confidence__isnull=False).prefetch_related('attachments')
        for insurance_request in queryset.order_by('pk'):
            parser_v2 = (insurance_request.additional_data or {}).get('parser_v2') or {}
            file_name = parser_v2.get('source_file_name') or ''
            if is_seized_filename(file_name) and not options['include_seized']:
                requests_total['исключено: «Изъятое»'] += 1
                continue
            attachment = next(
                (item for item in insurance_request.attachments.all()
                 if (item.original_filename or item.file.name).lower().endswith(('.xls', '.xlsx'))),
                None,
            )
            if attachment is None:
                requests_total['нет исходного файла'] += 1
                continue
            path = attachment.file.path
            if path not in parsed_cache:
                try:
                    parsed_cache[path] = ExcelRequestParserV2().parse(path, original_filename=file_name).data
                except Exception as error:  # noqa: BLE001 — отчёт по корпусу не должен падать на одном файле
                    parsed_cache[path] = error
            current = parsed_cache[path]
            if isinstance(current, Exception):
                requests_total['файл не разобран'] += 1
                continue
            requests_total['проверено'] += 1

            upload = parser_v2.get('original_data') or {}
            position = (insurance_request.item_no or 1) - 1
            current_objects = parser_v2_object_initial_from_payload(
                (current.get('parser_v2_payload') or {}).get('insured_objects') or []
            )
            upload_objects = (parser_v2.get('tracking') or {}).get('object_originals') or []
            if upload_objects and len(current_objects) != len(upload_objects):
                # Объекты группируются по-разному (другая версия группировки одинаковых
                # объектов) — сопоставить по номеру нельзя, поля объекта не сравниваем.
                requests_total['поля объекта не сопоставимы (другая группировка)'] += 1
                current_object = upload_object = {}
            else:
                current_object = current_objects[position] if position < len(current_objects) else {}
                upload_object = upload_objects[position] if position < len(upload_objects) else {}

            all_upload_ok = all_current_ok = True
            for name in meta:
                if name in object_meta:
                    if not current_object and not upload_object:
                        continue
                    upload_value, current_value = upload_object.get(name), current_object.get(name)
                elif name in upload or name in current:
                    upload_value, current_value = upload.get(name), current.get(name)
                else:
                    continue
                final_value = getattr(insurance_request, name, None)
                final = _post_canonical(name, final_value, meta)
                upload_ok = _post_canonical(name, upload_value, meta) == final
                current_ok = _post_canonical(name, current_value, meta) == final
                field_stats = stats[name]
                field_stats['compared'] += 1
                field_stats['upload_ok'] += upload_ok
                field_stats['current_ok'] += current_ok
                all_upload_ok &= upload_ok
                all_current_ok &= current_ok
                if options['field'] == name and not current_ok:
                    mismatches.append((insurance_request.pk, upload_value, current_value, final_value, file_name))
            requests_total['все поля совпали при загрузке'] += all_upload_ok
            requests_total['все поля совпадают сейчас'] += all_current_ok

        checked = requests_total['проверено']
        self.stdout.write(f"Заявок проверено: {checked}")
        for key, value in requests_total.items():
            if key != 'проверено':
                suffix = f' ({value / checked * 100:.0f}%)' if checked and key.startswith('все поля') else ''
                self.stdout.write(f'  {key}: {value}{suffix}')

        self.stdout.write('\nПоле | сравнено | совпадало при загрузке | совпадает сейчас | Δ')
        rows = sorted(stats.items(), key=lambda item: (item[1]['upload_ok'] - item[1]['compared'], item[0]))
        for name, field_stats in rows:
            compared = field_stats['compared']
            upload_miss = compared - field_stats['upload_ok']
            current_miss = compared - field_stats['current_ok']
            if not upload_miss and not current_miss:
                continue
            delta = upload_miss - current_miss
            self.stdout.write(
                f"{name} | {compared} | {field_stats['upload_ok']} (расх. {upload_miss}) | "
                f"{field_stats['current_ok']} (расх. {current_miss}) | {'+' if delta > 0 else ''}{delta}"
            )
        fully_matching = sum(1 for field_stats in stats.values() if field_stats['compared'] == field_stats['current_ok'])
        self.stdout.write(f'Полей без расхождений сейчас: {fully_matching} из {len(stats)}')

        if options['field']:
            self.stdout.write(f"\nРасхождения по «{options['field']}» (заявка | при загрузке | сейчас | итог | файл):")
            for row in mismatches[:options['limit']]:
                self.stdout.write(' | '.join(str(value) for value in row))

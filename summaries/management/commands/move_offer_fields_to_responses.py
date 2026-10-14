"""Уборка данных ответа страховщика (docs/improvement_plans/backlog.md, п. 3; мягкий вариант).

Территория, примечание и исходный файл ответа — одни на страховщика в своде, но хранились в каждой
годовой строке `InsuranceOffer`. Команда копирует их на уровень «Ответа СК» (`InsurerResponse`),
создавая «Ответ СК» там, где его нет. Ничего не удаляет: поля годовых строк остаются архивом.

- территория — первое непустое значение по годам; у всех лет пусто — пусто; у всех лет NULL
  (предложения до сбора территории) — NULL;
- примечание — непустые примечания лет без повторов (сравнение без учёта пробелов), через перевод строки;
- исходный файл — первый непустой файл по годам.

Заполняются только пустые поля «Ответа СК» — повторный запуск безопасен (догоняет предложения,
созданные между запусками). Запись — через QuerySet: без сигналов и журнала правок.

По умолчанию — только отчёт; запись — с --apply.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from summaries.models import InsuranceOffer, InsurerResponse


def _norm(value) -> str:
    return ' '.join((value or '').split())


def company_values(offers) -> dict:
    """Территория, примечание и файл компании в своде по её годовым строкам (offers — по возрастанию года)."""
    territories = [o['coverage_territory'] for o in offers]
    filled = [t.strip() for t in territories if (t or '').strip()]
    if filled:
        territory = filled[0]
    elif any(t is not None for t in territories):
        territory = ''
    else:
        territory = None
    notes, seen = [], set()
    for offer in offers:
        note = (offer['notes'] or '').strip()
        if note and _norm(note) not in seen:
            seen.add(_norm(note))
            notes.append(note)
    source_file = next((o['attachment_file'] for o in offers if o['attachment_file']), '')
    return {
        'coverage_territory': territory,
        'notes': '\n'.join(notes),
        'source_file': source_file,
        'received_at': min(o['received_at'] for o in offers),
    }


def build_plan():
    """[(ключ, существующий ответ или None, {поле: значение})] и счётчики расхождений."""
    groups = defaultdict(list)
    offers = InsuranceOffer.objects.order_by('summary_id', 'company_name', 'insurance_year').values(
        'summary_id', 'company_name', 'coverage_territory', 'notes', 'attachment_file', 'received_at')
    for offer in offers:
        groups[(offer['summary_id'], offer['company_name'])].append(offer)
    responses = {(r.summary_id, r.company_name): r for r in InsurerResponse.objects.all()}

    plan, conflicts = [], Counter()
    for key, company_offers in groups.items():
        values = company_values(company_offers)
        response = responses.get(key)
        if response is None:
            plan.append((key, None, values))
            continue
        changes = {}
        if response.coverage_territory in (None, '') and values['coverage_territory'] not in (None, ''):
            changes['coverage_territory'] = values['coverage_territory']
        elif response.coverage_territory is None and values['coverage_territory'] == '':
            changes['coverage_territory'] = ''
        elif values['coverage_territory'] and _norm(response.coverage_territory) != _norm(values['coverage_territory']):
            conflicts['coverage_territory'] += 1
        if not response.notes.strip() and values['notes']:
            changes['notes'] = values['notes']
        elif values['notes'] and _norm(response.notes) != _norm(values['notes']):
            conflicts['notes'] += 1
        if not response.source_file and values['source_file']:
            changes['source_file'] = values['source_file']
        if changes:
            plan.append((key, response, changes))
    return plan, conflicts, len(groups)


class Command(BaseCommand):
    help = ('Копирует территорию, примечание и исходный файл из годовых предложений в «Ответ СК». '
            'Без --apply — отчёт.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения.')
        parser.add_argument('--samples', type=int, default=5, help='Сколько примеров показать.')

    def handle(self, *args, **options):
        plan, conflicts, pairs = build_plan()
        to_create = [(key, values) for key, response, values in plan if response is None]
        to_update = [(key, response, changes) for key, response, changes in plan if response is not None]
        filled = Counter()
        for _, values in to_create:
            filled['coverage_territory'] += values['coverage_territory'] not in (None, '')
            filled['notes'] += bool(values['notes'])
            filled['source_file'] += bool(values['source_file'])
        for _, _, changes in to_update:
            for field in ('coverage_territory', 'notes', 'source_file'):
                filled[field] += field in changes and changes[field] not in (None, '')

        self.stdout.write(f'Пар «свод + СК» с предложениями: {pairs}')
        self.stdout.write(f'  «Ответ СК» создать: {len(to_create)}, дополнить: {len(to_update)}')
        self.stdout.write(f"  территория: {filled['coverage_territory']}, примечание: {filled['notes']}, "
                          f"исходный файл: {filled['source_file']}")
        if conflicts:
            self.stdout.write(self.style.WARNING(
                f'В «Ответе СК» уже другое значение (оставлено как есть): {dict(conflicts)}'))
        samples = [(key, v) for key, v in to_create if v['notes'] or v['coverage_territory']][:options['samples']]
        for (summary_id, company), values in samples:
            self.stdout.write(f"  свод #{summary_id}, {company}: территория «{_norm(values['coverage_territory'])[:60]}», "
                              f"примечание «{_norm(values['notes'])[:60]}»")

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Только отчёт. Для записи запустите с --apply.'))
            return
        with transaction.atomic():
            for (summary_id, company), values in to_create:
                received_at = values.pop('received_at')
                response = InsurerResponse.objects.create(summary_id=summary_id, company_name=company, **values)
                # «Получен» — когда пришло первое предложение, а не дата переноса
                InsurerResponse.objects.filter(pk=response.pk).update(received_at=received_at)
            for _, response, changes in to_update:
                InsurerResponse.objects.filter(pk=response.pk).update(**changes)
        self.stdout.write(self.style.SUCCESS(f'Создано: {len(to_create)}, дополнено: {len(to_update)}'))

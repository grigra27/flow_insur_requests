"""Фаза D3 депрекейта legacy-полей объекта (docs/improvement_plans/backlog.md, п. 1).

Копирует данные старых полей в структурные — ничего не удаляет:
- `object_description` ← `vehicle_info`, если описания нет (201 заявка V1 хранит объект только там);
- `condition` ← `asset_status` («новое» → new, «б/у» → used), если состояние не заполнено.

Старые столбцы остаются как замороженный архив. Запись — через QuerySet.update(): без сигналов
(журнал правок оператора не пополняется) и без смены «даты изменения» заявки.

По умолчанию — только отчёт; запись — с --apply.
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from insurance_requests.models import InsuranceRequest
from insurance_requests.object_condition import condition_from_asset_status


def build_plan():
    """[(заявка, {поле: новое значение})] и значения asset_status, которые не разобраны."""
    plan, unmapped = [], Counter()
    for request in InsuranceRequest.objects.order_by('pk'):
        changes = {}
        vehicle_info = (request.vehicle_info or '').strip()
        if vehicle_info and not (request.object_description or '').strip():
            changes['object_description'] = vehicle_info
        asset_status = (request.asset_status or '').strip()
        if asset_status and not request.condition:
            condition = condition_from_asset_status(asset_status)
            if condition:
                changes['condition'] = condition
            else:
                unmapped[asset_status] += 1
        if changes:
            plan.append((request, changes))
    return plan, unmapped


def summary_after(request, changes) -> str:
    for field, value in changes.items():
        setattr(request, field, value)
    return request.object_summary


class Command(BaseCommand):
    help = 'Копирует vehicle_info/asset_status в object_description/condition (фаза D3). Без --apply — отчёт.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения.')
        parser.add_argument('--samples', type=int, default=8, help='Сколько примеров «было → стало» показать.')

    def handle(self, *args, **options):
        plan, unmapped = build_plan()
        fields = Counter(field for _, changes in plan for field in changes)
        conditions = Counter(changes['condition'] for _, changes in plan if 'condition' in changes)
        self.stdout.write(f'Заявок к обновлению: {len(plan)}')
        self.stdout.write(f"  object_description ← vehicle_info: {fields['object_description']}")
        self.stdout.write(f"  condition ← asset_status: {fields['condition']} ({dict(conditions)})")
        if unmapped:
            self.stdout.write(self.style.WARNING(f'asset_status не разобран (останется как есть): {dict(unmapped)}'))

        changed_summary = 0
        samples = []
        for request, changes in plan:
            before = request.object_summary
            after = summary_after(InsuranceRequest.objects.get(pk=request.pk), changes)
            if before != after:
                changed_summary += 1
                if len(samples) < options['samples']:
                    samples.append((request.pk, before, after))
        self.stdout.write(f'Сводка объекта изменится у {changed_summary} заявок; примеры:')
        for pk, before, after in samples:
            self.stdout.write(f'  #{pk}: «{before[:90]}»\n        → «{after[:90]}»')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Только отчёт. Для записи запустите с --apply.'))
            return
        with transaction.atomic():
            for request, changes in plan:
                InsuranceRequest.objects.filter(pk=request.pk).update(**changes)
        self.stdout.write(self.style.SUCCESS(f'Обновлено заявок: {len(plan)}'))

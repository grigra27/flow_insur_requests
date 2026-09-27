"""Разовое выравнивание территории страхования по годам компании в своде (решение владельца 2026-09-27).

Территория — одна на страховую компанию в своде (summaries/services/offer_territory.py). До этого
правило не действовало: сотрудники правили территорию у одного года (обычно у 1-го после загрузки
файла), и годы расходились — в Excel-своде у остальных лет выходило «Не указано страховщиком».

Для каждой компании в своде с непустой территорией хотя бы у одного года, где годы расходятся, берётся
текст последнего отредактированного года (по журналу easy-audit; без журнала — года с самым поздним
изменением записи по pk) среди лет с непустой территорией, и он ставится во все годы. По умолчанию —
отчёт, запись — с --apply. Пишет через update(): это исправление данных, а не действие сотрудника.
"""
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from summaries.models import InsuranceOffer


def _norm(value):
    return ' '.join((value or '').split()).casefold()


def _last_edited(offer_ids):
    """{offer_id: время последнего события в журнале}."""
    try:
        from easyaudit.models import CRUDEvent
    except ImportError:
        return {}
    content_type = ContentType.objects.get_for_model(InsuranceOffer)
    latest = {}
    for object_id, moment in CRUDEvent.objects.filter(
        content_type=content_type, object_id__in=[str(pk) for pk in offer_ids],
    ).values_list('object_id', 'datetime'):
        key = int(object_id)
        if key not in latest or moment > latest[key]:
            latest[key] = moment
    return latest


def build_plan():
    groups = defaultdict(list)
    for offer in InsuranceOffer.objects.order_by('insurance_year'):
        groups[(offer.summary_id, offer.company_name)].append(offer)
    candidates = {}
    for key, offers in groups.items():
        filled = [offer for offer in offers if (offer.coverage_territory or '').strip()]
        if not filled or len({_norm(offer.coverage_territory) for offer in offers}) == 1 and all(
                offer.coverage_territory is not None for offer in offers):
            continue
        candidates[key] = (offers, filled)
    edited = _last_edited([offer.pk for offers, _ in candidates.values() for offer in offers])
    plan = []
    for key, (offers, filled) in sorted(candidates.items()):
        source = max(filled, key=lambda offer: (edited.get(offer.pk) is not None, edited.get(offer.pk), offer.pk))
        targets = [offer for offer in offers if offer.coverage_territory != source.coverage_territory]
        if targets:
            plan.append({'key': key, 'source': source, 'targets': targets})
    return plan


class Command(BaseCommand):
    help = 'Выровнять территорию страхования по годам компании в своде (по умолчанию — только отчёт).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения.')

    def handle(self, *args, **options):
        plan = build_plan()
        self.stdout.write(f'Компаний в сводах с расхождением территории по годам: {len(plan)}')
        for item in plan:
            summary_id, company = item['key']
            source = item['source']
            self.stdout.write(f'  свод #{summary_id}, {company}: берём {source.insurance_year} год — '
                              f'«{" ".join(source.coverage_territory.split())[:90]}»')
            for offer in item['targets']:
                current = offer.coverage_territory
                shown = 'нет данных (до сбора территории)' if current is None else (
                    '«' + ' '.join(current.split())[:60] + '»' if current.strip() else 'пусто')
                self.stdout.write(f'      {offer.insurance_year} год: {shown} → как {source.insurance_year} год')
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Только отчёт. Для записи запустите с --apply.'))
            return
        updated = 0
        with transaction.atomic():
            for item in plan:
                updated += InsuranceOffer.objects.filter(pk__in=[offer.pk for offer in item['targets']]) \
                    .update(coverage_territory=item['source'].coverage_territory)
        self.stdout.write(self.style.SUCCESS(f'Обновлено предложений: {updated}'))

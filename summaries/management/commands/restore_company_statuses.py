"""Восстановить статусы СК для сводов, созданных до запуска статусов (analytics_redesign_2026_09, задача 2.5).

- «Предложение» — по наличию предложений СК в своде.
- «Отказ» — по общему примечанию свода: фрагменты со словом «отказ» («СК Абсолют, Зетта - ОТКАЗ»,
  «Зетта, Ренессанс - отказ от страхования»), СК ищутся по названию и сокращениям (РГС, ПСБ, …).
- «Запрошена» (нет ответа) — фрагменты «тариф не предоставил», «не ответил», «без ответа».
- Остальные СК — без строки («неизвестно»): что было на самом деле, не восстановить.

Строки помечаются `restored=True`, создаются bulk_create (в журнал StatusEvent не пишутся — это не
смены статуса), `company_statuses_required` у старых сводов не включается: восстановление не
блокирует смену статуса. Уже существующие строки не меняются.

По умолчанию — только отчёт (dry-run); запись — с --apply.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary

DECLINED_RE = re.compile(r'отказ', re.IGNORECASE)
NO_ANSWER_RE = re.compile(r'не\s+предостав|не\s+ответ|без\s+ответа|не\s+дал[аи]?\s', re.IGNORECASE)
FRAGMENT_SPLIT_RE = re.compile(r'[\n\r]+|(?<=[.;])\s+|\s+/\s+')

# Сокращения и варианты написания в примечаниях → название в справочнике.
ALIASES = {
    'РГС': 'Росгосстрах',
    'ПСБ': 'ПСБ-страхование',
    'Совкомбанк': 'Совкомбанк СК',
    'Ингос': 'Ингосстрах',
    'Ренесанс': 'Ренессанс',
    'Альфастрахование': 'Альфа',
    'Альфа-страхование': 'Альфа',
}


def _company_patterns():
    names = {name: name for name in InsuranceCompany.objects.filter(is_other=False).values_list('name', flat=True)}
    names.update({alias: target for alias, target in ALIASES.items() if target in names.values()})
    # длинные варианты раньше коротких, чтобы «ПСБ-страхование» не распознавалось как «ПСБ» дважды
    return [
        (re.compile(r'(?<![\w-])' + re.escape(variant) + r'(?![\w])', re.IGNORECASE), target)
        for variant, target in sorted(names.items(), key=lambda item: -len(item[0]))
    ]


def companies_in(text, patterns):
    found = []
    for pattern, target in patterns:
        if pattern.search(text) and target not in found:
            found.append(target)
    return found


def parse_notes(notes, patterns):
    """(отказавшие СК, СК без ответа) из общего примечания свода."""
    declined, no_answer = [], []
    carry = None  # «отказы от Страховщиков» + список СК на следующей строке
    for fragment in FRAGMENT_SPLIT_RE.split(notes or ''):
        found = companies_in(fragment, patterns)
        if DECLINED_RE.search(fragment):
            bucket = declined
        elif NO_ANSWER_RE.search(fragment):
            bucket = no_answer
        elif carry is not None and found:
            bucket = carry
        else:
            carry = None
            continue
        carry = bucket if not found else None
        for company in found:
            if company not in bucket:
                bucket.append(company)
    return declined, [company for company in no_answer if company not in declined]


def build_plan():
    """{summary_id: {company_name: status}} для старых сводов; и список примечаний с «отказ» без найденных СК."""
    patterns = _company_patterns()
    offered = defaultdict(set)
    for summary_id, company_name in InsuranceOffer.objects.values_list('summary_id', 'company_name'):
        offered[summary_id].add(company_name)

    plan, unparsed = {}, []
    summaries = InsuranceSummary.objects.filter(company_statuses_required=False).order_by('pk')
    for summary in summaries.only('pk', 'notes'):
        statuses = {name: 'offered' for name in offered.get(summary.pk, ())}
        declined, no_answer = parse_notes(summary.notes, patterns)
        for company in declined:
            statuses.setdefault(company, 'declined')  # есть предложение — оно важнее
        for company in no_answer:
            statuses.setdefault(company, 'requested')
        if DECLINED_RE.search(summary.notes or '') and not declined:
            unparsed.append((summary.pk, summary.notes))
        if statuses:
            plan[summary.pk] = statuses
    return plan, unparsed


class Command(BaseCommand):
    help = 'Восстановить статусы СК старых сводов по предложениям и примечаниям (по умолчанию — только отчёт).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать восстановленные статусы.')
        parser.add_argument('--show', type=int, default=15, help='Сколько сводов показать в отчёте.')

    def handle(self, *args, **options):
        plan, unparsed = build_plan()
        totals = Counter(status for statuses in plan.values() for status in statuses.values())
        by_company = defaultdict(Counter)
        for statuses in plan.values():
            for company, status in statuses.items():
                by_company[company][status] += 1

        self.stdout.write(f'Старых сводов со статусами к восстановлению: {len(plan)}')
        self.stdout.write(f'  предложение: {totals["offered"]}, отказ: {totals["declined"]}, '
                          f'запрошена (нет ответа): {totals["requested"]}')
        self.stdout.write('По СК (предложение / отказ / нет ответа):')
        for company, counts in sorted(by_company.items(), key=lambda item: -sum(item[1].values())):
            self.stdout.write(f'  {company}: {counts["offered"]} / {counts["declined"]} / {counts["requested"]}')
        notes = dict(InsuranceSummary.objects.filter(pk__in=list(plan)).values_list('pk', 'notes'))
        shown = 0
        self.stdout.write('Примеры разбора примечаний:')
        for summary_id, statuses in sorted(plan.items(), reverse=True):
            parsed = {company: status for company, status in statuses.items() if status != 'offered'}
            if parsed and shown < options['show']:
                shown += 1
                self.stdout.write(f'  #{summary_id}: {" ".join((notes.get(summary_id) or "").split())[:110]}')
                self.stdout.write(f'      → {", ".join(f"{c}: {s}" for c, s in sorted(parsed.items()))}')
        self.stdout.write(f'Примечаний со словом «отказ», где СК не найдены: {len(unparsed)}')
        for summary_id, text in unparsed[:options['show']]:
            self.stdout.write(f'  #{summary_id}: {" ".join((text or "").split())[:140]}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Только отчёт. Для записи запустите с --apply.'))
            return

        from summaries.models import SummaryCompanyStatus

        companies = {company.name: company for company in InsuranceCompany.objects.all()}
        created = 0
        with transaction.atomic():
            existing = set(SummaryCompanyStatus.objects.values_list('summary_id', 'company__name'))
            rows = [
                SummaryCompanyStatus(summary_id=summary_id, company=companies[company], status=status, restored=True)
                for summary_id, statuses in plan.items()
                for company, status in statuses.items()
                if company in companies and (summary_id, company) not in existing
            ]
            SummaryCompanyStatus.objects.bulk_create(rows)
            created = len(rows)
        self.stdout.write(self.style.SUCCESS(f'Записано строк статусов: {created}'))

"""Перенос ОСВР из примечаний страховщиков в поле «Ответа СК» (решение владельца 2026-10-15).

До блока «Риски ОСВР» страховщики писали про ОСВР в примечании: «без ОСВР», «с ОСВР», «С ОСВР (без риска
БПЛА)», «вариант 2 с ОСВР. Ограничения по ОСВР: …», «Риски ОСВР не включены». Команда разбирает такие
фразы и заполняет `osvr_status` (и `osvr_terms` — ограничения), только если поле ещё пустое. Неоднозначные
примечания (и «с», и «без» без указания варианта) не трогает и показывает в отчёте. Примечание не меняется.
Запись — через QuerySet.update(): без сигналов и смены «даты изменения».

По умолчанию — только отчёт; запись — с --apply.
"""
from __future__ import annotations

import re
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from summaries.models import InsurerResponse
from summaries.response_sections import OSVR_INCLUDED, OSVR_LIMITED, OSVR_NONE, OSVR_VARIANT_2

OSVR = r'(?:рисками\s+|риски\s+)?о\.?\s*с\.?\s*в\.?\s*р\.?'
MENTION = re.compile(r'о\.?\s*с\.?\s*в\.?\s*р', re.I)
VARIANT_2 = re.compile(rf'(?:вариант\s*(?:№\s*)?2|2\s*-?\s*(?:й\s*)?вариант)\s*[-—:]?\s*с\s+{OSVR}', re.I)
NONE = re.compile(rf'без\s+{OSVR}|о\.?\s*с\.?\s*в\.?\s*р\.?\s+не\s+включ', re.I)
WITH = re.compile(rf'(?<!без\s)\bс\s+{OSVR}(?:\s*\(([^)]*)\))?', re.I)
LIMITS = re.compile(r'ограничени[яе]\s+по\s+о\.?\s*с\.?\s*в\.?\s*р\.?\s*:\s*(.+)', re.I | re.S)


def parse(notes: str):
    """(статус, ограничения) по тексту примечания; (None, '') — ОСВР не упомянут или неоднозначно."""
    text = ' '.join((notes or '').split())
    if not MENTION.search(text):
        return None, ''
    limits = LIMITS.search(text)
    # примечание бывает продублировано («…Ограничения по ОСВР: … вариант 2 с ОСВР. Ограничения по ОСВР: …») —
    # берём ограничения до первого повтора
    terms = re.split(rf'(?:вариант\s*2\s*с\s+{OSVR}\s*)?ограничени[яе]\s+по\s+{OSVR}\s*:', limits.group(1),
                     flags=re.I)[0].strip() if limits else ''
    if VARIANT_2.search(text):
        return OSVR_VARIANT_2, terms
    with_match, none_match = WITH.search(text), NONE.search(text)
    if with_match and none_match:
        return None, ''
    if with_match:
        brackets = (with_match.group(1) or '').strip()
        if brackets or terms:
            return OSVR_LIMITED, brackets or terms
        return OSVR_INCLUDED, ''
    if none_match:
        return OSVR_NONE, ''
    return None, ''


class Command(BaseCommand):
    help = 'Заполняет «Риски ОСВР» в «Ответах СК» по примечаниям страховщиков. Без --apply — отчёт.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения.')

    def handle(self, *args, **options):
        plan, unparsed, mentioned = [], [], 0
        for response in InsurerResponse.objects.exclude(notes='').order_by('summary_id', 'company_name'):
            if not MENTION.search(response.notes):
                continue
            mentioned += 1
            if response.osvr_status:
                continue
            status, terms = parse(response.notes)
            if status is None:
                unparsed.append(response)
            else:
                plan.append((response, status, terms))

        statuses = Counter(status for _, status, _ in plan)
        self.stdout.write(f'Ответов с ОСВР в примечании: {mentioned}, к заполнению: {len(plan)} {dict(statuses)}')
        for response, status, terms in plan:
            self.stdout.write(f'  свод #{response.summary_id}, {response.company_name}: {status}'
                              + (f' — «{terms[:70]}»' if terms else ''))
        if unparsed:
            self.stdout.write(self.style.WARNING(f'Не разобрано (оставлено пустым): {len(unparsed)}'))
            for response in unparsed:
                self.stdout.write(f"  свод #{response.summary_id}, {response.company_name}: "
                                  f"«{' '.join(response.notes.split())[:120]}»")
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Только отчёт. Для записи запустите с --apply.'))
            return
        with transaction.atomic():
            for response, status, terms in plan:
                InsurerResponse.objects.filter(pk=response.pk).update(osvr_status=status, osvr_terms=terms)
        self.stdout.write(self.style.SUCCESS(f'Заполнено: {len(plan)}'))

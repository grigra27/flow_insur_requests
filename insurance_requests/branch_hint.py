"""Подсказка филиала по истории менеджера лизинговой компании.

docs/improvement_plans/analytics_redesign_2026_09.md, задача 6.7. Если парсер не нашёл
филиал ни в бланке, ни в коде номера ДФА (бланки Санкт-Петербурга его не содержат),
предлагаем филиал, в котором этот менеджер работал во всех прошлых заявках.
Подставляется в форму превью с явной пометкой — сотрудник проверяет, не молча.

Менеджер сравнивается по фамилии и первой букве имени: одно лицо пишут по-разному
(«Бурак А.», «Бурак А.В. (менеджер УКО)», «УВОЛ. Таралов Э.В.»). Менеджеры головного
офиса работают с разными филиалами (Овдина Е.М. — 8 филиалов) — для них подсказки нет.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Optional, Tuple

MIN_HISTORY_REQUESTS = 2
_PREFIX_RE = re.compile(r'^\s*увол\.?\s*', re.IGNORECASE)


def manager_key(name: str) -> Optional[Tuple[str, str]]:
    """(фамилия, первая буква имени) в нижнем регистре или None."""
    text = _PREFIX_RE.sub('', (name or '').split('(')[0]).replace('ё', 'е').replace('Ё', 'Е')
    tokens = [token for token in re.split(r'[\s.]+', text) if token]
    if not tokens:
        return None
    surname = tokens[0].lower()
    initial = tokens[1][0].lower() if len(tokens) > 1 else ''
    return surname, initial


def suggest_branch(manager_name: str) -> Optional[Tuple[str, int]]:
    """(филиал, число прошлых заявок) — если у менеджера в истории ровно один филиал."""
    from .models import InsuranceRequest

    key = manager_key(manager_name)
    if key is None:
        return None
    branches: dict = defaultdict(Counter)
    # Сравниваем в Python: icontains в SQLite не учитывает регистр кириллицы; заявок — сотни.
    surname_rows = InsuranceRequest.objects.exclude(branch='').exclude(manager_name='').values_list(
        'manager_name', 'branch',
    )
    for name, branch in surname_rows:
        if manager_key(name) == key:
            branches[key][branch] += 1
    history = branches.get(key)
    if not history or len(history) != 1:
        return None
    branch, count = next(iter(history.items()))
    if count < MIN_HISTORY_REQUESTS:
        return None
    return branch, count


def apply_branch_hint(parse_result) -> None:
    """Подставляет филиал по истории менеджера в результат разбора, если филиала нет."""
    data = parse_result.data
    if data.get('branch') or not data.get('manager_name'):
        return
    hint = suggest_branch(data['manager_name'])
    if hint is None:
        return
    branch, count = hint
    data['branch'] = branch
    parse_result.source_map['branch'] = 'история менеджера'
    parse_result.warnings.append({
        'level': 'check',
        'field': 'branch',
        'message': f'Филиал в бланке не указан — подставлен по истории менеджера «{data["manager_name"]}»: '
                   f'все его прошлые заявки ({count}) из филиала «{branch}». Проверьте.',
        'source': 'история менеджера',
    })

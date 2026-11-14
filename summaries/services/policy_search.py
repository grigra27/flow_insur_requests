"""Ограниченный поиск сделок для ручной привязки уже оформленного полиса.

Нечёткое совпадение помогает выбрать кандидата, но не устанавливает связь и не
меняет исходные ДФА. Ранжирование и пагинация выполняются в БД без чтения оферт.
"""
import re

from django.db.models import Case, IntegerField, Q, Value, When

from summaries.models import InsuranceSummary


PAGE_SIZE = 20
MAX_PAGE = 10000
DASHES = '-‐‑‒–—−'
SEPARATOR = rf'\s*[{re.escape(DASHES)}/]\s*'
PREFIX = rf'(?:[A-Za-zА-Яа-яЁё]+\s*(?:[{re.escape(DASHES)}/]\s*)?)?'
NO_MATCH = Q(pk__in=[])


def parse_search_params(params, query_length=0):
    if query_length > 4096:
        raise ValueError('invalid_query')
    result = {}
    for name, limit in (('dfa', 100), ('inn', 12), ('q', 100)):
        values = params.getlist(name)
        value = values[0] if values else ''
        if len(values) > 1 or len(value) > limit or any(ord(c) < 32 for c in value):
            raise ValueError('invalid_query')
        result[name] = value.strip()
    if result['inn'] and not re.fullmatch(r'[0-9]{1,12}', result['inn']):
        raise ValueError('invalid_query')
    hints = params.getlist('summary_ids')
    raw_ids = hints[0] if hints else ''
    if len(hints) > 1 or len(raw_ids) > 399:
        raise ValueError('invalid_summary_ids')
    parts = raw_ids.split(',') if raw_ids else []
    if len(parts) > 20 or any(
        not re.fullmatch(r'[0-9]{1,19}', value) or not 0 < int(value) < 2**63
        for value in parts
    ):
        raise ValueError('invalid_summary_ids')
    result['summary_ids'] = [int(value) for value in parts]
    if len(set(result['summary_ids'])) != len(parts):
        raise ValueError('invalid_summary_ids')
    pages = params.getlist('page')
    page = pages[0] if pages else '1'
    if len(pages) > 1 or not re.fullmatch(r'[0-9]{1,5}', page) or not 1 <= int(page) <= MAX_PAGE:
        raise ValueError('invalid_page')
    result['page'] = int(page)
    return result


def _dfa_conditions(value):
    """Exact presentation, full numeric structure, then missing suffix only."""
    value = ' '.join(value.split()).upper()
    if not value or 'ПРЕДВАР' in value or not re.search(r'[0-9]', value):
        return NO_MATCH, NO_MATCH, NO_MATCH
    value = re.sub(rf'\s*([{re.escape(DASHES)}/])\s*', r'\1', value)
    # Exact matching retains all letters, suffixes, leading zeroes and slash/dash.
    pattern = ''.join(
        rf'\s*[{re.escape(DASHES)}]\s*' if char in DASHES else
        r'\s*/\s*' if char == '/' else r'\s+' if char == ' ' else re.escape(char)
        for char in value
    )
    exact = Q(request__dfa_number__iregex=rf'^\s*{pattern}\s*$')
    if not re.fullmatch(rf'{PREFIX}[0-9]+(?:{SEPARATOR}[0-9]+)*', value):
        return exact, NO_MATCH, NO_MATCH
    parts = re.findall(r'[0-9]+', value)
    not_preliminary = ~Q(request__dfa_number__iregex='ПРЕДВАР')
    structure = Q(request__dfa_number__iregex=rf'^\s*{PREFIX}{SEPARATOR.join(parts)}\s*$') & not_preliminary
    # A missing suffix is a weaker suggestion. Different suffixes never match.
    base_tail = rf'(?:{SEPARATOR}[0-9]+)+' if len(parts) == 1 else ''
    base = Q(request__dfa_number__iregex=rf'^\s*{PREFIX}{parts[0]}{base_tail}\s*$') & not_preliminary
    return exact, structure, base


def _manual_condition(query):
    condition = (
        Q(request__dfa_number__icontains=query)
        | Q(request__client_name__icontains=query)
        | Q(request__inn__icontains=query)
    )
    if re.fullmatch(r'[0-9]{1,19}', query) and 0 < int(query) < 2**63:
        condition |= Q(pk=int(query)) | Q(request_id=int(query))
    for match in _dfa_conditions(query):
        condition |= match
    return condition


def search_summaries(*, dfa='', inn='', q='', page=1, summary_ids=()):
    empty = {'results': [], 'page': page, 'has_next': False}
    if not (dfa or inn or q or summary_ids):
        return empty
    exact, structure, base = _dfa_conditions(dfa)
    same_client = Q(request__inn__regex=rf'^\s*{re.escape(inn)}\s*$') if inn else NO_MATCH
    # Known final-DFA groups live in Policies, which derives these hints from q
    # during a manual search and from the policy DFA during automatic selection.
    hinted = Q(pk__in=summary_ids)
    candidates = (_manual_condition(q) if q else exact | structure | base | same_client) | hinted
    summaries = (
        InsuranceSummary.objects.filter(status='completed_accepted')
        .exclude(selected_company__isnull=True).exclude(selected_company='')
        .filter(candidates)
        .select_related('request')
        .only(
            'id', 'request_id', 'selected_company', 'completed_at',
            'request__id', 'request__dfa_number', 'request__client_name', 'request__inn',
            'request__insurance_type', 'request__brand', 'request__model',
            'request__object_description', 'request__source_object_count',
            'request__item_no', 'request__item_count',
        )
        .annotate(
            match_rank=Case(
                When(exact, then=Value(0)), When(structure, then=Value(1)),
                When(base, then=Value(2)), When(same_client, then=Value(3)),
                default=Value(4), output_field=IntegerField(),
            ),
            client_rank=Case(When(same_client, then=Value(0)), default=Value(1), output_field=IntegerField()),
            hint_rank=Case(When(hinted, then=Value(0)), default=Value(1), output_field=IntegerField()),
        )
        .order_by('hint_rank', 'match_rank', 'client_rank', '-completed_at', '-pk')
    )
    start = (page - 1) * PAGE_SIZE
    rows = list(summaries[start:start + PAGE_SIZE + 1])
    kinds = ('exact', 'structure', 'base', 'client', 'search')
    labels = (
        'Совпал номер ДФА',
        'Совпали числовые части ДФА; отличаются префикс или разделитель',
        'Совпала основная часть ДФА; в одном номере нет окончания',
        'Совпал ИНН; проверьте номер ДФА',
        'Найдено по вашему запросу',
    )
    results = []
    for summary in rows[:PAGE_SIZE]:
        source = summary.request
        label = labels[summary.match_rank]
        if summary.hint_rank == 0 and summary.match_rank >= 3:
            label = 'Предложено по группе ДФА в «Полисах»'
        if summary.match_rank < 3 and summary.client_rank == 0:
            label += '. Совпал ИНН'
        results.append({
            'summary_id': summary.pk, 'request_id': summary.request_id,
            'dfa_number': source.dfa_number or '', 'client_name': source.client_name or '',
            'client_inn': source.inn or '', 'selected_company': summary.selected_company,
            'insurance_type': source.insurance_type or '',
            'property_description': source.object_display_name,
            'accepted_at': summary.completed_at.isoformat() if summary.completed_at else None,
            'source_object_count': source.source_object_count or 1,
            'item_no': source.item_no or 1, 'item_count': source.item_count or 1,
            'match_kind': kinds[summary.match_rank], 'match_label': label,
        })
    return {'results': results, 'page': page, 'has_next': len(rows) > PAGE_SIZE}

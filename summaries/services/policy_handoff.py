"""Данные принятого предложения и обращения к реестру полисов."""
import hashlib
import json
import re
from decimal import Decimal
from urllib.parse import urlsplit

import requests
from django.conf import settings

from core.text import plural_form
from summaries.models import InsurerResponse


class InactiveAcceptance(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def polis_base_url():
    base = settings.FLOW_POLIS_BASE_URL.rstrip('/')
    url = urlsplit(base)
    if (not url.hostname or url.username or url.password or url.path or url.fragment or url.query
            or not (url.scheme == 'https' or
                    (url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}))):
        raise ValueError('Некорректный адрес модуля полисов')
    return base


def can_start(summary):
    return summary.status == 'completed_accepted' and bool(summary.selected_company)


def _offer_rows(offers, variant):
    rows = []
    for offer in offers:
        # У ответа с премией варианта 2 пустая franchise_2 означает нулевую франшизу.
        franchise = getattr(offer, f'franchise_{variant}') or Decimal('0')
        installments = getattr(offer, f'payments_per_year_variant_{variant}')
        by_installments = getattr(offer, f'installment_variant_{variant}')
        rows.append({
            'year': offer.insurance_year,
            'insurance_sum': format(offer.insurance_sum, '.2f'),
            'premium': format(getattr(offer, f'premium_with_franchise_{variant}'), '.2f'),
            'franchise': format(franchise, '.2f'),
            'installments': installments if by_installments else 1,
        })
    return rows


def _response_extras(summary):
    reply = InsurerResponse.objects.filter(summary=summary, company_name=summary.selected_company).first()
    extra = {'deal_note': summary.deal_summary_note} if summary.deal_summary_note else {}
    if not reply:
        return extra
    names = ('coverage_territory', 'notes', 'transport_cost', 'transport_terms', 'smr_status',
             'smr_cost', 'smr_terms', 'inspection_status', 'rnpk_status', 'osvr_status',
             'osvr_terms', 'ce_risks_status', 'ce_risks_comment')
    for name in names:
        value = getattr(reply, name)
        if value in ('', None):
            continue
        extra[name] = str(value)
        if name.endswith('_status'):
            extra[f'{name}_display'] = getattr(reply, f'get_{name}_display')()
    return extra


def snapshot_and_options(summary):
    if not can_start(summary):
        raise InactiveAcceptance('Свод больше не акцептован или не выбрана страховая компания.')
    request = summary.request
    offers = list(summary.offers.filter(is_valid=True, company_name=summary.selected_company).order_by('insurance_year'))
    # Работать с одним прочитанным набором строк: вариант должен быть доступен во всех годах.
    variants = summary.get_company_available_variants(summary.selected_company, offers=offers)
    options = {v: _offer_rows(offers, v) for v in variants}
    variant = summary.selected_franchise_variant
    if variant is None and len(variants) == 1:
        variant = variants[0]
    if variant not in variants:
        variant = None

    year_text = (request.manufacturing_year or '').strip()
    year = int(year_text) if re.fullmatch(r'[0-9]{4}', year_text) else 0
    data = {
        'schema_version': 1, 'source': 'zs', 'summary_id': summary.pk, 'request_id': request.pk,
        'dfa_number': request.dfa_number or '', 'branch': request.branch or '',
        'client_name': request.client_name or '', 'client_inn': request.inn or '',
        'insurance_type': request.insurance_type or '', 'selected_company': summary.selected_company,
        'accepted_at': summary.completed_at.isoformat() if summary.completed_at else None,
        'variant': variant, 'available_variants': variants,
        'insured_party': request.insured_party or '', 'manager_name': request.manager_name or '',
        'property_description': request.object_display_name,
        'property_year': year if 1900 <= year <= 2100 else None,
        'source_object_count': request.source_object_count, 'item_no': request.item_no or 1,
        'item_count': request.item_count or 1,
        'source_batch_id': str(request.source_batch_id) if request.source_batch_id else None,
        'lease_start_date': request.lease_start_date.isoformat() if request.lease_start_date else None,
        'lease_end_date': request.lease_end_date.isoformat() if request.lease_end_date else None,
        'insurance_period': request.insurance_period or '',
        'offers': options.get(variant, []),
        'extras': _response_extras(summary),
    }
    # Уточнение старого акцепта подтверждает суммы из открытой формы выбора.
    material = data if variant else [data, options]
    data['revision'] = digest(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return data, options


def _link_state(summary, data, base, *, allow_start=False):
    mode, links, total = data['mode'], data['links'], data['total']
    if mode not in (None, 'common', 'separate') or not isinstance(links, list) or type(total) is not int:
        raise ValueError('Некорректный ответ реестра')
    result = [
        {'number': row['policy_number'], 'url': f"{base}/policies/{int(row['policy_id'])}/",
         'position': int(row['position'])} for row in links
    ]
    if not result and not can_start(summary):
        return None
    open_url = result[0]['url'] if result else None
    open_label = 'Открыть полис'
    if len(result) > 1:
        open_url = f'{base}/policies/by-summary/{summary.pk}/'
        noun = plural_form(len(result), 'полис', 'полиса', 'полисов')
        open_label = f'Открыть {len(result)} {noun}'
    # Пока полисов нет, количество в своде может измениться после создания плана.
    if not result:
        total = summary.request.source_object_count or 1
    covered = total if result and mode == 'common' else len(result)
    remaining = max(total - covered, 0)
    action_label = 'Создать полис'
    if result and remaining:
        if remaining == 1:
            action_label = 'Оформить последний объект'
        elif remaining % 10 == 1 and remaining % 100 != 11:
            action_label = f'Оформить ещё {remaining} объект'
        else:
            action_label = f'Оформить оставшиеся {remaining}'
    return {
        'links': result, 'total': total, 'mode': mode, 'covered': covered, 'portal_host': urlsplit(base).netloc,
        'remaining': remaining, 'remaining_noun': plural_form(remaining, 'объект', 'объекта', 'объектов'),
        'action_label': action_label,
        'open_url': open_url, 'open_label': open_label,
        'can_continue': allow_start and can_start(summary) and (
            not result or mode == 'separate' and remaining > 0
        ),
    }



def _registry_status(base, summary_ids=None, *, summary_id=None):
    if not settings.FLOW_SERVICE_TOKEN:
        raise ValueError('Не задан ключ служебного обмена')
    options = {
        'headers': {'Authorization': f'Bearer {settings.FLOW_SERVICE_TOKEN}'},
        'timeout': (1.5, 3), 'allow_redirects': False,
    }
    endpoint = f'{base}/internal/flow/v1/summaries'
    if summary_ids is None:
        response = requests.get(f'{endpoint}/{summary_id}/links/', **options)
    else:
        response = requests.post(f'{endpoint}/links/', json={'summary_ids': summary_ids}, **options)
    if response.status_code != 200:
        raise ValueError('Реестр недоступен')
    return response.json()


def policy_links(summary, *, allow_start=False):
    """Реестр полисов — единственный источник связей, включая частично оформленные группы."""
    try:
        base = polis_base_url()
        return _link_state(summary, _registry_status(base, summary_id=summary.pk), base, allow_start=allow_start)
    except (ValueError, KeyError, TypeError, requests.RequestException):
        return {'unavailable': True}


def policy_links_for_page(summaries):
    """Для одной отображаемой страницы списков делаем один запрос в реестр."""
    summaries = list(summaries)
    if not summaries:
        return {}
    try:
        base = polis_base_url()
        response = _registry_status(base, [summary.pk for summary in summaries])
        states = response['summaries']
        return {summary.pk: _link_state(summary, states[str(summary.pk)], base) for summary in summaries}
    except (ValueError, KeyError, TypeError, requests.RequestException):
        return {}

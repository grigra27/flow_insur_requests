"""Переход менеджера из ЗС и закрытый обмен c модулем «Полисы»."""
import json
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from insurance_requests.decorators import has_user_access, user_required
from .models import InsuranceSummary, PolicyHandoffCode, PolicyVariantDecision
from .services.policy_handoff import (
    InactiveAcceptance, can_start, digest, policy_links, policy_links_for_page, polis_base_url,
    snapshot_and_options,
)


def in_pilot(user):
    group = settings.FLOW_HANDOFF_GROUP
    return not group or user.groups.filter(name=group).exists()


def _show_handoff(user):
    return (settings.FLOW_HANDOFF_ENABLED or settings.FLOW_SERVICE_TOKEN) and in_pilot(user)


def handoff_context(user, summary):
    return policy_links(summary) if _show_handoff(user) else None


def handoff_list_context(user, summaries):
    return policy_links_for_page(summaries) if _show_handoff(user) else {}


def employee_handoff(view):
    @wraps(view)
    @user_required
    def wrapper(request, *args, **kwargs):
        if not settings.FLOW_HANDOFF_ENABLED:
            raise Http404
        if not in_pilot(request.user):
            return HttpResponseForbidden('Нет доступа к оформлению из ЗС.')
        return view(request, *args, **kwargs)
    return wrapper


def service_handoff(view):
    @wraps(view)
    @never_cache
    def wrapper(request, *args, **kwargs):
        if not settings.FLOW_HANDOFF_ENABLED:
            raise Http404
        token = settings.FLOW_SERVICE_TOKEN
        auth = request.headers.get('Authorization', '')
        if not token or not constant_time_compare(auth, f'Bearer {token}'):
            return JsonResponse({'error': 'unauthorized'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def _error(request, summary, message, status):
    return render(request, 'summaries/policy_notice.html', {'summary': summary, 'message': message}, status=status)


@never_cache
@require_POST
@employee_handoff
def start(request, summary_id):
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    if not can_start(summary):
        return _error(request, summary, 'Начать оформление можно из акцептованного свода с выбранной компанией.', 409)
    variants = summary.get_company_available_variants(summary.selected_company)
    if len(variants) > 1 and summary.selected_franchise_variant not in variants:
        return redirect('summaries:policy_variant', summary_id=summary.pk)
    return _open_polis(request, summary)


def _open_polis(request, summary):
    try:
        base = polis_base_url()
    except ValueError:
        base = ''
    if not base or not settings.FLOW_SERVICE_TOKEN:
        return _error(request, summary, 'Обмен с модулем «Полисы» не настроен.', 503)
    now = timezone.now()
    PolicyHandoffCode.objects.filter(expires_at__lte=now).delete()
    code = secrets.token_urlsafe(32)
    PolicyHandoffCode.objects.create(
        summary=summary, issued_by=request.user, digest=digest(code), expires_at=now + timedelta(minutes=10),
    )
    response = redirect(f'{base}/flow/from-zs/?{urlencode({"code": code})}')
    response['Referrer-Policy'] = 'no-referrer'
    return response


@csrf_exempt
@service_handoff
@require_POST
def exchange(request):
    try:
        payload = json.loads(request.body)
        code = payload.get('code') if isinstance(payload, dict) else None
    except (UnicodeDecodeError, ValueError):
        code = None
    if not isinstance(code, str) or not 32 <= len(code) <= 128:
        return JsonResponse({'error': 'invalid_code'}, status=400)
    now = timezone.now()
    # Только первый потребитель атомарно погашает действующий код; следующий получает 410.
    key = digest(code)
    with transaction.atomic():
        claimed = PolicyHandoffCode.objects.filter(digest=key, expires_at__gt=now).update(expires_at=now)
        if not claimed:
            return JsonResponse({'error': 'expired_or_used'}, status=410)
        ticket = PolicyHandoffCode.objects.select_related('summary__request', 'issued_by').get(digest=key)
        if not (ticket.issued_by.is_active and has_user_access(ticket.issued_by) and in_pilot(ticket.issued_by)):
            return JsonResponse({'error': 'access_revoked'}, status=403)
        return _current(ticket.summary)


@service_handoff
@require_GET
def current(request, summary_id):
    summary = get_object_or_404(InsuranceSummary.objects.select_related('request'), pk=summary_id)
    return _current(summary)


def _current(summary):
    try:
        snapshot, _ = snapshot_and_options(summary)
    except InactiveAcceptance:
        return JsonResponse({'error': 'inactive_acceptance'}, status=409)
    return JsonResponse({'snapshot': snapshot})


@never_cache
@require_http_methods(['GET', 'POST'])
@employee_handoff
def choose_variant(request, summary_id):
    with transaction.atomic():
        summary = get_object_or_404(InsuranceSummary.objects.select_for_update().select_related('request'), pk=summary_id)
        try:
            snapshot, options = snapshot_and_options(summary)
        except InactiveAcceptance as exc:
            return _error(request, summary, str(exc), 409)
        message = ''
        status = 200
        if request.method == 'POST':
            if snapshot['revision'] != request.POST.get('revision') or snapshot['variant'] is not None:
                message = 'Условия свода изменились. Проверьте актуальный вариант.'
                status = 409
            elif request.POST.get('variant') not in {str(v) for v in options}:
                message = 'Выберите действующий вариант предложения.'
                status = 400
            else:
                variant = int(request.POST['variant'])
                summary.selected_franchise_variant = variant
                summary.save(update_fields=['selected_franchise_variant'])
                PolicyVariantDecision.objects.create(
                    summary=summary, selected_company=summary.selected_company, variant=variant, user=request.user,
                )
                return _open_polis(request, summary)
        return render(request, 'summaries/policy_variant.html', {
            'summary': summary, 'snapshot': snapshot, 'options': options, 'message': message,
        }, status=status)

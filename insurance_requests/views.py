"""
Представления для работы со страховыми заявками
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename
import os
import tempfile
import logging
import uuid

from .models import InsuranceRequest, RequestAttachment
from .forms import (
    ExcelUploadForm,
    InsuranceRequestForm,
    EmailPreviewForm,
    CustomAuthenticationForm,
    RequestStatusForm,
    ParserV2ExcelUploadForm,
    ParserV2PreviewForm,
)
from .decorators import user_required, admin_required, superuser_required
from .security import (
    clear_login_failures,
    format_lockout_message,
    get_login_client_ip,
    get_login_lock_state,
    register_failed_login_attempt,
)
from .parsers.excel_v2 import ExcelRequestParserV2
from core.excel_utils import ExcelReader
from core.templates import EmailTemplateGenerator


logger = logging.getLogger(__name__)
PARSER_V2_SESSION_KEY = 'parser_v2_drafts'


def _get_format_context_for_logging(application_type=None, application_format=None):
    """
    Создает строку контекста формата для логирования в views
    
    Args:
        application_type: Тип заявки ('legal_entity' или 'individual_entrepreneur')
        application_format: Формат заявки ('casco_equipment' или 'property')
        
    Returns:
        str: Строка формата "Format: имущество, Type: заявка от ИП"
    """
    if not application_type or not application_format:
        return "Format: unknown, Type: unknown"
    
    app_type_display = "заявка от ИП" if application_type == 'individual_entrepreneur' else "заявка от юр.лица"
    format_display = "КАСКО/спецтехника" if application_format == 'casco_equipment' else "имущество"
    return f"Format: {format_display}, Type: {app_type_display}"


def _get_detailed_format_context_for_logging(application_type=None, application_format=None):
    """
    Создает детальную строку контекста формата для логирования в views
    
    Args:
        application_type: Тип заявки ('legal_entity' или 'individual_entrepreneur')
        application_format: Формат заявки ('casco_equipment' или 'property')
        
    Returns:
        str: Строка формата "application_type: individual_entrepreneur, application_format: property"
    """
    if not application_type or not application_format:
        return "application_type: unknown, application_format: unknown"
    
    return f"application_type: {application_type}, application_format: {application_format}"


def _get_parser_v2_drafts(request):
    return request.session.get(PARSER_V2_SESSION_KEY, {})


def _store_parser_v2_draft(request, draft_id, draft):
    drafts = _get_parser_v2_drafts(request)
    drafts[draft_id] = draft
    request.session[PARSER_V2_SESSION_KEY] = drafts
    request.session.modified = True


def _pop_parser_v2_draft(request, draft_id):
    drafts = _get_parser_v2_drafts(request)
    draft = drafts.pop(draft_id, None)
    request.session[PARSER_V2_SESSION_KEY] = drafts
    request.session.modified = True
    return draft


def _get_parser_v2_draft(request, draft_id):
    return _get_parser_v2_drafts(request).get(draft_id)


def _save_parser_v2_upload(uploaded_file):
    original_name = os.path.basename(uploaded_file.name)
    safe_name = get_valid_filename(original_name) or 'insurance_request.xlsx'
    storage_path = f"parser_v2_uploads/{uuid.uuid4().hex}_{safe_name}"
    content = ContentFile(b''.join(uploaded_file.chunks()))
    return default_storage.save(storage_path, content)


def _get_parser_v2_file_path(storage_path):
    try:
        return default_storage.path(storage_path), None
    except NotImplementedError:
        suffix = os.path.splitext(storage_path)[1] or '.xlsx'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        with default_storage.open(storage_path, 'rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                temp_file.write(chunk)
        temp_file.close()
        return temp_file.name, temp_file.name


def _parser_v2_initial_data(draft_id, parse_result):
    data = parse_result.get('data', {}).copy()
    data['draft_id'] = draft_id
    return data


def _json_safe_value(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value


def _build_parser_v2_additional_data(draft, request_fields, user):
    parse_result = draft.get('parse_result', {})
    parsed_payload = parse_result.get('data', {}).get('parser_v2_payload', {})
    application_type = parsed_payload.get('application_type', 'legal_entity')
    application_format = parsed_payload.get('application_format', 'casco_equipment')
    format_context = _get_format_context_for_logging(application_type, application_format)
    detailed_context = _get_detailed_format_context_for_logging(application_type, application_format)
    application_type_display = "заявка от ИП" if application_type == 'individual_entrepreneur' else "заявка от юр.лица"
    application_format_display = "КАСКО/спецтехника" if application_format == 'casco_equipment' else "имущество"

    return {
        'application_type': application_type,
        'application_format': application_format,
        'application_type_display': application_type_display,
        'application_format_display': application_format_display,
        'format_context': format_context,
        'detailed_context': detailed_context,
        'processed_by_user': user.username,
        'processing_timestamp': timezone.now().isoformat(),
        'parser_version': 'v2',
        'parser_v2': {
            'version': parse_result.get('parser_version'),
            'confidence': parse_result.get('confidence', 0),
            'warnings': parse_result.get('warnings', []),
            'source_map': parse_result.get('source_map', {}),
            'raw_debug': parse_result.get('raw_debug', {}),
            'parsed_payload': parsed_payload,
            'preview_fields': _json_safe_value(request_fields),
            'source_file_name': draft.get('original_filename', ''),
            'created_from_preview': True,
            'created_by_user': user.username,
            'created_at': timezone.now().isoformat(),
        }
    }


def _attach_parser_v2_original_file(insurance_request, draft, *, cleanup_source=True):
    """Attach the original Excel to a created request.

    With cleanup_source=False the source file in storage is kept after the
    attach, so the same draft can be attached to several sibling requests in
    a batch (stage 4 splitting). The caller is responsible for deleting the
    storage file once after all siblings have been attached.
    """
    storage_path = draft.get('storage_path')
    original_filename = draft.get('original_filename') or os.path.basename(storage_path or '')
    if not storage_path or not default_storage.exists(storage_path):
        logger.warning("Parser V2 original file is missing for request #%s", insurance_request.pk)
        return None

    safe_name = get_valid_filename(os.path.basename(original_filename)) or 'insurance_request.xlsx'
    with default_storage.open(storage_path, 'rb') as source:
        attachment = RequestAttachment.objects.create(
            request=insurance_request,
            file=File(source, name=safe_name),
            original_filename=original_filename,
            file_type=os.path.splitext(original_filename)[1]
        )
    if cleanup_source:
        try:
            default_storage.delete(storage_path)
        except Exception as cleanup_error:
            logger.warning("Could not delete Parser V2 temporary file %s: %s", storage_path, cleanup_error)
    return attachment


def _parser_v2_object_fields(payload_object):
    """Translate one parser_v2 insured_objects[] entry into model field kwargs.

    Returns a dict ready to spread into InsuranceRequest(**kwargs). Decimal
    fields are decoded back from the string form used in payload.
    """
    from decimal import Decimal, InvalidOperation

    def _decimal(value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    description = payload_object.get('description') or 'Предмет лизинга не указан'
    return {
        'brand': payload_object.get('brand') or None,
        'model': payload_object.get('model') or None,
        'condition': payload_object.get('condition') or None,
        'equipment_type': payload_object.get('equipment_type') or None,
        'power_or_capacity': payload_object.get('power_or_capacity') or None,
        'acquisition_cost_value': _decimal(payload_object.get('acquisition_cost_value')),
        'acquisition_cost_currency': payload_object.get('acquisition_cost_currency') or None,
        'vehicle_info': description[:5000],
        'manufacturing_year': (payload_object.get('year') or '')[:255],
    }


def _build_common_request_kwargs(request_fields, additional_data, user):
    """Common kwargs duplicated to every sibling request in a V2 batch."""
    return {
        'client_name': request_fields['client_name'],
        'inn': request_fields['inn'],
        'insurance_type': request_fields['insurance_type'],
        'insurance_period': request_fields['insurance_period'],
        'dfa_number': request_fields['dfa_number'],
        'branch': request_fields['branch'],
        'manager_name': request_fields['manager_name'],
        'deal_status': request_fields['deal_status'],
        'franchise_type': request_fields['franchise_type'],
        'has_installment': request_fields['has_installment'],
        'has_autostart': request_fields['has_autostart'],
        'has_casco_ce': request_fields['has_casco_ce'],
        'has_transportation': request_fields['has_transportation'],
        'has_construction_work': request_fields['has_construction_work'],
        'asset_status': request_fields['asset_status'],
        'key_completeness': request_fields['key_completeness'],
        'pts_psm': request_fields['pts_psm'],
        'creditor_bank': request_fields['creditor_bank'],
        'usage_purposes': request_fields['usage_purposes'],
        'telematics_complex': request_fields['telematics_complex'],
        'insurance_territory': request_fields['insurance_territory'],
        'response_deadline': request_fields['response_deadline'],
        'notes': request_fields['notes'],
        # Stage 2.2 — customer details
        'legal_address': request_fields.get('legal_address'),
        'postal_address': request_fields.get('postal_address'),
        'business_activity': request_fields.get('business_activity'),
        'birth_date': request_fields.get('birth_date'),
        'submission_date': request_fields.get('submission_date'),
        # Stage 2.3 — deal / insurance parameters
        'insured_party': request_fields.get('insured_party'),
        'insured_sum_type': request_fields.get('insured_sum_type'),
        'guard_conditions': request_fields.get('guard_conditions'),
        'property_location_right_holder': request_fields.get('property_location_right_holder'),
        'premium_frequency': request_fields.get('premium_frequency'),
        'additional_data': additional_data,
        'created_by': user,
    }


def _create_requests_with_splitting(*, request_fields, additional_data, insured_objects, draft, user):
    """Stage 4.1 splitting: produce N sibling InsuranceRequest rows from a
    single Excel upload.

    - 0 objects → fall back to a single request using the form's vehicle_info
      / manufacturing_year (legacy V2 behaviour, kept for files where the
      parser failed to identify any object row).
    - 1 object → create a single request, no source_batch_id / item_no /
      item_count (these stay NULL; user-confirmed default in stage 4 design).
    - N ≥ 2 objects → one source_batch_id (UUID), N rows with item_no=1..N
      and item_count=N. Common fields are duplicated; per-object fields
      (brand/model/condition/cost/...) come from each insured_objects[i].

    The original Excel is attached to every created request; the source file
    in storage is removed once after the loop.
    """
    common = _build_common_request_kwargs(request_fields, additional_data, user)
    created: list = []

    with transaction.atomic():
        if not insured_objects:
            # Legacy fallback — no objects parsed, use the form values.
            instance = InsuranceRequest.objects.create(
                vehicle_info=request_fields['vehicle_info'],
                manufacturing_year=request_fields['manufacturing_year'],
                **common,
            )
            created.append(instance)
        elif len(insured_objects) == 1:
            object_kwargs = _parser_v2_object_fields(insured_objects[0])
            instance = InsuranceRequest.objects.create(**object_kwargs, **common)
            created.append(instance)
        else:
            batch_id = uuid.uuid4()
            item_count = len(insured_objects)
            for idx, payload_object in enumerate(insured_objects, start=1):
                object_kwargs = _parser_v2_object_fields(payload_object)
                instance = InsuranceRequest.objects.create(
                    source_batch_id=batch_id,
                    item_no=idx,
                    item_count=item_count,
                    **object_kwargs,
                    **common,
                )
                created.append(instance)

    # Attach the original Excel to every sibling, clean storage at the end.
    last_index = len(created) - 1
    for idx, instance in enumerate(created):
        _attach_parser_v2_original_file(instance, draft, cleanup_source=(idx == last_index))

    return created


def _render_parser_v2_preview(request, draft_id, draft, preview_form=None):
    parse_result = draft.get('parse_result', {})
    if preview_form is None:
        preview_form = ParserV2PreviewForm(initial=_parser_v2_initial_data(draft_id, parse_result))
    confidence = parse_result.get('confidence', 0) or 0

    payload = (parse_result.get('data') or {}).get('parser_v2_payload') or {}
    insured_objects = payload.get('insured_objects') or []
    batch_size = len(insured_objects)

    return render(request, 'insurance_requests/upload_excel_v2_preview.html', {
        'form': preview_form,
        'warnings': parse_result.get('warnings', []),
        'source_map': parse_result.get('source_map', {}),
        'confidence': confidence,
        'confidence_percent': int(confidence * 100),
        'original_filename': draft.get('original_filename', ''),
        'draft_id': draft_id,
        'parse_result': parse_result,
        'insured_objects': insured_objects,
        'batch_size': batch_size,
        'is_batch': batch_size >= 2,
    })


def login_view(request):
    """Страница входа в систему с улучшенной обработкой ошибок"""
    if request.user.is_authenticated:
        return redirect('insurance_requests:request_list')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        client_ip = get_login_client_ip(request)
        current_lock_state = get_login_lock_state(request, username)
        form = CustomAuthenticationForm(request, data=request.POST)

        if current_lock_state.is_locked:
            lock_message = format_lockout_message(current_lock_state.remaining_seconds)
            form.add_error(None, lock_message)
            logger.warning(
                "Blocked login attempt from %s for username '%s' (scope=%s, remaining=%ss)",
                client_ip,
                username or '<empty>',
                current_lock_state.scope,
                current_lock_state.remaining_seconds,
            )
        elif form.is_valid():
            user = form.get_user()
            login(request, user)
            clear_login_failures(request, user.username)
            
            # Логируем успешный вход
            logger.info(f"User {user.username} successfully logged in from {client_ip}")
            
            # Добавляем сообщение о успешном входе
            messages.success(request, f'Добро пожаловать, {user.get_full_name() or user.username}!')
            
            # Перенаправляем на страницу, с которой пришел пользователь, или на главную
            next_url = request.GET.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            else:
                return redirect('insurance_requests:request_list')
        else:
            failure_reason = getattr(form, 'failure_reason', None)
            failure_context = getattr(form, 'failure_context', {})

            if failure_reason == 'invalid_credentials':
                updated_lock_state = register_failed_login_attempt(request, username)
                logger.warning(
                    "Failed login attempt for username '%s' from %s (reason=%s, details=%s, locked=%s)",
                    username or '<empty>',
                    client_ip,
                    failure_reason,
                    failure_context,
                    updated_lock_state.is_locked,
                )

                if updated_lock_state.is_locked:
                    lock_message = format_lockout_message(updated_lock_state.remaining_seconds)
                    if '__all__' not in form.errors or lock_message not in form.errors['__all__']:
                        form.add_error(None, lock_message)
            else:
                logger.warning(
                    "Login form validation failed for username '%s' from %s (errors=%s)",
                    username or '<empty>',
                    client_ip,
                    form.errors,
                )
                messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'insurance_requests/login.html', {
        'form': form,
        'next': request.GET.get('next', '')
    })


def logout_view(request):
    """Выход из системы с улучшенной обработкой"""
    username = request.user.username if request.user.is_authenticated else 'Unknown'
    
    # Логируем выход из системы
    logger.info(f"User {username} logged out")
    
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы')
    return redirect('login')


def access_denied_view(request):
    """Страница отказа в доступе"""
    user_groups = list(request.user.groups.values_list('name', flat=True)) if request.user.is_authenticated else []
    user_role = ', '.join(user_groups) if user_groups else 'Не авторизован'
    
    # Определяем требуемую роль на основе referrer или параметров
    required_role = request.GET.get('required', 'Администратор или Пользователь')
    
    return render(request, 'insurance_requests/access_denied.html', {
        'user_role': user_role,
        'required_role': required_role
    })


@user_required
def request_list(request):
    """Список всех заявок с поддержкой фильтрации по филиалу, дате и номеру ДФА"""
    # Получаем параметры фильтрации из GET запроса
    branch_filter = request.GET.get('branch', '').strip()
    month_filter = request.GET.get('month', '').strip()
    year_filter = request.GET.get('year', '').strip()
    dfa_filter = request.GET.get('dfa_filter', '').strip()
    
    # Начинаем с базового QuerySet
    queryset = InsuranceRequest.objects.all()
    
    # Применяем фильтр по номеру ДФА с улучшенной обработкой ошибок
    dfa_filter_error = None
    if dfa_filter:
        try:
            # Валидация длины входных данных (максимум 100 символов)
            if len(dfa_filter) > 100:
                dfa_filter_error = f"Номер ДФА слишком длинный ({len(dfa_filter)} символов). Максимум 100 символов."
                logger.warning(f"DFA filter input too long: {len(dfa_filter)} characters from user {request.user.username} | Filter operation")
                # Обрезаем до 100 символов для продолжения работы
                dfa_filter = dfa_filter[:100]
            
            # Проверяем, что после обрезки пробелов строка не пустая
            if dfa_filter:
                # Применяем фильтр с обработкой исключений базы данных
                queryset = queryset.filter(dfa_number__icontains=dfa_filter)
                logger.debug(f"Applied DFA filter '{dfa_filter}' by user {request.user.username} | Filter operation")
            else:
                logger.debug(f"Empty DFA filter after stripping whitespace by user {request.user.username} | Filter operation")
                
        except Exception as e:
            # Логируем ошибку базы данных и продолжаем без DFA фильтра
            logger.error(f"Database error applying DFA filter '{dfa_filter}' by user {request.user.username}: {str(e)} | Filter operation")
            dfa_filter_error = "Ошибка при применении фильтра по номеру ДФА. Попробуйте другой запрос."
            # Сбрасываем dfa_filter чтобы не показывать некорректное значение в форме
            dfa_filter = ""
    
    # Применяем фильтр по филиалу
    if branch_filter:
        queryset = queryset.filter(branch=branch_filter)
    
    # Применяем фильтры по дате
    if year_filter:
        try:
            year_int = int(year_filter)
            queryset = queryset.filter(created_at__year=year_int)
        except ValueError:
            # Игнорируем некорректные значения года
            pass
    
    if month_filter:
        try:
            month_int = int(month_filter)
            if 1 <= month_int <= 12:
                queryset = queryset.filter(created_at__month=month_int)
        except ValueError:
            # Игнорируем некорректные значения месяца
            pass
    
    # Сортируем по дате создания (новые сначала)
    queryset = queryset.order_by('-created_at')
    
    # Применяем пагинацию
    paginator = Paginator(queryset, 30)  # 30 заявок на страницу
    page_number = request.GET.get('page')
    
    try:
        requests = paginator.get_page(page_number)
    except PageNotAnInteger:
        # Если номер страницы не является числом, показываем первую страницу
        requests = paginator.get_page(1)
    except EmptyPage:
        # Если номер страницы больше максимального, показываем последнюю страницу
        requests = paginator.get_page(paginator.num_pages)
    
    # Генерируем данные для фильтров
    # Получаем все доступные филиалы
    available_branches = InsuranceRequest.objects.values_list('branch', flat=True)\
                                                .distinct()\
                                                .exclude(branch__isnull=True)\
                                                .exclude(branch__exact='')\
                                                .order_by('branch')
    
    # Получаем доступные годы из дат создания заявок
    available_years = InsuranceRequest.objects.dates('created_at', 'year', order='DESC')\
                                             .values_list('created_at__year', flat=True)
    available_years = list(set(available_years))  # Убираем дубликаты
    available_years.sort(reverse=True)  # Сортируем по убыванию (новые годы сначала)
    
    # Список месяцев для выпадающего списка
    months = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]
    
    # Преобразуем параметры фильтров в числа для сравнения в шаблоне
    current_month = None
    current_year = None
    
    if month_filter:
        try:
            current_month = int(month_filter)
        except ValueError:
            pass
    
    if year_filter:
        try:
            current_year = int(year_filter)
        except ValueError:
            pass
    
    context = {
        'requests': requests,
        'available_branches': available_branches,
        'available_years': available_years,
        'months': months,
        'current_branch': branch_filter,
        'current_month': current_month,
        'current_year': current_year,
        'current_dfa_filter': dfa_filter,
        'dfa_filter_error': dfa_filter_error,
        # Дополнительные данные для удобства работы с фильтрами
        'has_filters': bool(branch_filter or month_filter or year_filter or dfa_filter),
        'total_requests': paginator.count,
        # Данные пагинации
        'paginator': paginator,
        'page_obj': requests,
        'is_paginated': paginator.num_pages > 1,
    }
    
    return render(request, 'insurance_requests/request_list.html', context)


@user_required
def upload_excel(request):
    """Загрузка Excel файла и создание заявки с улучшенной обработкой ошибок"""
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = None
            application_type = None
            try:
                # Сохраняем загруженный файл временно
                excel_file = form.cleaned_data['excel_file']
                
                # Получаем тип заявки из формы с fallback
                application_type = form.cleaned_data.get('application_type', 'legal_entity')
                
                # Дополнительная валидация типа заявки
                valid_types = ['legal_entity', 'individual_entrepreneur']
                if application_type not in valid_types:
                    format_context = _get_format_context_for_logging(application_type, None)
                    logger.warning(f"Invalid application type '{application_type}' received, falling back to 'legal_entity' | {format_context}")
                    application_type = 'legal_entity'
                
                # Получаем формат заявки из формы с fallback для обратной совместимости
                application_format = form.cleaned_data.get('application_format', 'casco_equipment')
                
                # Дополнительная валидация формата заявки
                valid_formats = ['casco_equipment', 'property']
                if application_format not in valid_formats:
                    format_context = _get_format_context_for_logging(application_type, application_format)
                    logger.warning(f"Invalid application format '{application_format}' received, falling back to 'casco_equipment' | {format_context}")
                    application_format = 'casco_equipment'
                
                # Логируем выбранный тип и формат заявки для диагностики
                format_context = _get_format_context_for_logging(application_type, application_format)
                detailed_context = _get_detailed_format_context_for_logging(application_type, application_format)
                logger.info(f"Processing Excel file '{excel_file.name}' ({detailed_context}) by user {request.user.username} | {format_context}")
                
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    for chunk in excel_file.chunks():
                        tmp_file.write(chunk)
                    tmp_file_path = tmp_file.name
                
                try:
                    # Читаем данные из Excel с передачей типа и формата заявки
                    reader = ExcelReader(tmp_file_path, application_type=application_type, application_format=application_format)
                    excel_data = reader.read_insurance_request()
                    
                    # Дополнительная проверка и логирование для CASCO C/E
                    has_casco_ce = excel_data.get('has_casco_ce', False)
                    if has_casco_ce:
                        logger.info(f"CASCO C/E automatically detected for file: {excel_file.name} ({detailed_context}) | {format_context}")
                    else:
                        logger.debug(f"No CASCO C/E indicators found in file: {excel_file.name} ({detailed_context}) | {format_context}")
                    
                    # Дополнительная проверка и логирование для типа франшизы
                    franchise_type_from_excel = excel_data.get('franchise_type', 'none')
                    logger.info(f"Franchise processing for file: {excel_file.name} ({detailed_context}) - franchise_type: '{franchise_type_from_excel}' | {format_context}")
                    
                    # Обрабатываем дату ответа
                    response_deadline = None
                    if excel_data.get('response_deadline'):
                        try:
                            from datetime import datetime
                            date_str = str(excel_data.get('response_deadline'))
                            # Пробуем разные форматы дат
                            for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                                try:
                                    response_deadline = datetime.strptime(date_str, fmt)
                                    break
                                except ValueError:
                                    continue
                        except Exception as date_error:
                            logger.warning(f"Error parsing response deadline from {excel_file.name} ({detailed_context}): {str(date_error)} | {format_context}")
                    
                    # Обрабатываем response_deadline из excel_data если он есть
                    if not response_deadline and excel_data.get('response_deadline'):
                        response_deadline = excel_data.get('response_deadline')
                    
                    # Подготавливаем additional_data, преобразуя datetime в строку для JSON
                    additional_data = {}
                    for key, value in excel_data.items():
                        if hasattr(value, 'strftime'):  # datetime объект
                            additional_data[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            additional_data[key] = value
                    
                    # Добавляем расширенную информацию о типе и формате заявки в additional_data для диагностики
                    additional_data['application_type'] = application_type
                    additional_data['application_format'] = application_format
                    additional_data['format_context'] = format_context
                    additional_data['detailed_context'] = detailed_context
                    additional_data['processed_by_user'] = request.user.username
                    additional_data['processing_timestamp'] = timezone.now().isoformat()
                    
                    # Валидируем тип страхования
                    insurance_type = excel_data.get('insurance_type', 'КАСКО')
                    valid_insurance_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
                    if insurance_type not in valid_insurance_types:
                        logger.warning(f"Invalid insurance type '{insurance_type}' from Excel file {excel_file.name} ({detailed_context}), defaulting to 'КАСКО' | {format_context}")
                        insurance_type = 'КАСКО'
                    
                    # Валидируем тип франшизы
                    franchise_type = excel_data.get('franchise_type', 'none')
                    valid_franchise_types = ['none', 'with_franchise', 'both_variants']
                    if franchise_type not in valid_franchise_types:
                        logger.warning(f"Invalid franchise type '{franchise_type}' from Excel file {excel_file.name} ({detailed_context}), defaulting to 'none' | {format_context}")
                        franchise_type = 'none'
                    
                    # Извлекаем manager_name для логирования
                    manager_name_value = excel_data.get('manager_name', '')
                    logger.info(f"Creating request with manager_name: '{manager_name_value}' (empty: {not bool(manager_name_value)}) | {format_context}")
                    
                    # Создаем заявку
                    insurance_request = InsuranceRequest.objects.create(
                        client_name=excel_data.get('client_name', ''),
                        inn=excel_data.get('inn', ''),
                        insurance_type=insurance_type,
                        insurance_period=excel_data.get('insurance_period', ''),
                        vehicle_info=excel_data.get('vehicle_info', ''),
                        dfa_number=excel_data.get('dfa_number', ''),
                        branch=excel_data.get('branch', ''),
                        manager_name=manager_name_value,
                        franchise_type=franchise_type,
                        has_installment=bool(excel_data.get('has_installment')),
                        has_autostart=bool(excel_data.get('has_autostart')),
                        has_casco_ce=bool(excel_data.get('has_casco_ce', False)),
                        has_transportation=bool(excel_data.get('has_transportation', False)),
                        has_construction_work=bool(excel_data.get('has_construction_work', False)),
                        # Дополнительные параметры КАСКО/спецтехника
                        key_completeness=excel_data.get('key_completeness', ''),
                        pts_psm=excel_data.get('pts_psm', ''),
                        creditor_bank=excel_data.get('creditor_bank', ''),
                        usage_purposes=excel_data.get('usage_purposes', ''),
                        telematics_complex=excel_data.get('telematics_complex', ''),
                        manufacturing_year=excel_data.get('manufacturing_year', ''),
                        asset_status=excel_data.get('asset_status', ''),
                        # Дополнительные параметры для страхования имущества
                        insurance_territory=excel_data.get('insurance_territory', ''),
                        response_deadline=response_deadline,
                        additional_data=additional_data,
                        created_by=request.user
                    )
                    
                    # Логируем дополнительные параметры в зависимости от формата заявки
                    if application_format == 'casco_equipment':
                        additional_params = {
                            'key_completeness': excel_data.get('key_completeness', ''),
                            'pts_psm': excel_data.get('pts_psm', ''),
                            'creditor_bank': excel_data.get('creditor_bank', ''),
                            'usage_purposes': excel_data.get('usage_purposes', ''),
                            'telematics_complex': excel_data.get('telematics_complex', '')
                        }
                        non_empty_params = [k for k, v in additional_params.items() if v.strip()]
                        if non_empty_params:
                            logger.info(f"Saved CASCO additional parameters for request #{insurance_request.id}: {len(non_empty_params)} non-empty parameters ({', '.join(non_empty_params)}) | {format_context}")
                        else:
                            logger.info(f"Saved CASCO additional parameters for request #{insurance_request.id}: all parameters are empty | {format_context}")
                    elif application_format == 'property':
                        additional_params = {
                            'creditor_bank': excel_data.get('creditor_bank', ''),
                            'usage_purposes': excel_data.get('usage_purposes', ''),
                            'insurance_territory': excel_data.get('insurance_territory', '')
                        }
                        non_empty_params = [k for k, v in additional_params.items() if v.strip()]
                        if non_empty_params:
                            logger.info(f"Saved property insurance additional parameters for request #{insurance_request.id}: {len(non_empty_params)} non-empty parameters ({', '.join(non_empty_params)}) | {format_context}")
                        else:
                            logger.info(f"Saved property insurance additional parameters for request #{insurance_request.id}: all parameters are empty | {format_context}")
                    
                    # Сохраняем файл как вложение
                    attachment = RequestAttachment.objects.create(
                        request=insurance_request,
                        file=excel_file,
                        original_filename=excel_file.name,
                        file_type=os.path.splitext(excel_file.name)[1]
                    )
                    
                    # Логируем успешное создание заявки с полной информацией о формате и франшизе
                    logger.info(f"Successfully created request #{insurance_request.id} from file '{excel_file.name}' ({detailed_context}) by user {request.user.username} - franchise_type: '{franchise_type}' | {format_context}")
                    
                    # Улучшенное сообщение об успехе с информацией о формате
                    app_type_display = "заявка от ИП" if application_type == 'individual_entrepreneur' else "заявка от юр.лица"
                    format_display = "КАСКО/спецтехника" if application_format == 'casco_equipment' else "имущество"
                    success_message = f'Заявка {insurance_request.get_display_name()} успешно создана из файла "{excel_file.name}" формата "{format_display}" типа "{app_type_display}"'
                    messages.success(request, success_message)
                    
                    # Дополнительное логирование для диагностики
                    logger.info(f"Success message displayed: {success_message} | {format_context}")
                    return redirect('insurance_requests:request_detail', pk=insurance_request.pk)
                    
                finally:
                    # Удаляем временный файл
                    if 'tmp_file_path' in locals():
                        try:
                            os.unlink(tmp_file_path)
                        except Exception as cleanup_error:
                            logger.warning(f"Error cleaning up temporary file: {str(cleanup_error)} | {format_context}")
                    
            except Exception as e:
                # Улучшенная обработка ошибок с полной информацией о формате и типе заявки
                error_context = []
                if excel_file:
                    error_context.append(f"файл: {excel_file.name}")
                
                # Создаем контекст формата для логирования
                format_context = _get_format_context_for_logging(
                    application_type if 'application_type' in locals() else None,
                    application_format if 'application_format' in locals() else None
                )
                detailed_context = _get_detailed_format_context_for_logging(
                    application_type if 'application_type' in locals() else None,
                    application_format if 'application_format' in locals() else None
                )
                
                if 'application_type' in locals():
                    app_type_display = "заявка от ИП" if application_type == 'individual_entrepreneur' else "заявка от юр.лица"
                    error_context.append(f"тип: {app_type_display}")
                if 'application_format' in locals():
                    format_display = "КАСКО/спецтехника" if application_format == 'casco_equipment' else "имущество"
                    error_context.append(f"формат: {format_display}")
                
                context_str = f" ({', '.join(error_context)})" if error_context else ""
                
                # Расширенное логирование ошибки с полным контекстом
                logger.error(f"Error processing Excel file{context_str} by user {request.user.username}: {str(e)} | {format_context}", exc_info=True)
                
                # Определяем тип ошибки для более информативного сообщения с контекстом формата
                if "Permission denied" in str(e) or "access" in str(e).lower():
                    error_msg = f'Ошибка доступа к файлу{context_str}. Убедитесь, что файл не открыт в другой программе и попробуйте снова.'
                elif "corrupted" in str(e).lower() or "invalid" in str(e).lower():
                    error_msg = f'Файл поврежден или имеет неверный формат{context_str}. Проверьте целостность файла и попробуйте снова.'
                elif "memory" in str(e).lower() or "size" in str(e).lower():
                    error_msg = f'Файл слишком большой для обработки{context_str}. Попробуйте уменьшить размер файла.'
                elif "не удалось прочитать файл" in str(e).lower():
                    error_msg = f'Не удалось прочитать файл{context_str}. Проверьте, что выбран правильный формат заявки и файл соответствует ожидаемой структуре.'
                else:
                    error_msg = f'Ошибка при обработке файла{context_str}: {str(e)}'
                
                # Логируем отображаемое пользователю сообщение для диагностики
                logger.error(f"Error message displayed to user {request.user.username}: {error_msg} | {format_context}")
                
                messages.error(request, error_msg)
        else:
            # Обработка ошибок валидации формы с улучшенным контекстом
            # Пытаемся извлечь контекст формата из данных формы для логирования
            form_application_type = request.POST.get('application_type')
            form_application_format = request.POST.get('application_format')
            form_format_context = _get_format_context_for_logging(form_application_type, form_application_format)
            
            logger.warning(f"Form validation failed for user {request.user.username}: {form.errors} | {form_format_context}")
            
            # Добавляем информативные сообщения об ошибках с контекстом формата
            for field, errors in form.errors.items():
                for error in errors:
                    if field == 'application_type':
                        error_msg = f'Ошибка выбора типа заявки: {error}'
                        messages.error(request, error_msg)
                        logger.warning(f"Application type validation error for user {request.user.username}: {error} | {form_format_context}")
                    elif field == 'application_format':
                        error_msg = f'Ошибка выбора формата заявки: {error}'
                        messages.error(request, error_msg)
                        logger.warning(f"Application format validation error for user {request.user.username}: {error} | {form_format_context}")
                    elif field == 'excel_file':
                        error_msg = f'Ошибка файла: {error}'
                        messages.error(request, error_msg)
                        logger.warning(f"Excel file validation error for user {request.user.username}: {error} | {form_format_context}")
                    else:
                        error_msg = f'Ошибка в поле {field}: {error}'
                        messages.error(request, error_msg)
                        logger.warning(f"Field validation error for user {request.user.username} in field {field}: {error} | {form_format_context}")
    else:
        form = ExcelUploadForm()
    
    return render(request, 'insurance_requests/upload_excel.html', {
        'form': form
    })


@superuser_required
def upload_excel_v2(request):
    """Экспериментальный Parser V2: upload -> preview -> best-effort create."""
    if request.method == 'POST' and request.POST.get('draft_id'):
        draft_id = request.POST.get('draft_id')
        draft = _get_parser_v2_draft(request, draft_id)
        if not draft:
            messages.error(request, 'Черновик Parser V2 не найден. Загрузите файл еще раз.')
            return redirect('insurance_requests:upload_excel_v2')

        form = ParserV2PreviewForm(request.POST)
        if form.is_valid():
            request_fields = form.to_request_fields()
            additional_data = _build_parser_v2_additional_data(draft, request_fields, request.user)

            parse_result = draft.get('parse_result', {})
            payload = (parse_result.get('data') or {}).get('parser_v2_payload') or {}
            insured_objects = payload.get('insured_objects') or []

            created_requests = _create_requests_with_splitting(
                request_fields=request_fields,
                additional_data=additional_data,
                insured_objects=insured_objects,
                draft=draft,
                user=request.user,
            )

            _pop_parser_v2_draft(request, draft_id)

            warning_count = len(additional_data['parser_v2'].get('warnings', []))
            batch_size = len(created_requests)
            primary = created_requests[0]
            if batch_size > 1:
                messages.success(
                    request,
                    f'Создана партия из {batch_size} заявок через Parser V2. '
                    f'Первая: {primary.get_display_name()}.'
                )
            else:
                if warning_count:
                    messages.warning(
                        request,
                        f'Заявка {primary.get_display_name()} создана через Parser V2. '
                        f'Предупреждений разбора: {warning_count}. Проверьте данные перед дальнейшей работой.'
                    )
                else:
                    messages.success(
                        request,
                        f'Заявка {primary.get_display_name()} успешно создана через Parser V2.'
                    )

            logger.info(
                "Parser V2 created %d request(s) from file '%s' by user %s (batch_size=%d)",
                batch_size,
                draft.get('original_filename', ''),
                request.user.username,
                batch_size,
            )
            return redirect('insurance_requests:request_detail', pk=primary.pk)

        messages.error(request, 'Проверьте значения на странице предварительной проверки.')
        return _render_parser_v2_preview(request, draft_id, draft, preview_form=form)

    if request.method == 'POST':
        upload_form = ParserV2ExcelUploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            uploaded_file = upload_form.cleaned_data['excel_file']
            storage_path = _save_parser_v2_upload(uploaded_file)
            parser_file_path, temp_copy_path = _get_parser_v2_file_path(storage_path)
            try:
                parse_result = ExcelRequestParserV2().parse(
                    parser_file_path,
                    original_filename=uploaded_file.name,
                )
            finally:
                if temp_copy_path:
                    try:
                        os.unlink(temp_copy_path)
                    except Exception as cleanup_error:
                        logger.warning("Could not delete Parser V2 temp copy %s: %s", temp_copy_path, cleanup_error)

            draft_id = uuid.uuid4().hex
            draft = {
                'storage_path': storage_path,
                'original_filename': uploaded_file.name,
                'parse_result': parse_result.to_session_dict(),
                'created_at': timezone.now().isoformat(),
                'created_by_user': request.user.username,
            }
            _store_parser_v2_draft(request, draft_id, draft)

            messages.info(
                request,
                'Файл разобран Parser V2. Проверьте распознанные данные и создайте заявку.'
            )
            return _render_parser_v2_preview(request, draft_id, draft)

        for field, errors in upload_form.errors.items():
            for error in errors:
                messages.error(request, f'Ошибка загрузки Parser V2 ({field}): {error}')
    else:
        upload_form = ParserV2ExcelUploadForm()

    return render(request, 'insurance_requests/upload_excel_v2.html', {
        'form': upload_form,
    })


@user_required
def request_detail(request, pk):
    """Детальная информация о заявке"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    # Создаем форму для изменения статуса
    status_form = RequestStatusForm(initial={'status': insurance_request.status})
    
    return render(request, 'insurance_requests/request_detail.html', {
        'request': insurance_request,
        'status_form': status_form
    })


@user_required
def edit_request(request, pk):
    """Редактирование заявки с улучшенной предзаполнением формы"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    if request.method == 'POST':
        form = InsuranceRequestForm(request.POST, instance=insurance_request)
        if form.is_valid():
            updated_request = form.save()
            
            # Получаем информацию о формате для логирования
            format_info = ""
            format_context = "Format: unknown, Type: unknown"
            if updated_request.additional_data:
                application_type = updated_request.additional_data.get('application_type')
                application_format = updated_request.additional_data.get('application_format')
                format_context = _get_format_context_for_logging(application_type, application_format)
                
                format_display = updated_request.additional_data.get('application_format_display', 'неизвестно')
                type_display = updated_request.additional_data.get('application_type_display', 'неизвестно')
                format_info = f" (формат: {format_display}, тип: {type_display})"
            
            success_message = f'Заявка {insurance_request.get_display_name()} успешно обновлена{format_info}'
            messages.success(request, success_message)
            logger.info(f"Request {pk} updated by user {request.user.username}{format_info} | {format_context}")
            return redirect('insurance_requests:request_detail', pk=pk)
        else:
            # Log form errors for debugging with format information
            format_info = ""
            format_context = "Format: unknown, Type: unknown"
            if insurance_request.additional_data:
                application_type = insurance_request.additional_data.get('application_type')
                application_format = insurance_request.additional_data.get('application_format')
                format_context = _get_format_context_for_logging(application_type, application_format)
                
                format_display = insurance_request.additional_data.get('application_format_display', 'неизвестно')
                type_display = insurance_request.additional_data.get('application_type_display', 'неизвестно')
                format_info = f" (формат: {format_display}, тип: {type_display})"
            
            logger.warning(f"Form validation errors for request {pk}{format_info}: {form.errors} | {format_context}")
    else:
        # Initialize form with instance data
        form = InsuranceRequestForm(instance=insurance_request)
        
        # Log successful form initialization for debugging with format context
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
        
        logger.debug(f"Form initialized for request {pk} with data: {insurance_request.to_dict()} | {format_context}")
    
    return render(request, 'insurance_requests/edit_request.html', {
        'form': form,
        'request': insurance_request
    })


@user_required
def generate_email(request, pk):
    """Генерация письма для заявки"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    try:
        # Генерируем письмо
        template_generator = EmailTemplateGenerator()
        request_data = insurance_request.to_dict()
        
        email_subject = template_generator.generate_subject(request_data)
        email_body = template_generator.generate_email_body(request_data)
        
        # Сохраняем сгенерированное письмо
        insurance_request.email_subject = email_subject
        insurance_request.email_body = email_body
        insurance_request.status = 'email_generated'
        insurance_request.save()
        
        # Получаем информацию о формате из additional_data для логирования
        format_info = ""
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
            
            format_display = insurance_request.additional_data.get('application_format_display', 'неизвестно')
            type_display = insurance_request.additional_data.get('application_type_display', 'неизвестно')
            format_info = f" (формат: {format_display}, тип: {type_display})"
        
        success_message = f'Письмо успешно сгенерировано для заявки #{pk}{format_info}'
        messages.success(request, success_message)
        logger.info(f"Email generated successfully for request {pk}{format_info} by user {request.user.username} | {format_context}")
        
    except Exception as e:
        # Получаем информацию о формате для ошибки
        format_info = ""
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
            
            format_display = insurance_request.additional_data.get('application_format_display', 'неизвестно')
            type_display = insurance_request.additional_data.get('application_type_display', 'неизвестно')
            format_info = f" (формат: {format_display}, тип: {type_display})"
        
        error_message = f'Ошибка при генерации письма для заявки #{pk}{format_info}: {str(e)}'
        logger.error(f"Error generating email for request {pk}{format_info}: {str(e)} | {format_context}")
        messages.error(request, error_message)
    
    return redirect('insurance_requests:request_detail', pk=pk)


@user_required
def preview_email(request, pk):
    """Редактирование письма"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    if request.method == 'POST':
        form = EmailPreviewForm(request.POST)
        if form.is_valid():
            # Обновляем данные письма
            insurance_request.email_subject = form.cleaned_data['email_subject']
            insurance_request.email_body = form.cleaned_data['email_body']
            insurance_request.save()
            
            # Сохраняем изменения и возвращаемся к заявке
            messages.success(request, 'Изменения в письме сохранены')
            return redirect('insurance_requests:request_detail', pk=pk)
    else:
        # Если письмо еще не сгенерировано, генерируем его
        if not insurance_request.email_body:
            template_generator = EmailTemplateGenerator()
            request_data = insurance_request.to_dict()
            
            insurance_request.email_subject = template_generator.generate_subject(request_data)
            insurance_request.email_body = template_generator.generate_email_body(request_data)
            insurance_request.save()
        
        form = EmailPreviewForm(initial={
            'email_subject': insurance_request.email_subject,
            'email_body': insurance_request.email_body,
        })
    
    return render(request, 'insurance_requests/preview_email.html', {
        'form': form,
        'request': insurance_request
    })


@require_http_methods(["POST"])
@user_required
def send_email(request, pk):
    """Ручная установка статуса 'Письма отправлены'"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    try:
        # Обновляем статус без фактической отправки email
        insurance_request.status = 'emails_sent'
        insurance_request.save()
        
        # Получаем информацию о формате для логирования
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
        
        logger.info(f"Request {pk} status manually set to 'emails_sent' by user {request.user.username} | {format_context}")
        return JsonResponse({'success': True, 'message': 'Статус изменен на "Письма отправлены"'})
        
    except Exception as e:
        # Получаем информацию о формате для логирования ошибки
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
        
        logger.error(f"Error updating request {pk} status: {str(e)} | {format_context}")
        return JsonResponse({'success': False, 'error': str(e)})





@require_http_methods(["POST"])
@user_required
def change_request_status(request, pk):
    """Изменение статуса заявки"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    new_status = request.POST.get('status')
    
    if new_status in dict(InsuranceRequest.STATUS_CHOICES):
        old_status = insurance_request.status
        insurance_request.status = new_status
        insurance_request.save(update_fields=['status', 'updated_at'])
        
        logger.info(f"Request {pk} status changed from '{old_status}' to '{new_status}' by user {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': f'Статус заявки изменен на "{insurance_request.get_status_display()}"',
            'new_status': new_status,
            'new_status_display': insurance_request.get_status_display()
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Недопустимый статус'
    })

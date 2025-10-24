"""
Представления для работы со страховыми заявками
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
import os
import tempfile
import logging

from .models import InsuranceRequest, RequestAttachment
from .forms import ExcelUploadForm, InsuranceRequestForm, EmailPreviewForm, CustomAuthenticationForm, RequestStatusForm
from .decorators import user_required, admin_required
from core.excel_utils import ExcelReader
from core.templates import EmailTemplateGenerator
from core.mail_utils import EmailSender, EmailMessage, EmailConfig


logger = logging.getLogger(__name__)


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


def login_view(request):
    """Страница входа в систему с улучшенной обработкой ошибок"""
    if request.user.is_authenticated:
        return redirect('insurance_requests:request_list')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Логируем успешный вход
            logger.info(f"User {user.username} successfully logged in")
            
            # Добавляем сообщение о успешном входе
            messages.success(request, f'Добро пожаловать, {user.get_full_name() or user.username}!')
            
            # Перенаправляем на страницу, с которой пришел пользователь, или на главную
            next_url = request.GET.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            else:
                return redirect('insurance_requests:request_list')
        else:
            # Детализированная обработка ошибок
            username = request.POST.get('username', '')
            
            # Логируем неудачную попытку входа
            logger.warning(f"Failed login attempt for username: {username}")
            
            # Проверяем специфические ошибки
            if form.errors.get('__all__'):
                error_messages = form.errors['__all__']
                for error in error_messages:
                    if 'inactive' in str(error).lower():
                        messages.error(request, 'Ваша учетная запись отключена. Обратитесь к администратору.')
                    else:
                        messages.error(request, 'Неверный логин или пароль. Проверьте правильность введенных данных.')
            else:
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
                    has_franchise_from_excel = excel_data.get('has_franchise', False)
                    logger.info(f"Franchise processing for file: {excel_file.name} ({detailed_context}) - franchise_type: '{franchise_type_from_excel}', has_franchise: {has_franchise_from_excel} | {format_context}")
                    
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
                    
                    # Создаем заявку
                    insurance_request = InsuranceRequest.objects.create(
                        client_name=excel_data.get('client_name', ''),
                        inn=excel_data.get('inn', ''),
                        insurance_type=insurance_type,
                        insurance_period=excel_data.get('insurance_period', ''),
                        vehicle_info=excel_data.get('vehicle_info', ''),
                        dfa_number=excel_data.get('dfa_number', ''),
                        branch=excel_data.get('branch', ''),
                        franchise_type=franchise_type,
                        has_franchise=bool(excel_data.get('has_franchise')),
                        has_installment=bool(excel_data.get('has_installment')),
                        has_autostart=bool(excel_data.get('has_autostart')),
                        has_casco_ce=bool(excel_data.get('has_casco_ce', False)),
                        has_transportation=bool(excel_data.get('has_transportation', False)),
                        has_construction_work=bool(excel_data.get('has_construction_work', False)),
                        response_deadline=response_deadline,
                        additional_data=additional_data,
                        created_by=request.user
                    )
                    
                    # Сохраняем файл как вложение
                    attachment = RequestAttachment.objects.create(
                        request=insurance_request,
                        file=excel_file,
                        original_filename=excel_file.name,
                        file_type=os.path.splitext(excel_file.name)[1]
                    )
                    
                    # Логируем успешное создание заявки с полной информацией о формате и франшизе
                    logger.info(f"Successfully created request #{insurance_request.id} from file '{excel_file.name}' ({detailed_context}) by user {request.user.username} - franchise_type: '{franchise_type}', has_franchise: {insurance_request.has_franchise} | {format_context}")
                    
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
    """Отправка письма"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    try:
        # TODO: Получить настройки email из конфигурации
        # Пока используем заглушку
        messages.info(request, 'Функция отправки email будет реализована после настройки SMTP')
        
        # Обновляем статус и время отправки в московском времени
        from django.utils import timezone
        import pytz
        
        moscow_tz = pytz.timezone('Europe/Moscow')
        moscow_now = timezone.now().astimezone(moscow_tz)
        
        insurance_request.status = 'emails_sent'
        insurance_request.email_sent_at = moscow_now
        insurance_request.save()
        
        # Получаем информацию о формате для логирования успеха
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
        
        logger.info(f"Email sent successfully for request {pk} | {format_context}")
        return JsonResponse({'success': True, 'message': 'Письмо отправлено'})
        
    except Exception as e:
        # Получаем информацию о формате для логирования ошибки
        format_context = "Format: unknown, Type: unknown"
        if insurance_request.additional_data:
            application_type = insurance_request.additional_data.get('application_type')
            application_format = insurance_request.additional_data.get('application_format')
            format_context = _get_format_context_for_logging(application_type, application_format)
        
        logger.error(f"Error sending email for request {pk}: {str(e)} | {format_context}")
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

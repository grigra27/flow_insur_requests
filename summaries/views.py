"""
Представления для работы со сводами предложений
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import logging
import os

from .models import InsuranceSummary, InsuranceOffer, SummaryTemplate
from insurance_requests.models import InsuranceRequest
from insurance_requests.decorators import user_required, admin_required
from .forms import OfferForm, SummaryForm, AddOfferToSummaryForm
from .exceptions import DuplicateOfferError

logger = logging.getLogger(__name__)


@user_required
def summary_list(request):
    """Список всех сводов с фильтрацией и сортировкой"""
    from .forms import SummaryFilterForm
    
    # Получаем базовый queryset с оптимизацией запросов
    summaries = InsuranceSummary.objects.select_related('request')
    
    # Получаем список доступных филиалов из сводов
    available_branches = summaries.values_list('request__branch', flat=True).distinct().exclude(
        request__branch__isnull=True
    ).exclude(request__branch='').order_by('request__branch')
    
    # Применяем фильтры
    filter_form = SummaryFilterForm(request.GET)
    current_branch = request.GET.get('branch')
    
    if filter_form.is_valid():
        # Фильтрация по филиалу
        if current_branch:
            summaries = summaries.filter(request__branch=current_branch)
        

        
        # Фильтрация по номеру ДФА
        if filter_form.cleaned_data.get('dfa_number'):
            summaries = summaries.filter(
                request__dfa_number__icontains=filter_form.cleaned_data['dfa_number']
            )
        
        # Фильтрация по месяцу создания свода
        if filter_form.cleaned_data.get('month'):
            summaries = summaries.filter(created_at__month=filter_form.cleaned_data['month'])
        
        # Фильтрация по году создания свода
        if filter_form.cleaned_data.get('year'):
            summaries = summaries.filter(created_at__year=filter_form.cleaned_data['year'])
    
    # Подсчет количества сводов для каждого филиала (только если выбран конкретный филиал)
    branch_counts = {}
    if available_branches and current_branch:
        # Считаем только для текущего активного филиала
        branch_summaries = InsuranceSummary.objects.select_related('request').filter(request__branch=current_branch)
        
        # Применяем остальные фильтры для корректного подсчета
        if filter_form.is_valid():
            if filter_form.cleaned_data.get('dfa_number'):
                branch_summaries = branch_summaries.filter(
                    request__dfa_number__icontains=filter_form.cleaned_data['dfa_number']
                )
            
            if filter_form.cleaned_data.get('month'):
                branch_summaries = branch_summaries.filter(created_at__month=filter_form.cleaned_data['month'])
            
            if filter_form.cleaned_data.get('year'):
                branch_summaries = branch_summaries.filter(created_at__year=filter_form.cleaned_data['year'])
        
        branch_counts[current_branch] = branch_summaries.count()
    
    # Подсчет общего количества сводов (только если не выбран конкретный филиал)
    total_summaries_count = 0
    if not current_branch:
        total_summaries_queryset = InsuranceSummary.objects.select_related('request')
        if filter_form.is_valid():
            if filter_form.cleaned_data.get('dfa_number'):
                total_summaries_queryset = total_summaries_queryset.filter(
                    request__dfa_number__icontains=filter_form.cleaned_data['dfa_number']
                )
            
            if filter_form.cleaned_data.get('month'):
                total_summaries_queryset = total_summaries_queryset.filter(created_at__month=filter_form.cleaned_data['month'])
            
            if filter_form.cleaned_data.get('year'):
                total_summaries_queryset = total_summaries_queryset.filter(created_at__year=filter_form.cleaned_data['year'])
        
        total_summaries_count = total_summaries_queryset.count()
    
    # Сортировка по умолчанию
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = ['-created_at', 'created_at', '-total_offers', 'total_offers', 'status']
    if sort_by in valid_sorts:
        summaries = summaries.order_by(sort_by)
    else:
        summaries = summaries.order_by('-created_at')
    
    # Реализация пагинации (требование 5.1, 5.2)
    paginator = Paginator(summaries, 30)  # 30 сводов на страницу
    page = request.GET.get('page')
    
    try:
        summaries = paginator.page(page)
    except PageNotAnInteger:
        # Если номер страницы не является целым числом, показываем первую страницу
        summaries = paginator.page(1)
    except EmptyPage:
        # Если номер страницы превышает максимальный, показываем последнюю страницу
        summaries = paginator.page(paginator.num_pages)
    
    # Обновляем контекст шаблона для передачи информации о филиале (требование 4.1, 4.2, 4.3)
    return render(request, 'summaries/summary_list.html', {
        'summaries': summaries,
        'paginator': paginator,
        'filter_form': filter_form,
        'available_branches': available_branches,
        'branch_counts': branch_counts,
        'current_branch': current_branch,
        'total_summaries_count': total_summaries_count,
        'current_sort': sort_by,
        'show_branch_counts': bool(current_branch),  # Показывать счетчики только для активного филиала
        'show_total_count': not current_branch,      # Показывать общий счетчик только для "Все своды"
    })


@user_required
def summary_detail(request, pk):
    """Детальная информация о своде"""
    summary = get_object_or_404(
        InsuranceSummary.objects.select_related('request').prefetch_related('offers'), 
        pk=pk
    )
    
    # Получаем предложения с правильной сортировкой по новой структуре
    offers = summary.offers.filter(is_valid=True).order_by('company_name', 'insurance_year')
    
    # Группируем предложения по компаниям (company-first grouping)
    companies_with_offers = summary.get_offers_grouped_by_company()
    
    # Получаем структурированные данные для шаблона (company-year matrix)
    company_year_matrix = summary.get_company_year_matrix()
    
    # Сортируем компании по алфавиту
    sorted_companies = sorted(companies_with_offers.keys())
    
    # Получаем корректное количество уникальных компаний
    unique_companies_count = summary.get_unique_companies_count()
    
    # Получаем данные о компаниях с количеством лет для отображения тегов
    companies_with_year_counts = summary.get_companies_with_year_counts()
    
    # Получаем данные об итоговых суммах по компаниям для многолетних предложений
    company_totals = summary.get_company_totals()
    
    # Получаем примечания, сгруппированные по компаниям
    company_notes = summary.get_company_notes()
    
    return render(request, 'summaries/summary_detail.html', {
        'summary': summary,
        'offers': offers,
        'companies_with_offers': companies_with_offers,
        'company_year_matrix': company_year_matrix,
        'sorted_companies': sorted_companies,
        'unique_companies_count': unique_companies_count,
        'companies_with_year_counts': companies_with_year_counts,
        'company_totals': company_totals,
        'company_notes': company_notes,
    })


@user_required
def create_summary(request, request_id):
    """
    Создание свода для заявки с улучшенной обработкой ошибок и проверками доступа.
    
    Требования: 1.2, 1.3, 1.4
    """
    insurance_request = get_object_or_404(InsuranceRequest, pk=request_id)
    
    # Дополнительные проверки прав доступа (требование 1.2)
    if not request.user.is_authenticated:
        messages.error(request, 'Необходимо войти в систему для создания свода')
        return redirect('insurance_requests:login')
    
    # Проверяем права пользователя на создание сводов
    from insurance_requests.decorators import has_user_access
    if not has_user_access(request.user):
        messages.error(request, 'У вас недостаточно прав для создания сводов')
        return redirect('insurance_requests:request_detail', pk=request_id)
    
    # Проверяем, можно ли создать свод для этой заявки (требование 1.2)
    if hasattr(insurance_request, 'summary'):
        messages.info(request, f'Свод для заявки {insurance_request.get_display_name()} уже существует')
        return redirect('summaries:summary_detail', pk=insurance_request.summary.pk)
    
    # Проверяем статус заявки - можно создавать свод только для определенных статусов
    allowed_statuses = ['uploaded', 'email_generated', 'emails_sent', 'response_received']
    if insurance_request.status not in allowed_statuses:
        messages.error(request, 
                      f'Нельзя создать свод для заявки со статусом "{insurance_request.get_status_display()}". '
                      f'Свод можно создать только для заявок со статусами: '
                      f'{", ".join([dict(insurance_request.STATUS_CHOICES).get(s, s) for s in allowed_statuses])}')
        return redirect('insurance_requests:request_detail', pk=request_id)
    
    # Проверяем обязательные поля заявки
    validation_errors = []
    if not insurance_request.client_name or not insurance_request.client_name.strip():
        validation_errors.append('Не указано имя клиента')
    
    if not insurance_request.inn or not insurance_request.inn.strip():
        validation_errors.append('Не указан ИНН клиента')
    
    if not insurance_request.insurance_type:
        validation_errors.append('Не указан тип страхования')
    
    if validation_errors:
        messages.error(request, 
                      f'Невозможно создать свод: {"; ".join(validation_errors)}. '
                      'Пожалуйста, дополните информацию в заявке.')
        return redirect('insurance_requests:request_detail', pk=request_id)
    
    # Создание свода с улучшенной обработкой ошибок (требование 1.3)
    try:
        with transaction.atomic():
            # Создаем свод
            summary = InsuranceSummary.objects.create(
                request=insurance_request,
                status='collecting'
            )
            
            # Обновляем статус заявки, если необходимо
            if insurance_request.status == 'uploaded':
                insurance_request.status = 'email_generated'
                insurance_request.save(update_fields=['status', 'updated_at'])
            
            logger.info(f"Summary created successfully for request {request_id} by user {request.user.username}")
            
            # Улучшенное сообщение об успехе (требование 1.3)
            messages.success(request, 
                           f'Свод предложений для заявки {insurance_request.get_display_name()} '
                           f'({insurance_request.client_name}) успешно создан')
            
            # Корректное перенаправление после создания свода (требование 1.4)
            return redirect('summaries:summary_detail', pk=summary.pk)
            
    except Exception as e:
        # Улучшенная обработка ошибок (требование 1.3)
        error_message = str(e)
        logger.error(f"Error creating summary for request {request_id} by user {request.user.username}: {error_message}", 
                    exc_info=True)
        
        # Более информативные сообщения об ошибках для пользователя
        if 'UNIQUE constraint failed' in error_message or 'duplicate key' in error_message.lower():
            messages.error(request, 
                          f'Свод для заявки {insurance_request.get_display_name()} уже существует. '
                          'Обновите страницу и попробуйте снова.')
        elif 'permission' in error_message.lower() or 'access' in error_message.lower():
            messages.error(request, 
                          'Недостаточно прав для создания свода. '
                          'Обратитесь к администратору системы.')
        elif 'database' in error_message.lower() or 'connection' in error_message.lower():
            messages.error(request, 
                          'Временная ошибка базы данных. '
                          'Пожалуйста, попробуйте создать свод через несколько минут.')
        else:
            messages.error(request, 
                          f'Произошла ошибка при создании свода: {error_message}. '
                          'Если ошибка повторяется, обратитесь к администратору.')
        
        # Корректное перенаправление при ошибке (требование 1.4)
        return redirect('insurance_requests:request_detail', pk=request_id)


@user_required
def add_offer(request, summary_id):
    """Добавление предложения к своду"""
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    
    if request.method == 'POST':
        form = AddOfferToSummaryForm(request.POST)
        
        # Логируем данные формы для отладки
        logger.info(f"Form data received for summary {summary_id}: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    offer = form.save(commit=False)
                    offer.summary = summary
                    offer.save()
                    
                    # Обновляем счетчик предложений в своде
                    summary.update_total_offers_count()
                    
                    logger.info(f"Offer saved successfully: {offer.company_name} ({offer.get_insurance_year_display()}) for summary {summary_id}")
                    
                    messages.success(request, f'Предложение от {offer.company_name} ({offer.get_insurance_year_display()}) успешно добавлено')
                    return redirect('summaries:summary_detail', pk=summary_id)
                    
            except IntegrityError as e:
                # Специальная обработка ошибок дублирования предложений
                error_str = str(e)
                if ('UNIQUE constraint failed' in error_str or 
                    'duplicate key value violates unique constraint' in error_str):
                    # Извлекаем информацию о дублирующемся предложении из данных формы
                    company_name = form.cleaned_data.get('company_name', 'неизвестная компания')
                    insurance_year = form.cleaned_data.get('insurance_year', 'неизвестный год')
                    
                    # Создаем кастомное исключение для лучшей обработки
                    duplicate_error = DuplicateOfferError(company_name, insurance_year)
                    messages.error(request, duplicate_error.get_user_message())
                    logger.warning(f"Duplicate offer attempt for summary {summary_id}: {company_name} year {insurance_year}")
                else:
                    # Обработка других ошибок целостности данных
                    logger.error(f"IntegrityError adding offer to summary {summary_id}: {str(e)}", exc_info=True)
                    messages.error(request, f'Ошибка целостности данных при сохранении предложения: {str(e)}')
            except Exception as e:
                # Обработка всех остальных ошибок
                logger.error(f"Error adding offer to summary {summary_id}: {str(e)}", exc_info=True)
                messages.error(request, f'Ошибка при сохранении предложения: {str(e)}')
        else:
            # Логируем ошибки валидации
            logger.warning(f"Form validation failed for summary {summary_id}. Errors: {form.errors}")
            
            # Добавляем общее сообщение об ошибке валидации
            error_messages = []
            for field, errors in form.errors.items():
                if field == '__all__':
                    error_messages.extend(errors)
                else:
                    field_label = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_label}: {error}")
            
            if error_messages:
                messages.error(request, f'Ошибки в форме: {"; ".join(error_messages)}')
            else:
                messages.error(request, 'Проверьте правильность заполнения всех полей')
    else:
        form = AddOfferToSummaryForm()
    
    return render(request, 'summaries/add_offer.html', {
        'form': form,
        'summary': summary
    })


@user_required
def generate_summary_file(request, summary_id):
    """Генерация Excel файла свода"""
    from datetime import datetime
    from urllib.parse import quote
    import re
    from .services import get_excel_export_service, ExcelExportServiceError, InvalidSummaryDataError, TemplateNotFoundError
    
    summary = get_object_or_404(InsuranceSummary.objects.select_related('request'), pk=summary_id)
    
    # Проверка статуса свода - требование 1.1
    if summary.status != 'ready':
        logger.warning(f"Attempt to generate Excel for summary {summary_id} with status '{summary.status}'")
        return JsonResponse({
            'error': 'Файл можно генерировать только для сводов в статусе "Готов к отправке"'
        }, status=400)
    
    try:
        # Создание сервиса для генерации Excel - требование 1.2
        service = get_excel_export_service()
        
        # Генерация Excel файла - требование 1.2, 1.3
        excel_file = service.generate_summary_excel(summary)
        
        # Формирование имени файла - требование 3.2, 15.1-15.8
        # Обработка номера ДФА: извлечение только цифр
        dfa_number_digits_only = re.sub(r'[^\d]', '', summary.request.dfa_number)
        # Изменение формата даты на день_месяц_год
        date_formatted = datetime.now().strftime('%d_%m_%Y')
        filename = f"svod_{dfa_number_digits_only}_{date_formatted}.xlsx"
        
        # Создание HTTP response с Excel файлом - требование 3.1
        response = HttpResponse(
            excel_file.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        logger.info(f"Excel file successfully generated for summary {summary_id}: {filename}")
        return response
        
    except InvalidSummaryDataError as e:
        # Обработка ошибок валидации данных - требование 4.1, 4.2
        logger.error(f"Invalid summary data for {summary_id}: {str(e)}")
        return JsonResponse({
            'error': f'Ошибка в данных свода: {str(e)}'
        }, status=400)
        
    except TemplateNotFoundError as e:
        # Обработка ошибок недоступности шаблона - требование 4.3
        logger.error(f"Template not found for summary {summary_id}: {str(e)}")
        return JsonResponse({
            'error': 'Шаблон Excel-файла недоступен. Обратитесь к администратору.'
        }, status=500)
        
    except ExcelExportServiceError as e:
        # Обработка других ошибок сервиса - требование 3.3
        logger.error(f"Excel export service error for summary {summary_id}: {str(e)}")
        return JsonResponse({
            'error': f'Ошибка при генерации файла: {str(e)}'
        }, status=500)
        
    except Exception as e:
        # Обработка неожиданных ошибок - требование 3.3
        logger.error(f"Unexpected error generating summary file for {summary_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Произошла неожиданная ошибка при генерации файла. Обратитесь к администратору.'
        }, status=500)


@require_http_methods(["POST"])
@user_required
def send_summary_to_client(request, summary_id):
    """Отправка свода клиенту без автоматического изменения статуса"""
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    
    try:
        # TODO: Реализовать отправку email клиенту
        # Пока используем заглушку
        
        # Логируем действие отправки без изменения статуса
        logger.info(f"Summary {summary_id} sent to client without status change by user {request.user.username}")
        
        # Возвращаем успешный результат без изменения статуса
        return JsonResponse({
            'success': True, 
            'message': 'Свод отправлен в Альянс. Для изменения статуса используйте блок "Управление статусом".'
        })
        
    except Exception as e:
        logger.error(f"Error sending summary {summary_id} to client: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Ошибка при отправке свода: {str(e)}'})


@user_required
def copy_offer(request, offer_id):
    """Копирование предложения"""
    original_offer = get_object_or_404(InsuranceOffer, pk=offer_id)
    
    if request.method == 'POST':
        form = OfferForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Создаем новое предложение на основе данных формы
                    new_offer = form.save(commit=False)
                    new_offer.summary = original_offer.summary
                    new_offer.save()
                    
                    # Обновляем счетчик предложений в своде
                    original_offer.summary.update_total_offers_count()
                    
                    logger.info(f"Offer copied: {original_offer.id} -> {new_offer.id} by user {request.user.username}")
                    
                    messages.success(request, f'Предложение от {new_offer.company_name} ({new_offer.get_insurance_year_display()}) успешно скопировано')
                    return redirect('summaries:summary_detail', pk=new_offer.summary.pk)
                    
            except IntegrityError as e:
                # Специальная обработка ошибок дублирования предложений
                error_str = str(e)
                if ('UNIQUE constraint failed' in error_str or 
                    'duplicate key value violates unique constraint' in error_str):
                    # Извлекаем информацию о дублирующемся предложении из данных формы
                    company_name = form.cleaned_data.get('company_name', 'неизвестная компания')
                    insurance_year = form.cleaned_data.get('insurance_year', 'неизвестный год')
                    
                    # Создаем кастомное исключение для лучшей обработки
                    duplicate_error = DuplicateOfferError(company_name, insurance_year)
                    messages.error(request, duplicate_error.get_user_message())
                    logger.warning(f"Duplicate offer attempt during copy for summary {original_offer.summary.id}: {company_name} year {insurance_year}")
                else:
                    # Обработка других ошибок целостности данных
                    logger.error(f"IntegrityError copying offer {offer_id}: {str(e)}", exc_info=True)
                    messages.error(request, f'Ошибка целостности данных при копировании предложения: {str(e)}')
            except Exception as e:
                # Обработка всех остальных ошибок
                logger.error(f"Error copying offer {offer_id}: {str(e)}", exc_info=True)
                messages.error(request, f'Ошибка при копировании предложения: {str(e)}')
        else:
            # Логируем ошибки валидации
            logger.warning(f"Form validation failed for copying offer {offer_id}. Errors: {form.errors}")
            
            # Добавляем общее сообщение об ошибке валидации
            error_messages = []
            for field, errors in form.errors.items():
                if field == '__all__':
                    error_messages.extend(errors)
                else:
                    field_label = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_label}: {error}")
            
            if error_messages:
                messages.error(request, f'Ошибки в форме: {"; ".join(error_messages)}')
            else:
                messages.error(request, 'Проверьте правильность заполнения всех полей')
    else:
        # Создаем форму с данными из оригинального предложения
        initial_data = {
            'company_name': original_offer.company_name,
            'insurance_year': original_offer.insurance_year,
            'insurance_sum': original_offer.insurance_sum,
            'franchise_1': original_offer.franchise_1,
            'premium_with_franchise_1': original_offer.premium_with_franchise_1,
            'franchise_2': original_offer.franchise_2,
            'premium_with_franchise_2': original_offer.premium_with_franchise_2,
            'installment_variant_1': original_offer.installment_variant_1,
            'payments_per_year_variant_1': original_offer.payments_per_year_variant_1,
            'installment_variant_2': original_offer.installment_variant_2,
            'payments_per_year_variant_2': original_offer.payments_per_year_variant_2,
            'notes': original_offer.notes,
        }
        form = OfferForm(initial=initial_data)
    
    return render(request, 'summaries/copy_offer.html', {
        'form': form,
        'original_offer': original_offer
    })


@user_required
def edit_offer(request, offer_id):
    """Редактирование предложения"""
    offer = get_object_or_404(InsuranceOffer, pk=offer_id)
    
    if request.method == 'POST':
        form = OfferForm(request.POST, request.FILES, instance=offer)
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated_offer = form.save()
                    

                    
                    messages.success(request, f'Предложение от {updated_offer.company_name} ({updated_offer.get_insurance_year_display()}) обновлено')
                    return redirect('summaries:summary_detail', pk=updated_offer.summary.pk)
                    
            except Exception as e:
                logger.error(f"Error updating offer {offer_id}: {str(e)}")
                messages.error(request, f'Ошибка при обновлении предложения: {str(e)}')
        else:
            # Добавляем обработку ошибок валидации для лучшего UX
            error_messages = []
            for field, errors in form.errors.items():
                if field == '__all__':
                    error_messages.extend(errors)
                else:
                    field_label = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_label}: {error}")
            
            if error_messages:
                messages.error(request, f'Ошибки в форме: {"; ".join(error_messages)}')
            else:
                messages.error(request, 'Проверьте правильность заполнения всех полей')
    else:
        form = OfferForm(instance=offer)
    
    return render(request, 'summaries/edit_offer.html', {
        'form': form,
        'offer': offer
    })


@require_http_methods(["POST"])
@user_required
def delete_offer(request, offer_id):
    """Удаление предложения"""
    offer = get_object_or_404(InsuranceOffer, pk=offer_id)
    summary = offer.summary
    summary_id = summary.pk
    company_name = offer.company_name
    insurance_year_display = offer.get_insurance_year_display()
    
    try:
        with transaction.atomic():
            # Удаляем предложение
            offer.delete()
            
            # Обновляем счетчик предложений в своде
            summary.update_total_offers_count()
            
            logger.info(f"Offer deleted: {company_name} ({insurance_year_display}) from summary {summary_id}")
            
            return JsonResponse({
                'success': True, 
                'message': f'Предложение от {company_name} ({insurance_year_display}) удалено',
                'new_companies_count': summary.get_unique_companies_count()
            })
        
    except Exception as e:
        logger.error(f"Error deleting offer {offer_id}: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'Не удалось удалить предложение: {str(e)}'
        })


@require_http_methods(["POST"])
@user_required
def change_summary_status(request, summary_id):
    """Изменение статуса свода"""
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    new_status = request.POST.get('status')
    
    if new_status in dict(InsuranceSummary.STATUS_CHOICES):
        old_status = summary.status
        summary.status = new_status
        
        # Если статус изменен на "Отправлен в Альянс", устанавливаем время отправки
        if new_status == 'sent':
            from django.utils import timezone
            summary.sent_to_client_at = timezone.now()
        
        summary.save()
        
        logger.info(f"Summary {summary_id} status changed from '{old_status}' to '{new_status}'")
        
        return JsonResponse({
            'success': True, 
            'message': f'Статус изменен на "{summary.get_status_display()}"',
            'new_status': new_status,
            'new_status_display': summary.get_status_display()
        })
    
    return JsonResponse({
        'success': False, 
        'error': 'Недопустимый статус'
    })


# Удалена дублирующаяся функция upload_multiple_company_responses - используется версия ниже

@require_http_methods(["POST"])
@user_required
def upload_company_response(request, summary_id):
    """
    Загрузка ответа страховой компании через Excel файл
    
    Требования: 1.3, 2.1, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5
    """
    from .services import get_excel_response_processor
    from .services import ExcelProcessingError, InvalidFileFormatError, MissingDataError, InvalidDataError, RowProcessingError
    from .forms import CompanyResponseUploadForm
    
    # Получаем свод с проверкой доступа
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    
    # Проверка аутентификации и прав пользователя (требование 1.3, 2.1)
    if not request.user.is_authenticated:
        logger.warning(f"Unauthenticated user attempted to upload company response for summary {summary_id}")
        return JsonResponse({
            'success': False,
            'error': 'Необходимо войти в систему для загрузки ответов компаний'
        }, status=401)
    
    # Проверяем права пользователя на изменение сводов
    from insurance_requests.decorators import has_user_access
    if not has_user_access(request.user):
        logger.warning(f"User {request.user.username} without sufficient permissions attempted to upload company response for summary {summary_id}")
        return JsonResponse({
            'success': False,
            'error': 'У вас недостаточно прав для загрузки ответов компаний'
        }, status=403)
    
    # Валидация статуса свода (только "Сбор предложений") (требование 2.1)
    if summary.status != 'collecting':
        logger.warning(f"Attempt to upload company response for summary {summary_id} with status '{summary.status}' by user {request.user.username}")
        return JsonResponse({
            'success': False,
            'error': 'Загрузка ответов компаний доступна только при статусе "Сбор предложений"'
        }, status=400)
    
    # Обработка POST запросов с файлами (требование 2.1)
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Метод не поддерживается. Используйте POST для загрузки файлов.'
        }, status=405)
    
    # Валидация формы загрузки файла
    form = CompanyResponseUploadForm(request.POST, request.FILES)
    
    if not form.is_valid():
        # Обработка ошибок валидации файлов (требование 5.1, 5.3, 5.5)
        error_messages = []
        for field, errors in form.errors.items():
            if field == '__all__':
                error_messages.extend(errors)
            else:
                field_label = form.fields[field].label if field in form.fields else field
                for error in errors:
                    error_messages.append(f"{field_label}: {error}")
        
        error_message = '; '.join(error_messages) if error_messages else 'Ошибка валидации файла'
        
        logger.warning(f"File validation failed for summary {summary_id} by user {request.user.username}: {error_message}")
        return JsonResponse({
            'success': False,
            'error': error_message,
            'field_errors': form.errors
        }, status=400)
    
    # Получаем загруженный файл
    excel_file = form.cleaned_data['excel_file']
    
    try:
        # Интеграция с сервисом ExcelResponseProcessor (требование 4.3, 5.2, 5.4)
        processor = get_excel_response_processor()
        
        # Обработка успешной загрузки с созданием предложений (требование 4.3, 5.2, 5.4)
        result = processor.process_excel_file(excel_file, summary)
        
        # Логирование успешной операции
        logger.info(f"Company response uploaded successfully for summary {summary_id} by user {request.user.username}: "
                   f"Company '{result['company_name']}', {result['offers_created']} offers created for years {result['years']}")
        
        # Формируем улучшенное сообщение об успешной обработке (требование 3.1, 3.2)
        years_processed = result.get('years', [])
        skipped_rows = result.get('skipped_rows', [])
        processed_rows = result.get('processed_rows', [])
        
        # Основное сообщение с количеством обработанных лет
        if len(years_processed) == 1:
            base_message = f'Предложение от компании "{result["company_name"]}" успешно загружено для {years_processed[0]} года страхования'
        else:
            years_str = ', '.join(map(str, sorted(years_processed)))
            base_message = f'Предложение от компании "{result["company_name"]}" успешно загружено для {len(years_processed)} лет страхования ({years_str})'
        
        # Проверяем информацию о сопоставлении компании
        matching_info = result.get('company_matching_info', {})
        additional_messages = []
        
        # Информация о пропущенных строках (требование 3.2)
        if skipped_rows:
            if len(processed_rows) > 0:
                additional_messages.append(
                    f'Обработано строк: {len(processed_rows)} ({", ".join(map(str, processed_rows))}). '
                    f'Пропущено строк: {len(skipped_rows)} ({", ".join(map(str, skipped_rows))})'
                )
            else:
                additional_messages.append(
                    f'Пропущено строк с пустыми данными: {len(skipped_rows)} ({", ".join(map(str, skipped_rows))})'
                )
        elif processed_rows:
            additional_messages.append(
                f'Все данные успешно обработаны из {len(processed_rows)} строк ({", ".join(map(str, processed_rows))})'
            )
        
        # Информация о сопоставлении названия компании
        if matching_info.get('assigned_other'):
            additional_messages.append(
                f'Внимание: Название компании "{matching_info["original_name"]}" не найдено в списке, '
                f'поэтому было присвоено значение "Другое". Проверьте правильность названия в файле.'
            )
        elif matching_info.get('was_matched') and not matching_info.get('assigned_other'):
            additional_messages.append(
                f'Название компании автоматически сопоставлено: "{matching_info["original_name"]}" → "{matching_info["standardized_name"]}"'
            )
        
        # Возврат JSON ответов с результатами обработки (требование 5.2, 5.4)
        return JsonResponse({
            'success': True,
            'message': base_message,
            'additional_messages': additional_messages,
            'details': {
                'company_name': result['company_name'],
                'offers_created': result['offers_created'],
                'years': result['years'],
                'processed_rows': processed_rows,
                'skipped_rows': skipped_rows,
                'matching_info': matching_info
            }
        })
        
    except InvalidFileFormatError as e:
        # Улучшенная обработка ошибок формата файла (требование 3.4, 4.3)
        error_details = str(e)
        error_message = f"Ошибка формата файла: {error_details}"
        
        # Добавляем инструкции по исправлению
        correction_instructions = []
        if 'расширение' in error_details.lower() or '.xlsx' in error_details:
            correction_instructions.append("Убедитесь, что файл имеет расширение .xlsx")
            correction_instructions.append("Сохраните файл в формате Excel (.xlsx) если он в другом формате")
        elif 'лист' in error_details.lower():
            correction_instructions.append("Убедитесь, что файл содержит хотя бы один рабочий лист")
        elif 'поврежден' in error_details.lower() or 'corrupt' in error_details.lower():
            correction_instructions.append("Файл может быть поврежден - попробуйте пересохранить его")
        else:
            correction_instructions.append("Убедитесь, что загружаете корректный Excel файл (.xlsx)")
            correction_instructions.append("Проверьте, что файл не поврежден и открывается в Excel")
        
        if correction_instructions:
            error_message += f". Рекомендации: {'; '.join(correction_instructions)}"
        
        logger.warning(f"Invalid file format for summary {summary_id} by user {request.user.username}: {error_message}")
        return JsonResponse({
            'success': False,
            'error': error_message,
            'error_type': 'file_format',
            'correction_instructions': correction_instructions
        }, status=400)
        
    except MissingDataError as e:
        # Улучшенная обработка ошибок отсутствующих данных (требование 3.4, 4.3)
        missing_cells = getattr(e, 'missing_cells', [])
        
        if missing_cells:
            cells_str = ', '.join(missing_cells)
            error_message = f"Отсутствуют обязательные данные в ячейках: {cells_str}"
            
            # Добавляем инструкции по исправлению для конкретных ячеек
            correction_instructions = []
            for cell in missing_cells:
                if cell == 'B2':
                    correction_instructions.append("Ячейка B2: укажите название страховой компании")
                elif cell.startswith('A') and cell[1:].isdigit():
                    row = cell[1:]
                    correction_instructions.append(f"Ячейка A{row}: укажите номер года страхования (1, 2, 3 и т.д.)")
                elif cell.startswith('B') and cell[1:].isdigit():
                    row = cell[1:]
                    correction_instructions.append(f"Ячейка B{row}: укажите страховую сумму")
                elif cell.startswith('D') and cell[1:].isdigit():
                    row = cell[1:]
                    correction_instructions.append(f"Ячейка D{row}: укажите размер премии")
                elif cell.startswith('E') and cell[1:].isdigit():
                    row = cell[1:]
                    correction_instructions.append(f"Ячейка E{row}: укажите размер франшизы (может быть 0)")
                elif cell.startswith('F') and cell[1:].isdigit():
                    row = cell[1:]
                    correction_instructions.append(f"Ячейка F{row}: укажите тип рассрочки (1, 2, 3, 4 или 12)")
            
            if correction_instructions:
                error_message += f". Необходимо заполнить: {'; '.join(correction_instructions)}"
        else:
            error_message = f"Отсутствуют обязательные данные: {str(e)}"
            correction_instructions = ["Проверьте, что файл содержит данные в правильном формате"]
        
        logger.warning(f"Missing data in file for summary {summary_id} by user {request.user.username}: {error_message}")
        return JsonResponse({
            'success': False,
            'error': error_message,
            'error_type': 'missing_data',
            'missing_cells': missing_cells,
            'correction_instructions': correction_instructions
        }, status=400)
        
    except InvalidDataError as e:
        # Улучшенная обработка ошибок некорректных данных (требование 3.4, 4.3)
        field_name = getattr(e, 'field_name', 'неизвестное поле')
        field_value = getattr(e, 'value', 'неизвестное значение')
        expected_format = getattr(e, 'expected_format', 'корректный формат')
        
        error_message = f"Некорректные данные в поле '{field_name}': значение '{field_value}' не соответствует ожидаемому формату ({expected_format})"
        
        # Добавляем инструкции по исправлению
        correction_instructions = []
        if 'год' in field_name.lower():
            correction_instructions.append("Убедитесь, что год указан числом от 1 до 10")
        elif 'сумма' in field_name.lower() or 'премия' in field_name.lower() or 'франшиза' in field_name.lower():
            correction_instructions.append("Убедитесь, что сумма указана числом без пробелов и специальных символов")
        elif 'рассрочка' in field_name.lower():
            correction_instructions.append("Рассрочка должна быть одним из значений: 1, 2, 3, 4, 12")
        
        if correction_instructions:
            error_message += f". {' '.join(correction_instructions)}"
        
        logger.warning(f"Invalid data in file for summary {summary_id} by user {request.user.username}: {error_message}")
        return JsonResponse({
            'success': False,
            'error': error_message,
            'error_type': 'invalid_data',
            'field_name': field_name,
            'field_value': field_value,
            'expected_format': expected_format,
            'correction_instructions': correction_instructions
        }, status=400)
        
    except RowProcessingError as e:
        # Обработка ошибок конкретных строк (требование 3.4, 4.3)
        row_number = getattr(e, 'row_number', 'неизвестная')
        field_name = getattr(e, 'field_name', 'неизвестное поле')
        cell_address = getattr(e, 'cell_address', None)
        error_details = getattr(e, 'error_message', str(e))
        
        if cell_address:
            error_message = f"Ошибка в строке {row_number}, ячейка {cell_address} (поле '{field_name}'): {error_details}"
        else:
            error_message = f"Ошибка в строке {row_number} (поле '{field_name}'): {error_details}"
        
        # Добавляем инструкции по исправлению в зависимости от типа ошибки
        correction_instructions = []
        if 'год' in field_name.lower():
            correction_instructions.append(f"Проверьте ячейку {cell_address or f'A{row_number}'} - год должен быть числом от 1 до 10")
        elif 'сумма' in field_name.lower():
            correction_instructions.append(f"Проверьте ячейку {cell_address or f'B{row_number}'} - страховая сумма должна быть положительным числом")
        elif 'премия' in field_name.lower():
            correction_instructions.append(f"Проверьте ячейку {cell_address or f'D{row_number}'} - премия должна быть положительным числом")
        elif 'франшиза' in field_name.lower():
            correction_instructions.append(f"Проверьте ячейку {cell_address or f'E{row_number}'} - франшиза должна быть числом (может быть 0)")
        elif 'рассрочка' in field_name.lower():
            correction_instructions.append(f"Проверьте ячейку {cell_address or f'F{row_number}'} - рассрочка должна быть одним из значений: 1, 2, 3, 4, 12")
        
        if correction_instructions:
            error_message += f". {' '.join(correction_instructions)}"
        
        logger.warning(f"Row processing error for summary {summary_id} by user {request.user.username}: {error_message}")
        return JsonResponse({
            'success': False,
            'error': error_message,
            'error_type': 'row_processing_error',
            'row_number': row_number,
            'field_name': field_name,
            'cell_address': cell_address,
            'correction_instructions': correction_instructions
        }, status=400)
        
    except DuplicateOfferError as e:
        # Обработка дублирования предложений (IntegrityError) (требование 5.1, 5.3, 5.5)
        error_message = f"Дублирование предложения: {str(e)}"
        logger.warning(f"Duplicate offer attempt for summary {summary_id} by user {request.user.username}: {error_message}")
        return JsonResponse({
            'success': False,
            'error': error_message,
            'error_type': 'duplicate_offer',
            'company_name': getattr(e, 'company_name', None),
            'year': getattr(e, 'year', None)
        }, status=409)
        
    except ExcelProcessingError as e:
        # Обработка других ошибок обработки Excel (требование 5.1, 5.3, 5.5)
        error_message = f"Ошибка обработки Excel файла: {str(e)}"
        logger.error(f"Excel processing error for summary {summary_id} by user {request.user.username}: {error_message}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': error_message,
            'error_type': 'processing_error'
        }, status=500)
        
    except Exception as e:
        # Логирование всех операций и ошибок (требование 5.1, 5.3, 5.5)
        error_message = f"Неожиданная ошибка при загрузке ответа компании: {str(e)}"
        logger.error(f"Unexpected error uploading company response for summary {summary_id} by user {request.user.username}: {error_message}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Произошла неожиданная ошибка при обработке файла. Обратитесь к администратору.',
            'error_type': 'unexpected_error'
        }, status=500)


@require_http_methods(["POST"])
@user_required
def upload_multiple_company_responses(request, summary_id):
    """
    Загрузка множественных ответов страховых компаний через Excel файлы
    
    Требования: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2
    """
    import time
    from .services.multiple_file_processor import MultipleFileProcessor
    from .forms import MultipleCompanyResponseUploadForm
    
    # Получаем свод с проверкой доступа
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    
    # Проверка аутентификации и прав пользователя
    if not request.user.is_authenticated:
        logger.warning(
            f"UPLOAD_MULTIPLE_AUTH_ERROR - Неавторизованная попытка загрузки | "
            f"summary_id={summary_id} | ip={request.META.get('REMOTE_ADDR', 'unknown')}"
        )
        return JsonResponse({
            'success': False,
            'error': 'Необходимо войти в систему для загрузки ответов компаний'
        }, status=401)
    
    # Проверяем права пользователя на изменение сводов
    from insurance_requests.decorators import has_user_access
    if not has_user_access(request.user):
        logger.warning(
            f"UPLOAD_MULTIPLE_PERMISSION_ERROR - Недостаточно прав | "
            f"user={request.user.username} | user_id={request.user.id} | summary_id={summary_id}"
        )
        return JsonResponse({
            'success': False,
            'error': 'У вас недостаточно прав для загрузки ответов компаний'
        }, status=403)
    
    # Валидация статуса свода (только "Сбор предложений")
    if summary.status != 'collecting':
        logger.warning(
            f"UPLOAD_MULTIPLE_STATUS_ERROR - Неверный статус свода | "
            f"user={request.user.username} | summary_id={summary_id} | "
            f"current_status={summary.status} | required_status=collecting"
        )
        return JsonResponse({
            'success': False,
            'error': 'Загрузка ответов компаний доступна только при статусе "Сбор предложений"'
        }, status=400)
    
    # Обработка POST запросов с файлами
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Метод не поддерживается. Используйте POST для загрузки файлов.'
        }, status=405)
    
    # Получаем загруженные файлы напрямую
    excel_files = request.FILES.getlist('excel_files')
    
    # Базовая валидация файлов
    if not excel_files:
        error_message = 'Ни одного файла не было отправлено. Проверьте тип кодировки формы.'
        logger.warning(
            f"UPLOAD_MULTIPLE_FORM_VALIDATION_ERROR - Ошибка валидации формы | "
            f"user={request.user.username} | summary_id={summary_id} | "
            f"error_message={error_message} | form_errors=<ul class=\"errorlist\"><li>excel_files<ul class=\"errorlist\"><li>{error_message}</li></ul></li></ul>"
        )
        return JsonResponse({
            'success': False,
            'error': error_message
        }, status=400)
    
    # Валидация файлов
    MAX_FILES = 10
    MAX_FILE_SIZE_MB = 1
    MAX_TOTAL_SIZE_MB = 10
    
    if len(excel_files) > MAX_FILES:
        error_message = f'Слишком много файлов ({len(excel_files)}). Максимальное количество файлов: {MAX_FILES}'
        logger.warning(
            f"UPLOAD_MULTIPLE_FORM_VALIDATION_ERROR - Ошибка валидации формы | "
            f"user={request.user.username} | summary_id={summary_id} | "
            f"error_message={error_message}"
        )
        return JsonResponse({
            'success': False,
            'error': error_message
        }, status=400)
    
    # Проверка каждого файла
    total_size = 0
    for file in excel_files:
        # Проверка расширения
        ext = os.path.splitext(file.name)[1].lower()
        if ext != '.xlsx':
            error_message = f'Файл "{file.name}" имеет неподдерживаемый формат. Разрешены только файлы .xlsx'
            logger.warning(
                f"UPLOAD_MULTIPLE_FORM_VALIDATION_ERROR - Ошибка валидации формы | "
                f"user={request.user.username} | summary_id={summary_id} | "
                f"error_message={error_message}"
            )
            return JsonResponse({
                'success': False,
                'error': error_message
            }, status=400)
        
        # Проверка размера файла
        max_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size > max_size_bytes:
            error_message = f'Файл "{file.name}" слишком большой ({file.size / (1024*1024):.1f}MB). Максимальный размер: {MAX_FILE_SIZE_MB}MB'
            logger.warning(
                f"UPLOAD_MULTIPLE_FORM_VALIDATION_ERROR - Ошибка валидации формы | "
                f"user={request.user.username} | summary_id={summary_id} | "
                f"error_message={error_message}"
            )
            return JsonResponse({
                'success': False,
                'error': error_message
            }, status=400)
        
        # Проверка на пустой файл
        if file.size == 0:
            error_message = f'Файл "{file.name}" пустой. Загрузите файл с данными'
            logger.warning(
                f"UPLOAD_MULTIPLE_FORM_VALIDATION_ERROR - Ошибка валидации формы | "
                f"user={request.user.username} | summary_id={summary_id} | "
                f"error_message={error_message}"
            )
            return JsonResponse({
                'success': False,
                'error': error_message
            }, status=400)
        
        total_size += file.size
    
    # Проверка общего размера
    max_total_size_bytes = MAX_TOTAL_SIZE_MB * 1024 * 1024
    if total_size > max_total_size_bytes:
        error_message = f'Общий размер файлов слишком большой ({total_size / (1024*1024):.1f}MB). Максимальный общий размер: {MAX_TOTAL_SIZE_MB}MB'
        logger.warning(
            f"UPLOAD_MULTIPLE_FORM_VALIDATION_ERROR - Ошибка валидации формы | "
            f"user={request.user.username} | summary_id={summary_id} | "
            f"error_message={error_message}"
        )
        return JsonResponse({
            'success': False,
            'error': error_message
        }, status=400)
    
# Файлы уже получены выше в блоке валидации
    
    try:
        # Засекаем время начала обработки
        start_time = time.time()
        total_size_mb = sum(file.size for file in excel_files) / (1024 * 1024)
        
        # Логирование начала операции
        logger.info(
            f"UPLOAD_MULTIPLE_START - Начало загрузки множественных файлов | "
            f"user={request.user.username} | user_id={request.user.id} | "
            f"summary_id={summary_id} | files_count={len(excel_files)} | "
            f"total_size_mb={total_size_mb:.2f} | "
            f"files=[{', '.join(f.name for f in excel_files)}]"
        )
        
        # Создаем процессор для множественных файлов
        processor = MultipleFileProcessor(summary)
        
        # Обрабатываем файлы
        results = processor.process_files(excel_files)
        
        # Вычисляем время обработки
        processing_time = time.time() - start_time
        
        # Подсчитываем статистику
        successful_files = sum(1 for result in results if result['success'])
        failed_files = len(results) - successful_files
        total_offers_created = sum(result.get('offers_created', 0) for result in results if result['success'])
        
        # Детальное логирование результатов
        logger.info(
            f"UPLOAD_MULTIPLE_COMPLETE - Загрузка множественных файлов завершена | "
            f"user={request.user.username} | summary_id={summary_id} | "
            f"total_files={len(results)} | successful={successful_files} | failed={failed_files} | "
            f"success_rate={successful_files/len(results)*100:.1f}% | "
            f"total_offers_created={total_offers_created} | processing_time={processing_time:.2f}s"
        )
        
        # Логирование деталей каждого файла
        for result in results:
            if result['success']:
                logger.debug(
                    f"UPLOAD_MULTIPLE_FILE_SUCCESS - Файл успешно обработан | "
                    f"filename={result['file_name']} | company={result.get('company_name', 'N/A')} | "
                    f"offers_created={result.get('offers_created', 0)}"
                )
            else:
                logger.debug(
                    f"UPLOAD_MULTIPLE_FILE_ERROR - Ошибка обработки файла | "
                    f"filename={result['file_name']} | error_type={result.get('error_type', 'unknown')} | "
                    f"error_message={result.get('error_message', 'N/A')}"
                )
        
        # Формируем ответ
        response_data = {
            'success': True,
            'total_files': len(results),
            'successful_files': successful_files,
            'failed_files': failed_files,
            'processing_time': processing_time,
            'results': results
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        processing_time = time.time() - start_time if 'start_time' in locals() else 0
        error_message = f"Неожиданная ошибка при загрузке множественных ответов компаний: {str(e)}"
        
        logger.error(
            f"UPLOAD_MULTIPLE_EXCEPTION - Неожиданная ошибка | "
            f"user={request.user.username} | summary_id={summary_id} | "
            f"files_count={len(excel_files)} | processing_time={processing_time:.2f}s | "
            f"error={error_message}",
            exc_info=True
        )
        
        return JsonResponse({
            'success': False,
            'error': 'Произошла неожиданная ошибка при обработке файлов. Обратитесь к администратору.',
            'error_type': 'unexpected_error'
        }, status=500)


@user_required
def offer_search(request):
    """Поиск и фильтрация предложений по различным критериям"""
    from .forms import CompanyOfferSearchForm
    from django.db.models import Q
    
    offers = InsuranceOffer.objects.filter(is_valid=True).select_related('summary', 'summary__request')
    search_form = CompanyOfferSearchForm(request.GET)
    
    if search_form.is_valid():
        # Фильтр по названию компании
        if search_form.cleaned_data.get('company_name'):
            offers = offers.filter(
                company_name__icontains=search_form.cleaned_data['company_name']
            )
        
        # Фильтр по минимальной премии
        if search_form.cleaned_data.get('min_premium'):
            offers = offers.filter(
                Q(premium_with_franchise_1__gte=search_form.cleaned_data['min_premium']) |
                Q(premium_with_franchise_2__gte=search_form.cleaned_data['min_premium'])
            )
        
        # Фильтр по максимальной премии
        if search_form.cleaned_data.get('max_premium'):
            offers = offers.filter(
                Q(premium_with_franchise_1__lte=search_form.cleaned_data['max_premium']) |
                Q(premium_with_franchise_2__lte=search_form.cleaned_data['max_premium'])
            )
        
        # Фильтр только предложения с рассрочкой
        if search_form.cleaned_data.get('installment_only'):
            offers = offers.filter(installment_available=True, payments_per_year__gt=1)
    
    # Сортировка
    sort_by = request.GET.get('sort', 'premium_with_franchise_1')
    valid_sorts = [
        'premium_with_franchise_1', '-premium_with_franchise_1',
        'premium_with_franchise_2', '-premium_with_franchise_2',
        'company_name', '-company_name',
        'insurance_year', '-insurance_year',
        'payments_per_year', '-payments_per_year'
    ]
    if sort_by in valid_sorts:
        offers = offers.order_by(sort_by)
    else:
        offers = offers.order_by('premium_with_franchise_1')
    
    # Группировка предложений по компаниям для лучшего отображения
    companies_data = {}
    for offer in offers:
        if offer.company_name not in companies_data:
            companies_data[offer.company_name] = []
        companies_data[offer.company_name].append(offer)
    
    return render(request, 'summaries/offer_search.html', {
        'offers': offers,
        'search_form': search_form,
        'companies_data': companies_data,
        'current_sort': sort_by
    })



@admin_required
def summary_statistics(request):
    """Статистика по сводам"""
    from django.db.models import Count, Avg, Min, Max
    
    stats = {
        'total_summaries': InsuranceSummary.objects.count(),
        'collecting': InsuranceSummary.objects.filter(status='collecting').count(),
        'ready': InsuranceSummary.objects.filter(status='ready').count(),
        'sent': InsuranceSummary.objects.filter(status='sent').count(),
        'completed_accepted': InsuranceSummary.objects.filter(status='completed_accepted').count(),
        'completed_rejected': InsuranceSummary.objects.filter(status='completed_rejected').count(),
        # Keep old 'completed' for backward compatibility during transition
        'completed': InsuranceSummary.objects.filter(status__in=['completed', 'completed_accepted', 'completed_rejected']).count(),
        'avg_offers_per_summary': InsuranceSummary.objects.aggregate(
            avg=Avg('total_offers')
        )['avg'] or 0,
        'total_offers': InsuranceOffer.objects.filter(is_valid=True).count(),
    }
    
    # Топ компаний по количеству предложений с обновленной статистикой
    top_companies = InsuranceOffer.objects.filter(is_valid=True).values('company_name').annotate(
        count=Count('id'),
        avg_premium_1=Avg('premium_with_franchise_1'),
        avg_premium_2=Avg('premium_with_franchise_2'),
        min_premium=Min('premium_with_franchise_1'),
        max_premium=Max('premium_with_franchise_1')
    ).order_by('-count')[:10]
    
    # Статистика по годам страхования
    year_stats = InsuranceOffer.objects.filter(is_valid=True).values('insurance_year').annotate(
        count=Count('id'),
        avg_premium=Avg('premium_with_franchise_1')
    ).order_by('insurance_year')
    
    # Статистика по рассрочке
    installment_stats = InsuranceOffer.objects.filter(is_valid=True).values('payments_per_year').annotate(
        count=Count('id')
    ).order_by('payments_per_year')
    
    return render(request, 'summaries/statistics.html', {
        'stats': stats,
        'top_companies': top_companies,
        'year_stats': year_stats,
        'installment_stats': installment_stats
    })

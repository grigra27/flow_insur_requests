"""
Представления для работы со сводами предложений
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
import logging

from .models import InsuranceSummary, InsuranceOffer, SummaryTemplate
from insurance_requests.models import InsuranceRequest
from insurance_requests.decorators import user_required, admin_required
from .forms import OfferForm, SummaryForm, AddOfferToSummaryForm

logger = logging.getLogger(__name__)


@user_required
def summary_list(request):
    """Список всех сводов с фильтрацией и сортировкой"""
    from .forms import SummaryFilterForm
    
    # Получаем базовый queryset
    summaries = InsuranceSummary.objects.select_related('request').prefetch_related('offers')
    
    # Применяем фильтры
    filter_form = SummaryFilterForm(request.GET)
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('status'):
            summaries = summaries.filter(status=filter_form.cleaned_data['status'])
        
        if filter_form.cleaned_data.get('date_from'):
            summaries = summaries.filter(created_at__date__gte=filter_form.cleaned_data['date_from'])
        
        if filter_form.cleaned_data.get('date_to'):
            summaries = summaries.filter(created_at__date__lte=filter_form.cleaned_data['date_to'])
        
        if filter_form.cleaned_data.get('client_name'):
            summaries = summaries.filter(
                request__client_name__icontains=filter_form.cleaned_data['client_name']
            )
    
    # Сортировка по умолчанию
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = ['-created_at', 'created_at', '-total_offers', 'total_offers', 'status']
    if sort_by in valid_sorts:
        summaries = summaries.order_by(sort_by)
    else:
        summaries = summaries.order_by('-created_at')
    

    
    return render(request, 'summaries/summary_list.html', {
        'summaries': summaries,
        'filter_form': filter_form,
        'current_sort': sort_by
    })


@user_required
def summary_detail(request, pk):
    """Детальная информация о своде"""
    summary = get_object_or_404(InsuranceSummary, pk=pk)
    
    # Получаем предложения с правильной сортировкой по новой структуре
    offers = summary.offers.filter(is_valid=True).order_by('company_name', 'insurance_year')
    
    # Группируем предложения по компаниям (company-first grouping)
    companies_with_offers = summary.get_offers_grouped_by_company()
    
    # Получаем структурированные данные для шаблона (company-year matrix)
    company_year_matrix = summary.get_company_year_matrix()
    
    # Сортируем компании по алфавиту
    sorted_companies = sorted(companies_with_offers.keys())
    
    return render(request, 'summaries/summary_detail.html', {
        'summary': summary,
        'offers': offers,
        'companies_with_offers': companies_with_offers,
        'company_year_matrix': company_year_matrix,
        'sorted_companies': sorted_companies
    })


@user_required
def create_summary(request, request_id):
    """Создание свода для заявки"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=request_id)
    
    # Проверяем, нет ли уже свода для этой заявки
    if hasattr(insurance_request, 'summary'):
        messages.info(request, 'Свод для этой заявки уже существует')
        return redirect('summaries:summary_detail', pk=insurance_request.summary.pk)
    
    try:
        with transaction.atomic():
            # Создаем свод
            summary = InsuranceSummary.objects.create(
                request=insurance_request,
                status='collecting'
            )
            
            # Обновляем статус заявки
            insurance_request.status = 'email_sent'  # Предполагаем, что письма уже отправлены
            insurance_request.save()
            
            messages.success(request, f'Свод к {insurance_request.get_display_name()} создан')
            return redirect('summaries:summary_detail', pk=summary.pk)
            
    except Exception as e:
        logger.error(f"Error creating summary for request {request_id}: {str(e)}")
        messages.error(request, f'Ошибка при создании свода: {str(e)}')
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
                    
                    logger.info(f"Offer saved successfully: {offer.company_name} ({offer.get_insurance_year_display()}) for summary {summary_id}")
                    

                    
                    # Если набралось достаточно предложений, меняем статус
                    if summary.total_offers >= 3:  # Например, минимум 3 предложения
                        summary.status = 'ready'
                        summary.save()
                    
                    messages.success(request, f'Предложение от {offer.company_name} ({offer.get_insurance_year_display()}) успешно добавлено')
                    return redirect('summaries:summary_detail', pk=summary_id)
                    
            except Exception as e:
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
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    
    try:
        # TODO: Реализовать генерацию Excel файла
        # Пока используем заглушку
        messages.info(request, 'Генерация Excel файла свода будет реализована на следующем этапе')
        
        # Обновляем статус
        summary.status = 'ready'
        summary.save()
        
        return redirect('summaries:summary_detail', pk=summary_id)
        
    except Exception as e:
        logger.error(f"Error generating summary file for {summary_id}: {str(e)}")
        messages.error(request, f'Ошибка при генерации файла: {str(e)}')
        return redirect('summaries:summary_detail', pk=summary_id)


@require_http_methods(["POST"])
@user_required
def send_summary_to_client(request, summary_id):
    """Отправка свода клиенту"""
    summary = get_object_or_404(InsuranceSummary, pk=summary_id)
    
    try:
        # TODO: Реализовать отправку email клиенту
        # Пока используем заглушку
        messages.info(request, 'Отправка свода клиенту будет реализована после настройки SMTP')
        
        # Обновляем статус
        from django.utils import timezone
        summary.status = 'sent'
        summary.sent_to_client_at = timezone.now()
        summary.save()
        
        return JsonResponse({'success': True, 'message': 'Свод отправлен клиенту'})
        
    except Exception as e:
        logger.error(f"Error sending summary {summary_id} to client: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


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
    summary_id = offer.summary.pk
    company_name = offer.company_name
    insurance_year_display = offer.get_insurance_year_display()
    
    try:
        with transaction.atomic():
            # Удаляем предложение
            offer.delete()
            

            
            logger.info(f"Offer deleted: {company_name} ({insurance_year_display}) from summary {summary_id}")
            
            return JsonResponse({
                'success': True, 
                'message': f'Предложение от {company_name} ({insurance_year_display}) удалено'
            })
        
    except Exception as e:
        logger.error(f"Error deleting offer {offer_id}: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'Не удалось удалить предложение: {str(e)}'
        })


@user_required
def create_summary_from_offers(request, request_id):
    """
    Создание свода из загруженных предложений.
    
    Эта функция будет реализована в задаче 6.
    Пока что это заглушка для корректной работы задачи 5.
    """
    insurance_request = get_object_or_404(InsuranceRequest, pk=request_id)
    
    # Получаем данные из сессии
    session_key = f'parsed_offers_{request_id}'
    parsed_data = request.session.get(session_key)
    
    if not parsed_data:
        messages.error(request, 'Данные загруженных предложений не найдены. Попробуйте загрузить файлы заново.')
        return redirect('insurance_requests:request_detail', pk=request_id)
    
    # Временная заглушка - показываем информацию о загруженных данных
    messages.info(request, 
                 f'Загружено {parsed_data["successful_files"]} предложений. '
                 'Страница формирования свода будет реализована в задаче 6.')
    
    # Очищаем данные из сессии
    if session_key in request.session:
        del request.session[session_key]
    
    return redirect('insurance_requests:request_detail', pk=request_id)


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
        'completed': InsuranceSummary.objects.filter(status='completed').count(),
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

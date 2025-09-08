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
from .forms import OfferForm, SummaryForm

logger = logging.getLogger(__name__)


@user_required
def summary_list(request):
    """Список всех сводов с оптимизированными запросами"""
    summaries = InsuranceSummary.objects.select_related(
        'request', 'request__created_by'
    ).prefetch_related('offers').order_by('-created_at')
    
    # Add filtering capabilities for better performance
    status_filter = request.GET.get('status')
    if status_filter:
        summaries = summaries.filter(status=status_filter)
    
    return render(request, 'summaries/summary_list.html', {
        'summaries': summaries,
        'status_choices': InsuranceSummary.STATUS_CHOICES,
    })


@user_required
def summary_detail(request, pk):
    """Детальная информация о своде с оптимизированными запросами"""
    summary = get_object_or_404(
        InsuranceSummary.objects.select_related(
            'request', 'request__created_by'
        ).prefetch_related('offers'), 
        pk=pk
    )
    offers = summary.offers.all().order_by('insurance_premium')
    
    return render(request, 'summaries/summary_detail.html', {
        'summary': summary,
        'offers': offers
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
                client_email=insurance_request.additional_data.get('client_email', ''),
                status='collecting'
            )
            
            # Обновляем статус заявки
            insurance_request.status = 'email_sent'  # Предполагаем, что письма уже отправлены
            insurance_request.save()
            
            messages.success(request, f'Свод #{summary.id} создан для заявки #{insurance_request.id}')
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
        form = OfferForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    offer = form.save(commit=False)
                    offer.summary = summary
                    offer.save()
                    
                    # Пересчитываем лучшее предложение
                    summary.calculate_best_offer()
                    
                    # Если набралось достаточно предложений, меняем статус
                    if summary.total_offers >= 3:  # Например, минимум 3 предложения
                        summary.status = 'ready'
                        summary.save()
                    
                    messages.success(request, f'Предложение от {offer.company_name} добавлено')
                    return redirect('summaries:summary_detail', pk=summary_id)
                    
            except Exception as e:
                logger.error(f"Error adding offer to summary {summary_id}: {str(e)}")
                messages.error(request, f'Ошибка при добавлении предложения: {str(e)}')
    else:
        form = OfferForm()
    
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
            form.save()
            # Пересчитываем лучшее предложение
            offer.summary.calculate_best_offer()
            messages.success(request, 'Предложение обновлено')
            return redirect('summaries:summary_detail', pk=offer.summary.pk)
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
    
    try:
        offer.delete()
        # Пересчитываем лучшее предложение
        summary = InsuranceSummary.objects.get(pk=summary_id)
        summary.calculate_best_offer()
        
        messages.success(request, 'Предложение удалено')
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting offer {offer_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


@admin_required
def summary_statistics(request):
    """Статистика по сводам с оптимизированными запросами"""
    from django.db.models import Count, Avg, Min, Max, Q
    from django.db.models.functions import TruncMonth
    
    # Use single query with conditional aggregation for better performance
    stats_query = InsuranceSummary.objects.aggregate(
        total_summaries=Count('id'),
        collecting=Count('id', filter=Q(status='collecting')),
        ready=Count('id', filter=Q(status='ready')),
        sent=Count('id', filter=Q(status='sent')),
        completed=Count('id', filter=Q(status='completed')),
        avg_offers_per_summary=Avg('total_offers'),
        min_premium=Min('best_premium'),
        max_premium=Max('best_premium'),
        avg_premium=Avg('best_premium'),
    )
    
    stats = {
        'total_summaries': stats_query['total_summaries'] or 0,
        'collecting': stats_query['collecting'] or 0,
        'ready': stats_query['ready'] or 0,
        'sent': stats_query['sent'] or 0,
        'completed': stats_query['completed'] or 0,
        'avg_offers_per_summary': stats_query['avg_offers_per_summary'] or 0,
        'min_premium': stats_query['min_premium'] or 0,
        'max_premium': stats_query['max_premium'] or 0,
        'avg_premium': stats_query['avg_premium'] or 0,
        'total_offers': InsuranceOffer.objects.count(),
    }
    
    # Топ компаний по количеству предложений с оптимизированным запросом
    top_companies = InsuranceOffer.objects.filter(is_valid=True).values('company_name').annotate(
        count=Count('id'),
        avg_premium=Avg('insurance_premium'),
        min_premium=Min('insurance_premium'),
        max_premium=Max('insurance_premium')
    ).order_by('-count')[:10]
    
    # Monthly statistics for trends
    monthly_stats = InsuranceSummary.objects.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        count=Count('id'),
        avg_offers=Avg('total_offers')
    ).order_by('-month')[:12]
    
    return render(request, 'summaries/statistics.html', {
        'stats': stats,
        'top_companies': top_companies,
        'monthly_stats': monthly_stats,
    })

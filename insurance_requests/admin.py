from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import pytz
from .models import InsuranceRequest, RequestAttachment, InsuranceResponse, ResponseAttachment


@admin.register(InsuranceRequest)
class InsuranceRequestAdmin(admin.ModelAdmin):
    # Расширенный список отображения с ключевыми полями
    list_display = [
        'get_display_name', 'client_name', 'inn', 'branch', 
        'insurance_type', 'status', 'created_at_moscow', 
        'response_deadline_moscow', 'created_by'
    ]
    
    # Улучшенные фильтры по ключевым полям
    list_filter = [
        'status', 'insurance_type', 'branch', 'has_franchise', 
        'has_installment', 'has_autostart', 'created_at'
    ]
    
    # Расширенный поиск по ключевым полям
    search_fields = [
        'dfa_number', 'client_name', 'inn', 'branch', 
        'email_subject', 'vehicle_info'
    ]
    
    # Поля только для чтения
    readonly_fields = [
        'created_at', 'updated_at', 'email_sent_at',
        'get_attachments_count'
    ]
    
    # Массовые операции для управления статусами и сроками ответа
    actions = ['mark_as_completed', 'mark_as_email_sent', 'mark_as_email_generated', 'reset_response_deadline']
    
    # Логически сгруппированные fieldsets для удобного редактирования
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'created_by', 'status', 'created_at', 'updated_at'
            )
        }),
        ('Данные клиента', {
            'fields': (
                'client_name', 'inn', 'dfa_number', 'branch'
            )
        }),
        ('Страхование', {
            'fields': (
                'insurance_type', 'insurance_period', 'vehicle_info'
            )
        }),
        ('Параметры', {
            'fields': (
                'has_franchise', 'has_installment', 'has_autostart', 
                'response_deadline'
            )
        }),
        ('Письмо', {
            'fields': (
                'email_subject', 'email_body', 'email_sent_at'
            ),
            'classes': ('collapse',)
        }),
        ('Дополнительные данные', {
            'fields': ('additional_data', 'get_attachments_count'),
            'classes': ('collapse',)
        })
    )
    
    # Кастомные методы отображения для времени в московском часовом поясе
    def get_display_name(self, obj):
        """Отображает название заявки с номером ДФА"""
        return obj.get_display_name()
    get_display_name.short_description = 'Название заявки'
    
    def created_at_moscow(self, obj):
        """Отображает время создания в московском часовом поясе"""
        moscow_time = timezone.localtime(obj.created_at)
        return moscow_time.strftime('%d.%m.%Y %H:%M')
    created_at_moscow.short_description = 'Создана (МСК)'
    created_at_moscow.admin_order_field = 'created_at'
    
    def response_deadline_moscow(self, obj):
        """Отображает срок ответа в московском часовом поясе"""
        if obj.response_deadline:
            moscow_time = timezone.localtime(obj.response_deadline)
            return moscow_time.strftime('%d.%m.%Y %H:%M')
        return '-'
    response_deadline_moscow.short_description = 'Срок ответа (МСК)'
    response_deadline_moscow.admin_order_field = 'response_deadline'
    

    
    def get_attachments_count(self, obj):
        """Отображает количество вложений с ссылкой на них"""
        count = obj.attachments.count()
        if count > 0:
            url = reverse('admin:insurance_requests_requestattachment_changelist')
            return format_html(
                '<a href="{}?request__id={}">{} файл(ов)</a>',
                url, obj.id, count
            )
        return 'Нет файлов'
    get_attachments_count.short_description = 'Вложения'
    
    # Массовые операции для управления статусами и сроками ответа
    def mark_as_completed(self, request, queryset):
        """Массовая операция: отметить как завершенные"""
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} заявок отмечено как завершенные.')
    mark_as_completed.short_description = 'Отметить как завершенные'
    
    def mark_as_email_sent(self, request, queryset):
        """Массовая операция: отметить как письмо отправлено"""
        updated = queryset.update(status='email_sent')
        self.message_user(request, f'{updated} заявок отмечено как письмо отправлено.')
    mark_as_email_sent.short_description = 'Отметить как письмо отправлено'
    
    def mark_as_email_generated(self, request, queryset):
        """Массовая операция: отметить как письмо сгенерировано"""
        updated = queryset.update(status='email_generated')
        self.message_user(request, f'{updated} заявок отмечено как письмо сгенерировано.')
    mark_as_email_generated.short_description = 'Отметить как письмо сгенерировано'
    
    def reset_response_deadline(self, request, queryset):
        """Массовая операция: сбросить срок ответа (+3 часа от текущего времени)"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        new_deadline = timezone.now().astimezone(moscow_tz) + timedelta(hours=3)
        updated = queryset.update(response_deadline=new_deadline)
        self.message_user(request, f'Срок ответа обновлен для {updated} заявок.')
    reset_response_deadline.short_description = 'Сбросить срок ответа (+3 часа)'


@admin.register(RequestAttachment)
class RequestAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'get_request_display', 'file_type', 'uploaded_at_moscow']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['original_filename', 'request__client_name', 'request__dfa_number']
    readonly_fields = ['uploaded_at']
    
    def get_request_display(self, obj):
        """Отображает заявку с ссылкой"""
        url = reverse('admin:insurance_requests_insurancerequest_change', args=[obj.request.id])
        return format_html('<a href="{}">{}</a>', url, obj.request.get_display_name())
    get_request_display.short_description = 'Заявка'
    
    def uploaded_at_moscow(self, obj):
        """Отображает время загрузки в московском часовом поясе"""
        moscow_time = timezone.localtime(obj.uploaded_at)
        return moscow_time.strftime('%d.%m.%Y %H:%M')
    uploaded_at_moscow.short_description = 'Загружено (МСК)'
    uploaded_at_moscow.admin_order_field = 'uploaded_at'


@admin.register(InsuranceResponse)
class InsuranceResponseAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'get_request_display', 'insurance_sum', 'insurance_premium', 'received_at_moscow']
    list_filter = ['company_name', 'received_at']
    search_fields = ['company_name', 'email_subject', 'request__client_name', 'request__dfa_number']
    readonly_fields = ['received_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('request', 'company_name', 'company_email', 'received_at')
        }),
        ('Данные письма', {
            'fields': ('email_subject', 'email_body')
        }),
        ('Извлеченные данные', {
            'fields': ('insurance_sum', 'insurance_premium', 'parsed_data'),
            'classes': ('collapse',)
        })
    )
    
    def get_request_display(self, obj):
        """Отображает заявку с ссылкой"""
        url = reverse('admin:insurance_requests_insurancerequest_change', args=[obj.request.id])
        return format_html('<a href="{}">{}</a>', url, obj.request.get_display_name())
    get_request_display.short_description = 'Заявка'
    
    def received_at_moscow(self, obj):
        """Отображает время получения в московском часовом поясе"""
        moscow_time = timezone.localtime(obj.received_at)
        return moscow_time.strftime('%d.%m.%Y %H:%M')
    received_at_moscow.short_description = 'Получено (МСК)'
    received_at_moscow.admin_order_field = 'received_at'


@admin.register(ResponseAttachment)
class ResponseAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'get_response_display', 'file_type']
    list_filter = ['file_type']
    search_fields = ['original_filename', 'response__company_name']
    
    def get_response_display(self, obj):
        """Отображает ответ с ссылкой"""
        url = reverse('admin:insurance_requests_insuranceresponse_change', args=[obj.response.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.response))
    get_response_display.short_description = 'Ответ'

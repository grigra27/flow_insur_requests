from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import InsuranceCompany, InsuranceSummary, InsuranceOffer, SummaryTemplate


@admin.register(InsuranceCompany)
class InsuranceCompanyAdmin(admin.ModelAdmin):
    """Административный интерфейс для управления страховыми компаниями"""
    
    list_display = ['name', 'display_name', 'is_active', 'is_other', 'sort_order', 'get_offers_count', 'created_at']
    list_filter = ['is_active', 'is_other', 'created_at']
    search_fields = ['name', 'display_name']
    readonly_fields = ['created_at', 'updated_at', 'get_offers_count']
    ordering = ['sort_order', 'name']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'display_name', 'is_active')
        }),
        ('Специальные настройки', {
            'fields': ('is_other', 'sort_order'),
            'description': 'Настройки для специальных значений и порядка отображения'
        }),
        ('Статистика', {
            'fields': ('get_offers_count',),
            'classes': ('collapse',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_offers_count(self, obj):
        """Отображает количество предложений от компании"""
        count = obj.get_offers_count()
        if count > 0:
            return f"{count} предложений"
        return "Нет предложений"
    get_offers_count.short_description = 'Количество предложений'
    
    def save_model(self, request, obj, form, change):
        """Переопределенное сохранение с дополнительной валидацией"""
        try:
            super().save_model(request, obj, form, change)
            if change:
                messages.success(request, f'Страховая компания "{obj.name}" успешно обновлена.')
            else:
                messages.success(request, f'Страховая компания "{obj.name}" успешно создана.')
        except ValidationError as e:
            messages.error(request, f'Ошибка валидации: {e}')
            raise
    
    def delete_model(self, request, obj):
        """Переопределенное удаление с проверкой связанных записей"""
        offers_count = obj.get_offers_count()
        
        if offers_count > 0:
            messages.warning(
                request, 
                f'Внимание! Компания "{obj.name}" имеет {offers_count} связанных предложений. '
                f'При удалении компании все связанные предложения останутся в базе данных, '
                f'но могут стать недоступными для редактирования через формы.'
            )
        
        super().delete_model(request, obj)
        messages.success(request, f'Страховая компания "{obj.name}" удалена.')
    
    def delete_queryset(self, request, queryset):
        """Переопределенное массовое удаление с предупреждениями"""
        total_offers = 0
        companies_with_offers = []
        
        for company in queryset:
            offers_count = company.get_offers_count()
            if offers_count > 0:
                total_offers += offers_count
                companies_with_offers.append(f"{company.name} ({offers_count} предложений)")
        
        if companies_with_offers:
            messages.warning(
                request,
                f'Внимание! Следующие компании имеют связанные предложения: '
                f'{", ".join(companies_with_offers)}. '
                f'Всего будет затронуто {total_offers} предложений.'
            )
        
        deleted_count = queryset.count()
        super().delete_queryset(request, queryset)
        messages.success(request, f'Удалено {deleted_count} страховых компаний.')
    
    def get_readonly_fields(self, request, obj=None):
        """Динамически определяет readonly поля"""
        readonly_fields = list(self.readonly_fields)
        
        # Если компания имеет предложения, делаем название только для чтения
        if obj and obj.has_offers():
            readonly_fields.append('name')
            if 'name' not in readonly_fields:
                readonly_fields.append('name')
        
        return readonly_fields
    
    def get_form(self, request, obj=None, **kwargs):
        """Переопределяем форму для добавления подсказок"""
        form = super().get_form(request, obj, **kwargs)
        
        if obj and obj.has_offers():
            # Добавляем предупреждение для компаний с существующими предложениями
            form.base_fields['name'].help_text = (
                f'Внимание: У этой компании есть {obj.get_offers_count()} предложений. '
                f'Изменение названия может повлиять на существующие данные.'
            )
        
        return form


@admin.register(InsuranceSummary)
class InsuranceSummaryAdmin(admin.ModelAdmin):
    list_display = ['id', 'request', 'status', 'total_offers', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['request__client_name', 'request__inn']
    readonly_fields = ['created_at', 'updated_at', 'total_offers']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('request', 'status')
        }),
        ('Сводные данные', {
            'fields': ('total_offers',)
        }),
        ('Файлы и отправка', {
            'fields': ('summary_file', 'sent_to_client_at')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(InsuranceOffer)
class InsuranceOfferAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'insurance_year', 'summary', 'premium_with_franchise_1', 'premium_with_franchise_2', 'insurance_sum', 'installment_variant_1', 'installment_variant_2', 'is_valid', 'received_at']
    list_filter = ['is_valid', 'insurance_year', 'installment_variant_1', 'installment_variant_2', 'company_name', 'received_at']
    search_fields = ['company_name', 'summary__request__client_name']
    readonly_fields = ['received_at']
    
    fieldsets = (
        ('Компания', {
            'fields': ('company_name',)
        }),
        ('Основное предложение', {
            'fields': ('summary', 'insurance_year', 'insurance_sum')
        }),
        ('Варианты франшизы и премий', {
            'fields': ('franchise_1', 'premium_with_franchise_1', 'franchise_2', 'premium_with_franchise_2'),
            'description': 'Структурированные данные о франшизах и соответствующих премиях'
        }),
        ('Условия оплаты', {
            'fields': ('installment_variant_1', 'payments_per_year_variant_1', 'installment_variant_2', 'payments_per_year_variant_2', 'is_valid')
        }),
        ('Дополнительно', {
            'fields': ('notes', 'original_email_subject', 'attachment_file', 'received_at')
        })
    )


@admin.register(SummaryTemplate)
class SummaryTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'is_default', 'created_at']
    list_filter = ['is_active', 'is_default', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']

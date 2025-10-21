from django.contrib import admin
from .models import InsuranceSummary, InsuranceOffer, SummaryTemplate


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

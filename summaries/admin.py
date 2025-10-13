from django.contrib import admin
from .models import InsuranceSummary, InsuranceOffer, SummaryTemplate


@admin.register(InsuranceSummary)
class InsuranceSummaryAdmin(admin.ModelAdmin):
    list_display = ['id', 'request', 'status', 'total_offers', 'best_premium', 'best_company', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['request__client_name', 'request__inn', 'best_company']
    readonly_fields = ['created_at', 'updated_at', 'total_offers', 'best_premium', 'best_company']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('request', 'status', 'client_email')
        }),
        ('Сводные данные', {
            'fields': ('total_offers', 'best_premium', 'best_company')
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
    list_display = ['company_name', 'insurance_year', 'summary', 'insurance_premium', 'yearly_premium_with_franchise', 'insurance_sum', 'is_valid', 'received_at']
    list_filter = ['is_valid', 'insurance_year', 'installment_available', 'company_name', 'received_at']
    search_fields = ['company_name', 'company_email', 'summary__request__client_name']
    readonly_fields = ['received_at']
    
    fieldsets = (
        ('Компания', {
            'fields': ('company_name', 'company_email')
        }),
        ('Основное предложение', {
            'fields': ('summary', 'insurance_year', 'insurance_sum', 'insurance_premium', 'franchise_amount')
        }),
        ('Многолетние данные', {
            'fields': ('yearly_premium_with_franchise', 'yearly_premium_without_franchise', 
                      'franchise_amount_variant1', 'franchise_amount_variant2'),
            'description': 'Данные для многолетних предложений, извлеченные из Excel файлов'
        }),
        ('Условия', {
            'fields': ('installment_available', 'installment_months', 'valid_until', 'is_valid')
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

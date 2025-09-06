"""
Формы для работы со сводами предложений
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import InsuranceOffer, InsuranceSummary, SummaryTemplate
from decimal import Decimal


class OfferForm(forms.ModelForm):
    """Форма для добавления/редактирования предложения от страховщика"""
    
    class Meta:
        model = InsuranceOffer
        fields = [
            'company_name', 'company_email', 'insurance_sum', 'insurance_premium',
            'franchise_amount', 'installment_available', 'installment_months',
            'valid_until', 'notes', 'attachment_file'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'company_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'insurance_sum': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'insurance_premium': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'franchise_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'installment_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'installment_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '60'}),
            'valid_until': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'attachment_file': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_insurance_premium(self):
        """Валидация страховой премии"""
        premium = self.cleaned_data.get('insurance_premium')
        if premium and premium <= 0:
            raise ValidationError('Страховая премия должна быть больше нуля')
        return premium
    
    def clean_insurance_sum(self):
        """Валидация страховой суммы"""
        sum_amount = self.cleaned_data.get('insurance_sum')
        if sum_amount and sum_amount <= 0:
            raise ValidationError('Страховая сумма должна быть больше нуля')
        return sum_amount
    
    def clean(self):
        """Дополнительная валидация формы"""
        cleaned_data = super().clean()
        premium = cleaned_data.get('insurance_premium')
        sum_amount = cleaned_data.get('insurance_sum')
        
        # Проверяем, что премия не больше страховой суммы
        if premium and sum_amount and premium > sum_amount:
            raise ValidationError('Страховая премия не может быть больше страховой суммы')
        
        # Проверяем рассрочку
        installment_available = cleaned_data.get('installment_available')
        installment_months = cleaned_data.get('installment_months')
        
        if installment_available and not installment_months:
            raise ValidationError('Укажите количество месяцев для рассрочки')
        
        if not installment_available and installment_months:
            cleaned_data['installment_months'] = None
        
        return cleaned_data


class SummaryForm(forms.ModelForm):
    """Форма для редактирования свода"""
    
    class Meta:
        model = InsuranceSummary
        fields = ['client_email', 'status']
        widgets = {
            'client_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class BulkOfferUploadForm(forms.Form):
    """Форма для массовой загрузки предложений из Excel"""
    
    excel_file = forms.FileField(
        label='Excel файл с предложениями',
        help_text='Загрузите файл с предложениями от страховщиков',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xls,.xlsx'
        })
    )
    
    def clean_excel_file(self):
        """Валидация загружаемого файла"""
        file = self.cleaned_data.get('excel_file')
        
        if not file:
            raise ValidationError('Файл не выбран')
        
        # Проверяем расширение файла
        import os
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ['.xls', '.xlsx']:
            raise ValidationError('Поддерживаются только файлы .xls и .xlsx')
        
        # Проверяем размер файла (максимум 10MB)
        if file.size > 10 * 1024 * 1024:
            raise ValidationError('Размер файла не должен превышать 10MB')
        
        return file


class SummaryFilterForm(forms.Form):
    """Форма для фильтрации сводов"""
    
    STATUS_CHOICES = [('', 'Все статусы')] + InsuranceSummary.STATUS_CHOICES
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    client_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Поиск по имени клиента'
        })
    )


class CompanyOfferSearchForm(forms.Form):
    """Форма для поиска предложений по компаниям"""
    
    company_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Название компании'
        })
    )
    
    min_premium = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Минимальная премия',
            'step': '0.01'
        })
    )
    
    max_premium = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Максимальная премия',
            'step': '0.01'
        })
    )
    
    installment_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
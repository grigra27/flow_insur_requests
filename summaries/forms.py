"""
Формы для работы со сводами предложений
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import InsuranceOffer, InsuranceSummary, SummaryTemplate
from decimal import Decimal


class OfferForm(forms.ModelForm):
    """Форма для добавления/редактирования предложения от страховщика"""
    
    # Переопределяем поле payments_per_year как необязательное
    payments_per_year = forms.IntegerField(
        required=False,
        widget=forms.Select(
            choices=[(1, '1 (годовой платеж)'), (2, '2 (полугодовые)'), (3, '3 (по 4 месяца)'), (4, '4 (квартальные)'), (12, '12 (ежемесячные)')],
            attrs={'class': 'form-select'}
        )
    )
    
    class Meta:
        model = InsuranceOffer
        fields = [
            'company_name', 'insurance_year', 'insurance_sum',
            'franchise_1', 'premium_with_franchise_1',
            'franchise_2', 'premium_with_franchise_2',
            'installment_available', 'payments_per_year',
            'notes', 'attachment_file'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'insurance_year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '10',
                'placeholder': 'Введите номер года (1, 2, 3...)'
            }),
            'insurance_sum': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'franchise_1': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Обычно 0 (без франшизы)',
                'value': '0'
            }),
            'premium_with_franchise_1': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Премия с франшизой-1'
            }),
            'franchise_2': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Обычно больше 0'
            }),
            'premium_with_franchise_2': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Премия с франшизой-2'
            }),
            'installment_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'attachment_file': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_insurance_year(self):
        """Валидация года страхования"""
        year = self.cleaned_data.get('insurance_year')
        if year and (year < 1 or year > 10):
            raise ValidationError('Год страхования должен быть от 1 до 10')
        return year
    
    def clean_insurance_sum(self):
        """Валидация страховой суммы"""
        sum_amount = self.cleaned_data.get('insurance_sum')
        if sum_amount and sum_amount <= 0:
            raise ValidationError('Страховая сумма должна быть больше нуля')
        return sum_amount
    
    def clean_franchise_1(self):
        """Валидация франшизы-1"""
        franchise = self.cleaned_data.get('franchise_1')
        if franchise is not None and franchise < 0:
            raise ValidationError('Размер франшизы не может быть отрицательным')
        return franchise
    
    def clean_franchise_2(self):
        """Валидация франшизы-2"""
        franchise = self.cleaned_data.get('franchise_2')
        if franchise is not None and franchise < 0:
            raise ValidationError('Размер франшизы не может быть отрицательным')
        return franchise
    
    def clean_premium_with_franchise_1(self):
        """Валидация премии с франшизой-1"""
        premium = self.cleaned_data.get('premium_with_franchise_1')
        if premium is not None and premium <= 0:
            raise ValidationError('Премия с франшизой-1 должна быть больше нуля')
        return premium
    
    def clean_premium_with_franchise_2(self):
        """Валидация премии с франшизой-2"""
        premium = self.cleaned_data.get('premium_with_franchise_2')
        if premium is not None and premium <= 0:
            raise ValidationError('Премия с франшизой-2 должна быть больше нуля')
        return premium
    
    def clean_payments_per_year(self):
        """Валидация количества платежей в год"""
        payments = self.cleaned_data.get('payments_per_year')
        installment_available = self.cleaned_data.get('installment_available')
        
        # Если рассрочка недоступна, автоматически устанавливаем 1 платеж в год
        if not installment_available:
            return 1
        
        # Если рассрочка доступна, проверяем валидность значения
        valid_payments = [1, 2, 3, 4, 12]
        if payments and payments not in valid_payments:
            raise ValidationError(f'Количество платежей должно быть одним из: {", ".join(map(str, valid_payments))}')
        
        # Если payments не указано, но рассрочка доступна, устанавливаем по умолчанию 1
        return payments or 1
    
    def clean(self):
        """Дополнительная валидация формы"""
        cleaned_data = super().clean()
        sum_amount = cleaned_data.get('insurance_sum')
        
        # Валидация франшизных вариантов
        franchise_1 = cleaned_data.get('franchise_1')
        franchise_2 = cleaned_data.get('franchise_2')
        premium_1 = cleaned_data.get('premium_with_franchise_1')
        premium_2 = cleaned_data.get('premium_with_franchise_2')
        
        # Проверяем, что указана хотя бы одна премия
        if premium_1 is None and premium_2 is None:
            raise ValidationError('Укажите хотя бы одну премию (с франшизой-1 или франшизой-2)')
        
        # Проверяем премии относительно страховой суммы
        if premium_1 and sum_amount and premium_1 > sum_amount:
            raise ValidationError('Премия с франшизой-1 не может быть больше страховой суммы')
        
        if premium_2 and sum_amount and premium_2 > sum_amount:
            raise ValidationError('Премия с франшизой-2 не может быть больше страховой суммы')
        
        # Проверяем рассрочку
        installment_available = cleaned_data.get('installment_available')
        payments_per_year = cleaned_data.get('payments_per_year')
        
        if not installment_available and payments_per_year != 1:
            # Если рассрочка не доступна, устанавливаем 1 платеж в год
            cleaned_data['payments_per_year'] = 1
        
        return cleaned_data


class SummaryForm(forms.ModelForm):
    """Форма для редактирования свода"""
    
    class Meta:
        model = InsuranceSummary
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class AddOfferToSummaryForm(forms.ModelForm):
    """Форма для добавления предложения к существующему своду (без загрузки файла)"""
    
    # Переопределяем поле payments_per_year как необязательное
    payments_per_year = forms.IntegerField(
        required=False,
        widget=forms.Select(
            choices=[(1, '1 (годовой платеж)'), (2, '2 (полугодовые)'), (3, '3 (по 4 месяца)'), (4, '4 (квартальные)'), (12, '12 (ежемесячные)')],
            attrs={'class': 'form-select'}
        )
    )
    
    class Meta:
        model = InsuranceOffer
        fields = [
            'company_name', 'insurance_year', 'insurance_sum',
            'franchise_1', 'premium_with_franchise_1',
            'franchise_2', 'premium_with_franchise_2',
            'installment_available', 'payments_per_year', 'notes'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'insurance_year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '10',
                'placeholder': 'Введите номер года (1, 2, 3...)',
                'value': '1'
            }),
            'insurance_sum': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'franchise_1': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Обычно 0 (без франшизы)',
                'value': '0'
            }),
            'premium_with_franchise_1': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Премия с франшизой-1'
            }),
            'franchise_2': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Обычно больше 0'
            }),
            'premium_with_franchise_2': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'placeholder': 'Премия с франшизой-2'
            }),
            'installment_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def clean_insurance_year(self):
        """Валидация года страхования"""
        year = self.cleaned_data.get('insurance_year')
        if year and (year < 1 or year > 10):
            raise ValidationError('Год страхования должен быть от 1 до 10')
        return year
    
    def clean_insurance_sum(self):
        """Валидация страховой суммы"""
        sum_amount = self.cleaned_data.get('insurance_sum')
        if sum_amount and sum_amount <= 0:
            raise ValidationError('Страховая сумма должна быть больше нуля')
        return sum_amount
    
    def clean_franchise_1(self):
        """Валидация франшизы-1"""
        franchise = self.cleaned_data.get('franchise_1')
        if franchise is not None and franchise < 0:
            raise ValidationError('Размер франшизы не может быть отрицательным')
        return franchise
    
    def clean_franchise_2(self):
        """Валидация франшизы-2"""
        franchise = self.cleaned_data.get('franchise_2')
        if franchise is not None and franchise < 0:
            raise ValidationError('Размер франшизы не может быть отрицательным')
        return franchise
    
    def clean_premium_with_franchise_1(self):
        """Валидация премии с франшизой-1"""
        premium = self.cleaned_data.get('premium_with_franchise_1')
        if premium is not None and premium <= 0:
            raise ValidationError('Премия с франшизой-1 должна быть больше нуля')
        return premium
    
    def clean_premium_with_franchise_2(self):
        """Валидация премии с франшизой-2"""
        premium = self.cleaned_data.get('premium_with_franchise_2')
        if premium is not None and premium <= 0:
            raise ValidationError('Премия с франшизой-2 должна быть больше нуля')
        return premium
    
    def clean_payments_per_year(self):
        """Валидация количества платежей в год"""
        payments = self.cleaned_data.get('payments_per_year')
        installment_available = self.cleaned_data.get('installment_available')
        
        # Если рассрочка недоступна, автоматически устанавливаем 1 платеж в год
        if not installment_available:
            return 1
        
        # Если рассрочка доступна, проверяем валидность значения
        valid_payments = [1, 2, 3, 4, 12]
        if payments and payments not in valid_payments:
            raise ValidationError(f'Количество платежей должно быть одним из: {", ".join(map(str, valid_payments))}')
        
        # Если payments не указано, но рассрочка доступна, устанавливаем по умолчанию 1
        return payments or 1
    
    def clean(self):
        """Дополнительная валидация формы"""
        cleaned_data = super().clean()
        sum_amount = cleaned_data.get('insurance_sum')
        
        # Валидация франшизных вариантов
        franchise_1 = cleaned_data.get('franchise_1')
        franchise_2 = cleaned_data.get('franchise_2')
        premium_1 = cleaned_data.get('premium_with_franchise_1')
        premium_2 = cleaned_data.get('premium_with_franchise_2')
        
        # Проверяем, что указана хотя бы одна премия
        if premium_1 is None and premium_2 is None:
            raise ValidationError('Укажите хотя бы одну премию (с франшизой-1 или франшизой-2)')
        
        # Проверяем премии относительно страховой суммы
        if premium_1 and sum_amount and premium_1 > sum_amount:
            raise ValidationError('Премия с франшизой-1 не может быть больше страховой суммы')
        
        if premium_2 and sum_amount and premium_2 > sum_amount:
            raise ValidationError('Премия с франшизой-2 не может быть больше страховой суммы')
        
        return cleaned_data


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
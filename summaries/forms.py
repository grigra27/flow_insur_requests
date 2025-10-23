"""
Формы для работы со сводами предложений
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import InsuranceOffer, InsuranceSummary, SummaryTemplate
from .constants import get_company_choices, is_valid_company_name, get_company_names
from decimal import Decimal
import os


# Удаляем дублирующийся виджет - используем тот что ниже


class OfferForm(forms.ModelForm):
    """Форма для добавления/редактирования предложения от страховщика"""
    
    # Поле для выбора страховщика из предопределенного списка
    company_name = forms.ChoiceField(
        choices=[],  # Будет заполнено в __init__
        label='Страховая компания',
        help_text='Выберите страховую компанию из списка. Если нужной компании нет в списке, выберите "Другое".',
        error_messages={
            'required': 'Пожалуйста, выберите страховую компанию из выпадающего списка.',
            'invalid_choice': 'Выберите страховую компанию из предложенного списка. Если нужной компании нет, используйте вариант "Другое".'
        },
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-bs-toggle': 'tooltip',
            'data-bs-placement': 'top',
            'title': 'Список содержит основные страховые компании. Для нестандартных компаний используйте "Другое".'
        })
    )
    
    # Новые поля для рассрочки по вариантам премии
    payments_per_year_variant_1 = forms.IntegerField(
        required=False,
        label='Количество платежей для варианта 1',
        widget=forms.Select(
            choices=[(1, '1 (годовой платеж)'), (2, '2 (полугодовые)'), (3, '3 (по 4 месяца)'), (4, '4 (квартальные)'), (12, '12 (ежемесячные)')],
            attrs={'class': 'form-select'}
        )
    )
    
    payments_per_year_variant_2 = forms.IntegerField(
        required=False,
        label='Количество платежей для варианта 2',
        widget=forms.Select(
            choices=[(1, '1 (годовой платеж)'), (2, '2 (полугодовые)'), (3, '3 (по 4 месяца)'), (4, '4 (квартальные)'), (12, '12 (ежемесячные)')],
            attrs={'class': 'form-select'}
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Динамически загружаем список страховых компаний
        self.fields['company_name'].choices = get_company_choices()
    class Meta:
        model = InsuranceOffer
        fields = [
            'company_name', 'insurance_year', 'insurance_sum',
            'franchise_1', 'premium_with_franchise_1',
            'franchise_2', 'premium_with_franchise_2',
            'installment_variant_1', 'payments_per_year_variant_1',
            'installment_variant_2', 'payments_per_year_variant_2',
            'notes', 'attachment_file'
        ]
        widgets = {
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
            'installment_variant_1': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'installment_variant_2': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'attachment_file': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_company_name(self):
        """Валидация выбора страховой компании"""
        company_name = self.cleaned_data.get('company_name')
        
        if not company_name:
            raise ValidationError('Пожалуйста, выберите страховую компанию из выпадающего списка.')
        
        if not is_valid_company_name(company_name):
            raise ValidationError(
                'Выберите страховую компанию из предложенного списка. '
                'Если нужной компании нет, используйте вариант "Другое".'
            )
        
        return company_name
    
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
    
    def clean_payments_per_year_variant_1(self):
        """Валидация количества платежей в год для варианта 1"""
        payments = self.cleaned_data.get('payments_per_year_variant_1')
        installment_variant_1 = self.cleaned_data.get('installment_variant_1')
        
        # Если рассрочка для варианта 1 недоступна, устанавливаем 1 платеж в год
        if not installment_variant_1:
            return 1
        
        # Если рассрочка доступна, проверяем валидность значения
        valid_payments = [1, 2, 3, 4, 12]
        if payments and payments not in valid_payments:
            raise ValidationError(f'Количество платежей для варианта 1 должно быть одним из: {", ".join(map(str, valid_payments))}')
        
        # Если payments не указано, но рассрочка доступна, устанавливаем по умолчанию 1
        return payments or 1
    
    def clean_payments_per_year_variant_2(self):
        """Валидация количества платежей в год для варианта 2"""
        payments = self.cleaned_data.get('payments_per_year_variant_2')
        installment_variant_2 = self.cleaned_data.get('installment_variant_2')
        
        # Если рассрочка для варианта 2 недоступна, устанавливаем 1 платеж в год
        if not installment_variant_2:
            return 1
        
        # Если рассрочка доступна, проверяем валидность значения
        valid_payments = [1, 2, 3, 4, 12]
        if payments and payments not in valid_payments:
            raise ValidationError(f'Количество платежей для варианта 2 должно быть одним из: {", ".join(map(str, valid_payments))}')
        
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
        
        # Проверяем новые поля рассрочки
        installment_variant_1 = cleaned_data.get('installment_variant_1')
        installment_variant_2 = cleaned_data.get('installment_variant_2')
        payments_per_year_variant_1 = cleaned_data.get('payments_per_year_variant_1')
        payments_per_year_variant_2 = cleaned_data.get('payments_per_year_variant_2')
        
        # Валидация рассрочки для варианта 1
        if installment_variant_1 and not premium_1:
            raise ValidationError('Нельзя включить рассрочку для варианта 1 без указания премии с франшизой-1')
        
        # Валидация рассрочки для варианта 2
        if installment_variant_2 and not premium_2:
            raise ValidationError('Нельзя включить рассрочку для варианта 2 без указания премии с франшизой-2')
        
        # Устанавливаем значения по умолчанию для полей рассрочки
        if not installment_variant_1:
            cleaned_data['payments_per_year_variant_1'] = 1
        if not installment_variant_2:
            cleaned_data['payments_per_year_variant_2'] = 1
        
        return cleaned_data


class SummaryForm(forms.ModelForm):
    """Форма для редактирования свода"""
    
    class Meta:
        model = InsuranceSummary
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class SummaryStatusForm(forms.Form):
    """Форма для управления статусом свода"""
    
    status = forms.ChoiceField(
        choices=InsuranceSummary.STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'status-select'
        }),
        label='Статус свода'
    )
    
    def __init__(self, *args, **kwargs):
        current_status = kwargs.pop('current_status', None)
        super().__init__(*args, **kwargs)
        
        if current_status:
            self.fields['status'].initial = current_status
    
    def clean_status(self):
        """Валидация статуса"""
        status = self.cleaned_data.get('status')
        valid_statuses = [choice[0] for choice in InsuranceSummary.STATUS_CHOICES]
        
        if status not in valid_statuses:
            raise ValidationError('Недопустимый статус')
        
        return status


class AddOfferToSummaryForm(forms.ModelForm):
    """Форма для добавления предложения к существующему своду (без загрузки файла)"""
    
    # Поле для выбора страховщика из предопределенного списка
    company_name = forms.ChoiceField(
        choices=[],  # Будет заполнено в __init__
        label='Страховая компания',
        help_text='Выберите страховую компанию из списка. Если нужной компании нет в списке, выберите "Другое".',
        error_messages={
            'required': 'Пожалуйста, выберите страховую компанию из выпадающего списка.',
            'invalid_choice': 'Выберите страховую компанию из предложенного списка. Если нужной компании нет, используйте вариант "Другое".'
        },
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-bs-toggle': 'tooltip',
            'data-bs-placement': 'top',
            'title': 'Список содержит основные страховые компании. Для нестандартных компаний используйте "Другое".'
        })
    )
    
    # Новые поля для рассрочки по вариантам премии
    payments_per_year_variant_1 = forms.IntegerField(
        required=False,
        label='Количество платежей для варианта 1',
        widget=forms.Select(
            choices=[(1, '1 (годовой платеж)'), (2, '2 (полугодовые)'), (3, '3 (по 4 месяца)'), (4, '4 (квартальные)'), (12, '12 (ежемесячные)')],
            attrs={'class': 'form-select'}
        )
    )
    
    payments_per_year_variant_2 = forms.IntegerField(
        required=False,
        label='Количество платежей для варианта 2',
        widget=forms.Select(
            choices=[(1, '1 (годовой платеж)'), (2, '2 (полугодовые)'), (3, '3 (по 4 месяца)'), (4, '4 (квартальные)'), (12, '12 (ежемесячные)')],
            attrs={'class': 'form-select'}
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Динамически загружаем список страховых компаний
        self.fields['company_name'].choices = get_company_choices()
    class Meta:
        model = InsuranceOffer
        fields = [
            'company_name', 'insurance_year', 'insurance_sum',
            'franchise_1', 'premium_with_franchise_1',
            'franchise_2', 'premium_with_franchise_2',
            'installment_variant_1', 'payments_per_year_variant_1',
            'installment_variant_2', 'payments_per_year_variant_2',
            'notes'
        ]
        widgets = {
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
            'installment_variant_1': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'installment_variant_2': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def clean_company_name(self):
        """Валидация выбора страховщика"""
        company_name = self.cleaned_data.get('company_name')
        
        if not company_name:
            raise ValidationError('Пожалуйста, выберите страховую компанию из выпадающего списка.')
        
        if not is_valid_company_name(company_name):
            raise ValidationError(
                'Выберите страховую компанию из предложенного списка. '
                'Если нужной компании нет, используйте вариант "Другое".'
            )
        
        return company_name
    
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
    
    def clean_payments_per_year_variant_1(self):
        """Валидация количества платежей в год для варианта 1"""
        payments = self.cleaned_data.get('payments_per_year_variant_1')
        installment_variant_1 = self.cleaned_data.get('installment_variant_1')
        
        # Если рассрочка для варианта 1 недоступна, устанавливаем 1 платеж в год
        if not installment_variant_1:
            return 1
        
        # Если рассрочка доступна, проверяем валидность значения
        valid_payments = [1, 2, 3, 4, 12]
        if payments and payments not in valid_payments:
            raise ValidationError(f'Количество платежей для варианта 1 должно быть одним из: {", ".join(map(str, valid_payments))}')
        
        # Если payments не указано, но рассрочка доступна, устанавливаем по умолчанию 1
        return payments or 1
    
    def clean_payments_per_year_variant_2(self):
        """Валидация количества платежей в год для варианта 2"""
        payments = self.cleaned_data.get('payments_per_year_variant_2')
        installment_variant_2 = self.cleaned_data.get('installment_variant_2')
        
        # Если рассрочка для варианта 2 недоступна, устанавливаем 1 платеж в год
        if not installment_variant_2:
            return 1
        
        # Если рассрочка доступна, проверяем валидность значения
        valid_payments = [1, 2, 3, 4, 12]
        if payments and payments not in valid_payments:
            raise ValidationError(f'Количество платежей для варианта 2 должно быть одним из: {", ".join(map(str, valid_payments))}')
        
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
        
        # Проверяем новые поля рассрочки
        installment_variant_1 = cleaned_data.get('installment_variant_1')
        installment_variant_2 = cleaned_data.get('installment_variant_2')
        payments_per_year_variant_1 = cleaned_data.get('payments_per_year_variant_1')
        payments_per_year_variant_2 = cleaned_data.get('payments_per_year_variant_2')
        
        # Валидация рассрочки для варианта 1
        if installment_variant_1 and not premium_1:
            raise ValidationError('Нельзя включить рассрочку для варианта 1 без указания премии с франшизой-1')
        
        # Валидация рассрочки для варианта 2
        if installment_variant_2 and not premium_2:
            raise ValidationError('Нельзя включить рассрочку для варианта 2 без указания премии с франшизой-2')
        
        # Устанавливаем значения по умолчанию для полей рассрочки
        if not installment_variant_1:
            cleaned_data['payments_per_year_variant_1'] = 1
        if not installment_variant_2:
            cleaned_data['payments_per_year_variant_2'] = 1
        
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
    
    # Месяцы для выбора
    MONTH_CHOICES = [('', 'Все месяцы')] + [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]
    
    # Новое поле для фильтрации по номеру ДФА
    dfa_number = forms.CharField(
        required=False,
        label='Номер ДФА',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите номер ДФА'
        })
    )
    
    # Новое поле для фильтрации по месяцу
    month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        required=False,
        label='Месяц создания',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Новое поле для фильтрации по году
    year = forms.ChoiceField(
        required=False,
        label='Год создания',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    

    
    # Новое поле для фильтрации по филиалам (управляется через вкладки)
    branch = forms.CharField(
        required=False,
        label='Филиал',
        widget=forms.HiddenInput()  # Скрытое поле, управляется через вкладки
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Динамически генерируем список годов на основе существующих сводов
        from datetime import datetime
        current_year = datetime.now().year
        
        # Создаем список годов от текущего года до 5 лет назад
        year_choices = [('', 'Все годы')]
        for year in range(current_year, current_year - 6, -1):
            year_choices.append((year, str(year)))
        
        self.fields['year'].choices = year_choices
    
    def clean_dfa_number(self):
        """Валидация номера ДФА"""
        dfa_number = self.cleaned_data.get('dfa_number')
        if dfa_number:
            # Убираем лишние пробелы
            dfa_number = dfa_number.strip()
            # Проверяем, что номер не пустой после очистки
            if not dfa_number:
                return None
        return dfa_number
    
    def clean_month(self):
        """Валидация месяца"""
        month = self.cleaned_data.get('month')
        if month:
            try:
                month_int = int(month)
                if month_int < 1 or month_int > 12:
                    raise forms.ValidationError('Месяц должен быть от 1 до 12')
                return month_int
            except (ValueError, TypeError):
                raise forms.ValidationError('Некорректный формат месяца')
        return None
    
    def clean_year(self):
        """Валидация года"""
        year = self.cleaned_data.get('year')
        if year:
            try:
                year_int = int(year)
                from datetime import datetime
                current_year = datetime.now().year
                if year_int < 2020 or year_int > current_year + 1:
                    raise forms.ValidationError(f'Год должен быть от 2020 до {current_year + 1}')
                return year_int
            except (ValueError, TypeError):
                raise forms.ValidationError('Некорректный формат года')
        return None
    
    def clean(self):
        """Дополнительная валидация формы"""
        cleaned_data = super().clean()
        month = cleaned_data.get('month')
        year = cleaned_data.get('year')
        
        # Если указан месяц, но не указан год, используем текущий год
        if month and not year:
            from datetime import datetime
            cleaned_data['year'] = datetime.now().year
        
        return cleaned_data



class CompanyResponseUploadForm(forms.Form):
    """Форма для загрузки ответов страховых компаний"""
    
    excel_file = forms.FileField(
        label='Файл с предложением',
        help_text='Загрузите Excel файл (.xlsx) с предложением от страховой компании по утвержденному шаблону',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx',
            'id': 'company-response-file'
        })
    )
    
    def clean_excel_file(self):
        """Валидация загружаемого Excel файла"""
        file = self.cleaned_data.get('excel_file')
        
        if not file:
            raise ValidationError('Файл не выбран')
        
        # Проверяем расширение файла - только .xlsx
        ext = os.path.splitext(file.name)[1].lower()
        if ext != '.xlsx':
            raise ValidationError(
                'Поддерживаются только файлы формата .xlsx. '
                'Пожалуйста, сохраните файл в формате Excel (.xlsx) и попробуйте снова.'
            )
        
        # Проверяем размер файла (максимум 5MB)
        max_size = 5 * 1024 * 1024  # 5MB в байтах
        if file.size > max_size:
            raise ValidationError(
                f'Размер файла не должен превышать 5MB. '
                f'Текущий размер: {file.size / (1024 * 1024):.1f}MB'
            )
        
        # Проверяем минимальный размер файла (не менее 1KB)
        min_size = 1024  # 1KB
        if file.size < min_size:
            raise ValidationError(
                'Файл слишком мал. Убедитесь, что загружаете корректный Excel файл.'
            )
        
        # Проверяем MIME тип для дополнительной безопасности
        valid_mime_types = [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/octet-stream'  # Иногда браузеры отправляют этот тип для .xlsx
        ]
        
        if hasattr(file, 'content_type') and file.content_type:
            if file.content_type not in valid_mime_types:
                raise ValidationError(
                    'Неверный тип файла. Загрузите файл Excel в формате .xlsx'
                )
        
        # Базовая проверка структуры файла
        try:
            # Пытаемся прочитать файл как Excel для проверки его корректности
            import openpyxl
            from io import BytesIO
            
            # Создаем копию файла для проверки, не изменяя оригинальный
            file_content = file.read()
            file.seek(0)  # Возвращаем указатель в начало файла
            
            # Проверяем, что файл можно открыть как Excel
            try:
                workbook = openpyxl.load_workbook(BytesIO(file_content), read_only=True)
                
                # Проверяем, что есть хотя бы один лист
                if not workbook.worksheets:
                    raise ValidationError(
                        'Excel файл не содержит листов с данными'
                    )
                
                # Проверяем первый лист на наличие базовой структуры
                worksheet = workbook.active
                
                # Проверяем наличие ключевых ячеек согласно шаблону
                # B2 должна содержать название компании
                company_cell = worksheet['B2']
                if not company_cell.value or str(company_cell.value).strip() == '':
                    raise ValidationError(
                        'Ошибка в структуре файла: ячейка B2 должна содержать название страховой компании'
                    )
                
                # Проверяем наличие данных в строке 6 (первый год)
                year_1_cells = ['A6', 'B6', 'D6', 'E6', 'F6']
                has_year_1_data = any(
                    worksheet[cell].value is not None and str(worksheet[cell].value).strip() != ''
                    for cell in year_1_cells
                )
                
                # Проверяем наличие данных в строке 7 (второй год)
                year_2_cells = ['A7', 'B7', 'D7', 'E7', 'F7']
                has_year_2_data = any(
                    worksheet[cell].value is not None and str(worksheet[cell].value).strip() != ''
                    for cell in year_2_cells
                )
                
                if not has_year_1_data and not has_year_2_data:
                    raise ValidationError(
                        'Ошибка в структуре файла: не найдены данные предложений в строках 6 или 7. '
                        'Убедитесь, что файл соответствует утвержденному шаблону.'
                    )
                
                workbook.close()
                
            except openpyxl.utils.exceptions.InvalidFileException:
                raise ValidationError(
                    'Поврежденный или некорректный Excel файл. '
                    'Убедитесь, что файл не поврежден и соответствует формату .xlsx'
                )
            except Exception as e:
                # Если это не наша ValidationError, то это системная ошибка
                if isinstance(e, ValidationError):
                    raise e
                raise ValidationError(
                    'Не удалось прочитать Excel файл. '
                    'Убедитесь, что файл не поврежден и соответствует утвержденному шаблону.'
                )
                
        except ImportError:
            # Если openpyxl не установлен, пропускаем детальную проверку структуры
            # Это будет обработано на уровне сервиса
            pass
        
        return file


class MultipleFileInput(forms.FileInput):
    """Custom widget for multiple file input"""
    allow_multiple_selected = True
    
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'multiple': True})
        super().__init__(attrs)
    
    def value_from_datadict(self, data, files, name):
        """Return a list of files from the datadict"""
        if hasattr(files, 'getlist'):
            return files.getlist(name)
        else:
            return files.get(name)


class MultipleCompanyResponseUploadForm(forms.Form):
    """Форма для множественной загрузки ответов страховых компаний"""
    
    excel_files = forms.FileField(
        widget=MultipleFileInput(attrs={
            'accept': '.xlsx',
            'class': 'form-control',
            'id': 'company-response-files'
        }),
        label='Файлы с предложениями',
        help_text='Выберите один или несколько Excel файлов (.xlsx) с предложениями от страховых компаний. Максимум 10 файлов, размер каждого файла до 1MB, общий размер до 10MB.',
        required=False  # Делаем поле не обязательным для формы, проверим в clean_excel_files
    )
    
    def clean_excel_files(self):
        """Валидация множественных файлов"""
        # Получаем файлы из request.FILES через форму
        if hasattr(self, 'files') and self.files:
            files = self.files.getlist('excel_files')
        else:
            files = []
        
        if not files:
            raise ValidationError('Не выбрано ни одного файла для загрузки')
        
        # Ограничения согласно требованиям
        MAX_FILES = 10
        MAX_FILE_SIZE_MB = 1
        MAX_TOTAL_SIZE_MB = 10
        
        # Проверка количества файлов
        if len(files) > MAX_FILES:
            raise ValidationError(f'Слишком много файлов ({len(files)}). Максимальное количество файлов: {MAX_FILES}')
        
        # Проверка каждого файла
        total_size = 0
        valid_mime_types = [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ]
        
        for i, file in enumerate(files, 1):
            # Проверка расширения
            ext = os.path.splitext(file.name)[1].lower()
            if ext != '.xlsx':
                raise ValidationError(f'Файл "{file.name}" имеет неподдерживаемый формат. Разрешены только файлы .xlsx')
            
            # Проверка MIME типа
            if hasattr(file, 'content_type') and file.content_type:
                if file.content_type not in valid_mime_types:
                    raise ValidationError(f'Файл "{file.name}" имеет неверный тип. Загрузите файл Excel в формате .xlsx')
            
            # Проверка размера файла
            max_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
            if file.size > max_size_bytes:
                raise ValidationError(f'Файл "{file.name}" слишком большой ({file.size / (1024*1024):.1f}MB). Максимальный размер: {MAX_FILE_SIZE_MB}MB')
            
            # Проверка на пустой файл
            if file.size == 0:
                raise ValidationError(f'Файл "{file.name}" пуст')
            
            total_size += file.size
            
            # Базовая проверка структуры файла (аналогично CompanyResponseUploadForm)
            try:
                import openpyxl
                from io import BytesIO
                
                # Создаем копию файла для проверки
                file_content = file.read()
                file.seek(0)  # Возвращаем указатель в начало файла
                
                # Проверяем, что файл можно открыть как Excel
                try:
                    workbook = openpyxl.load_workbook(BytesIO(file_content), read_only=True)
                    
                    # Проверяем, что есть хотя бы один лист
                    if not workbook.worksheets:
                        raise ValidationError(f'Файл "{file.name}" не содержит листов с данными')
                    
                    # Проверяем первый лист на наличие базовой структуры
                    worksheet = workbook.active
                    
                    # Проверяем наличие ключевых ячеек согласно шаблону
                    # B2 должна содержать название компании
                    company_cell = worksheet['B2']
                    if not company_cell.value or str(company_cell.value).strip() == '':
                        raise ValidationError(f'Ошибка в структуре файла "{file.name}": ячейка B2 должна содержать название страховой компании')
                    
                    # Проверяем наличие данных в строке 6 (первый год)
                    year_1_cells = ['A6', 'B6', 'D6', 'E6', 'F6']
                    has_year_1_data = any(
                        worksheet[cell].value is not None and str(worksheet[cell].value).strip() != ''
                        for cell in year_1_cells
                    )
                    
                    # Проверяем наличие данных в строке 7 (второй год)
                    year_2_cells = ['A7', 'B7', 'D7', 'E7', 'F7']
                    has_year_2_data = any(
                        worksheet[cell].value is not None and str(worksheet[cell].value).strip() != ''
                        for cell in year_2_cells
                    )
                    
                    if not has_year_1_data and not has_year_2_data:
                        raise ValidationError(f'Ошибка в структуре файла "{file.name}": не найдены данные предложений в строках 6 или 7. Убедитесь, что файл соответствует утвержденному шаблону.')
                    
                    workbook.close()
                    
                except openpyxl.utils.exceptions.InvalidFileException:
                    raise ValidationError(f'Файл "{file.name}" поврежден или имеет некорректный формат. Убедитесь, что файл не поврежден и соответствует формату .xlsx')
                except Exception as e:
                    # Если это не наша ValidationError, то это системная ошибка
                    if isinstance(e, ValidationError):
                        raise e
                    raise ValidationError(f'Не удалось прочитать файл "{file.name}". Убедитесь, что файл не поврежден и соответствует утвержденному шаблону.')
                        
            except ImportError:
                # Если openpyxl не установлен, пропускаем детальную проверку структуры
                # Это будет обработано на уровне сервиса
                pass
        
        # Проверка общего размера
        max_total_size_bytes = MAX_TOTAL_SIZE_MB * 1024 * 1024
        if total_size > max_total_size_bytes:
            raise ValidationError(f'Общий размер файлов слишком большой ({total_size / (1024*1024):.1f}MB). Максимальный общий размер: {MAX_TOTAL_SIZE_MB}MB')
        
        return files


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
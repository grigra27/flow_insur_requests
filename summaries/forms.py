"""
Формы для работы со сводами предложений
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import InsuranceOffer, InsuranceSummary, SummaryTemplate
from decimal import Decimal


# Константа со списком страховых компаний
INSURANCE_COMPANIES = [
    ('', 'Выберите страховщика'),
    ('Абсолют', 'Абсолют'),
    ('Альфа', 'Альфа'),
    ('ВСК', 'ВСК'),
    ('Согаз', 'Согаз'),
    ('РЕСО', 'РЕСО'),
    ('Ингосстрах', 'Ингосстрах'),
    ('Ренессанс', 'Ренессанс'),
    ('Росгосстрах', 'Росгосстрах'),
    ('Пари', 'Пари'),
    ('Совкомбанк СК', 'Совкомбанк СК'),
    ('Согласие', 'Согласие'),
    ('Энергогарант', 'Энергогарант'),
    ('ПСБ-страхование', 'ПСБ-страхование'),
    ('Зетта', 'Зетта'),
]


class OfferForm(forms.ModelForm):
    """Форма для добавления/редактирования предложения от страховщика"""
    
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
            'installment_variant_1': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'installment_variant_2': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
        choices=INSURANCE_COMPANIES,
        label='Страховая компания',
        widget=forms.Select(attrs={'class': 'form-select'})
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
        valid_companies = [choice[0] for choice in INSURANCE_COMPANIES if choice[0]]  # Исключаем пустой выбор
        
        if not company_name:
            raise ValidationError('Выберите страховую компанию')
        
        if company_name not in valid_companies:
            raise ValidationError('Выберите страховщика из списка')
        
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
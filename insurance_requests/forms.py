"""
Формы для работы со страховыми заявками
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import InsuranceRequest, RequestAttachment
import os
import re
import pytz
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class CustomAuthenticationForm(AuthenticationForm):
    """Кастомная форма аутентификации с улучшенной валидацией"""
    
    username = forms.CharField(
        label='Логин',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите логин',
            'autocomplete': 'username',
            'autofocus': True
        })
    )
    
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль',
            'autocomplete': 'current-password'
        })
    )
    
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        
        # Добавляем дополнительные атрибуты для улучшения UX
        self.fields['username'].widget.attrs.update({
            'required': True,
            'minlength': '3',
            'maxlength': '150'
        })
        
        self.fields['password'].widget.attrs.update({
            'required': True,
            'minlength': '6'
        })
    
    def clean_username(self):
        """Валидация логина"""
        username = self.cleaned_data.get('username')
        
        if not username:
            raise ValidationError('Логин обязателен для заполнения')
        
        # Проверяем минимальную длину
        if len(username) < 3:
            raise ValidationError('Логин должен содержать минимум 3 символа')
        
        # Проверяем максимальную длину
        if len(username) > 150:
            raise ValidationError('Логин не должен превышать 150 символов')
        
        # Проверяем на недопустимые символы
        if not re.match(r'^[a-zA-Z0-9_@+.-]+$', username):
            raise ValidationError('Логин может содержать только буквы, цифры и символы @/./+/-/_')
        
        return username
    
    def clean_password(self):
        """Валидация пароля"""
        password = self.cleaned_data.get('password')
        
        if not password:
            raise ValidationError('Пароль обязателен для заполнения')
        
        # Проверяем минимальную длину
        if len(password) < 6:
            raise ValidationError('Пароль должен содержать минимум 6 символов')
        
        return password
    
    def clean(self):
        """Валидация формы с улучшенной обработкой ошибок"""
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            # Проверяем аутентификацию
            self.user_cache = authenticate(
                self.request, 
                username=username, 
                password=password
            )
            
            if self.user_cache is None:
                # Проверяем, существует ли пользователь
                from django.contrib.auth.models import User
                try:
                    user = User.objects.get(username=username)
                    if not user.is_active:
                        raise ValidationError(
                            'Ваша учетная запись отключена. Обратитесь к администратору.',
                            code='inactive'
                        )
                    else:
                        raise ValidationError(
                            'Неверный пароль. Проверьте правильность введенных данных.',
                            code='invalid_password'
                        )
                except User.DoesNotExist:
                    raise ValidationError(
                        'Пользователь с таким логином не найден.',
                        code='invalid_username'
                    )
            else:
                self.confirm_login_allowed(self.user_cache)
        
        return self.cleaned_data
    
    def confirm_login_allowed(self, user):
        """Дополнительные проверки для разрешения входа"""
        if not user.is_active:
            raise ValidationError(
                'Ваша учетная запись отключена.',
                code='inactive'
            )


class ExcelUploadForm(forms.Form):
    """Форма для загрузки Excel файла с заявкой"""
    
    # Варианты типов заявок
    APPLICATION_TYPE_CHOICES = [
        ('legal_entity', 'Заявка от юр.лица'),
        ('individual_entrepreneur', 'Заявка от ИП'),
    ]
    
    # Варианты форматов заявок
    APPLICATION_FORMAT_CHOICES = [
        ('', '-- Выберите формат заявки --'),
        ('casco_equipment', 'КАСКО/спецтехника'),
        ('property', 'имущество'),
    ]
    
    application_format = forms.ChoiceField(
        choices=APPLICATION_FORMAT_CHOICES,
        label='Формат заявки',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Выберите формат загружаемой заявки. КАСКО/спецтехника - для автострахования и спецтехники, имущество - для страхования имущества.',
        required=True
    )
    
    application_type = forms.ChoiceField(
        choices=[('', '-- Выберите тип заявки --')] + APPLICATION_TYPE_CHOICES,
        label='Тип заявки',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Выберите тип загружаемой заявки. Заявки от ИП имеют дополнительную строку в позиции 8, что влияет на расположение данных в файле.',
        required=True
    )
    
    excel_file = forms.FileField(
        label='Excel файл с заявкой',
        help_text='Загрузите файл в формате .xls, .xlsx или .xltx',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xls,.xlsx,.xltx'
        })
    )
    
    def clean_application_format(self):
        """Валидация формата заявки с улучшенными сообщениями об ошибках"""
        application_format = self.cleaned_data.get('application_format')
        
        if not application_format:
            raise ValidationError(
                'Необходимо выбрать формат заявки. Выберите "КАСКО/спецтехника" для автострахования '
                'и спецтехники или "имущество" для страхования имущества.'
            )
        
        # Проверяем, что выбрано одно из допустимых значений
        valid_formats = [choice[0] for choice in self.APPLICATION_FORMAT_CHOICES if choice[0]]
        if application_format not in valid_formats:
            # Реализуем fallback на формат "КАСКО/спецтехника" при некорректных данных
            logger.warning(f"Invalid application format '{application_format}' provided, falling back to 'casco_equipment'")
            return 'casco_equipment'
        
        return application_format
    
    def clean_application_type(self):
        """Валидация типа заявки с улучшенными сообщениями об ошибках"""
        application_type = self.cleaned_data.get('application_type')
        
        if not application_type:
            raise ValidationError(
                'Необходимо выбрать тип заявки. Выберите "Заявка от юр.лица" или "Заявка от ИП" '
                'в зависимости от структуры вашего Excel файла.'
            )
        
        # Проверяем, что выбрано одно из допустимых значений
        valid_types = [choice[0] for choice in self.APPLICATION_TYPE_CHOICES]
        if application_type not in valid_types:
            # Реализуем fallback на тип "юр.лицо" при некорректных данных
            logger.warning(f"Invalid application type '{application_type}' provided, falling back to 'legal_entity'")
            return 'legal_entity'
        
        return application_type
    
    def clean_excel_file(self):
        """Валидация загружаемого файла с улучшенными сообщениями об ошибках"""
        file = self.cleaned_data.get('excel_file')
        
        if not file:
            raise ValidationError('Файл не выбран. Пожалуйста, выберите Excel файл для загрузки.')
        
        # Проверяем расширение файла
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ['.xls', '.xlsx', '.xltx']:
            raise ValidationError(
                f'Неподдерживаемый формат файла: {ext}. '
                'Поддерживаются только файлы форматов .xls, .xlsx и .xltx. '
                'Пожалуйста, сохраните ваш файл в одном из поддерживаемых форматов.'
            )
        
        # Проверяем размер файла (максимум 10MB)
        if file.size > 10 * 1024 * 1024:
            size_mb = file.size / (1024 * 1024)
            raise ValidationError(
                f'Размер файла слишком большой: {size_mb:.1f}MB. '
                'Максимально допустимый размер файла: 10MB. '
                'Пожалуйста, уменьшите размер файла или обратитесь к администратору.'
            )
        
        return file
    
    def clean(self):
        """Общая валидация формы с проверкой совместимости формата, типа заявки и файла"""
        cleaned_data = super().clean()
        application_format = cleaned_data.get('application_format')
        application_type = cleaned_data.get('application_type')
        excel_file = cleaned_data.get('excel_file')
        
        # Если все поля валидны, проводим дополнительные проверки
        if application_format and application_type and excel_file:
            # Логируем выбранные параметры для диагностики
            logger.info(f"Form validation: application_format='{application_format}', application_type='{application_type}', file='{excel_file.name}'")
            
            # Проверяем, что формат заявки корректный (дополнительная проверка)
            valid_formats = [choice[0] for choice in self.APPLICATION_FORMAT_CHOICES if choice[0]]
            if application_format not in valid_formats:
                # Применяем fallback и предупреждаем пользователя
                cleaned_data['application_format'] = 'casco_equipment'
                logger.warning(f"Invalid application format '{application_format}' in form clean, using fallback 'casco_equipment'")
            
            # Проверяем, что тип заявки корректный (дополнительная проверка)
            valid_types = [choice[0] for choice in self.APPLICATION_TYPE_CHOICES]
            if application_type not in valid_types:
                # Применяем fallback и предупреждаем пользователя
                cleaned_data['application_type'] = 'legal_entity'
                logger.warning(f"Invalid application type '{application_type}' in form clean, using fallback 'legal_entity'")
            
            # Валидация совместимости формата и типа заявки
            # Все форматы совместимы с обоими типами заявок (юр.лицо и ИП)
            # Дополнительных ограничений совместимости нет согласно требованиям
            
        return cleaned_data


class DateTimeLocalWidget(forms.DateTimeInput):
    """Custom widget for datetime-local input with proper formatting"""
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {'type': 'datetime-local', 'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, format=format)
    
    def format_value(self, value):
        """Format datetime value for HTML5 datetime-local input"""
        if value is None:
            return ''
        
        if isinstance(value, str):
            # Try to parse string value
            try:
                from datetime import datetime
                # Try different formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%d.%m.%Y %H:%M:%S']:
                    try:
                        value = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return value  # Return as-is if we can't parse
            except:
                return value
        
        if hasattr(value, 'strftime'):
            # Convert timezone-aware datetime to local time if needed
            if hasattr(value, 'tzinfo') and value.tzinfo is not None:
                # Convert to Moscow timezone for display
                moscow_tz = pytz.timezone('Europe/Moscow')
                value = value.astimezone(moscow_tz).replace(tzinfo=None)
            
            # Format for HTML5 datetime-local: YYYY-MM-DDTHH:MM
            return value.strftime('%Y-%m-%dT%H:%M')
        
        return value


class InsuranceRequestForm(forms.ModelForm):
    """Улучшенная форма для редактирования заявок"""
    
    # Предопределенные варианты филиалов
    BRANCH_CHOICES = [
        ('', '-- Выберите филиал --'),
        ('Казань', 'Казань'),
        ('Нижний Новгород', 'Нижний Новгород'),
        ('Краснодар', 'Краснодар'),
        ('Санкт-Петербург', 'Санкт-Петербург'),
        ('Мурманск', 'Мурманск'),
        ('Псков', 'Псков'),
        ('Челябинск', 'Челябинск'),
        ('Москва', 'Москва'),
        ('Великий Новгород', 'Великий Новгород'),
        ('Архангельск', 'Архангельск'),
    ]
    
    # Варианты периода страхования
    INSURANCE_PERIOD_CHOICES = [
        ('', '-- Выберите период --'),
        ('1 год', '1 год'),
        ('на весь срок лизинга', 'на весь срок лизинга'),
    ]
    
    # Переопределяем поле филиала как выпадающий список
    branch = forms.ChoiceField(
        choices=BRANCH_CHOICES,
        required=False,
        label='Филиал',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Переопределяем поле периода страхования как выпадающий список
    insurance_period = forms.ChoiceField(
        choices=INSURANCE_PERIOD_CHOICES,
        required=False,
        label='Срок страхования',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def clean_branch(self):
        """Валидация филиала - только разрешенные значения"""
        branch = self.cleaned_data.get('branch')
        if branch:
            valid_branches = [choice[0] for choice in self.BRANCH_CHOICES if choice[0]]
            if branch not in valid_branches:
                # If invalid branch, return empty string
                return ''
        return branch
    
    class Meta:
        model = InsuranceRequest
        fields = [
            'client_name', 'inn', 'insurance_type', 'insurance_period',
            'vehicle_info', 'dfa_number', 'branch', 'has_franchise', 
            'has_installment', 'has_autostart', 'has_casco_ce', 'has_transportation',
            'has_construction_work', 'response_deadline', 'notes'
        ]
        
        widgets = {
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'inn': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '12'}),
            'insurance_type': forms.Select(
                choices=InsuranceRequest.INSURANCE_TYPE_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'vehicle_info': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'dfa_number': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '100'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Введите дополнительные примечания к заявке...',
                'maxlength': '2000'
            }),
            'has_franchise': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_installment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_autostart': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_casco_ce': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_transportation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_construction_work': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'response_deadline': DateTimeLocalWidget(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Добавляем help text для поля периода страхования
        self.fields['insurance_period'].help_text = 'Выберите необходимый период страхования'
        
        # Добавляем help text для поля примечаний
        self.fields['notes'].help_text = 'Дополнительные примечания и комментарии к заявке (необязательно)'
        self.fields['notes'].required = False
        
        # Настройка полей для транспортировки и строительно-монтажных работ
        self.fields['has_transportation'].label = 'Требуется перевозка'
        self.fields['has_transportation'].help_text = ''  # No help text needed
        
        self.fields['has_construction_work'].label = 'Требуется СМР'
        self.fields['has_construction_work'].help_text = ''  # No help text needed
        
        # Make insurance_period not required for backward compatibility
        self.fields['insurance_period'].required = False
        
        # Ensure proper pre-population of all fields when editing existing instance
        if self.instance:
            # Handle insurance_period field - preserve original recognized value or set to empty for selection
            if self.instance.insurance_period and self.instance.insurance_period.strip():
                # Check if the current value matches one of our choices
                period_value = self.instance.insurance_period.strip()
                valid_periods = [choice[0] for choice in self.INSURANCE_PERIOD_CHOICES if choice[0]]
                if period_value in valid_periods:
                    self.initial['insurance_period'] = period_value
                else:
                    # For backward compatibility with old date-based periods, set to empty
                    self.initial['insurance_period'] = ''
            
            # Handle branch field - ensure it's properly selected if it matches a choice
            if self.instance.branch:
                valid_branches = [choice[0] for choice in self.BRANCH_CHOICES if choice[0]]
                if self.instance.branch not in valid_branches:
                    # If branch doesn't match any choice, set initial to empty
                    self.fields['branch'].initial = ''
            
            # Handle datetime field - ensure proper formatting for datetime-local
            if self.instance.response_deadline:
                # The custom widget will handle the formatting
                self.fields['response_deadline'].initial = self.instance.response_deadline
            
            # Ensure all boolean fields are properly set
            for field_name in ['has_franchise', 'has_installment', 'has_autostart', 'has_casco_ce', 'has_transportation', 'has_construction_work']:
                if hasattr(self.instance, field_name):
                    self.fields[field_name].initial = getattr(self.instance, field_name)
            
            # Ensure notes field is properly initialized
            if hasattr(self.instance, 'notes') and self.instance.notes:
                self.fields['notes'].initial = self.instance.notes
    
    def __getitem__(self, name):
        """Override to handle special cases for field values"""
        field = super().__getitem__(name)
        
        # Special handling for branch field with invalid values
        if name == 'branch' and self.instance and self.instance.pk:
            if self.instance.branch:
                valid_branches = [choice[0] for choice in self.BRANCH_CHOICES if choice[0]]
                if self.instance.branch not in valid_branches:
                    # Create a custom bound field that returns empty value
                    from django.forms.boundfield import BoundField
                    
                    class CustomBoundField(BoundField):
                        def value(self):
                            return ''
                    
                    return CustomBoundField(self, self.fields[name], name)
        
        return field
    

    

    
    def clean_response_deadline(self):
        """Валидация срока ответа с учетом московского времени"""
        deadline = self.cleaned_data.get('response_deadline')
        
        if deadline:
            # Преобразуем в московское время для сравнения
            moscow_tz = pytz.timezone('Europe/Moscow')
            moscow_now = timezone.now().astimezone(moscow_tz)
            
            # Если время введено без часового пояса, считаем его московским
            if deadline.tzinfo is None:
                deadline = moscow_tz.localize(deadline)
            
            # Предупреждение, если срок в прошлом (но не блокируем)
            if deadline < moscow_now:
                # Можно добавить предупреждение, но не блокировать сохранение
                pass
        
        return deadline
    
    def clean_inn(self):
        """Валидация ИНН"""
        inn = self.cleaned_data.get('inn')
        if inn and not inn.isdigit():
            raise ValidationError('ИНН должен содержать только цифры')
        if inn and len(inn) not in [10, 12]:
            raise ValidationError('ИНН должен содержать 10 или 12 цифр')
        return inn
    
    def clean_dfa_number(self):
        """Валидация номера ДФА"""
        dfa_number = self.cleaned_data.get('dfa_number')
        if dfa_number and len(dfa_number) > 100:
            raise ValidationError('Номер ДФА не должен превышать 100 символов')
        return dfa_number
    
    def clean_insurance_period(self):
        """Валидация периода страхования"""
        insurance_period = self.cleaned_data.get('insurance_period')
        
        # Поле не обязательно, но если заполнено, должно быть валидным
        if insurance_period:
            # Trim whitespace
            insurance_period = insurance_period.strip()
            
            # Проверяем, что выбрано одно из допустимых значений
            valid_periods = [choice[0] for choice in self.INSURANCE_PERIOD_CHOICES if choice[0]]
            if insurance_period not in valid_periods:
                raise ValidationError('Выберите один из предложенных вариантов периода страхования')
        
        return insurance_period
    
    def clean_branch(self):
        """Валидация филиала"""
        branch = self.cleaned_data.get('branch')
        # Django's ChoiceField automatically validates that the choice is valid
        # No additional validation needed
        return branch
    
    def clean_notes(self):
        """Валидация поля примечаний"""
        notes = self.cleaned_data.get('notes', '')
        
        if notes:
            # Trim whitespace
            notes = notes.strip()
            
            # Check maximum length
            if len(notes) > 2000:
                raise ValidationError('Примечание не должно превышать 2000 символов')
            
            # Basic XSS protection - remove potentially dangerous HTML tags
            import re
            # Remove script tags and their content
            notes = re.sub(r'<script[^>]*>.*?</script>', '', notes, flags=re.IGNORECASE | re.DOTALL)
            # Remove other potentially dangerous tags
            dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button']
            for tag in dangerous_tags:
                notes = re.sub(f'<{tag}[^>]*>', '', notes, flags=re.IGNORECASE)
                notes = re.sub(f'</{tag}>', '', notes, flags=re.IGNORECASE)
            
            # Remove javascript: and data: URLs
            notes = re.sub(r'javascript:', '', notes, flags=re.IGNORECASE)
            notes = re.sub(r'data:', '', notes, flags=re.IGNORECASE)
            
            # Check for minimum meaningful content (if not empty)
            if notes and len(notes.strip()) < 3:
                raise ValidationError('Примечание должно содержать минимум 3 символа')
        
        return notes
    
    def clean(self):
        """Общая валидация формы"""
        cleaned_data = super().clean()
        return cleaned_data
    
    def save(self, commit=True):
        """Сохранение формы"""
        instance = super().save(commit=False)
        
        # Сохраняем выбранный период страхования
        insurance_period = self.cleaned_data.get('insurance_period')
        if insurance_period and insurance_period.strip():
            instance.insurance_period = insurance_period
        # Если период не выбран, оставляем существующее значение или пустую строку
        elif not instance.insurance_period:
            instance.insurance_period = ""
        
        if commit:
            instance.save()
        return instance


class EmailPreviewForm(forms.Form):
    """Форма для предварительного просмотра и редактирования письма"""
    
    email_subject = forms.CharField(
        label='Тема письма',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    email_body = forms.CharField(
        label='Текст письма',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 15})
    )
    
    recipients = forms.CharField(
        label='Получатели (через запятую)',
        help_text='Введите email адреса получателей через запятую',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    def clean_recipients(self):
        """Валидация email адресов получателей"""
        recipients = self.cleaned_data.get('recipients', '')
        emails = [email.strip() for email in recipients.split(',') if email.strip()]
        
        if not emails:
            raise ValidationError('Укажите хотя бы один email адрес')
        
        # Проверяем каждый email
        for email in emails:
            try:
                forms.EmailField().clean(email)
            except ValidationError:
                raise ValidationError(f'Некорректный email адрес: {email}')
        
        return emails


class OfferUploadForm(forms.Form):
    """Форма для загрузки файлов предложений от страховых компаний"""
    
    # Простое поле для одного файла - множественность обрабатываем в JavaScript и представлении
    offer_files = forms.FileField(
        label='Файлы предложений',
        help_text='Выберите один или несколько Excel файлов (.xlsx) с предложениями от страховых компаний',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx',
            'id': 'offer-files-input'
        }),
        required=False  # Валидацию проведем в представлении
    )
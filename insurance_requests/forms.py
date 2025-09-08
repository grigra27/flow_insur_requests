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
from datetime import datetime


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
    """Форма для загрузки Excel файла с заявкой с улучшенной валидацией"""
    
    excel_file = forms.FileField(
        label='Excel файл с заявкой',
        help_text='Загрузите файл в формате .xls или .xlsx (максимум 50MB)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xls,.xlsx',
            'data-max-size': '52428800'  # 50MB in bytes
        })
    )
    
    def clean_excel_file(self):
        """Расширенная валидация загружаемого файла для HTTPS контекста"""
        file = self.cleaned_data.get('excel_file')
        
        if not file:
            raise ValidationError('Файл не выбран')
        
        # Проверяем расширение файла
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ['.xls', '.xlsx']:
            raise ValidationError('Поддерживаются только файлы .xls и .xlsx')
        
        # Проверяем размер файла (максимум 50MB для HTTPS)
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size > max_size:
            raise ValidationError(f'Размер файла не должен превышать 50MB. Текущий размер: {file.size / (1024*1024):.1f}MB')
        
        # Проверяем минимальный размер файла
        min_size = 1024  # 1KB
        if file.size < min_size:
            raise ValidationError('Файл слишком мал. Возможно, файл поврежден')
        
        # Проверяем имя файла на безопасность
        import re
        safe_filename_pattern = re.compile(r'^[a-zA-Z0-9._\-\s\u0400-\u04FF]+$')
        if not safe_filename_pattern.match(file.name):
            raise ValidationError('Имя файла содержит недопустимые символы')
        
        # Проверяем длину имени файла
        if len(file.name) > 255:
            raise ValidationError('Имя файла слишком длинное (максимум 255 символов)')
        
        # Проверяем MIME тип для дополнительной безопасности
        import magic
        try:
            file_content = file.read(2048)  # Читаем первые 2KB для определения типа
            file.seek(0)  # Возвращаем указатель в начало
            
            mime_type = magic.from_buffer(file_content, mime=True)
            allowed_mime_types = [
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/octet-stream'  # Иногда Excel файлы определяются как octet-stream
            ]
            
            if mime_type not in allowed_mime_types:
                raise ValidationError(f'Недопустимый тип файла: {mime_type}. Загрузите файл Excel (.xls или .xlsx)')
                
        except ImportError:
            # Если python-magic не установлен, пропускаем проверку MIME типа
            pass
        except Exception as e:
            # Если произошла ошибка при проверке MIME типа, логируем её но не блокируем загрузку
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not verify MIME type for file {file.name}: {str(e)}")
        
        return file


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
    
    # Переопределяем поле филиала как выпадающий список
    branch = forms.ChoiceField(
        choices=BRANCH_CHOICES,
        required=False,
        label='Филиал',
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
            'client_name', 'inn', 'insurance_type',
            'insurance_start_date', 'insurance_end_date',
            'vehicle_info', 'dfa_number', 'branch', 'has_franchise', 
            'has_installment', 'has_autostart', 'has_casco_ce', 'response_deadline'
        ]
        
        widgets = {
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'inn': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '12'}),
            'insurance_type': forms.Select(
                choices=InsuranceRequest.INSURANCE_TYPE_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'insurance_start_date': forms.DateInput(attrs={
                'class': 'form-control date-input',
                'type': 'date',
                'placeholder': 'дд.мм.гггг'
            }),
            'insurance_end_date': forms.DateInput(attrs={
                'class': 'form-control date-input',
                'type': 'date',
                'placeholder': 'дд.мм.гггг'
            }),
            'vehicle_info': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'dfa_number': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '100'}),

            'has_franchise': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_installment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_autostart': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_casco_ce': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'response_deadline': DateTimeLocalWidget(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Добавляем help text для полей дат
        self.fields['insurance_start_date'].help_text = 'Дата начала действия страхования'
        self.fields['insurance_end_date'].help_text = 'Дата окончания действия страхования'
        
        # Ensure proper pre-population of all fields when editing existing instance
        if self.instance and self.instance.pk:
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
            for field_name in ['has_franchise', 'has_installment', 'has_autostart', 'has_casco_ce']:
                if hasattr(self.instance, field_name):
                    self.fields[field_name].initial = getattr(self.instance, field_name)
            
            # Ensure date fields are properly formatted
            if self.instance.insurance_start_date:
                self.fields['insurance_start_date'].initial = self.instance.insurance_start_date
            if self.instance.insurance_end_date:
                self.fields['insurance_end_date'].initial = self.instance.insurance_end_date
    
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
    
    def clean_insurance_start_date(self):
        """Валидация даты начала страхования"""
        start_date = self.cleaned_data.get('insurance_start_date')
        
        if start_date:
            # Проверяем, что дата не слишком далеко в прошлом (более 5 лет)
            from datetime import date, timedelta
            five_years_ago = date.today() - timedelta(days=5*365)
            
            if start_date < five_years_ago:
                raise ValidationError('Дата начала страхования не может быть более 5 лет назад')
        
        return start_date
    
    def clean_insurance_end_date(self):
        """Валидация даты окончания страхования"""
        end_date = self.cleaned_data.get('insurance_end_date')
        
        if end_date:
            # Проверяем, что дата не слишком далеко в будущем (более 10 лет)
            from datetime import date, timedelta
            ten_years_ahead = date.today() + timedelta(days=10*365)
            
            if end_date > ten_years_ahead:
                raise ValidationError('Дата окончания страхования не может быть более 10 лет в будущем')
        
        return end_date
    
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
    
    def clean_branch(self):
        """Валидация филиала"""
        branch = self.cleaned_data.get('branch')
        # Django's ChoiceField automatically validates that the choice is valid
        # No additional validation needed
        return branch
    
    def clean(self):
        """Валидация дат страхования"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('insurance_start_date')
        end_date = cleaned_data.get('insurance_end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({
                    'insurance_end_date': 'Дата окончания страхования должна быть позже даты начала'
                })
            
            # Проверяем, что период не слишком короткий (менее 1 дня)
            if (end_date - start_date).days < 1:
                raise ValidationError({
                    'insurance_end_date': 'Период страхования должен составлять минимум 1 день'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Сохранение с обновлением поля insurance_period из дат"""
        instance = super().save(commit=False)
        
        # Обновляем поле insurance_period на основе отдельных дат
        start_date = self.cleaned_data.get('insurance_start_date')
        end_date = self.cleaned_data.get('insurance_end_date')
        
        if start_date and end_date:
            instance.insurance_period = f"с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}"
        elif start_date:
            instance.insurance_period = f"с {start_date.strftime('%d.%m.%Y')} по не указано"
        elif end_date:
            instance.insurance_period = f"с не указано по {end_date.strftime('%d.%m.%Y')}"
        else:
            instance.insurance_period = "Период не указан"
        
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
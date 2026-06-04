"""
Формы для работы со страховыми заявками
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import InsuranceRequest, RequestAttachment
import os
import re
import pytz
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


DEFAULT_BRANCH = 'Санкт-Петербург'

AVAILABLE_BRANCH_CHOICES = [
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


EDIT_BRANCH_CHOICES = [('', '-- Выберите филиал --')] + AVAILABLE_BRANCH_CHOICES


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
        self.failure_reason = None
        self.failure_context = {}
        
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
                # Анти-enumeration: не раскрываем, существует ли пользователь.
                user_model = get_user_model()
                user = user_model.objects.filter(username=username).only('is_active').first()
                self.failure_reason = 'invalid_credentials'
                self.failure_context = {
                    'user_exists': bool(user),
                    'user_active': bool(user.is_active) if user else None,
                }
                raise ValidationError(
                    'Неверный логин или пароль. Проверьте правильность введенных данных.',
                    code='invalid_login'
                )
            else:
                self.confirm_login_allowed(self.user_cache)
        
        return self.cleaned_data
    
    def confirm_login_allowed(self, user):
        """Дополнительные проверки для разрешения входа"""
        if not user.is_active:
            self.failure_reason = 'invalid_credentials'
            self.failure_context = {
                'user_exists': True,
                'user_active': False,
            }
            raise ValidationError(
                'Неверный логин или пароль. Проверьте правильность введенных данных.',
                code='invalid_login'
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
            'class': 'form-control form-control-lg',
            'accept': '.xls,.xlsx,.xltx',
            'style': 'height: 50px; font-size: 1.1rem;'
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


class ParserV2ExcelUploadForm(forms.Form):
    """Форма загрузки файла для экспериментального Parser V2."""

    excel_file = forms.FileField(
        label='Excel файл с заявкой',
        help_text='Загрузите файл в формате .xls, .xlsx или .xltx',
        widget=forms.FileInput(attrs={
            'class': 'form-control form-control-lg',
            'accept': '.xls,.xlsx,.xltx',
        })
    )

    def clean_excel_file(self):
        file = self.cleaned_data.get('excel_file')
        if not file:
            raise ValidationError('Файл не выбран. Пожалуйста, выберите Excel файл для загрузки.')

        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ['.xls', '.xlsx', '.xltx']:
            raise ValidationError(
                f'Неподдерживаемый формат файла: {ext}. Поддерживаются только .xls, .xlsx и .xltx.'
            )

        if file.size > 10 * 1024 * 1024:
            size_mb = file.size / (1024 * 1024)
            raise ValidationError(f'Размер файла слишком большой: {size_mb:.1f}MB. Максимум: 10MB.')

        return file


class ParserV2PreviewForm(forms.Form):
    """Editable best-effort preview before creating a request from Parser V2."""

    draft_id = forms.CharField(widget=forms.HiddenInput)
    client_name = forms.CharField(label='Клиент', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    inn = forms.CharField(label='ИНН', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    insurance_type = forms.ChoiceField(
        label='Тип страхования',
        required=False,
        choices=InsuranceRequest.INSURANCE_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    insurance_period = forms.ChoiceField(
        label='Срок страхования',
        required=False,
        choices=[('', '-- Не указан --')] + InsuranceRequest.INSURANCE_PERIOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    vehicle_info = forms.CharField(
        label='Информация о предмете лизинга',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4})
    )
    dfa_number = forms.CharField(label='Номер ДФА', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    branch = forms.ChoiceField(
        label='Филиал',
        required=False,
        choices=EDIT_BRANCH_CHOICES,
        initial=DEFAULT_BRANCH,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    manager_name = forms.CharField(label='ФИО менеджера', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    deal_status = forms.ChoiceField(
        label='Статус сделки',
        required=False,
        choices=InsuranceRequest.DEAL_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    franchise_type = forms.ChoiceField(
        label='Тип франшизы',
        required=False,
        choices=InsuranceRequest.FRANCHISE_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    has_installment = forms.BooleanField(label='Требуется рассрочка', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    has_autostart = forms.BooleanField(label='Есть автозапуск', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    has_casco_ce = forms.BooleanField(label='КАСКО кат. C/E', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    has_transportation = forms.BooleanField(label='Требуется перевозка', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    transportation_departure = forms.CharField(
        label='Пункт отправления (перевозка)', required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '500'})
    )
    transportation_destination = forms.CharField(
        label='Пункт назначения (перевозка)', required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '500'})
    )
    transportation_days = forms.IntegerField(
        label='Срок перевозки, дней', required=False, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )
    has_construction_work = forms.BooleanField(label='Требуется СМР', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    manufacturing_year = forms.CharField(label='Год выпуска', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    asset_status = forms.CharField(label='Статус имущества', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    key_completeness = forms.CharField(label='Комплектность ключей', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    pts_psm = forms.CharField(label='ПТС/ПСМ', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    creditor_bank = forms.CharField(label='Банк-кредитор', required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    usage_purposes = forms.CharField(label='Цели использования', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    telematics_complex = forms.CharField(label='Телематический комплекс', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    insurance_territory = forms.CharField(label='Территория страхования', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    response_deadline = forms.CharField(
        label='Срок ответа',
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    notes = forms.CharField(
        label='Примечание',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4})
    )
    # Stage 2.2/2.3 — customer + deal/insurance common fields.
    legal_address = forms.CharField(
        label='Юридический адрес', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    postal_address = forms.CharField(
        label='Почтовый адрес', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    business_activity = forms.CharField(
        label='Основной вид деятельности', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    birth_date = forms.DateField(
        label='Дата рождения (для ИП)', required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    submission_date = forms.DateField(
        label='Дата подачи заявки', required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    insured_party = forms.ChoiceField(
        label='Страхователь', required=False,
        choices=[('', '-- Не указан --')] + InsuranceRequest.INSURED_PARTY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    insured_sum_type = forms.ChoiceField(
        label='Тип страховой суммы', required=False,
        choices=[('', '-- Не указан --')] + InsuranceRequest.INSURED_SUM_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    guard_conditions = forms.CharField(
        label='Условия охраны/хранения', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    property_location_right_holder = forms.ChoiceField(
        label='Правообладатель места расположения', required=False,
        choices=[('', '-- Не указан --')] + InsuranceRequest.PROPERTY_LOCATION_RIGHT_HOLDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    premium_frequency = forms.ChoiceField(
        label='Частота уплаты премии', required=False,
        choices=[('', '-- Не указан --')] + InsuranceRequest.PREMIUM_FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get('branch'):
            self.initial['branch'] = DEFAULT_BRANCH

    def to_request_fields(self):
        """Return model-safe values without blocking request creation."""
        cleaned = self.cleaned_data
        insurance_type = cleaned.get('insurance_type') or 'другое'
        valid_insurance_types = {choice[0] for choice in InsuranceRequest.INSURANCE_TYPE_CHOICES}
        if insurance_type not in valid_insurance_types:
            insurance_type = 'другое'

        franchise_type = cleaned.get('franchise_type') or 'none'
        valid_franchise_types = {choice[0] for choice in InsuranceRequest.FRANCHISE_TYPE_CHOICES}
        if franchise_type not in valid_franchise_types:
            franchise_type = 'none'

        deal_status = cleaned.get('deal_status') or 'new'
        valid_deal_statuses = {choice[0] for choice in InsuranceRequest.DEAL_STATUS_CHOICES}
        if deal_status not in valid_deal_statuses:
            deal_status = 'new'

        insured_party = cleaned.get('insured_party') or None
        valid_insured_party = {choice[0] for choice in InsuranceRequest.INSURED_PARTY_CHOICES}
        if insured_party not in valid_insured_party:
            insured_party = None

        insured_sum_type = cleaned.get('insured_sum_type') or None
        valid_sum_types = {choice[0] for choice in InsuranceRequest.INSURED_SUM_TYPE_CHOICES}
        if insured_sum_type not in valid_sum_types:
            insured_sum_type = None

        plrh = cleaned.get('property_location_right_holder') or None
        valid_plrh = {choice[0] for choice in InsuranceRequest.PROPERTY_LOCATION_RIGHT_HOLDER_CHOICES}
        if plrh not in valid_plrh:
            plrh = None

        premium_freq = cleaned.get('premium_frequency') or None
        valid_premium_freq = {choice[0] for choice in InsuranceRequest.PREMIUM_FREQUENCY_CHOICES}
        if premium_freq not in valid_premium_freq:
            premium_freq = None

        return {
            'client_name': self._limit(cleaned.get('client_name') or 'Клиент не указан', 255),
            'inn': self._limit(cleaned.get('inn') or '', 12),
            'insurance_type': insurance_type,
            'insurance_period': cleaned.get('insurance_period') or '',
            'vehicle_info': cleaned.get('vehicle_info') or 'Предмет лизинга не указан',
            'dfa_number': self._limit(cleaned.get('dfa_number') or 'Номер ДФА не указан', 100),
            'branch': self._normalize_branch(cleaned.get('branch')),
            'manager_name': self._limit(cleaned.get('manager_name') or '', 255),
            'deal_status': deal_status,
            'franchise_type': franchise_type,
            'has_installment': bool(cleaned.get('has_installment')),
            'has_autostart': bool(cleaned.get('has_autostart')),
            'has_casco_ce': bool(cleaned.get('has_casco_ce')),
            'has_transportation': bool(cleaned.get('has_transportation')),
            'transportation_departure': self._limit(cleaned.get('transportation_departure') or '', 500),
            'transportation_destination': self._limit(cleaned.get('transportation_destination') or '', 500),
            'transportation_days': cleaned.get('transportation_days') or None,
            'has_construction_work': bool(cleaned.get('has_construction_work')),
            'manufacturing_year': self._limit(cleaned.get('manufacturing_year') or '', 255),
            'asset_status': self._limit(cleaned.get('asset_status') or '', 255),
            'key_completeness': self._limit(cleaned.get('key_completeness') or '', 255),
            'pts_psm': self._limit(cleaned.get('pts_psm') or '', 255),
            'creditor_bank': self._limit(cleaned.get('creditor_bank') or '', 255),
            'usage_purposes': cleaned.get('usage_purposes') or '',
            'telematics_complex': cleaned.get('telematics_complex') or '',
            'insurance_territory': cleaned.get('insurance_territory') or '',
            'notes': cleaned.get('notes') or '',
            'response_deadline': self._parse_response_deadline(cleaned.get('response_deadline')),
            # Stage 2.2 — customer details
            'legal_address': cleaned.get('legal_address') or None,
            'postal_address': cleaned.get('postal_address') or None,
            'business_activity': cleaned.get('business_activity') or None,
            'birth_date': cleaned.get('birth_date') or None,
            'submission_date': cleaned.get('submission_date') or None,
            # Stage 2.3 — deal / insurance parameters
            'insured_party': insured_party,
            'insured_sum_type': insured_sum_type,
            'guard_conditions': cleaned.get('guard_conditions') or None,
            'property_location_right_holder': plrh,
            'premium_frequency': premium_freq,
        }

    def _parse_response_deadline(self, value):
        if not value:
            return None
        for date_format in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y %H:%M']:
            try:
                parsed = datetime.strptime(value, date_format)
                moscow_tz = pytz.timezone('Europe/Moscow')
                return timezone.make_aware(parsed, moscow_tz)
            except ValueError:
                continue
        return None

    def _limit(self, value, max_length):
        value = str(value).strip()
        return value[:max_length]

    def _normalize_branch(self, value):
        valid_branches = {choice[0] for choice in AVAILABLE_BRANCH_CHOICES}
        return value if value in valid_branches else ''


class ParserV2ObjectForm(forms.Form):
    """Stage 4.2: one card per insured object in a V2 preview formset.

    The fields mirror the per-object columns introduced by stage 2.1
    (brand, model, condition, equipment_type, power_or_capacity,
    acquisition_cost_value, acquisition_cost_currency) plus the textual
    `manufacturing_year` and the free-form `vehicle_info` description for
    that object. The `skip` checkbox lets the operator drop a sibling
    before it is created.
    """

    skip = forms.BooleanField(
        label='Не создавать эту заявку',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    brand = forms.CharField(
        label='Марка', required=False, max_length=128,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    model = forms.CharField(
        label='Модель', required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    condition = forms.ChoiceField(
        label='Состояние', required=False,
        choices=[('', '— Не определено —')] + InsuranceRequest.OBJECT_CONDITION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    equipment_type = forms.CharField(
        label='Тип/категория', required=False, max_length=128,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    power_or_capacity = forms.CharField(
        label='Мощность/производительность', required=False, max_length=64,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    acquisition_cost_value = forms.DecimalField(
        label='Стоимость', required=False, max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    acquisition_cost_currency = forms.ChoiceField(
        label='Валюта', required=False,
        choices=[('', '— Не определена —')] + InsuranceRequest.ACQUISITION_COST_CURRENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    manufacturing_year = forms.CharField(
        label='Год выпуска', required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    vehicle_info = forms.CharField(
        label='Описание объекта', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    source_object_count = forms.IntegerField(
        label='Количество одинаковых объектов',
        min_value=1,
        required=True,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )

    def to_object_kwargs(self):
        """Return model field kwargs for one InsuranceRequest sibling.

        Mirrors `_parser_v2_object_fields()` in views.py but works from
        cleaned form data instead of parser payload.
        """
        cleaned = self.cleaned_data
        return {
            'brand': cleaned.get('brand') or None,
            'model': cleaned.get('model') or None,
            'condition': cleaned.get('condition') or None,
            'equipment_type': cleaned.get('equipment_type') or None,
            'power_or_capacity': cleaned.get('power_or_capacity') or None,
            'acquisition_cost_value': cleaned.get('acquisition_cost_value'),
            'acquisition_cost_currency': cleaned.get('acquisition_cost_currency') or None,
            'vehicle_info': (cleaned.get('vehicle_info') or 'Предмет лизинга не указан')[:5000],
            'manufacturing_year': (cleaned.get('manufacturing_year') or '')[:255],
            'source_object_count': cleaned.get('source_object_count') or 1,
        }


ParserV2ObjectFormSet = forms.formset_factory(
    ParserV2ObjectForm,
    extra=0,
    can_delete=False,
)


def parser_v2_object_initial_from_payload(insured_objects):
    """Build initial data for ParserV2ObjectFormSet from parser payload."""
    initial = []
    for obj in insured_objects:
        initial.append({
            'brand': obj.get('brand') or '',
            'model': obj.get('model') or '',
            'condition': obj.get('condition') or '',
            'equipment_type': obj.get('equipment_type') or '',
            'power_or_capacity': obj.get('power_or_capacity') or '',
            'acquisition_cost_value': obj.get('acquisition_cost_value') or '',
            'acquisition_cost_currency': obj.get('acquisition_cost_currency') or '',
            'manufacturing_year': obj.get('year') or '',
            'vehicle_info': obj.get('description') or '',
            'source_object_count': obj.get('source_object_count') or 1,
            'skip': False,
        })
    return initial


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
    BRANCH_CHOICES = EDIT_BRANCH_CHOICES
    
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
    
    class Meta:
        model = InsuranceRequest
        fields = [
            'client_name', 'inn', 'insurance_type', 'insurance_period',
            'vehicle_info', 'dfa_number', 'branch', 'manager_name', 'deal_status', 'franchise_type',
            'has_installment', 'has_autostart', 'has_casco_ce', 'has_transportation',
            'transportation_departure', 'transportation_destination', 'transportation_days',
            'has_construction_work', 'manufacturing_year', 'asset_status', 'response_deadline', 'notes',
            # Структурированные поля объекта Parser V2
            'brand', 'model', 'condition', 'equipment_type', 'power_or_capacity',
            'acquisition_cost_value', 'acquisition_cost_currency', 'source_object_count',
            # Реквизиты страхователя Parser V2
            'legal_address', 'postal_address', 'business_activity', 'birth_date', 'submission_date',
            # Параметры сделки и страхования Parser V2
            'insured_party', 'insured_sum_type', 'guard_conditions',
            'property_location_right_holder', 'premium_frequency',
            # Дополнительные параметры КАСКО/спецтехника
            'key_completeness', 'pts_psm', 'creditor_bank', 'usage_purposes', 'telematics_complex',
            # Дополнительные параметры для страхования имущества
            'insurance_territory'
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
            'manager_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ФИО Менеджера',
                'maxlength': '255'
            }),
            'deal_status': forms.Select(
                choices=InsuranceRequest.DEAL_STATUS_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'franchise_type': forms.Select(
                choices=InsuranceRequest.FRANCHISE_TYPE_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'manufacturing_year': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Год выпуска предмета лизинга',
                'maxlength': '255'
            }),
            'asset_status': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Статус имущества предмета лизинга',
                'maxlength': '255'
            }),
            'brand': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Марка',
                'maxlength': '128'
            }),
            'model': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Модель',
                'maxlength': '255'
            }),
            'condition': forms.Select(
                choices=[('', '-- Не указано --')] + InsuranceRequest.OBJECT_CONDITION_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'equipment_type': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Тип/категория техники',
                'maxlength': '128'
            }),
            'power_or_capacity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Мощность/производительность',
                'maxlength': '64'
            }),
            'acquisition_cost_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Стоимость',
                'step': '0.01'
            }),
            'acquisition_cost_currency': forms.Select(
                choices=[('', '-- Не указано --')] + InsuranceRequest.ACQUISITION_COST_CURRENCY_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'source_object_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Введите дополнительные примечания к заявке...',
                'maxlength': '2000'
            }),
            'has_installment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_autostart': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_casco_ce': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_transportation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'transportation_departure': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: г. Москва, ул. Ленина, 1',
                'maxlength': '500',
            }),
            'transportation_destination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: г. Псков, пр. Энтузиастов, 5',
                'maxlength': '500',
            }),
            'transportation_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Дней',
            }),
            'has_construction_work': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'response_deadline': DateTimeLocalWidget(),
            'legal_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Юридический адрес'
            }),
            'postal_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Почтовый адрес'
            }),
            'business_activity': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Основной вид деятельности'
            }),
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'submission_date': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'insured_party': forms.Select(
                choices=[('', '-- Не указано --')] + InsuranceRequest.INSURED_PARTY_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'insured_sum_type': forms.Select(
                choices=[('', '-- Не указано --')] + InsuranceRequest.INSURED_SUM_TYPE_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'guard_conditions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Условия охраны/хранения'
            }),
            'property_location_right_holder': forms.Select(
                choices=[('', '-- Не указано --')] + InsuranceRequest.PROPERTY_LOCATION_RIGHT_HOLDER_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'premium_frequency': forms.Select(
                choices=[('', '-- Не указано --')] + InsuranceRequest.PREMIUM_FREQUENCY_CHOICES,
                attrs={'class': 'form-control'}
            ),
            # Дополнительные параметры КАСКО/спецтехника
            'key_completeness': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Комплектность ключей',
                'maxlength': '255'
            }),
            'pts_psm': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ПТС/ПСМ',
                'maxlength': '255'
            }),
            'creditor_bank': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Банк-кредитор',
                'maxlength': '255'
            }),
            'usage_purposes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Цели использования'
            }),
            'telematics_complex': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Телематический комплекс'
            }),
            # Дополнительные параметры для страхования имущества
            'insurance_territory': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Территория страхования'
            }),
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
            for field_name in ['has_installment', 'has_autostart', 'has_casco_ce', 'has_transportation', 'has_construction_work']:
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
    
    def clean_key_completeness(self):
        """Валидация комплектности ключей"""
        value = self.cleaned_data.get('key_completeness', '')
        if value and len(value) > 255:
            raise ValidationError('Комплектность ключей не должна превышать 255 символов')
        return value.strip() if value else value
    
    def clean_pts_psm(self):
        """Валидация ПТС/ПСМ"""
        value = self.cleaned_data.get('pts_psm', '')
        if value and len(value) > 255:
            raise ValidationError('ПТС/ПСМ не должно превышать 255 символов')
        return value.strip() if value else value
    
    def clean_creditor_bank(self):
        """Валидация банка-кредитора"""
        value = self.cleaned_data.get('creditor_bank', '')
        if value and len(value) > 255:
            raise ValidationError('Банк-кредитор не должен превышать 255 символов')
        return value.strip() if value else value
    
    def clean_usage_purposes(self):
        """Валидация целей использования"""
        value = self.cleaned_data.get('usage_purposes', '')
        if value:
            value = value.strip()
            if len(value) > 1000:
                raise ValidationError('Цели использования не должны превышать 1000 символов')
        return value
    
    def clean_telematics_complex(self):
        """Валидация телематического комплекса"""
        value = self.cleaned_data.get('telematics_complex', '')
        if value:
            value = value.strip()
            if len(value) > 1000:
                raise ValidationError('Телематический комплекс не должен превышать 1000 символов')
        return value
    
    def clean_insurance_territory(self):
        """Валидация территории страхования"""
        value = self.cleaned_data.get('insurance_territory', '')
        if value:
            value = value.strip()
            if len(value) > 1000:
                raise ValidationError('Территория страхования не должна превышать 1000 символов')
        return value
    
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
    """Форма для редактирования письма"""
    
    email_subject = forms.CharField(
        label='Тема письма',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    email_body = forms.CharField(
        label='Текст письма',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 15})
    )


class RequestStatusForm(forms.Form):
    """Форма для изменения статуса заявки"""
    
    status = forms.ChoiceField(
        choices=InsuranceRequest.STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'request-status-select'
        }),
        label='Статус заявки'
    )


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

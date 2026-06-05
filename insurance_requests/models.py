from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, Any
import json
import pytz


class InsuranceRequest(models.Model):
    """Модель страховой заявки"""
    
    STATUS_CHOICES = [
        ('uploaded', 'Загружено'),
        ('email_generated', 'Письмо сгенерировано'),
        ('emails_sent', 'Письма отправлены'),
    ]
    
    INSURANCE_TYPE_CHOICES = [
        ('КАСКО', 'КАСКО'),
        ('страхование спецтехники', 'страхование спецтехники'),
        ('страхование имущества', 'страхование имущества'),
        ('другое', 'другое'),
    ]
    
    INSURANCE_PERIOD_CHOICES = [
        ('1 год', '1 год'),
        ('на весь срок лизинга', 'на весь срок лизинга'),
    ]
    
    FRANCHISE_TYPE_CHOICES = [
        ('none', 'Без франшизы'),
        ('with_franchise', 'Только с франшизой'),
        ('both_variants', 'Оба варианта'),
    ]
    
    DEAL_STATUS_CHOICES = [
        ('new', 'Новая сделка'),
        ('prolongation', 'Пролонгация'),
    ]

    OBJECT_CONDITION_CHOICES = [
        ('new', 'Новое'),
        ('used', 'Б/у'),
    ]

    ACQUISITION_COST_CURRENCY_CHOICES = [
        ('RUB', 'Рубли'),
        ('USD', 'Доллары США'),
        ('EUR', 'Евро'),
    ]

    INSURED_PARTY_CHOICES = [
        ('lessor', 'Лизингодатель'),
        ('lessee', 'Лизингополучатель'),
    ]

    INSURED_SUM_TYPE_CHOICES = [
        ('aggregate', 'Агрегатная'),
        ('non_aggregate', 'Неагрегатная'),
    ]

    PROPERTY_LOCATION_RIGHT_HOLDER_CHOICES = [
        ('lessee_owner', 'Собственность лизингополучателя'),
        ('third_party_owner', 'Стороннее лицо'),
    ]

    PREMIUM_FREQUENCY_CHOICES = [
        ('single', 'Единовременно'),
        ('quarterly', 'Поквартально'),
        ('biannual', '2 раза в год'),
        ('annual', 'Ежегодно'),
    ]
    
    # Основные поля
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Создал', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded', verbose_name='Статус')
    
    # Данные из Excel файла
    client_name = models.CharField(max_length=255, verbose_name='Имя клиента')
    inn = models.CharField(max_length=12, verbose_name='ИНН клиента')
    insurance_type = models.CharField(
        max_length=100, 
        choices=INSURANCE_TYPE_CHOICES,
        default='КАСКО', 
        verbose_name='Тип страхования'
    )
    insurance_period = models.CharField(
        max_length=50, 
        choices=INSURANCE_PERIOD_CHOICES,
        blank=True,
        verbose_name='Срок страхования'
    )
    vehicle_info = models.TextField(blank=True, verbose_name='Информация о предмете лизинга')
    dfa_number = models.CharField(max_length=100, blank=True, verbose_name='Номер ДФА')
    branch = models.CharField(max_length=255, blank=True, verbose_name='Филиал')
    
    # Дополнительные параметры
    franchise_type = models.CharField(
        max_length=20,
        choices=FRANCHISE_TYPE_CHOICES,
        default='none',
        verbose_name='Тип франшизы'
    )
    has_installment = models.BooleanField(default=False, verbose_name='Требуется рассрочка')
    has_autostart = models.BooleanField(default=False, verbose_name='Есть автозапуск')
    has_casco_ce = models.BooleanField(default=False, verbose_name='КАСКО кат. C/E')
    has_transportation = models.BooleanField(default=False, verbose_name='Требуется перевозка')
    transportation_departure = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Пункт отправления (перевозка)',
    )
    transportation_destination = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Пункт назначения (перевозка)',
    )
    transportation_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Срок перевозки, дней',
    )
    has_construction_work = models.BooleanField(default=False, verbose_name='Требуется СМР')
    response_deadline = models.DateTimeField(null=True, blank=True, verbose_name='Срок ответа')
    
    # Сгенерированное письмо
    email_subject = models.CharField(max_length=255, blank=True, verbose_name='Тема письма')
    email_body = models.TextField(blank=True, verbose_name='Текст письма')
    
    # Дополнительные данные в JSON формате
    additional_data = models.JSONField(default=dict, blank=True, verbose_name='Дополнительные данные')

    # Денормализованный счётчик ручных правок оператора относительно
    # распознанного парсером (для бейджей в списке и аналитики без разбора
    # JSON). Заполняется при создании заявки из V2-превью; для V1 и
    # исторических заявок остаётся 0.
    manual_edits_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name='Ручных правок оператора',
        help_text='Сколько полей оператор изменил относительно распознанного из Excel'
    )

    # Денормализованная уверенность парсера (0..1) на момент создания —
    # для аналитики динамики качества распознавания без разбора JSON.
    # NULL для V1 и исторических заявок.
    parser_confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Уверенность парсера',
        help_text='Уверенность распознавания парсером V2 на момент создания (0..1)'
    )
    
    # Примечание
    notes = models.TextField(blank=True, verbose_name='Примечание')
    
    # Дополнительные параметры КАСКО/спецтехника
    key_completeness = models.CharField(
        max_length=255, 
        blank=True, 
        verbose_name='Комплектность ключей'
    )
    pts_psm = models.CharField(
        max_length=255, 
        blank=True, 
        verbose_name='ПТС/ПСМ'
    )
    creditor_bank = models.CharField(
        max_length=255, 
        blank=True, 
        verbose_name='Банк-кредитор'
    )
    usage_purposes = models.TextField(
        blank=True, 
        verbose_name='Цели использования'
    )
    telematics_complex = models.TextField(
        blank=True, 
        verbose_name='Телематический комплекс'
    )
    
    # Дополнительные параметры для страхования имущества
    insurance_territory = models.TextField(
        blank=True, 
        verbose_name='Территория страхования'
    )
    
    # Год выпуска предмета лизинга (для КАСКО/спецтехника)
    manufacturing_year = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Год выпуска'
    )

    # Статус имущества предмета лизинга (для КАСКО/спецтехника)
    asset_status = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Статус имущества'
    )
    
    # ФИО Менеджера
    manager_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='ФИО Менеджера'
    )
    
    # Статус сделки
    deal_status = models.CharField(
        max_length=20,
        choices=DEAL_STATUS_CHOICES,
        default='new',
        verbose_name='Статус сделки'
    )

    # Партия (для V2-splitting: один Excel с N объектами → N заявок-сестёр).
    # V1 и исторические заявки оставляют эти поля пустыми и отображаются как раньше.
    source_batch_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='ID партии',
        help_text='Общий идентификатор партии для заявок, созданных из одного Excel-файла'
    )
    item_no = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Номер объекта в партии'
    )
    item_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Всего объектов в партии'
    )

    # Поля объекта страхования (для V2; V1 их не заполняет — данные слипшейся
    # строкой остаются в vehicle_info / manufacturing_year / asset_status).
    brand = models.CharField(
        max_length=128, blank=True, null=True, verbose_name='Марка'
    )
    model = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Модель'
    )
    condition = models.CharField(
        max_length=10,
        choices=OBJECT_CONDITION_CHOICES,
        blank=True,
        null=True,
        verbose_name='Состояние объекта',
    )
    equipment_type = models.CharField(
        max_length=128, blank=True, null=True, verbose_name='Тип/категория техники'
    )
    power_or_capacity = models.CharField(
        max_length=64, blank=True, null=True, verbose_name='Мощность/производительность'
    )
    acquisition_cost_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Стоимость на момент приобретения',
    )
    acquisition_cost_currency = models.CharField(
        max_length=3,
        choices=ACQUISITION_COST_CURRENCY_CHOICES,
        blank=True,
        null=True,
        verbose_name='Валюта стоимости',
    )
    object_description = models.TextField(
        blank=True,
        verbose_name='Описание объекта (исходное)',
    )
    source_object_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name='Количество одинаковых объектов',
        help_text='Сколько полностью одинаковых строк объекта из исходной Excel-заявки представляет эта заявка',
    )

    # Реквизиты страхователя (для V2; V1 их не заполняет — данные приходят
    # из шапки лизинговой заявки). ОГРН/КПП сюда НЕ добавляем — в Excel заявки
    # они системно отсутствуют, см. docs/improvement_plans/json_schema_v2.md.
    legal_address = models.TextField(
        blank=True, null=True, verbose_name='Юридический адрес'
    )
    postal_address = models.TextField(
        blank=True, null=True, verbose_name='Почтовый адрес'
    )
    business_activity = models.TextField(
        blank=True, null=True, verbose_name='Основной вид деятельности'
    )
    birth_date = models.DateField(
        blank=True, null=True, verbose_name='Дата рождения (для ИП)'
    )
    submission_date = models.DateField(
        blank=True, null=True, verbose_name='Дата подачи заявки'
    )

    # Параметры сделки и страхования (для V2; V1 их не заполняет).
    # Поля contract_*, period_*, indemnity_basis из исходного плана не добавлены:
    # в Excel заявки от лизинга конкретных дат лизинга/периода страхования нет,
    # а indemnity_basis отсутствует (0/30 hits в мини-аудите).
    # Подробнее в docs/improvement_plans/json_schema_v2.md.
    insured_party = models.CharField(
        max_length=10,
        choices=INSURED_PARTY_CHOICES,
        blank=True,
        null=True,
        verbose_name='Страхователь',
    )
    insured_sum_type = models.CharField(
        max_length=15,
        choices=INSURED_SUM_TYPE_CHOICES,
        blank=True,
        null=True,
        verbose_name='Тип страховой суммы',
    )
    guard_conditions = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия охраны/хранения',
    )
    property_location_right_holder = models.CharField(
        max_length=20,
        choices=PROPERTY_LOCATION_RIGHT_HOLDER_CHOICES,
        blank=True,
        null=True,
        verbose_name='Правообладатель места расположения',
        help_text='Для страхования имущества',
    )
    premium_frequency = models.CharField(
        max_length=10,
        choices=PREMIUM_FREQUENCY_CHOICES,
        blank=True,
        null=True,
        verbose_name='Частота уплаты премии',
    )

    class Meta:
        verbose_name = 'Страховая заявка'
        verbose_name_plural = 'Страховые заявки'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def get_display_name(self):
        """Возвращает отображаемое название заявки с использованием номера ДФА.

        Для заявок партии (item_count > 1) добавляет суффикс «объект K из N»,
        чтобы оператор различал сёстры одной загрузки.
        """
        if self.dfa_number and self.dfa_number.strip() and self.dfa_number != 'Номер ДФА не указан':
            base = self.dfa_number
        else:
            base = f"#{self.id}"
        if self.item_count and self.item_count > 1 and self.item_no:
            return f"{base} / объект {self.item_no} из {self.item_count}"
        return base

    @property
    def parser_v2_data(self):
        """Возвращает технический блок Parser V2 из additional_data."""
        if isinstance(self.additional_data, dict):
            parser_data = self.additional_data.get('parser_v2')
            if isinstance(parser_data, dict):
                return parser_data
        return {}

    @property
    def is_parser_v2(self):
        """True для заявок, созданных новым парсером."""
        if not isinstance(self.additional_data, dict):
            return False
        return (
            self.additional_data.get('parser_version') == 'v2'
            or bool(self.additional_data.get('parser_v2'))
        )

    @property
    def parser_v2_warning_count(self):
        warnings = self.parser_v2_data.get('warnings', [])
        return len(warnings) if isinstance(warnings, list) else 0

    @property
    def parser_v2_confidence_percent(self):
        confidence = self.parser_v2_data.get('confidence')
        try:
            return int(round(float(confidence) * 100))
        except (TypeError, ValueError):
            return None

    @property
    def parser_v2_source_file_name(self):
        return self.parser_v2_data.get('source_file_name', '')

    @property
    def parser_v2_tracking(self):
        """Блок ручных правок оператора (tracking) из parser_v2."""
        tracking = self.parser_v2_data.get('tracking')
        return tracking if isinstance(tracking, dict) else {}

    @property
    def parser_v2_field_edits(self):
        """Правки общих полей заявки (одинаковы для всех сестёр партии)."""
        edits = self.parser_v2_tracking.get('field_edits')
        return edits if isinstance(edits, list) else []

    @property
    def parser_v2_object_edits(self):
        """Правки объектных полей именно этой заявки (по её позиции в партии).

        object_edits хранится одинаково на каждой сестре как список по
        позициям; позиция = item_no (1-based). Для одиночных заявок
        item_no пуст — берётся первый (единственный) объект.
        """
        all_object_edits = self.parser_v2_tracking.get('object_edits')
        if not isinstance(all_object_edits, list) or not all_object_edits:
            return []
        position = (self.item_no or 1) - 1
        if 0 <= position < len(all_object_edits):
            edits = all_object_edits[position]
            return edits if isinstance(edits, list) else []
        return []

    @property
    def parser_v2_all_edits(self):
        """Все ручные правки этой заявки: общие + объектные."""
        return list(self.parser_v2_field_edits) + list(self.parser_v2_object_edits)

    @property
    def parser_v2_edit_count(self):
        return len(self.parser_v2_field_edits) + len(self.parser_v2_object_edits)

    @property
    def parser_v2_has_original_snapshot(self):
        """True, если сохранён полный снимок распознанных данных («до»).

        Заявки, созданные до внедрения трекинга, его не имеют — страница
        сравнения для них показывает соответствующее уведомление.
        """
        return bool(self.parser_v2_data.get('original_data'))

    @property
    def parser_v2_object_original(self):
        """«Before»-снимок объекта именно этой заявки (по позиции в партии)."""
        originals = self.parser_v2_tracking.get('object_originals')
        if not isinstance(originals, list) or not originals:
            return {}
        position = (self.item_no or 1) - 1
        if 0 <= position < len(originals):
            obj = originals[position]
            return obj if isinstance(obj, dict) else {}
        return {}

    def parser_v2_scalar_comparison(self):
        """Строки сравнения общих полей «распознано / итог» для страницы."""
        from .edit_tracking import scalar_comparison_rows
        original = self.parser_v2_data.get('original_data') or {}
        return scalar_comparison_rows(
            original, self.parser_v2_field_edits, bool(self.parser_v2_object_original)
        )

    def parser_v2_object_comparison(self):
        """Строки сравнения объектных полей этой заявки «распознано / итог»."""
        from .edit_tracking import object_comparison_rows
        original = self.parser_v2_object_original
        if not original:
            return []
        return object_comparison_rows(original, self.parser_v2_object_edits)

    @property
    def list_premium_frequency_display(self):
        """List view only: show within-year frequencies, hide single/annual noise."""
        if self.premium_frequency in {'quarterly', 'biannual'}:
            return self.get_premium_frequency_display()
        return ''

    @property
    def list_has_installment_badge(self):
        """Legacy list badge: only for old rows without an explicit frequency."""
        return bool(self.has_installment and not self.premium_frequency)

    @property
    def has_structured_object_data(self):
        return any([
            self.brand,
            self.model,
            self.condition,
            self.equipment_type,
            self.power_or_capacity,
            self.acquisition_cost_value,
            self.acquisition_cost_currency,
        ])

    @property
    def object_display_name(self):
        parts = [part.strip() for part in [self.brand or '', self.model or ''] if part and part.strip()]
        if parts:
            return ' '.join(parts)
        return self.vehicle_info or ''

    @property
    def condition_label(self):
        if self.condition:
            return self.get_condition_display()
        return (self.asset_status or '').strip()

    @property
    def is_new_object(self):
        if self.condition:
            return self.condition == 'new'
        return (self.asset_status or '').strip().lower() == 'новое'

    @property
    def object_summary(self):
        has_object_source = self.has_structured_object_data or bool((self.object_description or '').strip())
        if has_object_source:
            base_name = ' '.join(
                part.strip()
                for part in [self.brand or '', self.model or '']
                if part and part.strip()
            )
            if not base_name:
                base_name = (self.object_description or '').strip()

            parts = []
            if base_name:
                parts.append(base_name)

            year = (self.manufacturing_year or '').strip()
            if year:
                parts.append(f'{year} г.')

            condition_label = self.condition_label
            if condition_label:
                parts.append(condition_label)

            acquisition_cost = self.acquisition_cost_display
            if acquisition_cost:
                parts.append(acquisition_cost)

            if (self.source_object_count or 0) > 1:
                parts.append(f'×{self.source_object_count}')

            summary = ', '.join(part for part in parts if part).strip()
            if summary:
                return summary[:1000]

        fallback = (self.vehicle_info or '').strip()
        if fallback:
            return fallback[:1000]

        fallback = (self.object_description or '').strip()
        if fallback:
            return fallback[:1000]

        return ''

    @property
    def acquisition_cost_display(self):
        if self.acquisition_cost_value is None:
            return ''
        value = self.acquisition_cost_value
        if not hasattr(value, 'to_integral_value'):
            try:
                value = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return ''
        if value == value.to_integral_value():
            amount = f"{value:,.0f}".replace(",", " ")
        else:
            amount = f"{value:,.2f}".replace(",", " ")
        if self.acquisition_cost_currency:
            return f"{amount} {self.acquisition_cost_currency}"
        return amount
    

    
    def __str__(self):
        return f"{self.get_display_name()} - {self.client_name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        """Override save method to set automatic response deadline in Moscow timezone."""
        if not self.response_deadline:
            # Получаем текущее время в московском часовом поясе
            moscow_tz = pytz.timezone('Europe/Moscow')
            moscow_now = timezone.now().astimezone(moscow_tz)
            self.response_deadline = moscow_now + timedelta(hours=3)
        
        super().save(*args, **kwargs)
    
    def get_moscow_time(self, field_name):
        """Возвращает время поля в московском часовом поясе"""
        try:
            field_value = getattr(self, field_name)
            if field_value:
                moscow_tz = pytz.timezone('Europe/Moscow')
                return field_value.astimezone(moscow_tz)
        except AttributeError:
            pass
        return None
    
    @property
    def created_at_moscow(self):
        """Возвращает время создания в московском часовом поясе"""
        return self.get_moscow_time('created_at')
    
    @property
    def response_deadline_moscow(self):
        """Возвращает срок ответа в московском часовом поясе"""
        return self.get_moscow_time('response_deadline')
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует модель в словарь для использования в шаблонах с московским временем"""
        moscow_deadline = self.get_moscow_time('response_deadline')
        return {
            'client_name': self.client_name,
            'inn': self.inn,
            'insurance_type': self.insurance_type,
            'insurance_period': self.insurance_period or 'не указан',
            'vehicle_info': self.vehicle_info,
            'object_display_name': self.object_display_name,
            'object_summary': self.object_summary,
            'object_description': self.object_description,
            'dfa_number': self.dfa_number,
            'branch': self.branch,
            'franchise_type': self.franchise_type,
            'has_installment': self.has_installment,
            'has_autostart': self.has_autostart,
            'has_casco_ce': self.has_casco_ce,
            'has_transportation': self.has_transportation,
            'transportation_departure': self.transportation_departure or '',
            'transportation_destination': self.transportation_destination or '',
            'transportation_days': self.transportation_days,
            'has_construction_work': self.has_construction_work,
            'notes': self.notes,
            'response_deadline': moscow_deadline.strftime('%H:%M %d.%m.%Y') if moscow_deadline else None,
            # Дополнительные параметры КАСКО/спецтехника
            'key_completeness': self.key_completeness or 'не указано',
            'pts_psm': self.pts_psm or 'не указано',
            'creditor_bank': self.creditor_bank or 'не указано',
            'usage_purposes': self.usage_purposes or 'не указано',
            'telematics_complex': self.telematics_complex or 'не указано',
            # Дополнительные параметры для страхования имущества
            'insurance_territory': self.insurance_territory or 'не указано',
            # Год выпуска предмета лизинга
            'manufacturing_year': self.manufacturing_year or 'не указан',
            # Статус имущества предмета лизинга
            'asset_status': self.asset_status or 'не указан',
            'condition_label': self.condition_label or 'не указан',
            # ФИО Менеджера
            'manager_name': self.manager_name or 'не указано',
            # Статус сделки
            'deal_status': self.get_deal_status_display(),
        }
    
    def can_create_summary(self) -> bool:
        """Проверяет, можно ли создать свод для этой заявки"""
        return (
            self.status in ['emails_sent'] and
            not hasattr(self, 'summary')
        )
    
    def get_summary_status(self) -> str:
        """Возвращает статус свода или информацию о его отсутствии"""
        if hasattr(self, 'summary'):
            return self.summary.get_status_display()
        elif self.status == 'emails_sent':
            return 'Ожидает создания свода'
        else:
            return 'Свод недоступен'


class RequestAttachment(models.Model):
    """Модель вложений к заявке"""
    
    request = models.ForeignKey(InsuranceRequest, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/%d/', verbose_name='Файл')
    original_filename = models.CharField(max_length=255, verbose_name='Оригинальное имя файла')
    file_type = models.CharField(max_length=50, verbose_name='Тип файла')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')
    
    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'
    
    def __str__(self):
        return f"{self.original_filename} (Заявка {self.request.get_display_name()})"


class RequestFieldEdit(models.Model):
    """Одна ручная правка оператора относительно распознанного парсером.

    Нормализованный источник для аналитики качества парсера (какие поля
    операторы правят чаще всего, по филиалам/операторам, динамика). Строки
    создаются пакетно при сохранении заявки из V2-превью. Общие (scope=
    'common') правки записываются один раз на партию (к первой заявке),
    объектные (scope='object') — к своей заявке-сестре.
    """

    SCOPE_CHOICES = [
        ('common', 'Общее поле'),
        ('object', 'Поле объекта'),
    ]
    EDIT_TYPE_CHOICES = [
        ('filled', 'Дозаполнено'),
        ('cleared', 'Очищено'),
        ('changed', 'Исправлено'),
    ]

    request = models.ForeignKey(
        InsuranceRequest,
        on_delete=models.CASCADE,
        related_name='field_edits',
        verbose_name='Заявка',
    )
    scope = models.CharField(
        max_length=10, choices=SCOPE_CHOICES, default='common',
        verbose_name='Область поля',
    )
    field_name = models.CharField(max_length=100, db_index=True, verbose_name='Поле')
    field_label = models.CharField(max_length=255, verbose_name='Подпись поля')
    original_value = models.TextField(blank=True, verbose_name='Распознано из Excel')
    modified_value = models.TextField(blank=True, verbose_name='Внёс оператор')
    edit_type = models.CharField(
        max_length=10, choices=EDIT_TYPE_CHOICES, default='changed',
        db_index=True, verbose_name='Тип правки',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата правки')

    class Meta:
        verbose_name = 'Ручная правка поля'
        verbose_name_plural = 'Ручные правки полей'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['field_name', 'edit_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.field_label}: {self.original_value!r} → {self.modified_value!r}"

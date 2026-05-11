from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
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
    has_franchise = models.BooleanField(default=False, verbose_name='Требуется франшиза')
    has_installment = models.BooleanField(default=False, verbose_name='Требуется рассрочка')
    has_autostart = models.BooleanField(default=False, verbose_name='Есть автозапуск')
    has_casco_ce = models.BooleanField(default=False, verbose_name='КАСКО кат. C/E')
    has_transportation = models.BooleanField(default=False, verbose_name='Требуется перевозка')
    has_construction_work = models.BooleanField(default=False, verbose_name='Требуется СМР')
    response_deadline = models.DateTimeField(null=True, blank=True, verbose_name='Срок ответа')
    
    # Сгенерированное письмо
    email_subject = models.CharField(max_length=255, blank=True, verbose_name='Тема письма')
    email_body = models.TextField(blank=True, verbose_name='Текст письма')
    
    # Дополнительные данные в JSON формате
    additional_data = models.JSONField(default=dict, blank=True, verbose_name='Дополнительные данные')
    
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
    
    class Meta:
        verbose_name = 'Страховая заявка'
        verbose_name_plural = 'Страховые заявки'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def get_display_name(self):
        """Возвращает отображаемое название заявки с использованием номера ДФА"""
        if self.dfa_number and self.dfa_number.strip() and self.dfa_number != 'Номер ДФА не указан':
            return f"{self.dfa_number}"
        return f"#{self.id}"
    
    @property
    def insurance_objects_for_display(self):
        """
        Возвращает структурированные объекты страхования для интерфейса.

        Для старых заявок без связанных объектов строит один объект из legacy-полей,
        чтобы существующие данные оставались доступными в прежнем формате.
        """
        related_objects = []
        if self.pk:
            related_objects = list(self.insurance_objects.all())

        if related_objects:
            return [
                {
                    'position': insurance_object.position,
                    'description': insurance_object.description,
                    'manufacturing_year': insurance_object.manufacturing_year,
                    'asset_status': insurance_object.asset_status,
                    'source_row': insurance_object.source_row,
                    'is_legacy': False,
                }
                for insurance_object in related_objects
            ]

        has_legacy_object = any([
            self.vehicle_info and self.vehicle_info.strip(),
            self.manufacturing_year and self.manufacturing_year.strip(),
            self.asset_status and self.asset_status.strip(),
        ])
        if not has_legacy_object:
            return []

        return [
            {
                'position': 1,
                'description': self.vehicle_info,
                'manufacturing_year': self.manufacturing_year,
                'asset_status': self.asset_status,
                'source_row': None,
                'is_legacy': True,
            }
        ]

    @property
    def insurance_objects_count_for_display(self):
        """Количество объектов страхования с учетом fallback для старых заявок."""
        return len(self.insurance_objects_for_display)

    @property
    def has_multiple_insurance_objects(self):
        """Показывает, содержит ли заявка несколько объектов страхования."""
        return self.insurance_objects_count_for_display > 1

    @property
    def primary_insurance_object_description(self):
        """Описание первого объекта для компактных списков."""
        objects = self.insurance_objects_for_display
        if objects:
            return objects[0].get('description') or ''
        return ''

    def sync_legacy_object_fields_from_related(self, save=True):
        """
        Обновляет legacy-поля из связанных объектов страхования.

        Старые поля остаются источником совместимости для писем, сводов,
        экспортов и уже существующего кода.
        """
        if not self.pk:
            return

        objects = list(self.insurance_objects.all())
        if not objects:
            return

        self.vehicle_info = '; '.join(
            obj.description.strip()
            for obj in objects
            if obj.description and obj.description.strip()
        )
        self.manufacturing_year = '; '.join(
            obj.manufacturing_year.strip()
            for obj in objects
            if obj.manufacturing_year and obj.manufacturing_year.strip()
        )
        self.asset_status = '; '.join(
            obj.asset_status.strip()
            for obj in objects
            if obj.asset_status and obj.asset_status.strip()
        )

        if save:
            self.save(update_fields=['vehicle_info', 'manufacturing_year', 'asset_status', 'updated_at'])

    def __str__(self):
        return f"{self.get_display_name()} - {self.client_name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        """Override save method to set automatic response deadline in Moscow timezone and update has_franchise"""
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
        display_vehicle_info = self.vehicle_info or self.primary_insurance_object_description
        return {
            'client_name': self.client_name,
            'inn': self.inn,
            'insurance_type': self.insurance_type,
            'insurance_period': self.insurance_period or 'не указан',
            'vehicle_info': display_vehicle_info,
            'insurance_objects': self.insurance_objects_for_display,
            'dfa_number': self.dfa_number,
            'branch': self.branch,
            'franchise_type': self.franchise_type,
            'has_franchise': self.has_franchise,
            'has_installment': self.has_installment,
            'has_autostart': self.has_autostart,
            'has_casco_ce': self.has_casco_ce,
            'has_transportation': self.has_transportation,
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


class InsuranceRequestObject(models.Model):
    """Структурированный объект страхования внутри одной заявки."""

    request = models.ForeignKey(
        InsuranceRequest,
        on_delete=models.CASCADE,
        related_name='insurance_objects',
        verbose_name='Заявка'
    )
    position = models.PositiveIntegerField(default=1, verbose_name='Порядок')
    description = models.TextField(verbose_name='Описание объекта страхования')
    manufacturing_year = models.CharField(max_length=255, blank=True, verbose_name='Год выпуска')
    asset_status = models.CharField(max_length=255, blank=True, verbose_name='Статус имущества')
    source_row = models.PositiveIntegerField(null=True, blank=True, verbose_name='Строка источника')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        verbose_name = 'Объект страхования'
        verbose_name_plural = 'Объекты страхования'
        ordering = ['position', 'id']
        indexes = [
            models.Index(fields=['request', 'position']),
        ]

    def __str__(self):
        return f"{self.position}. {self.description}"


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

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
        ('uploaded', 'Загружена'),
        ('email_generated', 'Письмо сгенерировано'),
        ('email_sent', 'Письмо отправлено'),
        ('response_received', 'Получен ответ'),
        ('report_generated', 'Отчет сгенерирован'),
        ('completed', 'Завершена'),
        ('error', 'Ошибка'),
    ]
    
    INSURANCE_TYPE_CHOICES = [
        ('КАСКО', 'КАСКО'),
        ('страхование спецтехники', 'страхование спецтехники'),
        ('страхование имущества', 'страхование имущества'),
        ('другое', 'другое'),
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
    insurance_period = models.CharField(max_length=200, verbose_name='Срок страхования')
    insurance_start_date = models.DateField(null=True, blank=True, verbose_name='Дата начала страхования')
    insurance_end_date = models.DateField(null=True, blank=True, verbose_name='Дата окончания страхования')
    vehicle_info = models.TextField(blank=True, verbose_name='Информация о предмете лизинга')
    dfa_number = models.CharField(max_length=100, blank=True, verbose_name='Номер ДФА')
    branch = models.CharField(max_length=255, blank=True, verbose_name='Филиал')
    
    # Дополнительные параметры
    has_franchise = models.BooleanField(default=False, verbose_name='Требуется франшиза')
    has_installment = models.BooleanField(default=False, verbose_name='Требуется рассрочка')
    has_autostart = models.BooleanField(default=False, verbose_name='Есть автозапуск')
    has_casco_ce = models.BooleanField(default=False, verbose_name='КАСКО кат. C/E')
    response_deadline = models.DateTimeField(null=True, blank=True, verbose_name='Срок ответа')
    
    # Сгенерированное письмо
    email_subject = models.CharField(max_length=255, blank=True, verbose_name='Тема письма')
    email_body = models.TextField(blank=True, verbose_name='Текст письма')
    email_sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Время отправки')
    
    # Дополнительные данные в JSON формате
    additional_data = models.JSONField(default=dict, blank=True, verbose_name='Дополнительные данные')
    
    # Примечание
    notes = models.TextField(blank=True, verbose_name='Примечание')
    
    class Meta:
        verbose_name = 'Страховая заявка'
        verbose_name_plural = 'Страховые заявки'
        ordering = ['-created_at']
    
    def get_display_name(self):
        """Возвращает отображаемое название заявки с использованием номера ДФА"""
        if self.dfa_number and self.dfa_number.strip() and self.dfa_number != 'Номер ДФА не указан':
            return f"Заявка {self.dfa_number}"
        return f"Заявка #{self.id}"
    
    @property
    def insurance_period_formatted(self):
        """
        Свойство для обратной совместимости - форматирует две даты как "с [date1] по [date2]"
        Если новые поля заполнены, использует их, иначе возвращает старое поле
        """
        if self.insurance_start_date and self.insurance_end_date:
            return f"с {self.insurance_start_date.strftime('%d.%m.%Y')} по {self.insurance_end_date.strftime('%d.%m.%Y')}"
        elif self.insurance_period:
            return self.insurance_period
        else:
            return "Период не указан"
    
    def __str__(self):
        return f"{self.get_display_name()} - {self.client_name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        """Override save method to set automatic response deadline in Moscow timezone"""
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
            'insurance_period': self.insurance_period_formatted,
            'insurance_start_date': self.insurance_start_date,
            'insurance_end_date': self.insurance_end_date,
            'vehicle_info': self.vehicle_info,
            'dfa_number': self.dfa_number,
            'branch': self.branch,
            'has_franchise': self.has_franchise,
            'has_installment': self.has_installment,
            'has_autostart': self.has_autostart,
            'has_casco_ce': self.has_casco_ce,
            'notes': self.notes,
            'response_deadline': moscow_deadline.strftime('%H:%M %d.%m.%Y') if moscow_deadline else None,
        }
    
    def can_create_summary(self) -> bool:
        """Проверяет, можно ли создать свод для этой заявки"""
        return (
            self.status in ['email_sent', 'response_received'] and
            not hasattr(self, 'summary')
        )
    
    def get_summary_status(self) -> str:
        """Возвращает статус свода или информацию о его отсутствии"""
        if hasattr(self, 'summary'):
            return self.summary.get_status_display()
        elif self.status == 'email_sent':
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
        return f"{self.original_filename} (Заявка #{self.request.id})"


class InsuranceResponse(models.Model):
    """Модель ответа от страховой компании"""
    
    request = models.ForeignKey(InsuranceRequest, on_delete=models.CASCADE, related_name='responses')
    company_name = models.CharField(max_length=255, verbose_name='Название компании')
    company_email = models.EmailField(verbose_name='Email компании')
    
    # Данные ответа
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата получения')
    email_subject = models.CharField(max_length=255, verbose_name='Тема письма')
    email_body = models.TextField(verbose_name='Текст письма')
    
    # Извлеченные данные
    insurance_sum = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name='Страховая сумма')
    insurance_premium = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name='Страховая премия')
    
    # Дополнительные данные в JSON
    parsed_data = models.JSONField(default=dict, blank=True, verbose_name='Распарсенные данные')
    
    class Meta:
        verbose_name = 'Ответ страховой компании'
        verbose_name_plural = 'Ответы страховых компаний'
        ordering = ['-received_at']
    
    def __str__(self):
        return f"Ответ от {self.company_name} на заявку #{self.request.id}"


class ResponseAttachment(models.Model):
    """Модель вложений к ответу"""
    
    response = models.ForeignKey(InsuranceResponse, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='response_attachments/%Y/%m/%d/', verbose_name='Файл')
    original_filename = models.CharField(max_length=255, verbose_name='Оригинальное имя файла')
    file_type = models.CharField(max_length=50, verbose_name='Тип файла')
    
    class Meta:
        verbose_name = 'Вложение к ответу'
        verbose_name_plural = 'Вложения к ответам'
    
    def __str__(self):
        return f"{self.original_filename} (Ответ от {self.response.company_name})"

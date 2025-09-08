from django.db import models
from django.contrib.auth.models import User
from insurance_requests.models import InsuranceRequest
from decimal import Decimal
from core.query_optimization import OptimizedQueryMixin


class InsuranceSummary(models.Model, OptimizedQueryMixin):
    """Модель свода предложений по заявке"""
    
    STATUS_CHOICES = [
        ('collecting', 'Сбор предложений'),
        ('ready', 'Готов к отправке'),
        ('sent', 'Отправлен клиенту'),
        ('completed', 'Завершен'),
    ]
    
    # Связь с заявкой
    request = models.OneToOneField(
        InsuranceRequest, 
        on_delete=models.CASCADE, 
        related_name='summary',
        verbose_name='Заявка'
    )
    
    # Основные поля
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='collecting', verbose_name='Статус')
    
    # Сводная информация
    total_offers = models.IntegerField(default=0, verbose_name='Количество предложений')
    best_premium = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name='Лучшая премия')
    best_company = models.CharField(max_length=255, blank=True, verbose_name='Лучшая компания')
    
    # Файл свода
    summary_file = models.FileField(
        upload_to='summaries/%Y/%m/%d/', 
        null=True, 
        blank=True, 
        verbose_name='Файл свода'
    )
    
    # Отправка клиенту
    sent_to_client_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлен клиенту')
    client_email = models.EmailField(blank=True, verbose_name='Email клиента')
    
    class Meta:
        verbose_name = 'Свод предложений'
        verbose_name_plural = 'Своды предложений'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Свод по заявке #{self.request.id} - {self.request.client_name}"
    
    def calculate_best_offer(self):
        """Вычисляет лучшее предложение"""
        offers = self.offers.filter(is_valid=True)
        if offers.exists():
            best_offer = offers.order_by('insurance_premium').first()
            self.best_premium = best_offer.insurance_premium
            self.best_company = best_offer.company_name
            self.total_offers = offers.count()
            self.save()
            return best_offer
        return None


class InsuranceOffer(models.Model):
    """Модель предложения от страховой компании"""
    
    # Связь со сводом
    summary = models.ForeignKey(
        InsuranceSummary, 
        on_delete=models.CASCADE, 
        related_name='offers',
        verbose_name='Свод'
    )
    
    # Информация о компании
    company_name = models.CharField(max_length=255, verbose_name='Название компании')
    company_email = models.EmailField(verbose_name='Email компании')
    
    # Данные предложения
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата получения')
    insurance_sum = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Страховая сумма')
    insurance_premium = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Страховая премия')
    
    # Дополнительные условия
    franchise_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        verbose_name='Размер франшизы'
    )
    installment_available = models.BooleanField(default=False, verbose_name='Рассрочка доступна')
    installment_months = models.IntegerField(null=True, blank=True, verbose_name='Количество месяцев рассрочки')
    
    # Валидность предложения
    is_valid = models.BooleanField(default=True, verbose_name='Действительное предложение')
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name='Действительно до')
    
    # Дополнительная информация
    notes = models.TextField(blank=True, verbose_name='Примечания')
    original_email_subject = models.CharField(max_length=255, blank=True, verbose_name='Тема письма')
    
    # Вложения
    attachment_file = models.FileField(
        upload_to='offers/%Y/%m/%d/', 
        null=True, 
        blank=True, 
        verbose_name='Файл предложения'
    )
    
    class Meta:
        verbose_name = 'Предложение страховщика'
        verbose_name_plural = 'Предложения страховщиков'
        ordering = ['insurance_premium', '-received_at']
        unique_together = ['summary', 'company_name']  # Одно предложение от компании
    
    def __str__(self):
        return f"{self.company_name}: {self.insurance_premium} ₽"
    
    @property
    def premium_per_month(self):
        """Премия в месяц при рассрочке"""
        if self.installment_available and self.installment_months:
            return self.insurance_premium / self.installment_months
        return self.insurance_premium


class SummaryTemplate(models.Model):
    """Модель шаблона для генерации сводов"""
    
    name = models.CharField(max_length=255, verbose_name='Название шаблона')
    description = models.TextField(blank=True, verbose_name='Описание')
    
    # Шаблон Excel файла
    template_file = models.FileField(
        upload_to='summary_templates/', 
        verbose_name='Файл шаблона'
    )
    
    # Настройки шаблона
    is_active = models.BooleanField(default=True, verbose_name='Активный')
    is_default = models.BooleanField(default=False, verbose_name='По умолчанию')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    
    class Meta:
        verbose_name = 'Шаблон свода'
        verbose_name_plural = 'Шаблоны сводов'
        ordering = ['-is_default', 'name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Если этот шаблон устанавливается как default, убираем флаг у других
        if self.is_default:
            SummaryTemplate.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

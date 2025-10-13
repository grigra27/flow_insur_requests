from django.db import models
from django.contrib.auth.models import User
from insurance_requests.models import InsuranceRequest
from decimal import Decimal


class InsuranceSummary(models.Model):
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
        """Вычисляет лучшее предложение с учетом многолетних данных"""
        offers = self.offers.filter(is_valid=True)
        if offers.exists():
            # Для многолетних предложений ищем лучшее по эффективной премии с франшизой
            best_offer = min(offers, key=lambda x: x.effective_premium_with_franchise or float('inf'))
            self.best_premium = best_offer.effective_premium_with_franchise or best_offer.insurance_premium
            self.best_company = f"{best_offer.company_name} ({best_offer.insurance_year})"
            self.total_offers = offers.count()
            self.save()
            return best_offer
        return None
    
    def get_offers_by_year(self, year='1 год'):
        """Получает предложения для конкретного года страхования"""
        return self.offers.filter(insurance_year=year, is_valid=True)
    
    def get_companies_with_years(self):
        """Возвращает словарь компаний с их предложениями по годам"""
        companies = {}
        for offer in self.offers.filter(is_valid=True):
            if offer.company_name not in companies:
                companies[offer.company_name] = {}
            companies[offer.company_name][offer.insurance_year] = offer
        return companies


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
    company_email = models.EmailField(blank=True, verbose_name='Email компании')
    
    # Данные предложения
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата получения')
    insurance_sum = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Страховая сумма')
    insurance_premium = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Страховая премия')
    
    # Новые поля для многолетних предложений
    insurance_year = models.CharField(
        max_length=10, 
        default='1 год',
        verbose_name='Год страхования',
        help_text='Например: "1 год", "2 год", "3 год"'
    )
    yearly_premium_with_franchise = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name='Премия с франшизой'
    )
    yearly_premium_without_franchise = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        null=True, 
        blank=True, 
        verbose_name='Премия без франшизы'
    )
    franchise_amount_variant1 = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        null=True, 
        blank=True,
        verbose_name='Франшиза (вариант 1)'
    )
    franchise_amount_variant2 = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        null=True, 
        blank=True,
        verbose_name='Франшиза (вариант 2)'
    )
    
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
        unique_together = ['summary', 'company_name', 'insurance_year']  # Одно предложение от компании на год
    
    def __str__(self):
        return f"{self.company_name} ({self.insurance_year}): {self.insurance_premium} ₽"
    
    @property
    def premium_per_month(self):
        """Премия в месяц при рассрочке"""
        if self.installment_available and self.installment_months:
            return self.insurance_premium / self.installment_months
        return self.insurance_premium
    
    @property
    def effective_premium_with_franchise(self):
        """Эффективная премия с франшизой (приоритет новым полям)"""
        return self.yearly_premium_with_franchise or self.insurance_premium
    
    @property
    def effective_premium_without_franchise(self):
        """Эффективная премия без франшизы"""
        return self.yearly_premium_without_franchise or self.insurance_premium
    
    @property
    def effective_franchise_amount(self):
        """Эффективная франшиза (приоритет variant1, затем старое поле)"""
        return self.franchise_amount_variant1 or self.franchise_amount
    
    def get_year_number(self):
        """Извлекает номер года из строки insurance_year"""
        try:
            # Извлекаем число из строки типа "1 год", "2 год", "3 год"
            return int(self.insurance_year.split()[0])
        except (ValueError, IndexError):
            return 1  # По умолчанию первый год


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

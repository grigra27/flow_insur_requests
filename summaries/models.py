from django.db import models
from django.contrib.auth.models import User
from insurance_requests.models import InsuranceRequest
from decimal import Decimal


class InsuranceSummary(models.Model):
    """Модель свода предложений по заявке"""
    
    STATUS_CHOICES = [
        ('collecting', 'Сбор предложений'),
        ('ready', 'Готов к отправке'),
        ('sent', 'Отправлен в Альянс'),
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
    
    # Файл свода
    summary_file = models.FileField(
        upload_to='summaries/%Y/%m/%d/', 
        null=True, 
        blank=True, 
        verbose_name='Файл свода'
    )
    
    # Отправка клиенту
    sent_to_client_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлен клиенту')
    
    class Meta:
        verbose_name = 'Свод предложений'
        verbose_name_plural = 'Своды предложений'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Свод к {self.request.get_display_name()} - {self.request.client_name}"
    
    @property
    def branch(self):
        """Возвращает филиал из связанной заявки"""
        return self.request.branch if self.request else None
    
    @property
    def dfa_number(self):
        """Возвращает номер ДФА из связанной заявки"""
        return self.request.dfa_number if self.request else None
    
    def get_status_display(self):
        """Переопределенное отображение статусов"""
        # Get the display value from STATUS_CHOICES
        for choice_value, choice_display in self.STATUS_CHOICES:
            if choice_value == self.status:
                return choice_display
        return self.status
    
    def get_offers_by_year(self, year=1):
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
    
    def get_offers_grouped_by_company(self):
        """Returns offers organized by company with year breakdown and proper sorting"""
        companies = {}
        
        # Group offers by company
        for offer in self.offers.filter(is_valid=True).select_related():
            company_name = offer.company_name
            if company_name not in companies:
                companies[company_name] = []
            companies[company_name].append(offer)
        
        # Sort companies alphabetically and years numerically within each company
        sorted_companies = {}
        for company_name in sorted(companies.keys()):
            # Sort offers by year number within each company
            sorted_offers = sorted(companies[company_name], key=lambda x: x.get_year_number())
            sorted_companies[company_name] = sorted_offers
            
        return sorted_companies
    
    def get_company_year_matrix(self):
        """Returns structured data for template rendering with company-year organization"""
        companies_data = {}
        
        # Get grouped offers
        grouped_offers = self.get_offers_grouped_by_company()
        
        # Structure data for template consumption
        for company_name, offers in grouped_offers.items():
            companies_data[company_name] = {
                'name': company_name,
                'years': {},
                'offer_count': len(offers)
            }
            
            # Organize offers by year within company
            for offer in offers:
                year_key = offer.get_insurance_year_display()
                companies_data[company_name]['years'][year_key] = {
                    'offer': offer,
                    'year_number': offer.get_year_number(),
                    'insurance_sum': offer.insurance_sum,
                    'franchise_1': offer.get_franchise_display_variant1(),
                    'premium_1': offer.get_premium_with_franchise1(),
                    'franchise_2': offer.get_franchise_display_variant2(), 
                    'premium_2': offer.get_premium_with_franchise2()
                }
        
        return companies_data
    
    def get_unique_companies_count(self):
        """Возвращает количество уникальных компаний в своде"""
        return self.offers.filter(is_valid=True).values('company_name').distinct().count()
    
    def get_companies_with_year_counts(self):
        """Возвращает словарь компаний с количеством лет страхования"""
        companies = {}
        for offer in self.offers.filter(is_valid=True):
            if offer.company_name not in companies:
                companies[offer.company_name] = 0
            companies[offer.company_name] += 1
        return companies
    
    def get_unique_companies_list(self):
        """Возвращает список уникальных названий компаний"""
        return list(self.offers.filter(is_valid=True).values_list('company_name', flat=True).distinct())
    
    def update_total_offers_count(self):
        """Обновляет счетчик общего количества предложений"""
        self.total_offers = self.get_unique_companies_count()
        self.save(update_fields=['total_offers'])
    
    def get_companies_summary_data(self):
        """Возвращает сводные данные о компаниях для отображения в интерфейсе"""
        companies_data = {}
        for offer in self.offers.filter(is_valid=True):
            company_name = offer.company_name
            if company_name not in companies_data:
                companies_data[company_name] = {
                    'name': company_name,
                    'years_count': 0,
                    'years': [],
                    'min_premium': None,
                    'max_premium': None,
                }
            
            company_data = companies_data[company_name]
            company_data['years_count'] += 1
            company_data['years'].append(offer.insurance_year)
            
            # Обновляем минимальную и максимальную премии
            premium = offer.premium_with_franchise_1 or 0
            if company_data['min_premium'] is None or premium < company_data['min_premium']:
                company_data['min_premium'] = premium
            if company_data['max_premium'] is None or premium > company_data['max_premium']:
                company_data['max_premium'] = premium
        
        return companies_data
    
    def get_status_display_with_color(self):
        """Возвращает статус с соответствующим цветом для Bootstrap"""
        from .status_colors import get_status_display_data
        return get_status_display_data(self.status, self.get_status_display())
    
    def get_company_totals(self):
        """Возвращает итоговые суммы по компаниям для многолетних предложений"""
        companies_data = {}
        
        for offer in self.offers.filter(is_valid=True).order_by('company_name', 'insurance_year'):
            company_name = offer.company_name
            if company_name not in companies_data:
                companies_data[company_name] = {
                    'offers': [],
                    'total_premium_1': Decimal('0'),
                    'total_premium_2': Decimal('0'),
                    'is_multiyear': False
                }
            
            companies_data[company_name]['offers'].append(offer)
            companies_data[company_name]['total_premium_1'] += offer.premium_with_franchise_1 or Decimal('0')
            companies_data[company_name]['total_premium_2'] += offer.premium_with_franchise_2 or Decimal('0')
        
        # Определяем многолетние предложения (более одного года)
        for company_name, data in companies_data.items():
            data['is_multiyear'] = len(data['offers']) > 1
        
        return companies_data


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
    
    # Данные предложения
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата получения')
    insurance_sum = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Страховая сумма')
    
    # Год страхования (теперь числовое поле)
    insurance_year = models.PositiveIntegerField(
        default=1,
        verbose_name='Номер года страхования',
        help_text='Числовое значение года страхования (1, 2, 3, ...)'
    )
    
    # Структурированные поля для франшиз и премий
    franchise_1 = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name='Франшиза-1',
        help_text='Размер первой франшизы (обычно 0)'
    )
    premium_with_franchise_1 = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Премия с франшизой-1',
        help_text='Премия с первой франшизой'
    )
    franchise_2 = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Франшиза-2',
        help_text='Размер второй франшизы (обычно больше 0)'
    )
    premium_with_franchise_2 = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Премия с франшизой-2',
        help_text='Премия со второй франшизой'
    )
    
    # Условия оплаты (старые поля для обратной совместимости)
    installment_available = models.BooleanField(default=False, verbose_name='Рассрочка доступна')
    payments_per_year = models.PositiveIntegerField(
        default=1,
        verbose_name='Количество платежей в год',
        help_text='Количество платежей в год (1, 2, 3, 4, 12)'
    )
    
    # Расширенные условия рассрочки для каждого варианта премии
    installment_variant_1 = models.BooleanField(
        default=False, 
        verbose_name='Рассрочка для варианта 1',
        help_text='Доступна ли рассрочка для премии с франшизой-1'
    )
    payments_per_year_variant_1 = models.PositiveIntegerField(
        default=1,
        verbose_name='Платежей в год (вариант 1)',
        help_text='Количество платежей в год для варианта 1 (1, 2, 3, 4, 12)'
    )
    
    installment_variant_2 = models.BooleanField(
        default=False, 
        verbose_name='Рассрочка для варианта 2',
        help_text='Доступна ли рассрочка для премии с франшизой-2'
    )
    payments_per_year_variant_2 = models.PositiveIntegerField(
        default=1,
        verbose_name='Платежей в год (вариант 2)',
        help_text='Количество платежей в год для варианта 2 (1, 2, 3, 4, 12)'
    )
    
    # Валидность предложения
    is_valid = models.BooleanField(default=True, verbose_name='Действительное предложение')
    
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
        ordering = ['premium_with_franchise_1', '-received_at']
        unique_together = ['summary', 'company_name', 'insurance_year']  # Одно предложение от компании на год
    
    def __str__(self):
        return f"{self.company_name} ({self.get_insurance_year_display()}): {self.premium_with_franchise_1 or 0} ₽"
    
    @property
    def premium_per_payment(self):
        """Премия за один платеж при рассрочке (для обратной совместимости)"""
        if self.installment_available and self.payments_per_year > 1:
            return (self.premium_with_franchise_1 or 0) / self.payments_per_year
        return self.premium_with_franchise_1 or 0
    
    def get_installment_display(self):
        """Возвращает описание условий рассрочки (для обратной совместимости)"""
        if not self.installment_available or self.payments_per_year <= 1:
            return "Единовременно"
        return f"{self.payments_per_year} платежей в год"
    
    def get_payment_amount(self, franchise_variant=1):
        """Возвращает размер одного платежа для указанного варианта франшизы (для обратной совместимости)"""
        if franchise_variant == 1:
            premium = self.premium_with_franchise_1 or 0
        else:
            premium = self.premium_with_franchise_2 or self.premium_with_franchise_1 or 0
        
        if self.installment_available and self.payments_per_year > 1:
            return premium / self.payments_per_year
        return premium
    
    def get_payment_amount_variant_1(self):
        """Размер платежа для варианта 1 с учетом рассрочки"""
        premium = self.premium_with_franchise_1 or 0
        if self.installment_variant_1 and self.payments_per_year_variant_1 > 1:
            return premium / self.payments_per_year_variant_1
        return premium
    
    def get_payment_amount_variant_2(self):
        """Размер платежа для варианта 2 с учетом рассрочки"""
        premium = self.premium_with_franchise_2 or 0
        if self.installment_variant_2 and self.payments_per_year_variant_2 > 1:
            return premium / self.payments_per_year_variant_2
        return premium
    
    def get_installment_display_variant_1(self):
        """Возвращает описание условий рассрочки для варианта 1"""
        if not self.installment_variant_1 or self.payments_per_year_variant_1 <= 1:
            return "Единовременно"
        return f"{self.payments_per_year_variant_1} платежей в год"
    
    def get_installment_display_variant_2(self):
        """Возвращает описание условий рассрочки для варианта 2"""
        if not self.installment_variant_2 or self.payments_per_year_variant_2 <= 1:
            return "Единовременно"
        return f"{self.payments_per_year_variant_2} платежей в год"
    
    def has_installment_variant_1(self):
        """Проверяет, доступна ли рассрочка для варианта 1"""
        return self.installment_variant_1 and self.payments_per_year_variant_1 > 1
    
    def has_installment_variant_2(self):
        """Проверяет, доступна ли рассрочка для варианта 2"""
        return self.installment_variant_2 and self.payments_per_year_variant_2 > 1
    
    @property
    def effective_premium_with_franchise(self):
        """Эффективная премия с франшизой"""
        return self.premium_with_franchise_1 or 0
    
    @property
    def effective_premium_without_franchise(self):
        """Эффективная премия без франшизы (вторая франшиза)"""
        return self.premium_with_franchise_2 or self.premium_with_franchise_1 or 0
    
    @property
    def effective_franchise_amount(self):
        """Эффективная франшиза (первая франшиза)"""
        return self.franchise_1
    
    def get_year_number(self):
        """Возвращает номер года страхования"""
        return self.insurance_year
    
    def get_insurance_year_display(self):
        """Возвращает год страхования с добавлением слова 'год'"""
        return f"{self.insurance_year} год"
    
    def get_franchise_display_variant1(self):
        """Returns formatted franchise-1 amount or default indicator"""
        if self.franchise_1 == 0:
            return "0"
        return f"{self.franchise_1:,.0f} ₽"
    
    def get_franchise_display_variant2(self):
        """Returns formatted franchise-2 amount or default indicator"""
        if self.franchise_2 is not None:
            if self.franchise_2 == 0:
                return "0"
            return f"{self.franchise_2:,.0f} ₽"
        return "Нет"
    
    def get_premium_with_franchise1(self):
        """Returns premium with franchise-1 (typically with zero franchise)"""
        return self.premium_with_franchise_1 or 0
    
    def get_premium_with_franchise2(self):
        """Returns premium with franchise-2 (typically with non-zero franchise)"""
        return self.premium_with_franchise_2 or self.premium_with_franchise_1 or 0
    
    def has_second_franchise_variant(self):
        """Проверяет, есть ли второй вариант франшизы"""
        return self.franchise_2 is not None and self.premium_with_franchise_2 is not None
    

    
    def get_franchise_variants(self):
        """Возвращает список всех вариантов франшизы с премиями"""
        variants = [{
            'franchise': self.franchise_1,
            'premium': self.premium_with_franchise_1,
            'franchise_display': self.get_franchise_display_variant1(),
            'variant_number': 1
        }]
        
        if self.has_second_franchise_variant():
            variants.append({
                'franchise': self.franchise_2,
                'premium': self.premium_with_franchise_2,
                'franchise_display': self.get_franchise_display_variant2(),
                'variant_number': 2
            })
        
        return variants


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

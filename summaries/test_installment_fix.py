"""
Тест для проверки исправления проблемы с рассрочкой.
Проверяет, что когда галочка "рассрочка доступна" не отмечена,
поле payments_per_year автоматически устанавливается в 1.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User, Group

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary
from summaries.forms import OfferForm, AddOfferToSummaryForm


class TestInstallmentFix(TestCase):
    """Тест исправления проблемы с рассрочкой"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Test Client",
            inn="1234567890",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_offer_form_without_installment(self):
        """Тест OfferForm без рассрочки"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': False,  # Рассрочка НЕ доступна
            'payments_per_year': 4,  # Указываем 4, но должно стать 1
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Форма должна быть валидной. Ошибки: {form.errors}")
        
        # Проверяем, что payments_per_year автоматически установлено в 1
        self.assertEqual(form.cleaned_data['payments_per_year'], 1)
    
    def test_offer_form_with_installment(self):
        """Тест OfferForm с рассрочкой"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': True,  # Рассрочка доступна
            'payments_per_year': 4,  # Должно остаться 4
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Форма должна быть валидной. Ошибки: {form.errors}")
        
        # Проверяем, что payments_per_year остается 4
        self.assertEqual(form.cleaned_data['payments_per_year'], 4)
    
    def test_offer_form_without_installment_no_payments_specified(self):
        """Тест OfferForm без рассрочки и без указания payments_per_year"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': False,  # Рассрочка НЕ доступна
            # payments_per_year не указано
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Форма должна быть валидной. Ошибки: {form.errors}")
        
        # Проверяем, что payments_per_year автоматически установлено в 1
        self.assertEqual(form.cleaned_data['payments_per_year'], 1)
    
    def test_add_offer_form_without_installment(self):
        """Тест AddOfferToSummaryForm без рассрочки"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': False,  # Рассрочка НЕ доступна
            'payments_per_year': 12,  # Указываем 12, но должно стать 1
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Форма должна быть валидной. Ошибки: {form.errors}")
        
        # Проверяем, что payments_per_year автоматически установлено в 1
        self.assertEqual(form.cleaned_data['payments_per_year'], 1)
    
    def test_add_offer_form_with_installment(self):
        """Тест AddOfferToSummaryForm с рассрочкой"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': True,  # Рассрочка доступна
            'payments_per_year': 12,  # Должно остаться 12
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Форма должна быть валидной. Ошибки: {form.errors}")
        
        # Проверяем, что payments_per_year остается 12
        self.assertEqual(form.cleaned_data['payments_per_year'], 12)
    
    def test_offer_form_invalid_payments_with_installment(self):
        """Тест OfferForm с недопустимым количеством платежей при включенной рассрочке"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': True,  # Рассрочка доступна
            'payments_per_year': 15,  # Недопустимое значение
        }
        
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('payments_per_year', form.errors)
    
    def test_offer_form_invalid_payments_ignored_without_installment(self):
        """Тест OfferForm с недопустимым количеством платежей при выключенной рассрочке"""
        
        form_data = {
            'company_name': 'Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': False,  # Рассрочка НЕ доступна
            'payments_per_year': 15,  # Недопустимое значение, но должно игнорироваться
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Форма должна быть валидной. Ошибки: {form.errors}")
        
        # Проверяем, что payments_per_year автоматически установлено в 1
        self.assertEqual(form.cleaned_data['payments_per_year'], 1)


if __name__ == '__main__':
    import unittest
    unittest.main()
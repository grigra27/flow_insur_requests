"""
Интеграционный тест для проверки исправления проблемы с рассрочкой через веб-интерфейс.
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class TestInstallmentIntegration(TestCase):
    """Интеграционный тест исправления проблемы с рассрочкой"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='integrationuser',
            email='integration@example.com',
            password='testpass123'
        )
        
        # Добавляем пользователя в нужную группу
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.request = InsuranceRequest.objects.create(
            client_name="Integration Test Client",
            inn="1234567890",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Логинимся
        self.client.login(username='integrationuser', password='testpass123')
    
    def test_add_offer_without_installment_via_web(self):
        """Тест добавления предложения без рассрочки через веб-интерфейс"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        # Данные формы без рассрочки
        form_data = {
            'company_name': 'Web Test Company',
            'insurance_year': 2,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': False,  # Рассрочка НЕ доступна
            # payments_per_year не указываем - должно автоматически стать 1
        }
        
        response = self.client.post(url, data=form_data)
        
        # Должен быть редирект после успешного создания
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что предложение создалось
        offer = InsuranceOffer.objects.get(company_name='Web Test Company')
        self.assertEqual(offer.insurance_year, 2)
        self.assertEqual(offer.installment_available, False)
        self.assertEqual(offer.payments_per_year, 1)  # Должно быть автоматически установлено в 1
    
    def test_add_offer_with_installment_via_web(self):
        """Тест добавления предложения с рассрочкой через веб-интерфейс"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        # Данные формы с рассрочкой
        form_data = {
            'company_name': 'Web Installment Company',
            'insurance_year': 1,
            'insurance_sum': '1200000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '60000.00',
            'installment_available': True,  # Рассрочка доступна
            'payments_per_year': 4,  # Квартальные платежи
        }
        
        response = self.client.post(url, data=form_data)
        
        # Должен быть редирект после успешного создания
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что предложение создалось
        offer = InsuranceOffer.objects.get(company_name='Web Installment Company')
        self.assertEqual(offer.insurance_year, 1)
        self.assertEqual(offer.installment_available, True)
        self.assertEqual(offer.payments_per_year, 4)  # Должно остаться 4
    
    def test_edit_offer_without_installment_via_web(self):
        """Тест редактирования предложения без рассрочки через веб-интерфейс"""
        
        # Создаем предложение для редактирования
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name="Пари",
            insurance_year=1,
            insurance_sum=Decimal("800000.00"),
            franchise_1=Decimal("0.00"),
            premium_with_franchise_1=Decimal("40000.00"),
            installment_available=True,
            payments_per_year=4
        )
        
        url = reverse('summaries:edit_offer', kwargs={'offer_id': offer.pk})
        
        # Данные для редактирования - убираем рассрочку
        form_data = {
            'company_name': 'Edited Company',
            'insurance_year': 2,
            'insurance_sum': '900000.00',
            'franchise_1': '5000.00',
            'premium_with_franchise_1': '45000.00',
            'installment_available': False,  # Убираем рассрочку
            'payments_per_year': 12,  # Указываем 12, но должно стать 1
        }
        
        response = self.client.post(url, data=form_data)
        
        # Должен быть редирект после успешного обновления
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что предложение обновилось
        offer.refresh_from_db()
        self.assertEqual(offer.company_name, 'Edited Company')
        self.assertEqual(offer.insurance_year, 2)
        self.assertEqual(offer.installment_available, False)
        self.assertEqual(offer.payments_per_year, 1)  # Должно автоматически стать 1
    
    def test_form_validation_error_display(self):
        """Тест отображения ошибок валидации в веб-интерфейсе"""
        
        url = reverse('summaries:add_offer', kwargs={'summary_id': self.summary.pk})
        
        # Данные с ошибками
        form_data = {
            'company_name': '',  # Пустое обязательное поле
            'insurance_year': 15,  # Недопустимый год
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_available': False,
        }
        
        response = self.client.post(url, data=form_data)
        
        # Не должно быть редиректа (форма с ошибками)
        self.assertEqual(response.status_code, 200)
        
        # Должны быть ошибки в контексте
        self.assertContains(response, 'Обязательное поле')
        self.assertContains(response, 'Год страхования должен быть от 1 до 10')
        
        # Предложение не должно создаться
        self.assertFalse(InsuranceOffer.objects.filter(company_name='').exists())


if __name__ == '__main__':
    import unittest
    unittest.main()
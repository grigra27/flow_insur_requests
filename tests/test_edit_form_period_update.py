"""
Тесты для обновленной формы редактирования с новой логикой периода страхования
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from datetime import datetime

from insurance_requests.models import InsuranceRequest
from insurance_requests.forms import InsuranceRequestForm


class EditFormPeriodUpdateTests(TestCase):
    """Тесты для обновленной формы редактирования заявок"""
    
    def setUp(self):
        """Настройка тестов"""
        # Создаем пользователя и группу
        self.user_group = Group.objects.create(name='Пользователи')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.user.groups.add(self.user_group)
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_form_has_period_choices(self):
        """Тест что форма содержит правильные варианты периода страхования"""
        form = InsuranceRequestForm()
        
        # Проверяем, что поле insurance_period является ChoiceField
        self.assertIn('insurance_period', form.fields)
        period_field = form.fields['insurance_period']
        self.assertEqual(period_field.__class__.__name__, 'ChoiceField')
        
        # Проверяем варианты выбора
        expected_choices = [
            ('', '-- Выберите период --'),
            ('1 год', '1 год'),
            ('на весь срок лизинга', 'на весь срок лизинга'),
        ]
        self.assertEqual(period_field.choices, expected_choices)
    
    def test_form_does_not_have_date_fields(self):
        """Тест что форма не содержит поля дат страхования"""
        form = InsuranceRequestForm()
        
        # Проверяем, что полей дат нет в форме
        self.assertNotIn('insurance_start_date', form.fields)
        self.assertNotIn('insurance_end_date', form.fields)
        
        # Проверяем, что полей дат нет в Meta.fields
        self.assertNotIn('insurance_start_date', form.Meta.fields)
        self.assertNotIn('insurance_end_date', form.Meta.fields)
    
    def test_form_validation_with_valid_period(self):
        """Тест валидации формы с корректным периодом"""
        form_data = {
            'client_name': 'Тестовый клиент',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Toyota Camry',
            'dfa_number': 'ДФА-123',
            'branch': 'Москва',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': datetime.now(),
            'notes': ''
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_validation_with_invalid_period(self):
        """Тест валидации формы с некорректным периодом"""
        form_data = {
            'client_name': 'Тестовый клиент',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': 'неправильный период',  # Недопустимое значение
            'vehicle_info': 'Toyota Camry',
            'dfa_number': 'ДФА-123',
            'branch': 'Москва',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': datetime.now(),
            'notes': ''
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_period', form.errors)
        self.assertIn('Выберите корректный вариант', str(form.errors['insurance_period']))
    
    def test_form_validation_with_empty_period(self):
        """Тест валидации формы с пустым периодом (должно быть валидно)"""
        form_data = {
            'client_name': 'Тестовый клиент',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '',  # Пустое значение
            'vehicle_info': 'Toyota Camry',
            'dfa_number': 'ДФА-123',
            'branch': 'Москва',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': datetime.now(),
            'notes': ''
        }
        
        form = InsuranceRequestForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_initialization_with_new_period_format(self):
        """Тест инициализации формы с новым форматом периода"""
        # Создаем заявку с новым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Инициализируем форму с этой заявкой
        form = InsuranceRequestForm(instance=request)
        
        # Проверяем, что период правильно установлен
        self.assertEqual(form.initial['insurance_period'], '1 год')
    
    def test_form_initialization_with_old_period_format(self):
        """Тест инициализации формы со старым форматом периода"""
        # Создаем заявку со старым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='с 01.01.2024 по 31.12.2024',  # Старый формат
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Инициализируем форму с этой заявкой
        form = InsuranceRequestForm(instance=request)
        
        # Проверяем, что для старого формата устанавливается пустое значение
        self.assertEqual(form.initial['insurance_period'], '')
    
    def test_form_save_with_new_period(self):
        """Тест сохранения формы с новым периодом"""
        # Создаем заявку
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Обновляем через форму
        form_data = {
            'client_name': 'Тестовый клиент',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',
            'vehicle_info': 'Toyota Camry',
            'dfa_number': 'ДФА-123',
            'branch': 'Москва',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': datetime.now(),
            'notes': ''
        }
        
        form = InsuranceRequestForm(data=form_data, instance=request)
        self.assertTrue(form.is_valid())
        
        updated_request = form.save()
        self.assertEqual(updated_request.insurance_period, 'на весь срок лизинга')
    
    def test_edit_view_with_new_period_format(self):
        """Тест view редактирования с новым форматом периода"""
        # Создаем заявку с новым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Открываем страницу редактирования
        response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Проверяем, что форма содержит правильные поля
        form = response.context['form']
        self.assertIn('insurance_period', form.fields)
        self.assertNotIn('insurance_start_date', form.fields)
        self.assertNotIn('insurance_end_date', form.fields)
    
    def test_edit_view_post_with_new_period(self):
        """Тест POST запроса к view редактирования с новым периодом"""
        # Создаем заявку
        request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='',
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Отправляем POST запрос с обновленными данными
        response = self.client.post(
            reverse('insurance_requests:edit_request', kwargs={'pk': request.pk}),
            data={
                'client_name': 'Обновленный клиент',
                'inn': '1234567890',
                'insurance_type': 'КАСКО',
                'insurance_period': '1 год',
                'vehicle_info': 'Toyota Camry',
                'dfa_number': 'ДФА-123',
                'branch': 'Москва',
                'has_franchise': False,
                'has_installment': False,
                'has_autostart': False,
                'has_casco_ce': False,
                'response_deadline': datetime.now().strftime('%Y-%m-%dT%H:%M'),
                'notes': ''
            }
        )
        
        # Проверяем редирект после успешного сохранения
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что данные сохранились
        request.refresh_from_db()
        self.assertEqual(request.client_name, 'Обновленный клиент')
        self.assertEqual(request.insurance_period, '1 год')
    
    def test_form_help_text_updated(self):
        """Тест что help text для поля периода обновлен"""
        form = InsuranceRequestForm()
        
        period_field = form.fields['insurance_period']
        self.assertEqual(period_field.help_text, 'Выберите необходимый период страхования')
    
    def test_backward_compatibility_with_existing_requests(self):
        """Тест обратной совместимости с существующими заявками"""
        # Создаем заявку со старым форматом периода
        request = InsuranceRequest.objects.create(
            client_name='Старый клиент',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='с 01.01.2024 по 31.12.2024',
            vehicle_info='Toyota Camry',
            dfa_number='ДФА-123',
            branch='Москва',
            has_franchise=False,
            has_installment=False,
            has_autostart=False,
            has_casco_ce=False,
            response_deadline=datetime.now(),
            created_by=self.user
        )
        
        # Открываем форму редактирования
        form = InsuranceRequestForm(instance=request)
        
        # Проверяем, что старый период не выбран в dropdown (устанавливается пустое значение)
        self.assertEqual(form.initial['insurance_period'], '')
        
        # Проверяем, что можем выбрать новый период
        form_data = {
            'client_name': 'Старый клиент',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',  # Выбираем новый период
            'vehicle_info': 'Toyota Camry',
            'dfa_number': 'ДФА-123',
            'branch': 'Москва',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'has_casco_ce': False,
            'response_deadline': datetime.now(),
            'notes': ''
        }
        
        form = InsuranceRequestForm(data=form_data, instance=request)
        self.assertTrue(form.is_valid())
        
        updated_request = form.save()
        self.assertEqual(updated_request.insurance_period, '1 год')
"""
Тесты для форм и валидации страховых компаний.
Проверяет валидацию выбора страховых компаний в формах OfferForm и AddOfferToSummaryForm.
"""

from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceCompany
from summaries.forms import OfferForm, AddOfferToSummaryForm
from summaries.constants import get_company_names, is_valid_company_name


class TestOfferFormValidation(TestCase):
    """Тесты валидации формы OfferForm"""
    
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
        
        # Базовые валидные данные для формы
        self.valid_form_data = {
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            'installment_variant_1': False,
            'payments_per_year_variant_1': 1,
            'installment_variant_2': False,
            'payments_per_year_variant_2': 1,
        }
    
    def test_valid_company_name_selection(self):
        """Тест валидного выбора страховой компании"""
        valid_companies = get_company_names()
        
        for company in valid_companies:
            if company:  # Пропускаем пустые значения
                with self.subTest(company=company):
                    form_data = self.valid_form_data.copy()
                    form_data['company_name'] = company
                    
                    form = OfferForm(data=form_data)
                    self.assertTrue(
                        form.is_valid(), 
                        f"Форма должна быть валидной для компании '{company}'. Ошибки: {form.errors}"
                    )
                    self.assertEqual(form.cleaned_data['company_name'], company)
    
    def test_empty_company_name_validation(self):
        """Тест валидации пустого названия компании"""
        form_data = self.valid_form_data.copy()
        form_data['company_name'] = ''
        
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        self.assertIn(
            'Пожалуйста, выберите страховую компанию из выпадающего списка',
            str(form.errors['company_name'])
        )
    
    def test_invalid_company_name_validation(self):
        """Тест валидации недопустимого названия компании"""
        invalid_companies = [
            'Несуществующая компания',
            'Invalid Company',
            'Тест',
            'АльфаСтрахование',  # Похоже на валидное, но не точное совпадение
            'вск',  # Неправильный регистр
            'АБСОЛЮТ',  # Неправильный регистр
        ]
        
        for invalid_company in invalid_companies:
            with self.subTest(company=invalid_company):
                form_data = self.valid_form_data.copy()
                form_data['company_name'] = invalid_company
                
                form = OfferForm(data=form_data)
                self.assertFalse(
                    form.is_valid(),
                    f"Форма не должна быть валидной для компании '{invalid_company}'"
                )
                self.assertIn('company_name', form.errors)
                self.assertIn(
                    'Выберите страховую компанию из предложенного списка',
                    str(form.errors['company_name'])
                )
    
    def test_company_name_validation_with_whitespace(self):
        """Тест валидации названия компании с пробелами"""
        # Пробелы в начале и конце должны обрабатываться корректно
        form_data = self.valid_form_data.copy()
        form_data['company_name'] = '  Абсолют  '
        
        form = OfferForm(data=form_data)
        # Форма может быть невалидной, так как выбор происходит из списка
        # и пробелы могут не совпадать с точным значением
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
    
    def test_special_company_name_drugoe(self):
        """Тест валидации специального значения 'другое'"""
        form_data = self.valid_form_data.copy()
        form_data['company_name'] = 'другое'
        
        form = OfferForm(data=form_data)
        self.assertTrue(
            form.is_valid(),
            f"Форма должна быть валидной для значения 'другое'. Ошибки: {form.errors}"
        )
        self.assertEqual(form.cleaned_data['company_name'], 'другое')
    
    def test_company_name_field_choices_populated(self):
        """Тест что поле company_name содержит правильные варианты выбора"""
        form = OfferForm()
        
        # Проверяем, что choices заполнены
        self.assertTrue(len(form.fields['company_name'].choices) > 0)
        
        # Проверяем, что есть пустой вариант
        choice_values = [choice[0] for choice in form.fields['company_name'].choices]
        self.assertIn('', choice_values)
        
        # Проверяем, что есть значение 'другое'
        self.assertIn('другое', choice_values)
        
        # Проверяем, что есть основные компании
        expected_companies = ['Абсолют', 'ВСК', 'Согаз', 'РЕСО']
        for company in expected_companies:
            self.assertIn(company, choice_values)
    
    def test_company_name_field_widget_attributes(self):
        """Тест атрибутов виджета поля company_name"""
        form = OfferForm()
        widget = form.fields['company_name'].widget
        
        # Проверяем CSS класс
        self.assertIn('form-select', widget.attrs.get('class', ''))
        
        # Проверяем tooltip атрибуты
        self.assertEqual(widget.attrs.get('data-bs-toggle'), 'tooltip')
        self.assertEqual(widget.attrs.get('data-bs-placement'), 'top')
        self.assertIn('Список содержит основные страховые компании', widget.attrs.get('title', ''))
    
    def test_company_name_field_error_messages(self):
        """Тест кастомных сообщений об ошибках для поля company_name"""
        form = OfferForm()
        field = form.fields['company_name']
        
        # Проверяем кастомные сообщения об ошибках
        self.assertIn('required', field.error_messages)
        self.assertIn('invalid_choice', field.error_messages)
        
        self.assertIn(
            'Пожалуйста, выберите страховую компанию из выпадающего списка',
            field.error_messages['required']
        )
        self.assertIn(
            'Выберите страховую компанию из предложенного списка',
            field.error_messages['invalid_choice']
        )
    
    def test_company_name_field_help_text(self):
        """Тест текста подсказки для поля company_name"""
        form = OfferForm()
        field = form.fields['company_name']
        
        self.assertIn('Выберите страховую компанию из списка', field.help_text)
        self.assertIn('Другое', field.help_text)


class TestAddOfferToSummaryFormValidation(TestCase):
    """Тесты валидации формы AddOfferToSummaryForm"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Test Client 2",
            inn="0987654321",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
        
        # Базовые валидные данные для формы
        self.valid_form_data = {
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            'installment_variant_1': False,
            'payments_per_year_variant_1': 1,
            'installment_variant_2': False,
            'payments_per_year_variant_2': 1,
        }
    
    def test_valid_company_name_selection(self):
        """Тест валидного выбора страховой компании в AddOfferToSummaryForm"""
        valid_companies = get_company_names()
        
        for company in valid_companies:
            if company:  # Пропускаем пустые значения
                with self.subTest(company=company):
                    form_data = self.valid_form_data.copy()
                    form_data['company_name'] = company
                    
                    form = AddOfferToSummaryForm(data=form_data)
                    self.assertTrue(
                        form.is_valid(), 
                        f"AddOfferToSummaryForm должна быть валидной для компании '{company}'. Ошибки: {form.errors}"
                    )
                    self.assertEqual(form.cleaned_data['company_name'], company)
    
    def test_empty_company_name_validation(self):
        """Тест валидации пустого названия компании в AddOfferToSummaryForm"""
        form_data = self.valid_form_data.copy()
        form_data['company_name'] = ''
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        self.assertIn(
            'Пожалуйста, выберите страховую компанию из выпадающего списка',
            str(form.errors['company_name'])
        )
    
    def test_invalid_company_name_validation(self):
        """Тест валидации недопустимого названия компании в AddOfferToSummaryForm"""
        invalid_companies = [
            'Неизвестная компания',
            'Test Insurance',
            'Страховая компания №1',
            'альфа',  # Неправильный регистр
            'Абсолют Страхование',  # Дополнительные слова
        ]
        
        for invalid_company in invalid_companies:
            with self.subTest(company=invalid_company):
                form_data = self.valid_form_data.copy()
                form_data['company_name'] = invalid_company
                
                form = AddOfferToSummaryForm(data=form_data)
                self.assertFalse(
                    form.is_valid(),
                    f"AddOfferToSummaryForm не должна быть валидной для компании '{invalid_company}'"
                )
                self.assertIn('company_name', form.errors)
                self.assertIn(
                    'Выберите страховую компанию из предложенного списка',
                    str(form.errors['company_name'])
                )
    
    def test_special_company_name_drugoe(self):
        """Тест валидации специального значения 'другое' в AddOfferToSummaryForm"""
        form_data = self.valid_form_data.copy()
        form_data['company_name'] = 'другое'
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertTrue(
            form.is_valid(),
            f"AddOfferToSummaryForm должна быть валидной для значения 'другое'. Ошибки: {form.errors}"
        )
        self.assertEqual(form.cleaned_data['company_name'], 'другое')
    
    def test_company_name_field_consistency_between_forms(self):
        """Тест согласованности поля company_name между формами"""
        offer_form = OfferForm()
        add_offer_form = AddOfferToSummaryForm()
        
        # Проверяем, что choices одинаковые в обеих формах
        offer_choices = set(offer_form.fields['company_name'].choices)
        add_offer_choices = set(add_offer_form.fields['company_name'].choices)
        
        self.assertEqual(
            offer_choices, 
            add_offer_choices,
            "Варианты выбора компаний должны быть одинаковыми в обеих формах"
        )
        
        # Проверяем, что сообщения об ошибках одинаковые
        self.assertEqual(
            offer_form.fields['company_name'].error_messages,
            add_offer_form.fields['company_name'].error_messages,
            "Сообщения об ошибках должны быть одинаковыми в обеих формах"
        )
        
        # Проверяем, что help_text одинаковый
        self.assertEqual(
            offer_form.fields['company_name'].help_text,
            add_offer_form.fields['company_name'].help_text,
            "Текст подсказки должен быть одинаковым в обеих формах"
        )


class TestFormErrorMessages(TestCase):
    """Тесты сообщений об ошибках в формах"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='erroruser',
            email='error@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Error Test Client",
            inn="1111111111",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_offer_form_required_field_error_message(self):
        """Тест сообщения об ошибке для обязательного поля company_name в OfferForm"""
        form_data = {
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            # company_name отсутствует
        }
        
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        
        error_message = str(form.errors['company_name'][0])
        self.assertIn('Пожалуйста, выберите страховую компанию', error_message)
        self.assertIn('выпадающего списка', error_message)
    
    def test_offer_form_invalid_choice_error_message(self):
        """Тест сообщения об ошибке для недопустимого выбора в OfferForm"""
        form_data = {
            'company_name': 'Недопустимая компания',
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
        }
        
        form = OfferForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        
        error_message = str(form.errors['company_name'][0])
        self.assertIn('Выберите страховую компанию из предложенного списка', error_message)
        self.assertIn('Другое', error_message)
    
    def test_add_offer_form_required_field_error_message(self):
        """Тест сообщения об ошибке для обязательного поля company_name в AddOfferToSummaryForm"""
        form_data = {
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            # company_name отсутствует
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        
        error_message = str(form.errors['company_name'][0])
        self.assertIn('Пожалуйста, выберите страховую компанию', error_message)
        self.assertIn('выпадающего списка', error_message)
    
    def test_add_offer_form_invalid_choice_error_message(self):
        """Тест сообщения об ошибке для недопустимого выбора в AddOfferToSummaryForm"""
        form_data = {
            'company_name': 'Неизвестная страховая',
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
        }
        
        form = AddOfferToSummaryForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)
        
        error_message = str(form.errors['company_name'][0])
        self.assertIn('Выберите страховую компанию из предложенного списка', error_message)
        self.assertIn('Другое', error_message)
    
    def test_error_message_localization(self):
        """Тест локализации сообщений об ошибках"""
        form = OfferForm()
        field = form.fields['company_name']
        
        # Проверяем, что сообщения на русском языке
        for error_key, error_message in field.error_messages.items():
            self.assertIsInstance(error_message, str)
            # Проверяем, что в сообщениях есть русские слова
            russian_words = ['Пожалуйста', 'выберите', 'страховую', 'компанию', 'списка', 'Выберите', 'Другое']
            has_russian = any(word in error_message for word in russian_words)
            self.assertTrue(
                has_russian, 
                f"Сообщение об ошибке '{error_message}' должно содержать русские слова"
            )
    
    def test_help_text_informativeness(self):
        """Тест информативности текста подсказки"""
        form = OfferForm()
        help_text = form.fields['company_name'].help_text
        
        # Проверяем, что help_text содержит полезную информацию
        self.assertIn('Выберите', help_text)
        self.assertIn('страховую компанию', help_text)
        self.assertIn('списка', help_text)
        self.assertIn('Другое', help_text)
        
        # Проверяем, что текст не слишком длинный (удобство использования)
        self.assertLessEqual(len(help_text), 200, "Текст подсказки не должен быть слишком длинным")


class TestFormFieldValidationIntegration(TestCase):
    """Интеграционные тесты валидации полей форм"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='integrationuser',
            email='integration@example.com',
            password='testpass123'
        )
        
        self.request = InsuranceRequest.objects.create(
            client_name="Integration Test Client",
            inn="2222222222",
            insurance_type="КАСКО",
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status="collecting"
        )
    
    def test_form_validation_with_constants_module(self):
        """Тест интеграции валидации форм с модулем constants"""
        # Получаем валидные компании из модуля constants
        valid_companies = get_company_names()
        
        # Тестируем каждую валидную компанию
        for company in valid_companies:
            if company:  # Пропускаем пустые значения
                with self.subTest(company=company):
                    # Проверяем, что функция is_valid_company_name работает корректно
                    self.assertTrue(
                        is_valid_company_name(company),
                        f"Функция is_valid_company_name должна возвращать True для '{company}'"
                    )
                    
                    # Проверяем, что форма принимает эту компанию
                    form_data = {
                        'company_name': company,
                        'insurance_year': 1,
                        'insurance_sum': Decimal('1000000.00'),
                        'franchise_1': Decimal('0.00'),
                        'premium_with_franchise_1': Decimal('50000.00'),
                        'installment_variant_1': False,
                        'payments_per_year_variant_1': 1,
                        'installment_variant_2': False,
                        'payments_per_year_variant_2': 1,
                    }
                    
                    form = OfferForm(data=form_data)
                    self.assertTrue(
                        form.is_valid(),
                        f"Форма должна быть валидной для компании '{company}'. Ошибки: {form.errors}"
                    )
    
    def test_form_validation_consistency_with_model_validation(self):
        """Тест согласованности валидации формы с валидацией модели"""
        # Создаем валидную форму
        form_data = {
            'company_name': 'Абсолют',
            'insurance_year': 1,
            'insurance_sum': Decimal('1000000.00'),
            'franchise_1': Decimal('0.00'),
            'premium_with_franchise_1': Decimal('50000.00'),
            'installment_variant_1': False,
            'payments_per_year_variant_1': 1,
            'installment_variant_2': False,
            'payments_per_year_variant_2': 1,
        }
        
        form = OfferForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Сохраняем объект через форму
        offer = form.save(commit=False)
        offer.summary = self.summary
        
        # Проверяем, что модель также считает данные валидными
        try:
            offer.full_clean()  # Вызывает валидацию модели
            offer.save()
        except ValidationError as e:
            self.fail(f"Модель должна принимать данные, валидные для формы. Ошибка: {e}")
        
        # Проверяем, что объект сохранился корректно
        self.assertEqual(offer.company_name, 'Абсолют')
        self.assertIsNotNone(offer.pk)
    
    def test_form_choices_dynamic_loading(self):
        """Тест динамической загрузки вариантов выбора в формах"""
        # Создаем форму и проверяем, что choices загружены
        form = OfferForm()
        choices = form.fields['company_name'].choices
        
        self.assertIsInstance(choices, (list, tuple))
        self.assertGreater(len(choices), 0, "Варианты выбора должны быть загружены")
        
        # Проверяем, что choices содержат ожидаемые значения
        choice_values = [choice[0] for choice in choices]
        
        # Должен быть пустой вариант
        self.assertIn('', choice_values)
        
        # Должно быть значение 'другое'
        self.assertIn('другое', choice_values)
        
        # Должны быть основные компании
        expected_companies = ['Абсолют', 'ВСК', 'Согаз', 'РЕСО', 'Ингосстрах']
        for company in expected_companies:
            self.assertIn(
                company, 
                choice_values,
                f"Компания '{company}' должна быть в списке выбора"
            )
    
    def test_form_validation_edge_cases(self):
        """Тест граничных случаев валидации форм"""
        edge_cases = [
            ('', False, 'Пустая строка должна быть невалидной'),
            ('   ', False, 'Строка из пробелов должна быть невалидной'),
            ('другое', True, 'Значение "другое" должно быть валидным'),
            ('ДРУГОЕ', False, 'Значение "ДРУГОЕ" в верхнем регистре должно быть невалидным'),
            ('Другое', False, 'Значение "Другое" с заглавной буквы должно быть невалидным'),
            ('абсолют', False, 'Значение в нижнем регистре должно быть невалидным'),
            ('АБСОЛЮТ', False, 'Значение в верхнем регистре должно быть невалидным'),
        ]
        
        for test_value, should_be_valid, description in edge_cases:
            with self.subTest(value=test_value, description=description):
                form_data = {
                    'company_name': test_value,
                    'insurance_year': 1,
                    'insurance_sum': Decimal('1000000.00'),
                    'franchise_1': Decimal('0.00'),
                    'premium_with_franchise_1': Decimal('50000.00'),
                    'installment_variant_1': False,
                    'payments_per_year_variant_1': 1,
                    'installment_variant_2': False,
                    'payments_per_year_variant_2': 1,
                }
                
                form = OfferForm(data=form_data)
                
                if should_be_valid:
                    self.assertTrue(form.is_valid(), f"{description}. Ошибки: {form.errors}")
                else:
                    self.assertFalse(form.is_valid(), description)
                    if not form.is_valid():
                        self.assertIn('company_name', form.errors, f"{description} - ошибка должна быть в поле company_name")


def run_form_validation_tests():
    """Функция для запуска всех тестов валидации форм"""
    import unittest
    
    # Создаем набор тестов
    test_suite = unittest.TestSuite()
    
    # Добавляем тестовые классы
    test_suite.addTest(unittest.makeSuite(TestOfferFormValidation))
    test_suite.addTest(unittest.makeSuite(TestAddOfferToSummaryFormValidation))
    test_suite.addTest(unittest.makeSuite(TestFormErrorMessages))
    test_suite.addTest(unittest.makeSuite(TestFormFieldValidationIntegration))
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    run_form_validation_tests()
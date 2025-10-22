"""
Интеграционные тесты для проверки всех компонентов улучшений UI сводов
Тестирует требования: 1.1-1.6, 2.1-2.5, 3.1-3.6
"""
import os
import tempfile
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.db import IntegrityError
from django.contrib.messages import get_messages

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class SummariesUIIntegrationTest(TestCase):
    """Интеграционные тесты для всех компонентов улучшений UI"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        # Создаем группы пользователей
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.admins_group, _ = Group.objects.get_or_create(name='Администраторы')
        
        # Создаем пользователя
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        # Добавляем пользователя в группу
        self.user.groups.add(self.users_group)
        
        # Создаем клиент для тестирования
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        
        # Создаем тестовую заявку
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='ООО "Тест"',
            inn='1234567890',
            insurance_type='КАСКО',
            vehicle_info='Тестовый автомобиль',
            branch='Москва',
            dfa_number='DFA-2025-001',
            status='uploaded',
            created_by=self.user
        )
        
        # Создаем свод
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )
        
        # Создаем тестовые предложения
        self.offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Тестовая Страховая 1',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('45000.00'),
            notes='Тестовое примечание для компании 1'
        )
        
        self.offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Тестовая Страховая 1',
            insurance_year=2,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('52000.00'),
            franchise_2=Decimal('25000.00'),
            premium_with_franchise_2=Decimal('47000.00'),
            notes='Тестовое примечание для компании 1 год 2'
        )
        
        self.offer3 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Альфа Страхование',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('48000.00'),
            franchise_2=Decimal('30000.00'),
            premium_with_franchise_2=Decimal('43000.00')
        )

    def test_copy_offer_functionality_integration(self):
        """
        Тест 1: Интеграционный тест функциональности копирования предложений
        Требования: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
        """
        # Проверяем отображение кнопки "Копировать" на странице детального свода
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'copy_offer')
        self.assertContains(response, 'bi-copy')
        
        # Тестируем GET запрос к странице копирования
        copy_url = reverse('summaries:copy_offer', args=[self.offer1.pk])
        response = self.client.get(copy_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Копировать предложение')
        self.assertContains(response, self.offer1.company_name)
        
        # Проверяем, что форма заполнена данными оригинального предложения
        self.assertContains(response, str(self.offer1.insurance_sum))
        self.assertContains(response, str(self.offer1.franchise_1))
        self.assertContains(response, str(self.offer1.premium_with_franchise_1))
        
        # Тестируем успешное копирование предложения
        initial_offers_count = InsuranceOffer.objects.filter(summary=self.summary).count()
        
        copy_data = {
            'company_name': 'Новая Страховая Компания',
            'insurance_year': 1,
            'insurance_sum': '1500000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '55000.00',
            'franchise_2': '30000.00',
            'premium_with_franchise_2': '50000.00',
            'installment_variant_1': False,
            'payments_per_year_variant_1': 1,
            'installment_variant_2': False,
            'payments_per_year_variant_2': 1,
            'notes': 'Скопированное предложение'
        }
        
        response = self.client.post(copy_url, copy_data)
        
        # Проверяем редирект после успешного копирования
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('summaries:summary_detail', args=[self.summary.pk]))
        
        # Проверяем, что новое предложение создано
        new_offers_count = InsuranceOffer.objects.filter(summary=self.summary).count()
        self.assertEqual(new_offers_count, initial_offers_count + 1)
        
        # Проверяем данные нового предложения
        new_offer = InsuranceOffer.objects.get(company_name='Новая Страховая Компания')
        self.assertEqual(new_offer.summary, self.summary)
        self.assertEqual(new_offer.insurance_sum, Decimal('1500000.00'))
        self.assertEqual(new_offer.premium_with_franchise_1, Decimal('55000.00'))
        
        # Проверяем сообщение об успехе
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        messages = list(get_messages(response.wsgi_request))
        success_messages = [m for m in messages if m.level_tag == 'success']
        self.assertTrue(any('успешно скопировано' in str(m) for m in success_messages))

    def test_copy_offer_duplicate_prevention(self):
        """
        Тест 2: Проверка предотвращения дублирования при копировании
        Требования: 1.4, 1.5
        """
        copy_url = reverse('summaries:copy_offer', args=[self.offer1.pk])
        
        # Пытаемся создать дубликат (та же компания и год)
        duplicate_data = {
            'company_name': self.offer1.company_name,
            'insurance_year': self.offer1.insurance_year,
            'insurance_sum': '1000000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
            'installment_variant_1': False,
            'payments_per_year_variant_1': 1,
            'installment_variant_2': False,
            'payments_per_year_variant_2': 1,
        }
        
        response = self.client.post(copy_url, duplicate_data)
        
        # Проверяем, что форма возвращается с ошибкой
        self.assertEqual(response.status_code, 200)
        
        # Проверяем сообщение об ошибке дублирования
        messages = list(get_messages(response.wsgi_request))
        error_messages = [m for m in messages if m.level_tag == 'error']
        self.assertTrue(any('уже существует' in str(m) for m in error_messages))

    def test_color_coding_integration(self):
        """
        Тест 3: Интеграционный тест цветового кодирования
        Требования: 2.1, 2.2, 2.3, 2.4, 2.5
        """
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем наличие CSS классов для цветового кодирования
        self.assertContains(response, 'franchise-variant-1')
        self.assertContains(response, 'franchise-variant-2')
        self.assertContains(response, 'company-total-row')
        
        # Проверяем CSS стили в шаблоне
        self.assertContains(response, 'color: #0f5132')  # Темно-зеленый для варианта 1
        self.assertContains(response, 'color: #052c65')  # Темно-синий для варианта 2
        self.assertContains(response, 'background-color: #fff3cd')  # Бледно-желтый для итого
        
        # Проверяем применение классов к соответствующим элементам
        self.assertContains(response, 'class="franchise-variant-1"')
        self.assertContains(response, 'class="franchise-variant-2"')
        
        # Проверяем мобильную совместимость (media queries)
        self.assertContains(response, '@media (max-width: 768px)')
        self.assertContains(response, '@media (max-width: 576px)')

    def test_company_notes_reorganization_integration(self):
        """
        Тест 4: Интеграционный тест реорганизации примечаний
        Требования: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
        """
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем, что примечания отображаются под названием компании
        self.assertContains(response, 'company-notes')
        self.assertContains(response, 'Примечания:')
        
        # Проверяем группировку примечаний по компаниям
        company_notes = self.summary.get_company_notes()
        self.assertIn('Тестовая Страховая 1', company_notes)
        self.assertEqual(len(company_notes['Тестовая Страховая 1']), 2)
        
        # Проверяем, что примечания отображаются в правильном месте
        content = response.content.decode()
        
        # Находим позицию названия компании и примечаний
        company_pos = content.find('Тестовая Страховая 1')
        notes_pos = content.find('Тестовое примечание для компании 1')
        
        # Примечания должны идти после названия компании
        self.assertGreater(notes_pos, company_pos)
        
        # Проверяем стилизацию примечаний
        self.assertContains(response, 'alert alert-info')
        self.assertContains(response, 'bi-info-circle')
        
        # Проверяем, что для компании без примечаний раздел не отображается
        self.assertNotContains(response, 'Примечания:</strong>\n                                                    <div class="mt-1"></div>')

    def test_company_totals_for_multiyear_offers(self):
        """
        Тест 5: Проверка отображения итоговых сумм для многолетних предложений
        Требования: 3.1, 3.2
        """
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем наличие строки "Итого" для многолетних предложений
        self.assertContains(response, 'Итого')
        self.assertContains(response, 'company-total-row')
        
        # Проверяем расчет итоговых сумм
        company_totals = self.summary.get_company_totals()
        self.assertIn('Тестовая Страховая 1', company_totals)
        
        company_data = company_totals['Тестовая Страховая 1']
        self.assertTrue(company_data['is_multiyear'])
        self.assertEqual(company_data['total_premium_1'], Decimal('102000.00'))  # 50000 + 52000
        self.assertEqual(company_data['total_premium_2'], Decimal('92000.00'))   # 45000 + 47000
        
        # Проверяем, что для одногодичных предложений итого не отображается
        single_year_company = company_totals.get('Альфа Страхование')
        if single_year_company:
            self.assertFalse(single_year_company['is_multiyear'])

    def test_mobile_responsiveness(self):
        """
        Тест 6: Проверка мобильной адаптивности
        Требования: 2.5, 3.6
        """
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Проверяем наличие responsive CSS
        self.assertContains(response, '@media (max-width: 768px)')
        self.assertContains(response, '@media (max-width: 576px)')
        
        # Проверяем адаптивные стили для примечаний
        self.assertContains(response, 'company-notes .alert')
        
        # Проверяем сохранение цветового кодирования на мобильных устройствах
        mobile_css = response.content.decode()
        self.assertIn('franchise-variant-1', mobile_css)
        self.assertIn('franchise-variant-2', mobile_css)
        self.assertIn('color: #0f5132 !important', mobile_css)
        self.assertIn('color: #052c65 !important', mobile_css)

    def test_form_validation_integration(self):
        """
        Тест 7: Интеграционная проверка валидации форм
        Требования: 1.4, 1.5
        """
        copy_url = reverse('summaries:copy_offer', args=[self.offer1.pk])
        
        # Тест с пустыми обязательными полями
        invalid_data = {
            'company_name': '',
            'insurance_year': '',
            'insurance_sum': '',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '',
        }
        
        response = self.client.post(copy_url, invalid_data)
        self.assertEqual(response.status_code, 200)
        
        # Проверяем, что форма содержит ошибки
        self.assertContains(response, 'text-danger')
        
        # Тест с некорректными числовыми значениями
        invalid_numeric_data = {
            'company_name': 'Тест Компания',
            'insurance_year': 0,  # Некорректный год
            'insurance_sum': '-1000',  # Отрицательная сумма
            'franchise_1': '0.00',
            'premium_with_franchise_1': '50000.00',
        }
        
        response = self.client.post(copy_url, invalid_numeric_data)
        self.assertEqual(response.status_code, 200)

    def test_javascript_functionality(self):
        """
        Тест 8: Проверка JavaScript функциональности
        Требования: 1.1, 1.2, 1.3
        """
        # Проверяем наличие JavaScript кода в шаблонах
        detail_response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        self.assertContains(detail_response, 'deleteOffer')
        self.assertContains(detail_response, 'changeStatus')
        
        copy_response = self.client.get(reverse('summaries:copy_offer', args=[self.offer1.pk]))
        self.assertContains(copy_response, 'togglePaymentsVariant1')
        self.assertContains(copy_response, 'togglePaymentsVariant2')
        self.assertContains(copy_response, 'addEventListener')

    def test_url_routing_integration(self):
        """
        Тест 9: Проверка интеграции URL маршрутов
        Требования: 1.1, 1.2
        """
        # Проверяем доступность всех URL
        urls_to_test = [
            ('summaries:summary_detail', [self.summary.pk]),
            ('summaries:copy_offer', [self.offer1.pk]),
            ('summaries:edit_offer', [self.offer1.pk]),
        ]
        
        for url_name, args in urls_to_test:
            url = reverse(url_name, args=args)
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302], 
                         f"URL {url_name} returned status {response.status_code}")

    def test_database_integrity_integration(self):
        """
        Тест 10: Проверка целостности базы данных при интеграции компонентов
        Требования: 1.4, 1.5, 1.6
        """
        # Проверяем ограничение уникальности
        with self.assertRaises(IntegrityError):
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=self.offer1.company_name,
                insurance_year=self.offer1.insurance_year,
                insurance_sum=Decimal('1000000.00'),
                franchise_1=Decimal('0.00'),
                premium_with_franchise_1=Decimal('50000.00')
            )
        
        # Проверяем каскадное удаление (создаем новое предложение для удаления)
        test_offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Тест Удаление',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00')
        )
        offer_id = test_offer.pk
        test_offer.delete()
        
        with self.assertRaises(InsuranceOffer.DoesNotExist):
            InsuranceOffer.objects.get(pk=offer_id)

    def test_performance_integration(self):
        """
        Тест 11: Проверка производительности интегрированных компонентов
        """
        # Создаем больше данных для тестирования производительности
        for i in range(10):
            InsuranceOffer.objects.create(
                summary=self.summary,
                company_name=f'Компания {i}',
                insurance_year=1,
                insurance_sum=Decimal('1000000.00'),
                franchise_1=Decimal('0.00'),
                premium_with_franchise_1=Decimal('50000.00')
            )
        
        # Проверяем, что страница загружается быстро даже с большим количеством данных
        import time
        start_time = time.time()
        
        response = self.client.get(reverse('summaries:summary_detail', args=[self.summary.pk]))
        
        end_time = time.time()
        load_time = end_time - start_time
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(load_time, 2.0, "Страница загружается слишком медленно")

    def test_error_handling_integration(self):
        """
        Тест 12: Проверка обработки ошибок в интегрированной системе
        Требования: 1.5, 1.6
        """
        # Тест с несуществующим предложением
        non_existent_url = reverse('summaries:copy_offer', args=[99999])
        response = self.client.get(non_existent_url)
        self.assertEqual(response.status_code, 404)
        
        # Тест с несуществующим сводом
        non_existent_summary_url = reverse('summaries:summary_detail', args=[99999])
        response = self.client.get(non_existent_summary_url)
        self.assertEqual(response.status_code, 404)

    def tearDown(self):
        """Очистка после тестов"""
        # Удаляем созданные объекты
        InsuranceOffer.objects.all().delete()
        InsuranceSummary.objects.all().delete()
        InsuranceRequest.objects.all().delete()
        User.objects.all().delete()


class SummariesUIRegressionTest(TestCase):
    """Регрессионные тесты для проверки существующей функциональности"""
    
    def setUp(self):
        """Настройка тестовых данных для регрессионных тестов"""
        # Создаем группы пользователей
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')
        
        self.user = User.objects.create_user(
            username='regressionuser',
            password='testpass123'
        )
        # Добавляем пользователя в группу
        self.user.groups.add(self.users_group)
        
        self.client = Client()
        self.client.login(username='regressionuser', password='testpass123')
        
        self.insurance_request = InsuranceRequest.objects.create(
            client_name='Регрессионный Тест',
            inn='9876543210',
            insurance_type='ОСАГО',
            branch='СПб',
            dfa_number='REG-2025-001',
            status='uploaded',
            created_by=self.user
        )
        
        self.summary = InsuranceSummary.objects.create(
            request=self.insurance_request,
            status='collecting'
        )

    def test_existing_summary_list_functionality(self):
        """Регрессионный тест: проверка работы списка сводов"""
        response = self.client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.summary.request.client_name)

    def test_existing_add_offer_functionality(self):
        """Регрессионный тест: проверка добавления предложений"""
        add_url = reverse('summaries:add_offer', args=[self.summary.pk])
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, 200)
        
        # Тестируем добавление предложения
        offer_data = {
            'company_name': 'Регрессионная Компания',
            'insurance_year': 1,
            'insurance_sum': '500000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '25000.00',
        }
        
        response = self.client.post(add_url, offer_data)
        self.assertEqual(response.status_code, 302)
        
        # Проверяем, что предложение создано
        self.assertTrue(
            InsuranceOffer.objects.filter(
                company_name='Регрессионная Компания'
            ).exists()
        )

    def test_existing_edit_offer_functionality(self):
        """Регрессионный тест: проверка редактирования предложений"""
        # Создаем предложение для редактирования
        offer = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Тест Редактирование',
            insurance_year=1,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0.00'),
            premium_with_franchise_1=Decimal('50000.00')
        )
        
        edit_url = reverse('summaries:edit_offer', args=[offer.pk])
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)
        
        # Тестируем обновление предложения
        updated_data = {
            'company_name': 'Обновленная Компания',
            'insurance_year': 1,
            'insurance_sum': '1200000.00',
            'franchise_1': '0.00',
            'premium_with_franchise_1': '55000.00',
        }
        
        response = self.client.post(edit_url, updated_data)
        self.assertEqual(response.status_code, 302)
        
        # Проверяем обновление
        offer.refresh_from_db()
        self.assertEqual(offer.company_name, 'Обновленная Компания')
        self.assertEqual(offer.insurance_sum, Decimal('1200000.00'))

    def test_existing_status_management(self):
        """Регрессионный тест: проверка управления статусами"""
        change_status_url = reverse('summaries:change_summary_status', args=[self.summary.pk])
        
        # Тестируем изменение статуса
        response = self.client.post(change_status_url, {'status': 'ready'})
        self.assertEqual(response.status_code, 200)
        
        # Проверяем JSON ответ
        json_response = response.json()
        self.assertTrue(json_response['success'])
        
        # Проверяем обновление в базе данных
        self.summary.refresh_from_db()
        self.assertEqual(self.summary.status, 'ready')

    def tearDown(self):
        """Очистка после регрессионных тестов"""
        InsuranceOffer.objects.all().delete()
        InsuranceSummary.objects.all().delete()
        InsuranceRequest.objects.all().delete()
        User.objects.all().delete()
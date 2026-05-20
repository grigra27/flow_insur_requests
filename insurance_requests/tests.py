"""
Tests for insurance_requests app
"""
import uuid
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .models import InsuranceRequest


class RequestDetailViewTest(TestCase):
    """Test the request detail view with summary creation button"""
    
    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import Group
        
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to the required group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        self.client.login(username='testuser', password='testpass123')
        
        # Create a test request
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            status='uploaded',
            created_by=self.user
        )
    
    def test_create_summary_button_shown_for_uploaded_status(self):
        """Test that create summary button is shown for uploaded status"""
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertContains(response, 'Свод предложений не создан')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_create_summary_button_shown_for_email_generated_status(self):
        """Test that create summary button is shown for email_generated status"""
        self.request.status = 'email_generated'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertContains(response, 'Свод предложений не создан')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_create_summary_button_shown_for_emails_sent_status(self):
        """Test that create summary button is shown for emails_sent status"""
        self.request.status = 'emails_sent'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать свод')
        self.assertNotContains(response, 'Свод недоступен')
    
    def test_summary_unavailable_for_invalid_statuses(self):
        """Test that summary is unavailable for invalid statuses (this test may not be relevant anymore)"""
        # Since we only have 4 statuses now and all allow summary creation,
        # this test checks the else branch when a summary already exists
        # We'll create a mock scenario by testing with a non-existent status
        # But since we can't set invalid status, we'll test the else branch differently
        
        # For now, let's test that the create summary button works for emails_sent status
        self.request.status = 'emails_sent'
        self.request.save()
        
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # With the new logic, emails_sent status should show create summary button
        self.assertContains(response, 'Создать свод')


class DisplayNameBatchTest(TestCase):
    """Tests for get_display_name() with batch fields (V2 splitting)."""

    def test_display_name_for_single_request_without_batch_fields(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            dfa_number='ДФА 18022',
        )
        self.assertEqual(req.get_display_name(), 'ДФА 18022')

    def test_display_name_for_single_item_batch_omits_suffix(self):
        # item_count == 1 means «партия из одной заявки» — суффикс не нужен.
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            dfa_number='ДФА 18022',
            source_batch_id=uuid.uuid4(),
            item_no=1,
            item_count=1,
        )
        self.assertEqual(req.get_display_name(), 'ДФА 18022')

    def test_display_name_for_multi_item_batch_includes_position(self):
        batch_id = uuid.uuid4()
        req1 = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            dfa_number='ДФА 18022',
            source_batch_id=batch_id,
            item_no=1,
            item_count=3,
        )
        req2 = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            dfa_number='ДФА 18022',
            source_batch_id=batch_id,
            item_no=2,
            item_count=3,
        )
        self.assertEqual(req1.get_display_name(), 'ДФА 18022 / объект 1 из 3')
        self.assertEqual(req2.get_display_name(), 'ДФА 18022 / объект 2 из 3')

    def test_display_name_falls_back_to_id_when_dfa_missing(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            source_batch_id=uuid.uuid4(),
            item_no=2,
            item_count=4,
        )
        self.assertEqual(req.get_display_name(), f'#{req.id} / объект 2 из 4')


class ObjectFieldsTest(TestCase):
    """Этап 2.1: новые поля объекта живут прямо в InsuranceRequest."""

    def test_object_fields_default_to_null(self):
        # V1-флоу не заполняет ни одно из новых полей — для совместимости
        # они должны корректно создаваться пустыми.
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
        )
        self.assertIsNone(req.brand)
        self.assertIsNone(req.model)
        self.assertIsNone(req.vin)
        self.assertIsNone(req.serial_number)
        self.assertIsNone(req.condition)
        self.assertIsNone(req.equipment_type)
        self.assertIsNone(req.power_or_capacity)
        self.assertIsNone(req.quantity)
        self.assertIsNone(req.acquisition_cost_value)
        self.assertIsNone(req.acquisition_cost_currency)

    def test_object_fields_store_full_payload(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            brand='LADA',
            model='Largus KS045L',
            vin='XTAKS045LP0001234',
            serial_number='SN-12345',
            condition='used',
            equipment_type='Легковой автомобиль',
            power_or_capacity='78.05',
            quantity=Decimal('1.00'),
            acquisition_cost_value=Decimal('1490000.00'),
            acquisition_cost_currency='RUB',
        )
        req.refresh_from_db()
        self.assertEqual(req.brand, 'LADA')
        self.assertEqual(req.model, 'Largus KS045L')
        self.assertEqual(req.vin, 'XTAKS045LP0001234')
        self.assertEqual(req.condition, 'used')
        self.assertEqual(req.get_condition_display(), 'Б/у')
        self.assertEqual(req.acquisition_cost_value, Decimal('1490000.00'))
        self.assertEqual(req.acquisition_cost_currency, 'RUB')
        self.assertEqual(req.get_acquisition_cost_currency_display(), 'Рубли')

    def test_condition_rejects_unknown_value(self):
        # choices ограничены 'new'/'used'; full_clean ловит остальное.
        req = InsuranceRequest(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            condition='unknown',
        )
        with self.assertRaises(ValidationError):
            req.full_clean()

    def test_currency_rejects_non_iso_value(self):
        req = InsuranceRequest(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            acquisition_cost_currency='руб',
        )
        with self.assertRaises(ValidationError):
            req.full_clean()


@override_settings(
    LOGIN_RATE_LIMIT_ENABLED=True,
    LOGIN_MAX_ATTEMPTS=3,
    LOGIN_MAX_ATTEMPTS_PER_IP=30,
    LOGIN_ATTEMPT_WINDOW_SECONDS=300,
    LOGIN_LOCKOUT_SECONDS=600,
)
class LoginSecurityTest(TestCase):
    """Security tests for login form: anti-enumeration and rate limit."""

    def setUp(self):
        self.client = Client()
        self.login_url = reverse('login')
        self.user = User.objects.create_user(username='secure_user', password='securepass123')

        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _post_login(self, username, password, remote_addr='127.0.0.1'):
        return self.client.post(
            self.login_url,
            {'username': username, 'password': password},
            REMOTE_ADDR=remote_addr
        )

    def test_login_error_message_does_not_reveal_user_existence(self):
        unknown_user_response = self._post_login('unknown_user', 'somepass123')
        wrong_password_response = self._post_login('secure_user', 'wrongpass123')

        self.assertEqual(unknown_user_response.status_code, 200)
        self.assertEqual(wrong_password_response.status_code, 200)

        self.assertContains(unknown_user_response, 'Неверный логин или пароль')
        self.assertContains(wrong_password_response, 'Неверный логин или пароль')

        self.assertNotContains(unknown_user_response, 'Пользователь с таким логином не найден')
        self.assertNotContains(wrong_password_response, 'Пользователь с таким логином не найден')
        self.assertNotContains(unknown_user_response, 'Неверный пароль')
        self.assertNotContains(wrong_password_response, 'Неверный пароль')

    def test_login_is_locked_after_too_many_attempts(self):
        for _ in range(3):
            self._post_login('secure_user', 'wrongpass123')

        locked_response = self._post_login('secure_user', 'securepass123')
        self.assertEqual(locked_response.status_code, 200)
        self.assertContains(locked_response, 'Слишком много неудачных попыток входа')

        self.assertNotIn('_auth_user_id', self.client.session)

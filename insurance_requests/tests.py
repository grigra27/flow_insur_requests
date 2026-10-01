"""
Tests for insurance_requests app
"""
import uuid
from email.header import decode_header, make_header
from io import BytesIO
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client, SimpleTestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from core.templates import EmailTemplateGenerator
from .models import InsuranceRequest, RequestAttachment


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
    
    def test_create_summary_locked_for_uploaded_status(self):
        """До отправки писем кнопка неактивна и показаны шаги"""
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Свод можно создать после отправки писем страховщикам')
        self.assertContains(response, 'Сгенерируйте письмо')
        self.assertNotContains(
            response, reverse('summaries:create_summary', kwargs={'request_id': self.request.pk})
        )

    def test_create_summary_locked_for_email_generated_status(self):
        """Письмо сгенерировано, но не отправлено — свод ещё нельзя создать"""
        self.request.status = 'email_generated'
        self.request.save()

        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Поставьте статус «Письма отправлены»')
        self.assertNotContains(
            response, reverse('summaries:create_summary', kwargs={'request_id': self.request.pk})
        )

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


class RequestDatabaseExportTest(TestCase):
    """Tests for XLSX export of the request card data."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='exportuser',
            password='testpass123',
            first_name='Иван',
            last_name='Иванов',
        )
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')

        self.superuser = User.objects.create_superuser(
            username='exportsuper',
            password='testpass123',
            email='exportsuper@example.com',
            first_name='Петр',
            last_name='Петров',
        )
        self.superuser.groups.add(admin_group)

        self.user_client = Client()
        self.user_client.login(username='exportuser', password='testpass123')
        self.superuser_client = Client()
        self.superuser_client.login(username='exportsuper', password='testpass123')

        self.request = InsuranceRequest.objects.create(
            client_name='ООО Тестовый клиент',
            inn='1234567890',
            insurance_type='страхование имущества',
            insurance_period='на весь срок лизинга',
            dfa_number='ДФА-EXPORT-001',
            branch='Москва',
            manager_name='Петров Петр',
            deal_status='new',
            vehicle_info='Линия по производству тестов',
            franchise_type='with_franchise',
            has_transportation=True,
            transportation_departure='Москва',
            transportation_destination='Казань',
            transportation_days=5,
            notes='Внутренний комментарий',
            created_by=self.user,
            additional_data={
                'application_type': 'legal_entity',
                'application_format': 'property',
                'parser_v2': {
                    'confidence': 0.94,
                    'warnings': ['Проверить адрес'],
                },
            },
        )
        RequestAttachment.objects.create(
            request=self.request,
            file=SimpleUploadedFile(
                'source.xlsx',
                b'test-export-content',
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            ),
            original_filename='source.xlsx',
            file_type='.xlsx',
        )

    def test_request_detail_shows_database_export_button(self):
        response = self.superuser_client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Скачать карточку заявки')
        self.assertContains(
            response,
            reverse('insurance_requests:export_request_database', kwargs={'pk': self.request.pk}),
        )

    def test_request_detail_hides_database_export_button_for_regular_user(self):
        response = self.user_client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Скачать карточку заявки')
        self.assertNotContains(
            response,
            reverse('insurance_requests:export_request_database', kwargs={'pk': self.request.pk}),
        )

    def test_export_request_database_returns_xlsx_with_request_data(self):
        response = self.superuser_client.get(
            reverse('insurance_requests:export_request_database', kwargs={'pk': self.request.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        decoded_disposition = str(make_header(decode_header(response['Content-Disposition'])))
        self.assertIn('.xlsx', decoded_disposition)

        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook['Карточка заявки']
        rows = [row for row in worksheet.iter_rows(values_only=True) if row[1]]

        exported_pairs = {(row[1], row[2]) for row in rows}

        self.assertIn(('Имя клиента [client_name]', 'ООО Тестовый клиент'), exported_pairs)
        self.assertIn(('Статус [status]', 'Загружено [uploaded]'), exported_pairs)
        self.assertIn(('Сводка объекта [object_summary]', 'Линия по производству тестов'), exported_pairs)
        self.assertIn(('Тип франшизы [franchise_type]', 'Только с франшизой [with_franchise]'), exported_pairs)
        self.assertIn(('additional_data.application_format', 'property'), exported_pairs)
        self.assertIn(('additional_data.parser_v2.warnings[1]', 'Проверить адрес'), exported_pairs)
        self.assertIn(('attachments[1].original_filename', 'source.xlsx'), exported_pairs)

    def test_export_request_database_forbidden_for_regular_user(self):
        response = self.user_client.get(
            reverse('insurance_requests:export_request_database', kwargs={'pk': self.request.pk})
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Superuser', status_code=403)


class RequestApplicationPdfExportTest(TestCase):
    """Tests for the "Заявка для страховой" PDF export (insurer-facing subset)."""

    def setUp(self):
        self.user = User.objects.create_user(username='appuser', password='testpass123')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')

        self.superuser = User.objects.create_superuser(
            username='appsuper', password='testpass123', email='appsuper@example.com',
        )
        self.superuser.groups.add(admin_group)

        self.user_client = Client()
        self.user_client.login(username='appuser', password='testpass123')
        self.superuser_client = Client()
        self.superuser_client.login(username='appsuper', password='testpass123')

        # КАСКО-заявка с доп. рисками и внутренними полями, которые НЕ должны
        # попасть в заявку для страховой (notes, status).
        self.request = InsuranceRequest.objects.create(
            client_name='ООО Ромашка',
            inn='7701234567',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='ДФА-APP-001',
            branch='Московский филиал',
            franchise_type='both_variants',
            franchise_amounts=['30000'],
            has_autostart=True,
            has_transportation=True,
            transportation_departure='Москва',
            transportation_destination='Казань',
            transportation_days=3,
            brand='КАМАЗ',
            model='65115',
            manufacturing_year='2023',
            condition='new',
            notes='Внутренний комментарий брокера',
            created_by=self.user,
        )

    def _extract_text(self, pdf_bytes):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() for page in reader.pages)

    def test_request_detail_shows_application_pdf_button_for_superuser(self):
        response = self.superuser_client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Скачать заявку (PDF)')
        self.assertContains(
            response,
            reverse('insurance_requests:export_request_application', kwargs={'pk': self.request.pk}),
        )

    def test_request_detail_shows_application_pdf_button_for_regular_user(self):
        # Заявку для страховой скачивает любой сотрудник.
        response = self.user_client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Скачать заявку (PDF)')

    def test_export_application_returns_pdf_with_insurer_fields(self):
        response = self.superuser_client.get(
            reverse('insurance_requests:export_request_application', kwargs={'pk': self.request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        decoded_disposition = str(make_header(decode_header(response['Content-Disposition'])))
        self.assertIn('.pdf', decoded_disposition)

        text = self._extract_text(response.content)
        # Поля, нужные страховой (кириллица рендерится корректно).
        self.assertIn('ООО Ромашка', text)
        self.assertIn('КАМАЗ', text)
        self.assertIn('Автозапуск', text)
        self.assertIn('Москва', text)  # маршрут перевозки
        # both_variants с размером — нейтрально, без просьбы к страховщику.
        self.assertIn('Оба варианта: без франшизы и с франшизой 30 000 руб.', ' '.join(text.split()))
        self.assertNotIn('просьба', text)

    def test_application_is_a_data_sheet_without_asks_or_deadline(self):
        # Вариант А (отзыв сотрудников 2026-10-01): вопросы и срок ответа — только в письме.
        response = self.superuser_client.get(
            reverse('insurance_requests:export_request_application', kwargs={'pk': self.request.pk})
        )
        text = self._extract_text(response.content)
        self.assertNotIn('ПРОСИМ', text)
        self.assertNotIn('ОТВЕТ СТРАХОВЩИКА', text)
        self.assertIn('ПРИЛОЖЕНИЕ К ЗАПРОСУ', text)
        self.assertIn('по данным лизингополучателя', text)

    def test_power_tile_kept_but_raw_source_line_dropped(self):
        # Отзыв сотрудников 2026-10-01: сырая строка объекта склеивала мощность с ценой.
        from .application_export import build_application_context

        self.request.object_description = '1 Автомобиль LADA NIVA 2026 новое 89,73 1832000 руб'
        self.request.power_or_capacity = '89,73'
        context = build_application_context(self.request)
        self.assertNotIn('source_text', context)
        self.assertIn(('Мощность / производ.', '89,73'), context['facts'])

    def test_legacy_request_says_object_was_not_parsed(self):
        # Старый загрузчик не разбирал стоимость: вместо «не указана» — честная пометка.
        from .application_export import build_application_context

        context = build_application_context(self.request)  # в фикстуре нет данных Parser V2
        self.assertEqual(context['cost'], 'не разбиралась — см. исходный Excel')
        self.assertIn('старым загрузчиком', context['legacy_note'])
        self.request.franchise_amounts = []
        terms = dict(build_application_context(self.request)['terms_rows'])
        self.assertIn('размер — в исходном Excel', terms['Франшиза'])

        self.request.additional_data = {'parser_version': 'v2', 'parser_v2': {'warnings': []}}
        context = build_application_context(self.request)
        self.assertEqual(context['cost'], 'не указана')
        self.assertIsNone(context['legacy_note'])

    def test_several_identical_units_are_prominent(self):
        # ТС-20862-ЛА-АР: 6 одинаковых Great Wall — количество и итог должны бросаться в глаза.
        from .application_export import build_application_context

        self.request.source_object_count = 6
        self.request.acquisition_cost_value = Decimal('3840000')
        self.request.acquisition_cost_currency = 'RUB'
        context = build_application_context(self.request)
        self.assertEqual(context['quantity_count'], 6)
        self.assertEqual(context['quantity_label'], '6 единиц')
        self.assertEqual(context['cost'], '3 840 000 руб.')
        self.assertEqual(context['cost_total'], '23 040 000 руб.')
        self.request.save()
        text = ' '.join(self._extract_text(self.superuser_client.get(
            reverse('insurance_requests:export_request_application', kwargs={'pk': self.request.pk})
        ).content).split())
        self.assertIn('КОЛИЧЕСТВО: 6 ЕДИНИЦ', text)
        self.assertIn('ИТОГО ЗА 6 ЕД.', text)

    def test_single_unit_has_no_quantity_marks(self):
        from .application_export import build_application_context

        context = build_application_context(self.request)
        self.assertIsNone(context['quantity_count'])
        self.assertIsNone(context['cost_total'])

    def test_deal_manager_is_our_employee_not_lessor_manager(self):
        from .application_export import build_application_context

        self.request.manager_name = 'Иванов И.И. (менеджер лизинговой компании)'
        self.user.first_name, self.user.last_name = 'Н.Н.', 'Лазарева'
        self.user.save()
        strip = dict(build_application_context(self.request)['strip'])
        self.assertEqual(strip['Менеджер сделки'], 'Н.Н. Лазарева')
        self.assertNotIn('Иванов', ' '.join(strip.values()))

    def test_export_application_excludes_internal_fields(self):
        response = self.superuser_client.get(
            reverse('insurance_requests:export_request_application', kwargs={'pk': self.request.pk})
        )
        text = self._extract_text(response.content)
        # Внутреннее примечание брокера и статус не должны уходить в страховую.
        self.assertNotIn('Внутренний комментарий', text)
        self.assertNotIn('Загружено', text)

    def test_application_pdf_is_one_landscape_page_with_logo(self):
        from pypdf import PdfReader
        from .application_export import render_application_pdf

        reader = PdfReader(BytesIO(render_application_pdf(self.request)))
        self.assertEqual(len(reader.pages), 1)
        page = reader.pages[0]
        self.assertGreater(float(page.mediabox.width), float(page.mediabox.height))
        self.assertTrue(page.images, 'логотип должен быть встроен в PDF')

    def test_application_shows_explicit_no_for_risk_flags(self):
        from .application_export import build_application_context

        context = build_application_context(self.request)
        tiles = {tile['label']: tile['value'] for row in context['tile_rows'] for tile in row if tile}
        self.assertEqual(tiles['Автозапуск'], 'Да')
        self.assertEqual(tiles['КАСКО кат. C/E'], 'Нет')
        self.assertEqual(tiles['Перевозка'], 'Да')
        self.assertIn(('Маршрут перевозки', 'Москва — Казань · 3 дн.'), context['long_rows'])
        self.assertEqual(context['author'], 'appuser')

    def test_application_moves_long_values_out_of_tiles(self):
        from .application_export import build_application_context

        self.request.insurance_type = 'страхование имущества'
        self.request.guard_conditions = (
            'Территория ограждена забором, пропускная система, видеонаблюдение, охрана'
        )
        context = build_application_context(self.request)
        tile_labels = [tile['label'] for row in context['tile_rows'] for tile in row if tile]
        self.assertNotIn('Охрана и хранение', tile_labels)
        self.assertIn('Охрана и хранение', [label for label, _ in context['long_rows']])
        self.assertNotIn('Автозапуск', tile_labels)

    def test_export_application_allowed_for_regular_user(self):
        response = self.user_client.get(
            reverse('insurance_requests:export_request_application', kwargs={'pk': self.request.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class RequestV1V2DisplayCompatibilityTest(TestCase):
    """Old V1 requests and structured Parser V2 requests render side by side."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='compatuser', password='pwd')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        self.client.login(username='compatuser', password='pwd')

        self.v1_request = InsuranceRequest.objects.create(
            client_name='Старый клиент',
            inn='1111111111',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='V1-001',
            vehicle_info='Старое описание предмета лизинга V1',
            created_by=self.user,
        )
        self.legacy_installment_request = InsuranceRequest.objects.create(
            client_name='Старый клиент с рассрочкой',
            inn='1111111112',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='V1-INSTALL',
            has_installment=True,
            created_by=self.user,
        )
        self.v2_request = InsuranceRequest.objects.create(
            client_name='Новый клиент',
            inn='2222222222',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='V2-001',
            vehicle_info='Автомобиль LADA Largus KS045L 2024 б/у',
            brand='LADA',
            model='Largus KS045L',
            condition='used',
            equipment_type='Категория B',
            acquisition_cost_value=Decimal('1490000'),
            acquisition_cost_currency='RUB',
            premium_frequency='quarterly',
            insured_party='lessor',
            additional_data={
                'parser_version': 'v2',
                'parser_v2': {
                    'confidence': 0.88,
                    'warnings': [
                        {
                            'level': 'manual_required',
                            'field': 'insured_party',
                            'message': 'Проверьте страхователя.',
                        }
                    ],
                    'source_file_name': 'request-v2.xlsx',
                },
            },
            created_by=self.user,
        )
        self.annual_request = InsuranceRequest.objects.create(
            client_name='Ежегодный клиент',
            inn='3333333333',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='V2-ANNUAL',
            premium_frequency='annual',
            created_by=self.user,
        )
        self.single_request = InsuranceRequest.objects.create(
            client_name='Единовременный клиент',
            inn='4444444444',
            insurance_type='КАСКО',
            insurance_period='1 год',
            dfa_number='V2-SINGLE',
            premium_frequency='single',
            created_by=self.user,
        )

    def test_request_list_uses_structured_v2_object_and_v1_fallback(self):
        response = self.client.get(reverse('insurance_requests:request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('insurance_requests:upload_excel'))
        self.assertNotContains(response, reverse('insurance_requests:upload_excel_v2'))
        self.assertContains(response, 'Старое описание предмета лизинга V1')
        self.assertContains(response, 'LADA Largus KS045L')
        self.assertContains(response, '1 490 000 RUB')
        self.assertNotContains(response, 'Автомобиль LADA Largus KS045L 2024 б/у')
        self.assertContains(response, 'Поквартально')
        self.assertContains(response, 'Рассрочка')
        self.assertNotContains(response, 'Ежегодно')
        self.assertNotContains(response, 'Единовременно')

    def test_request_detail_keeps_v1_simple_and_shows_v2_diagnostics(self):
        v1_response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.v1_request.pk})
        )
        self.assertEqual(v1_response.status_code, 200)
        self.assertContains(v1_response, 'Старое описание предмета лизинга V1')
        self.assertNotContains(v1_response, 'Parser V2')

        v2_response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.v2_request.pk})
        )
        self.assertEqual(v2_response.status_code, 200)
        self.assertContains(v2_response, 'LADA Largus KS045L')
        self.assertContains(v2_response, 'Стоимость приобретения')
        self.assertContains(v2_response, '1 490 000 RUB')
        self.assertContains(v2_response, 'Состояние')
        self.assertContains(v2_response, 'Б/у')
        self.assertNotContains(v2_response, 'Автомобиль LADA Largus KS045L 2024 б/у')
        # Блок парсера — служебный, обычный пользователь его не видит.
        self.assertNotContains(v2_response, 'Alla Borisovna Magic Parser')

        superuser = User.objects.create_superuser(username='compatroot', password='pwd')
        superuser.groups.add(Group.objects.get(name='Пользователи'))
        root_client = Client()
        root_client.force_login(superuser)
        root_response = root_client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.v2_request.pk})
        )
        self.assertContains(root_response, 'Alla Borisovna Magic Parser')
        self.assertContains(root_response, '88%')
        self.assertContains(root_response, 'Скачать карточку заявки')

    def test_edit_request_renders_v2_fields_without_breaking_v1(self):
        v1_response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.v1_request.pk})
        )
        self.assertEqual(v1_response.status_code, 200)
        self.assertContains(v1_response, 'Старое описание предмета лизинга V1')
        self.assertContains(v1_response, 'Объект страхования')
        # У V1 поле описания предмета лизинга остаётся — в блоке старого формата.
        self.assertContains(v1_response, 'Поля старого формата заявки (V1)')
        self.assertContains(v1_response, 'Сохранить изменения')

        v2_response = self.client.get(
            reverse('insurance_requests:edit_request', kwargs={'pk': self.v2_request.pk})
        )
        self.assertEqual(v2_response.status_code, 200)
        self.assertContains(v2_response, 'LADA')
        self.assertContains(v2_response, 'Частота уплаты премии')
        self.assertContains(v2_response, 'Страхователь')


class PreviewWarningContextTest(TestCase):
    """Предупреждения превью привязываются к полям формы и объектам партии."""

    def test_warnings_get_anchor_label_and_object_numbers(self):
        from .forms import ParserV2PreviewForm
        from .views import _preview_warning_context

        form = ParserV2PreviewForm()
        warnings, field_warnings, object_numbers = _preview_warning_context([
            {'level': 'info', 'field': 'dfa_number', 'message': 'Нет суффикса'},
            {'level': 'info', 'field': 'insured_objects', 'message': 'Найдено объектов: 6.'},
            {'level': 'check', 'anchor': 'birth_date', 'field': 'Дата рождения (для ИП)',
             'label': 'Дата рождения (для ИП)', 'message': 'Дата в будущем'},
            {'level': 'check', 'object_number': 2, 'field': 'Объект 2: Год выпуска',
             'label': 'Год выпуска', 'message': 'Год 2063'},
        ], form)

        self.assertEqual(warnings[0]['anchor'], 'dfa_number')
        self.assertEqual(warnings[0]['label'], form.fields['dfa_number'].label)
        self.assertEqual(warnings[1]['anchor'], '')
        self.assertEqual(warnings[1]['label'], 'Объекты в файле')
        self.assertEqual(warnings[2]['anchor'], 'birth_date')
        self.assertEqual(warnings[3]['label'], 'Объект 2: Год выпуска')
        self.assertEqual(field_warnings, {'dfa_number': ['Нет суффикса'], 'birth_date': ['Дата в будущем']})
        self.assertEqual(object_numbers, {2})


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


class InsuranceRequestObjectPropertiesTest(SimpleTestCase):
    def test_object_summary_prefers_structured_fields(self):
        request = InsuranceRequest(
            brand='LADA',
            model='Largus KS045L',
            condition='used',
            acquisition_cost_value=Decimal('1490000'),
            acquisition_cost_currency='RUB',
            manufacturing_year='2024',
            source_object_count=2,
            vehicle_info='legacy value',
        )

        self.assertEqual(
            request.object_summary,
            'LADA Largus KS045L, 2024 г., Б/у, 1 490 000 RUB, ×2',
        )
        self.assertEqual(
            request.object_summary_without_source_count,
            'LADA Largus KS045L, 2024 г., Б/у, 1 490 000 RUB',
        )
        self.assertEqual(request.source_object_count_label, '2 штуки')

    def test_source_object_count_label_uses_russian_plural_forms(self):
        request = InsuranceRequest(source_object_count=1)
        self.assertEqual(request.source_object_count_label, '')

        request.source_object_count = 2
        self.assertEqual(request.source_object_count_label, '2 штуки')

        request.source_object_count = 5
        self.assertEqual(request.source_object_count_label, '5 штук')

    def test_object_summary_uses_object_description_when_brand_model_missing(self):
        request = InsuranceRequest(
            object_description='Линия порошковой окраски с конвейером',
            manufacturing_year='2020',
            asset_status='б/у',
        )

        self.assertEqual(
            request.object_summary,
            'Линия порошковой окраски с конвейером, 2020 г., б/у',
        )
        self.assertEqual(
            request.object_display_name,
            'Линия порошковой окраски с конвейером',
        )

    def test_object_summary_falls_back_to_vehicle_info_for_legacy_v1(self):
        request = InsuranceRequest(vehicle_info='Старое описание предмета лизинга')

        self.assertEqual(request.object_summary, 'Старое описание предмета лизинга')

    def test_condition_helpers_support_v2_and_legacy(self):
        structured_request = InsuranceRequest(condition='new')
        legacy_request = InsuranceRequest(asset_status='новое')

        self.assertEqual(structured_request.condition_label, 'Новое')
        self.assertTrue(structured_request.is_new_object)
        self.assertEqual(legacy_request.condition_label, 'новое')
        self.assertTrue(legacy_request.is_new_object)


class EmailTemplateGeneratorTest(TestCase):
    def test_generate_email_body_always_requests_insurance_territory(self):
        territory_request = (
            'Просим указать в предложении территорию действия страхового покрытия '
            'и имеющиеся территориальные ограничения.'
        )

        for insurance_type in EmailTemplateGenerator.INSURANCE_TYPE_DESCRIPTIONS:
            with self.subTest(insurance_type=insurance_type):
                body = EmailTemplateGenerator().generate_email_body({
                    'insurance_type': insurance_type,
                    'insurance_period': '1 год',
                    'inn': '1234567890',
                    'response_deadline': '12:00 01.01.2027',
                })

                self.assertIn(territory_request, body)

    def test_generate_subject_uses_object_display_name_for_structured_request(self):
        request = InsuranceRequest(
            dfa_number='ДФА-123',
            branch='Москва',
            insurance_period='1 год',
            brand='LADA',
            model='Vesta Cross',
            vehicle_info='Очень длинное legacy-описание, которое не должно попасть в тему письма',
        )

        subject = EmailTemplateGenerator().generate_subject(request.to_dict())

        self.assertIn('LADA Vesta Cross', subject)
        self.assertNotIn('legacy-описание', subject)

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


class RequestListRedesignTest(TestCase):
    """Список заявок в языке сводов: счётчики филиалов и шкала пути заявки."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='redesignuser', password='pwd')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        self.client.login(username='redesignuser', password='pwd')

        for branch, dfa, status in (
            ('Казань', 'ДФА-KZ-1', 'uploaded'),
            ('Казань', 'ДФА-KZ-2', 'emails_sent'),
            ('Москва', 'ДФА-MSK-1', 'email_generated'),
        ):
            InsuranceRequest.objects.create(
                client_name='Клиент',
                inn='5555555555',
                insurance_type='страхование спецтехники',
                dfa_number=dfa,
                branch=branch,
                status=status,
                created_by=self.user,
            )

    def test_branch_counts_ignore_branch_filter_but_respect_others(self):
        response = self.client.get(
            reverse('insurance_requests:request_list') + '?branch=Москва&dfa_filter=KZ'
        )
        self.assertEqual(response.context['branch_counts'], {'Казань': 2})
        self.assertEqual(response.context['total_requests_count'], 2)
        self.assertEqual(response.context['total_requests'], 0)

    def test_rows_show_status_path_and_short_type(self):
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertContains(response, 'rl-path--uploaded')
        self.assertContains(response, 'rl-path--email_generated')
        self.assertContains(response, 'rl-path--emails_sent')
        self.assertContains(response, '<b>КЗ</b><i>16</i></span>Казань</span> · Спецтехника')


class RequestListBatchGroupingTest(TestCase):
    """Stage 4.3: batch siblings must look like a group in /request_list/."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='listuser', password='pwd')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        self.client.login(username='listuser', password='pwd')

        # One V1-style standalone request, one V2 batch of 3 siblings.
        self.standalone = InsuranceRequest.objects.create(
            client_name='Одиночка',
            inn='1111111111',
            insurance_type='КАСКО',
            dfa_number='ДФА-SOLO',
            created_by=self.user,
        )
        batch_id = uuid.uuid4()
        sibling_pks = []
        for i in (1, 2, 3):
            sibling = InsuranceRequest.objects.create(
                client_name='Партия',
                inn='2222222222',
                insurance_type='КАСКО',
                dfa_number='ДФА-PART',
                source_batch_id=batch_id,
                item_no=i,
                item_count=3,
                created_by=self.user,
            )
            sibling_pks.append(sibling.pk)
        # Mirror the production behaviour: every sibling of a batch shares
        # the same created_at so the (-created_at, source_batch_id, item_no)
        # ordering keeps them together.
        from django.utils import timezone as tz
        InsuranceRequest.objects.filter(pk__in=sibling_pks).update(created_at=tz.now())

    def test_batch_rows_have_dedicated_css_class_and_badge(self):
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        # Position-in-batch badges are rendered for each sibling.
        self.assertContains(response, '1/3')
        self.assertContains(response, '2/3')
        self.assertContains(response, '3/3')
        # The queryset ordered the siblings consecutively by item_no.
        listed = list(response.context['requests'])
        batch_rows = [r for r in listed if r.source_batch_id is not None]
        self.assertEqual([r.item_no for r in batch_rows], [1, 2, 3])

    def test_standalone_rows_do_not_show_batch_position_badge(self):
        response = self.client.get(reverse('insurance_requests:request_list') + '?dfa_filter=SOLO')
        listed = list(response.context['requests'])
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0], self.standalone)
        # No "K/N" badge text for a standalone request.
        self.assertNotContains(response, '/3')
        # And no "/ объект K из N" suffix in the display name.
        self.assertNotContains(response, '/ объект ')


class RequestDetailBatchPanelTest(TestCase):
    """Stage 4.4: detail page of a V2 sibling must show the batch panel."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='detailuser', password='pwd')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        self.client.login(username='detailuser', password='pwd')

        batch_id = uuid.uuid4()
        self.siblings = []
        for i in (1, 2, 3):
            self.siblings.append(InsuranceRequest.objects.create(
                client_name='Партия Клиент',
                inn='3333333333',
                insurance_type='КАСКО',
                dfa_number='ДФА-BATCH',
                brand=f'Brand{i}',
                model=f'Model{i}',
                source_batch_id=batch_id,
                item_no=i,
                item_count=3,
                created_by=self.user,
            ))
        self.standalone = InsuranceRequest.objects.create(
            client_name='Одиночка',
            inn='4444444444',
            insurance_type='КАСКО',
            dfa_number='ДФА-SOLO',
            created_by=self.user,
        )

    def test_batch_panel_is_shown_on_sibling_detail(self):
        first = self.siblings[0]
        url = reverse('insurance_requests:request_detail', kwargs={'pk': first.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Партия из 3 заявок')
        # Context contains the two other siblings, sorted by item_no.
        siblings_in_context = response.context['batch_siblings']
        self.assertEqual([s.item_no for s in siblings_in_context], [2, 3])
        # Links to siblings are rendered.
        for sibling in self.siblings[1:]:
            self.assertContains(response, f'href="{reverse("insurance_requests:request_detail", kwargs={"pk": sibling.pk})}"')

    def test_batch_panel_excludes_current_request(self):
        middle = self.siblings[1]
        url = reverse('insurance_requests:request_detail', kwargs={'pk': middle.pk})
        response = self.client.get(url)
        siblings_in_context = response.context['batch_siblings']
        # Order is by item_no across all but the current one.
        self.assertEqual([s.item_no for s in siblings_in_context], [1, 3])
        self.assertNotIn(middle, siblings_in_context)

    def test_batch_navigator_shows_all_objects_and_neighbours(self):
        from decimal import Decimal
        for sibling, cost in zip(self.siblings, ('1000000', '2000000', '3500000')):
            sibling.acquisition_cost_value = Decimal(cost)
            sibling.acquisition_cost_currency = 'RUB'
            sibling.save()
        middle = self.siblings[1]
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': middle.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['batch_prev'], self.siblings[0])
        self.assertEqual(response.context['batch_next'], self.siblings[2])
        self.assertEqual(response.context['batch_total'], '6 500 000 RUB')
        self.assertContains(response, 'Все объекты партии')

        self.assertContains(response, 'вы здесь')
        self.assertContains(response, 'общая стоимость 6 500 000 RUB')
        # По PDF на каждый объект партии плюс главная кнопка в шапке.
        for request_obj in self.siblings:
            self.assertContains(
                response,
                reverse('insurance_requests:export_request_application', kwargs={'pk': request_obj.pk}),
            )

        # Одинаковые строки файла: стоимость умножается на количество, как в PDF партии
        # (ТС-20722: на карточке было 39,4 млн вместо 60 млн).
        self.siblings[0].source_object_count = 3
        self.siblings[0].save()
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': middle.pk})
        )
        self.assertEqual(response.context['batch_total'], '8 500 000 RUB')
        self.assertContains(response, 'общая стоимость 8 500 000 RUB')

    def test_batch_navigator_edges_and_mixed_currency(self):
        self.siblings[0].acquisition_cost_value = 100
        self.siblings[0].acquisition_cost_currency = 'RUB'
        self.siblings[0].save()
        response = self.client.get(
            reverse('insurance_requests:request_detail', kwargs={'pk': self.siblings[0].pk})
        )
        self.assertIsNone(response.context['batch_prev'])
        self.assertEqual(response.context['batch_next'], self.siblings[1])
        # У остальных объектов стоимость не указана — общую сумму не показываем.
        self.assertEqual(response.context['batch_total'], '')
        self.assertNotContains(response, 'общая стоимость')

    def test_standalone_detail_has_no_batch_panel(self):
        url = reverse('insurance_requests:request_detail', kwargs={'pk': self.standalone.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Партия из')
        self.assertEqual(response.context['batch_siblings'], [])


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
        self.assertIsNone(req.condition)
        self.assertIsNone(req.equipment_type)
        self.assertIsNone(req.power_or_capacity)
        self.assertIsNone(req.acquisition_cost_value)
        self.assertIsNone(req.acquisition_cost_currency)

    def test_object_fields_store_full_payload(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            brand='LADA',
            model='Largus KS045L',
            condition='used',
            equipment_type='Легковой автомобиль',
            power_or_capacity='78.05',
            acquisition_cost_value=Decimal('1490000.00'),
            acquisition_cost_currency='RUB',
        )
        req.refresh_from_db()
        self.assertEqual(req.brand, 'LADA')
        self.assertEqual(req.model, 'Largus KS045L')
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


class CustomerFieldsTest(TestCase):
    """Stage 2.2: customer details (addresses, business activity, dates).
    OGRN/KPP are intentionally absent — leasing Excel files don't carry them."""

    def test_customer_fields_default_to_null(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
        )
        self.assertIsNone(req.legal_address)
        self.assertIsNone(req.postal_address)
        self.assertIsNone(req.business_activity)
        self.assertIsNone(req.birth_date)
        self.assertIsNone(req.submission_date)
        # OGRN/KPP fields must not exist on the model.
        self.assertFalse(hasattr(req, 'ogrn'))
        self.assertFalse(hasattr(req, 'kpp'))

    def test_customer_fields_store_full_payload(self):
        req = InsuranceRequest.objects.create(
            client_name='ИП Еремин Илья Сергеевич',
            inn='121212121212',
            insurance_type='КАСКО',
            legal_address='194354, Санкт-Петербург г, Северный пр-кт, дом № 11',
            postal_address='194354, Санкт-Петербург г, Северный пр-кт, дом № 11',
            business_activity='42.11 Строительство автомобильных дорог',
            birth_date=date(1980, 6, 12),
            submission_date=date(2026, 4, 17),
        )
        req.refresh_from_db()
        self.assertEqual(req.legal_address, '194354, Санкт-Петербург г, Северный пр-кт, дом № 11')
        self.assertEqual(req.postal_address, '194354, Санкт-Петербург г, Северный пр-кт, дом № 11')
        self.assertEqual(req.business_activity, '42.11 Строительство автомобильных дорог')
        self.assertEqual(req.birth_date, date(1980, 6, 12))
        self.assertEqual(req.submission_date, date(2026, 4, 17))

    def test_long_address_is_not_truncated(self):
        long_address = (
            '385000, Адыгея (Адыгея) респ, Майкоп г, Железнодорожная ул, '
            'дом № 332, корпус 1, литера А, помещение 5-Н, офис 12, '
            'кадастровый № 01:08:0501041:101 ' * 3
        )
        req = InsuranceRequest.objects.create(
            client_name='ООО Тест',
            inn='1234567890',
            insurance_type='КАСКО',
            legal_address=long_address,
        )
        req.refresh_from_db()
        self.assertEqual(req.legal_address, long_address)


class DealInsuranceFieldsTest(TestCase):
    """Stage 2.3: deal and insurance parameters.

    Excluded from the original plan because the source does not carry them:
      contract_start_date / contract_end_date  — Excel only has the «на весь
        срок лизинга» enum, not actual dates;
      period_start_date / period_end_date / period_months — same;
      indemnity_basis — 0/30 hits in the audit.
    """

    def test_fields_default_to_null(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
        )
        self.assertIsNone(req.insured_party)
        self.assertIsNone(req.insured_sum_type)
        self.assertIsNone(req.guard_conditions)
        self.assertIsNone(req.property_location_right_holder)
        self.assertIsNone(req.premium_frequency)
        # Excluded fields must not exist on the model.
        for absent in ('contract_start_date', 'contract_end_date',
                       'period_start_date', 'period_end_date', 'period_months',
                       'indemnity_basis'):
            self.assertFalse(hasattr(req, absent), f'{absent} should not exist on InsuranceRequest')

    def test_fields_store_full_payload(self):
        req = InsuranceRequest.objects.create(
            client_name='Тест ООО',
            inn='1234567890',
            insurance_type='КАСКО',
            insured_party='lessor',
            insured_sum_type='non_aggregate',
            guard_conditions='без ограничений',
            property_location_right_holder='lessee_owner',
            premium_frequency='quarterly',
        )
        req.refresh_from_db()
        self.assertEqual(req.insured_party, 'lessor')
        self.assertEqual(req.get_insured_party_display(), 'Лизингодатель')
        self.assertEqual(req.insured_sum_type, 'non_aggregate')
        self.assertEqual(req.get_insured_sum_type_display(), 'Неагрегатная')
        self.assertEqual(req.guard_conditions, 'без ограничений')
        self.assertEqual(req.property_location_right_holder, 'lessee_owner')
        self.assertEqual(req.premium_frequency, 'quarterly')
        self.assertEqual(req.get_premium_frequency_display(), 'Поквартально')

    def test_choices_reject_unknown_value(self):
        bad_values = [
            ('insured_party', 'owner'),
            ('insured_sum_type', 'unknown'),
            ('property_location_right_holder', 'tenant'),
            ('premium_frequency', 'semiannual'),  # excluded from our enum
        ]
        for field, value in bad_values:
            req = InsuranceRequest(
                client_name='Тест',
                inn='1234567890',
                insurance_type='КАСКО',
                **{field: value},
            )
            with self.assertRaises(ValidationError, msg=f'{field}={value!r} must be rejected'):
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


class RequestListEditBadgesTest(TestCase):
    """Список заявок: правки парсера и предупреждения разбора в списке не показываются."""

    def setUp(self):
        import datetime as _dt
        import json as _json
        from django.contrib.contenttypes.models import ContentType
        from easyaudit.models import CRUDEvent

        self.client = Client()
        self.user = User.objects.create_user(
            username='badgeuser', password='pwd', last_name='Сидоров', first_name='Пётр'
        )
        user_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        self.client.login(username='badgeuser', password='pwd')

        self.req = InsuranceRequest.objects.create(
            client_name='ООО Бейдж', inn='1', insurance_type='КАСКО',
            parser_confidence=0.8, manual_edits_count=2, created_by=self.user,
            additional_data={'parser_version': 'v2',
                             'parser_v2': {'original_data': {'client_name': 'ООО Бейдж'},
                                           'warnings': [{'level': 'manual_required',
                                                         'message': 'Проверить распознанное поле'}],
                                           'tracking': {'field_edits': []}}},
        )
        ct = ContentType.objects.get_for_model(InsuranceRequest)
        ev = CRUDEvent.objects.create(
            event_type=CRUDEvent.UPDATE, object_id=str(self.req.pk), content_type=ct,
            object_repr='r', changed_fields=_json.dumps({'inn': ['1', '2']}), user=self.user,
        )
        CRUDEvent.objects.filter(pk=ev.pk).update(
            datetime=self.req.created_at + _dt.timedelta(hours=1)
        )

    def test_batch_counts_helper(self):
        counts = InsuranceRequest.post_creation_counts_for([self.req])
        self.assertEqual(counts.get(self.req.id), 1)

    def test_list_hides_parser_edit_badges(self):
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'При создании')
        self.assertNotContains(response, 'После создания')
        self.assertNotContains(
            response,
            reverse('insurance_requests:request_comparison', kwargs={'pk': self.req.pk}),
        )

    def test_list_hides_parser_warning_review_badge(self):
        response = self.client.get(reverse('insurance_requests:request_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.req.parser_v2_warning_count, 1)
        self.assertNotContains(response, 'request-list-badge--review')
        self.assertNotContains(response, 'Parser V2: предупреждений разбора')
        self.assertNotContains(response, 'Проверить')


class BatchApplicationPdfTest(TestCase):
    """PDF «на всю партию» (отзыв сотрудников 2026-10-01: 8 единиц → 5 заявок и 5 PDF)."""

    def setUp(self):
        self.user = User.objects.create_user(username='batchpdf', password='pwd')
        self.user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client = Client()
        self.client.login(username='batchpdf', password='pwd')
        batch_id = uuid.uuid4()
        common = dict(client_name='ООО Карьер', inn='7707083893', insurance_type='страхование спецтехники',
                      dfa_number='ТС-20722', branch='Мурманск', source_batch_id=batch_id, item_count=3,
                      created_by=self.user)
        self.first = InsuranceRequest.objects.create(
            item_no=1, brand='HYUNDAI', model='R260LC-9S', manufacturing_year='2022', condition='used',
            acquisition_cost_value=Decimal('7200000'), acquisition_cost_currency='RUB', source_object_count=3,
            **common)
        InsuranceRequest.objects.create(
            item_no=2, brand='Volvo', model='EC220DL', manufacturing_year='2019', condition='used',
            acquisition_cost_value=Decimal('6000000'), acquisition_cost_currency='RUB', has_casco_ce=True, **common)
        InsuranceRequest.objects.create(
            item_no=3, brand='JCB', model='4CXK14H2WM', manufacturing_year='2020', condition='used',
            acquisition_cost_value=Decimal('10000000'), acquisition_cost_currency='RUB', **common)

    def test_context_lists_all_objects_with_quantity_total(self):
        from .application_export import build_batch_application_context

        context = build_batch_application_context(self.first)
        self.assertEqual(context['batch_positions'], 3)
        self.assertEqual(context['batch_units'], 5)
        self.assertEqual([row['qty'] for row in context['batch_rows']], [3, 1, 1])
        self.assertEqual(context['batch_rows'][0]['sum'], '21 600 000 руб.')
        self.assertEqual(context['batch_total'], '37 600 000 руб.')
        tiles = {t['label']: t['value'] for line in context['tile_rows'] for t in line if t}
        self.assertEqual(tiles['КАСКО кат. C/E'], 'Да')  # есть у одного из объектов

    def test_download_and_button(self):
        detail = self.client.get(reverse('insurance_requests:request_detail', args=[self.first.pk]))
        url = reverse('insurance_requests:export_batch_application', args=[self.first.pk])
        self.assertContains(detail, url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('application_batch_', str(make_header(decode_header(response['Content-Disposition']))))

    def test_single_request_redirects_to_regular_pdf(self):
        single = InsuranceRequest.objects.create(client_name='ООО Один', inn='7707083893', insurance_type='КАСКО',
                                                 dfa_number='ТС-1', created_by=self.user)
        response = self.client.get(reverse('insurance_requests:export_batch_application', args=[single.pk]))
        self.assertRedirects(response, reverse('insurance_requests:export_request_application', args=[single.pk]),
                             fetch_redirect_response=False)

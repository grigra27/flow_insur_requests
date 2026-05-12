from io import BytesIO
import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from .forms import DEFAULT_BRANCH, ParserV2PreviewForm
from .models import InsuranceRequest, RequestAttachment


class ParserV2UploadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        user_group, _ = Group.objects.get_or_create(name='Пользователи')

        self.superuser = User.objects.create_superuser(
            username='parser_v2_root',
            email='root@example.com',
            password='pwd',
        )
        self.superuser.groups.add(admin_group)

        self.regular_user = User.objects.create_user(
            username='parser_v2_user',
            email='user@example.com',
            password='pwd',
        )
        self.regular_user.groups.add(user_group)

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _xlsx_upload(self, filename='заявка 20213-ЛТ-КЗ.xlsx'):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D6'] = '20213-ЛТ-КЗ'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['B14'] = 'Страхователь'
        sheet['D14'] = 'ЛизингоДАТЕЛЬ'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['B24'] = 'Предмет лизинга'
        sheet['B25'] = 'Мини-погрузчик Sunward SWL 4028, 2024 г.в.'
        sheet['D29'] = 'Без франшизы'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            filename,
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _xlsx_upload_with_template_object_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['A39'] = 'СВЕДЕНИЯ ОБ ОБЪЕКТЕ СТРАХОВАНИЯ'
        sheet['A41'] = '№ п/п'
        sheet['B41'] = 'Наименование и описание имущества  (марка модель комплектация)'
        sheet['C41'] = 'Год выпуска'
        sheet['A42'] = 'Транспортные средства категории B'
        sheet['A43'] = '1'
        sheet['B43'] = 'Lixiang L9 (пробег 13 000 км)'
        sheet['C43'] = '2024'
        sheet['D43'] = 'б/у'
        sheet['E43'] = '9 000 000'
        sheet['A45'] = 'Противоугонные системы и оборудование (отметьте знаком "Х")'
        sheet['B45'] = 'Штатная'
        sheet['C45'] = 'Установленная дополнительно'
        sheet['D45'] = 'название, модель'
        sheet['A46'] = 'Сигнализация'
        sheet['A47'] = 'Иммобилайзер'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'заявка object-template.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _xlsx_upload_with_unknown_branch(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Неизвестный филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['B24'] = 'Предмет лизинга'
        sheet['B25'] = 'Мини-погрузчик Sunward SWL 4028, 2024 г.в.'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'заявка unknown-branch.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _xlsx_upload_with_telematics_template_header(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet['C4'] = 'Казанский филиал'
        sheet['C5'] = 'Иванов Иван'
        sheet['D7'] = 'ООО Ромашка'
        sheet['D9'] = '1234567890'
        sheet['D21'] = 'КАСКО'
        sheet['N17'] = '1 год'
        sheet['B24'] = 'Предмет лизинга'
        sheet['B25'] = 'Мини-погрузчик Sunward SWL 4028, 2024 г.в.'
        sheet['A53'] = 'Телематический комплекс'
        sheet['B53'] = 'Наименование'
        sheet['C53'] = 'StarLine M96'

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'заявка telematics-template.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _post_data_from_preview(self, form):
        data = {}
        checkbox_fields = {
            'has_installment',
            'has_autostart',
            'has_casco_ce',
            'has_transportation',
            'has_construction_work',
        }
        for field in form.fields:
            if field in checkbox_fields:
                if form.initial.get(field):
                    data[field] = 'on'
            else:
                data[field] = form.initial.get(field, '')
        return data

    def test_parser_v2_access_is_superuser_only(self):
        url = reverse('insurance_requests:upload_excel_v2')

        anonymous_response = self.client.get(url)
        self.assertEqual(anonymous_response.status_code, 302)

        self.client.login(username='parser_v2_user', password='pwd')
        regular_response = self.client.get(url)
        self.assertEqual(regular_response.status_code, 403)

        self.client.logout()
        self.client.login(username='parser_v2_root', password='pwd')
        superuser_response = self.client.get(url)
        self.assertEqual(superuser_response.status_code, 200)
        self.assertTemplateUsed(superuser_response, 'insurance_requests/upload_excel_v2.html')

    def test_parser_v2_link_is_visible_only_for_superuser_on_request_list(self):
        request_list_url = reverse('insurance_requests:request_list')
        parser_v2_url = reverse('insurance_requests:upload_excel_v2')

        self.client.login(username='parser_v2_user', password='pwd')
        regular_response = self.client.get(request_list_url)
        self.assertEqual(regular_response.status_code, 200)
        self.assertNotContains(regular_response, parser_v2_url)

        self.client.logout()
        self.client.login(username='parser_v2_root', password='pwd')
        superuser_response = self.client.get(request_list_url)
        self.assertEqual(superuser_response.status_code, 200)
        self.assertContains(superuser_response, parser_v2_url)

    def test_parser_v2_upload_renders_editable_preview(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'insurance_requests/upload_excel_v2_preview.html')
        self.assertContains(response, 'ООО Ромашка')
        self.assertContains(response, 'Мини-погрузчик Sunward SWL 4028')
        self.assertIn('draft_id', response.context)
        self.assertEqual(response.context['form'].initial['client_name'], 'ООО Ромашка')
        self.assertEqual(response.context['form'].initial['manager_name'], 'Иванов Иван')

    def test_parser_v2_branch_defaults_to_spb_when_not_recognized(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_unknown_branch()},
        )

        form = response.context['form']
        self.assertEqual(form.initial['branch'], DEFAULT_BRANCH)
        self.assertEqual(form.fields['branch'].widget.__class__.__name__, 'Select')

    def test_parser_v2_branch_accepts_only_known_choices(self):
        form = ParserV2PreviewForm(data={'draft_id': 'draft', 'branch': 'Неизвестный филиал'})

        self.assertFalse(form.is_valid())
        self.assertIn('branch', form.errors)

    def test_parser_v2_does_not_take_template_rows_as_vehicle_info(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_template_object_rows()},
        )

        vehicle_info = response.context['form'].initial['vehicle_info']
        self.assertIn('Lixiang L9', vehicle_info)
        self.assertNotIn('Транспортные средства категории B', vehicle_info)
        self.assertNotIn('Противоугонные системы', vehicle_info)
        self.assertNotIn('Сигнализация', vehicle_info)

    def test_parser_v2_does_not_take_name_header_as_telematics_complex(self):
        self.client.login(username='parser_v2_root', password='pwd')

        response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload_with_telematics_template_header()},
        )

        telematics_complex = response.context['form'].initial['telematics_complex']
        self.assertEqual(telematics_complex, 'StarLine M96')
        self.assertNotEqual(telematics_complex, 'Наименование')

    def test_parser_v2_creates_request_from_preview_and_keeps_original_attachment(self):
        self.client.login(username='parser_v2_root', password='pwd')
        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': self._xlsx_upload()},
        )
        form = upload_response.context['form']
        post_data = self._post_data_from_preview(form)
        post_data['client_name'] = 'ООО Ромашка Проверено'

        create_response = self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        created_request = InsuranceRequest.objects.get()
        self.assertRedirects(
            create_response,
            reverse('insurance_requests:request_detail', kwargs={'pk': created_request.pk}),
        )
        self.assertEqual(created_request.client_name, 'ООО Ромашка Проверено')
        self.assertEqual(created_request.manager_name, 'Иванов Иван')
        self.assertEqual(created_request.branch, 'Казань')
        self.assertEqual(created_request.additional_data['parser_version'], 'v2')
        self.assertEqual(created_request.additional_data['parser_v2']['version'], '2.0.0')
        self.assertTrue(RequestAttachment.objects.filter(request=created_request).exists())

    def test_parser_v2_can_create_minimal_request_after_unreadable_file(self):
        self.client.login(username='parser_v2_root', password='pwd')
        unreadable_file = SimpleUploadedFile(
            'broken.xlsx',
            b'not an excel file',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        upload_response = self.client.post(
            reverse('insurance_requests:upload_excel_v2'),
            {'excel_file': unreadable_file},
        )

        self.assertEqual(upload_response.status_code, 200)
        self.assertContains(upload_response, 'Файл не удалось прочитать')

        post_data = self._post_data_from_preview(upload_response.context['form'])
        create_response = self.client.post(reverse('insurance_requests:upload_excel_v2'), post_data)

        created_request = InsuranceRequest.objects.get()
        self.assertRedirects(
            create_response,
            reverse('insurance_requests:request_detail', kwargs={'pk': created_request.pk}),
        )
        self.assertEqual(created_request.client_name, 'Клиент не указан')
        self.assertEqual(created_request.dfa_number, 'Номер ДФА не указан')
        self.assertTrue(created_request.additional_data['parser_v2']['warnings'])

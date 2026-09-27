"""Справочник техники (tariffs_analytics_2026_09, шаг 1). Формулировки — из реальных заявок."""
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .models import InsuranceRequest
from .object_catalog import classify


def info(text, insurance_type='КАСКО', dfa=''):
    result = classify(text, insurance_type, dfa)
    return result.brand, result.object_class, result.machine_kind


class ObjectCatalogTests(SimpleTestCase):
    def test_brand_spellings(self):
        self.assertEqual(info('Автомобиль Gazelle NEXT')[0], 'ГАЗ')
        self.assertEqual(info('А/м ГАЗель БИЗНЕС 330232')[0], 'ГАЗ')
        self.assertEqual(info('Соболь 2752, 2026 г., Новое')[0], 'ГАЗ')
        self.assertEqual(info('Mercedec-Benz V300d 4MATIC')[0], 'Mercedes-Benz')
        self.assertEqual(info('GWM WEY 80')[0], 'Great Wall')
        self.assertEqual(info('LYNK AND CO 900')[0], 'Lynk & Co')
        self.assertEqual(info('гусеничный экскаватор DEVELON DX220LCA-2M', 'страхование спецтехники')[0], 'Doosan')
        self.assertEqual(info('CAT320, 2021 г., Б/у', 'страхование спецтехники')[0], 'Caterpillar')
        self.assertEqual(info('Грузовой самосвал РЕНО К 8х4')[0], 'Renault')
        self.assertEqual(info('Паpоконвeктомат Fagor APW-202-E', 'страхование имущества')[0], '')

    def test_classes(self):
        self.assertEqual(info('Haval F7X')[1:], ('passenger', ''))
        self.assertEqual(info('Gazelle NEXT A31R22')[1], 'lcv')
        self.assertEqual(info('Автофургон SOLLERS ATLANT')[1], 'lcv')
        self.assertEqual(info('самосвал КамАЗ K4146')[1], 'truck')
        self.assertEqual(info('Грузовой самосвал РЕНО К 8х4')[1], 'truck')  # «самосвал» сильнее легковой марки
        self.assertEqual(info('мусоровоз СМ-16 на шасси JAC 200')[1], 'truck')
        self.assertEqual(info('полуприцеп-самосвал GRUNWALD 9453-0000011-60')[1], 'trailer')
        self.assertEqual(info('тягач седельный MAN TGX 18.400 и полуприцеп низкорамный KASSBOHRER LB4')[1], 'truck')
        self.assertEqual(info('седельный тягач для буксировки полуприцепов SITRAK C7H')[1], 'truck')
        self.assertEqual(info('автобус НЕФАЗ 5299-0000040-52')[1], 'bus')
        self.assertEqual(info('Автомобильные весы «Эталон-А» модель ТОНАР', 'страхование имущества')[1], 'equipment')
        self.assertEqual(info('Автотопливозаправщик ГРАЗ 36139')[1], 'truck')

    def test_special_equipment_kinds(self):
        self.assertEqual(info('Экскаватор XCMG XE225DN', 'страхование спецтехники'), ('XCMG', 'special', 'Экскаватор'))
        self.assertEqual(info('экскаватор-погрузчик JCB 4CX', 'страхование спецтехники')[2], 'Экскаватор-погрузчик')
        self.assertEqual(info('Автокран XCMG XCT25L5 (б-у, 2023 г.в)')[1:], ('special', 'Автокран и кран'))
        self.assertEqual(info('каток дорожный HAMM HD 110', 'страхование спецтехники')[2], 'Каток')
        self.assertEqual(info('Фронтальный погрузчик LGCE L968H', 'страхование спецтехники')[:3],
                         ('SDLG', 'special', 'Погрузчик'))
        self.assertEqual(info('Установка ХХХ', 'страхование спецтехники')[2], 'Прочая спецтехника')

    def test_dfa_code_decides_when_text_is_silent(self):
        self.assertEqual(info('Автомобиль UMO5 5А-2', dfa='ТС-1-ГА-КР')[1], 'truck')
        self.assertEqual(info('Автомобиль UMO5 5А-2', dfa='ТС-1-ЛА-КР')[1], 'passenger')


class ObjectCatalogOnRequestTests(TestCase):
    def test_saved_request_gets_catalog_fields_and_updates_on_edit(self):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', insurance_type='КАСКО',
                                                  vehicle_info='Автомобиль Haval M6', brand='Автомобиль')
        self.assertEqual((request.object_brand, request.object_class), ('Haval', 'passenger'))

        request.vehicle_info = 'Экскаватор SANY SY75C'
        request.insurance_type = 'страхование спецтехники'
        request.save(update_fields=['vehicle_info', 'insurance_type'])
        request.refresh_from_db()
        self.assertEqual((request.object_brand, request.object_class, request.machine_kind),
                         ('SANY', 'special', 'Экскаватор'))

    def test_command_reports_and_applies(self):
        request = InsuranceRequest.objects.create(client_name='ООО Тест', inn='7707083893', vehicle_info='Geely Monjaro')
        InsuranceRequest.objects.filter(pk=request.pk).update(object_brand='', object_class='')
        out = StringIO()
        call_command('classify_objects', stdout=out)
        self.assertIn('изменится: 1', out.getvalue())
        call_command('classify_objects', '--apply', stdout=StringIO())
        request.refresh_from_db()
        self.assertEqual((request.object_brand, request.object_class), ('Geely', 'passenger'))

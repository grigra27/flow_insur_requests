from django.db import migrations

LOGO_CODES = {
    'Абсолют': 'absolut',
    'Альфа': 'alfa',
    'ВСК': 'vsk',
    'Согаз': 'sogaz',
    'РЕСО': 'reso',
    'Ингосстрах': 'ingos',
    'Ренессанс': 'renins',
    'Росгосстрах': 'rgs',
    'Пари': 'pari',
    'Совкомбанк СК': 'sovcombank',
    'Согласие': 'soglasie',
    'Энергогарант': 'energogarant',
    'ПСБ-страхование': 'psb',
    'Зетта': 'zetta',
    'Югория': 'ugoria',
}


def set_logo_codes(apps, schema_editor):
    InsuranceCompany = apps.get_model('summaries', 'InsuranceCompany')
    for name, code in LOGO_CODES.items():
        InsuranceCompany.objects.filter(name=name, logo_code='').update(logo_code=code)


def clear_logo_codes(apps, schema_editor):
    InsuranceCompany = apps.get_model('summaries', 'InsuranceCompany')
    InsuranceCompany.objects.filter(logo_code__in=LOGO_CODES.values()).update(logo_code='')


class Migration(migrations.Migration):

    dependencies = [
        ('summaries', '0024_insurancecompany_logo_code'),
    ]

    operations = [
        migrations.RunPython(set_logo_codes, clear_logo_codes),
    ]

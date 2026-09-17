from django.db import migrations, models


def mark_legacy_territory_as_unknown(apps, schema_editor):
    InsuranceOffer = apps.get_model('summaries', 'InsuranceOffer')
    InsuranceOffer.objects.filter(coverage_territory='').update(
        coverage_territory=None
    )


def restore_empty_legacy_territory(apps, schema_editor):
    InsuranceOffer = apps.get_model('summaries', 'InsuranceOffer')
    InsuranceOffer.objects.filter(coverage_territory__isnull=True).update(
        coverage_territory=''
    )


class Migration(migrations.Migration):

    dependencies = [
        ('summaries', '0019_insuranceoffer_coverage_territory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='insuranceoffer',
            name='coverage_territory',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Территория и ограничения, подтвержденные страховщиком. '
                    'Не подменяется территорией из исходной заявки.'
                ),
                null=True,
                verbose_name='Территория страхования и территориальные ограничения',
            ),
        ),
        migrations.RunPython(
            mark_legacy_territory_as_unknown,
            restore_empty_legacy_territory,
        ),
    ]

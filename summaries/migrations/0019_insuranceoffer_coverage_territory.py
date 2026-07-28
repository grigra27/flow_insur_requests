from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('summaries', '0018_insurancesummary_deal_summary_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='insuranceoffer',
            name='coverage_territory',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Территория и ограничения, подтвержденные страховщиком. '
                    'Не подменяется территорией из исходной заявки.'
                ),
                verbose_name='Территория страхования и территориальные ограничения',
            ),
        ),
    ]

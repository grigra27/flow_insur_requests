from django.db import migrations, models


def backfill_completed_at(apps, schema_editor):
    InsuranceSummary = apps.get_model('summaries', 'InsuranceSummary')
    for summary in InsuranceSummary.objects.filter(
        status='completed_accepted',
        completed_at__isnull=True,
    ).iterator():
        summary.completed_at = summary.updated_at
        summary.save(update_fields=['completed_at'])


def rollback_completed_at(apps, schema_editor):
    InsuranceSummary = apps.get_model('summaries', 'InsuranceSummary')
    InsuranceSummary.objects.update(completed_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('summaries', '0015_add_selected_franchise_variant_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='insurancesummary',
            name='completed_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Фиксируется при переводе свода в статус "Завершен: акцепт/распоряжение"',
                null=True,
                verbose_name='Дата закрытия сделки',
            ),
        ),
        migrations.RunPython(backfill_completed_at, rollback_completed_at),
    ]

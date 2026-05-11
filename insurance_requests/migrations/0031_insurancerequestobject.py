from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('insurance_requests', '0030_insurancerequest_insurance_r_created_58527f_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='InsuranceRequestObject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(default=1, verbose_name='Порядок')),
                ('description', models.TextField(verbose_name='Описание объекта страхования')),
                ('manufacturing_year', models.CharField(blank=True, max_length=255, verbose_name='Год выпуска')),
                ('asset_status', models.CharField(blank=True, max_length=255, verbose_name='Статус имущества')),
                ('source_row', models.PositiveIntegerField(blank=True, null=True, verbose_name='Строка источника')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Дата обновления')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='insurance_objects', to='insurance_requests.insurancerequest', verbose_name='Заявка')),
            ],
            options={
                'verbose_name': 'Объект страхования',
                'verbose_name_plural': 'Объекты страхования',
                'ordering': ['position', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='insurancerequestobject',
            index=models.Index(fields=['request', 'position'], name='insurance_r_request_b382ee_idx'),
        ),
    ]

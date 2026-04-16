from django.db import migrations


class Migration(migrations.Migration):
    """
    Пустая миграция — модель DatabaseBackup имеет managed=False,
    таблица в БД не создаётся.
    """

    initial = True
    dependencies = []
    operations = []

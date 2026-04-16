from django.db import models


class DatabaseBackup(models.Model):
    """Фиктивная модель — таблица в БД не создаётся. Нужна только для регистрации в admin."""

    class Meta:
        managed = False
        verbose_name = 'Резервная копия'
        verbose_name_plural = 'Резервные копии базы данных'
        # Разместим в группе "Администрирование" (app_label совпадает с именем приложения)

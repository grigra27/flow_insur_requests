from django.apps import AppConfig


class SummariesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'summaries'

    def ready(self):
        # Регистрируем сигналы аудита смены статусов
        from . import signals  # noqa: F401

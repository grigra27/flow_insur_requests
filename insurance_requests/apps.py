from django.apps import AppConfig


class InsuranceRequestsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'insurance_requests'

    def ready(self):
        from . import signals  # noqa: F401 — регистрирует m2m_changed

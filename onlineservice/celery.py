"""
Конфигурация Celery для Django проекта
"""
import os
from celery import Celery
from django.conf import settings

# Устанавливаем переменную окружения для Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onlineservice.settings')

app = Celery('onlineservice')

# Используем настройки Django для конфигурации Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматически находим задачи в приложениях Django
app.autodiscover_tasks()

# Периодические задачи
app.conf.beat_schedule = {
    'check-emails-every-5-minutes': {
        'task': 'core.tasks.check_incoming_emails',
        'schedule': 300.0,  # каждые 5 минут
    },
}

app.conf.timezone = 'Europe/Moscow'


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
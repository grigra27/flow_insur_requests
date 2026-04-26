"""
Тесты для команды purge_audit_log.
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone


def _backdate(obj, field, dt):
    """Переписывает auto_now_add-поле через .update() (BaseManager его игнорирует на save)."""
    type(obj).objects.filter(pk=obj.pk).update(**{field: dt})


class PurgeAuditLogTests(TestCase):
    def setUp(self):
        from easyaudit.models import CRUDEvent, LoginEvent, RequestEvent

        self.LoginEvent = LoginEvent
        self.CRUDEvent = CRUDEvent
        self.RequestEvent = RequestEvent

        # easy-audit сам логирует наши действия (создание ContentType,
        # модели в миграциях и т.д.) — обнуляем перед каждым тестом.
        LoginEvent.objects.all().delete()
        CRUDEvent.objects.all().delete()
        RequestEvent.objects.all().delete()

        now = timezone.now()
        self.old = now - timedelta(days=120)   # старше 90д
        self.medium = now - timedelta(days=10)  # моложе 90д, старше 1д
        self.fresh = now - timedelta(hours=1)   # моложе всего

        # LoginEvent
        for dt in (self.old, self.medium, self.fresh):
            ev = LoginEvent.objects.create(login_type=0, username='tester')
            _backdate(ev, 'datetime', dt)

        # CRUDEvent — нужен content_type
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.first()
        for dt in (self.old, self.medium, self.fresh):
            ev = CRUDEvent.objects.create(
                event_type=CRUDEvent.CREATE,
                object_id='1',
                content_type=ct,
                object_repr='test',
            )
            _backdate(ev, 'datetime', dt)

        # RequestEvent
        for dt in (self.old, self.medium, self.fresh):
            ev = RequestEvent.objects.create(url='/test/', method='GET', remote_ip='127.0.0.1')
            _backdate(ev, 'datetime', dt)

    def test_default_retention_90d_login_crud_1d_request(self):
        """LoginEvent/CRUDEvent: остаются moderate+fresh; RequestEvent: только fresh."""
        call_command('purge_audit_log', stdout=StringIO())

        self.assertEqual(self.LoginEvent.objects.count(), 2)   # удалили old (120д)
        self.assertEqual(self.CRUDEvent.objects.count(), 2)
        self.assertEqual(self.RequestEvent.objects.count(), 1)  # удалили old + medium

    def test_dry_run_does_not_delete(self):
        call_command('purge_audit_log', '--dry-run', stdout=StringIO())

        self.assertEqual(self.LoginEvent.objects.count(), 3)
        self.assertEqual(self.CRUDEvent.objects.count(), 3)
        self.assertEqual(self.RequestEvent.objects.count(), 3)

    def test_custom_retention_args(self):
        # Очень короткие пороги — должно удалить всё кроме fresh
        call_command(
            'purge_audit_log',
            '--login-days=2',
            '--crud-days=2',
            '--request-days=2',
            stdout=StringIO(),
        )
        self.assertEqual(self.LoginEvent.objects.count(), 1)
        self.assertEqual(self.CRUDEvent.objects.count(), 1)
        self.assertEqual(self.RequestEvent.objects.count(), 1)

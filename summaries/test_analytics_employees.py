"""Страница «Сотрудники» (analytics_redesign_2026_09, этап 4)."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary, StatusEvent
from summaries.services import analytics_employees as service


class EmployeesTestBase(TestCase):
    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.admin = User.objects.create_user(username='emp_admin', password='testpass123')
        self.admin.groups.add(admin_group)
        self.anna = self._employee('anna', 'Анна', 'Иванова')
        self.boris = self._employee('boris', 'Борис', 'Петров')
        self.reader = self._employee('reader', 'Вера', 'Смирнова')
        self.client.login(username='emp_admin', password='testpass123')
        self.now = timezone.now()
        self._counter = 0

    def _employee(self, username, first, last):
        user = User.objects.create_user(username=username, password='p', first_name=first, last_name=last)
        user.groups.add(self.users_group)
        return user

    def _request(self, user, days_ago, batch=None):
        self._counter += 1
        insurance_request = InsuranceRequest.objects.create(
            created_by=user, client_name=f'Клиент {self._counter}', inn='1234567890',
            insurance_type='КАСКО', dfa_number=f'DFA-{self._counter}', source_batch_id=batch,
        )
        InsuranceRequest.objects.filter(pk=insurance_request.pk).update(created_at=self.now - timedelta(days=days_ago))
        return insurance_request

    def _summary_with_offers(self, insurance_request, offers=2, days_ago=1):
        summary = InsuranceSummary.objects.create(request=insurance_request, status='collecting')
        for index in range(offers):
            offer = InsuranceOffer.objects.create(
                summary=summary, company_name=['Абсолют', 'Альфа', 'ВСК'][index], insurance_year=1,
                insurance_sum=Decimal('1000000'), premium_with_franchise_1=Decimal('10000'), franchise_1=Decimal('0'),
            )
            InsuranceOffer.objects.filter(pk=offer.pk).update(received_at=self.now - timedelta(days=days_ago))
        return summary

    def _status(self, summary, to_status, user, days_ago=1):
        event = StatusEvent.objects.create(
            content_type=ContentType.objects.get_for_model(InsuranceSummary), object_id=summary.pk,
            from_status='collecting', to_status=to_status, changed_by=user,
        )
        StatusEvent.objects.filter(pk=event.pk).update(changed_at=self.now - timedelta(days=days_ago))


class LoadBlockTests(EmployeesTestBase):
    def setUp(self):
        super().setUp()
        batch = uuid.uuid4()
        first = self._request(self.anna, 3, batch)
        self._request(self.anna, 3, batch)            # тот же файл
        self._request(self.anna, 10)
        self._request(self.anna, 120)                 # предыдущий 90-дневный период
        boris_request = self._request(self.boris, 5)
        self._request(self.boris, 200)                # вне обоих периодов

        summary = self._summary_with_offers(first, offers=3)
        self._summary_with_offers(boris_request, offers=2, days_ago=100)  # предложения вне периода
        self._status(summary, 'ready', self.anna)
        self._status(summary, 'sent', self.anna)
        self._status(summary, 'completed_accepted', self.boris)
        self._status(summary, 'completed_rejected', None)  # автозакрытие — без автора

    def _load(self, **params):
        return self.client.get(reverse('summaries:analytics_managers'), params).context['load']

    def test_rows_per_employee(self):
        rows = {row['name']: row for row in self._load()['rows']}

        anna = rows['Иванова Анна']
        self.assertEqual((anna['requests'], anna['files']), (3, 2))
        self.assertEqual(anna['offers'], 3)
        self.assertEqual((anna['assembled'], anna['sent'], anna['accepted']), (1, 1, 0))
        self.assertEqual(anna['share_pct'], Decimal('75'))
        self.assertEqual(anna['previous_requests'], 1)
        self.assertEqual(anna['change_pct'], Decimal('200'))

        boris = rows['Петров Борис']
        self.assertEqual((boris['requests'], boris['offers'], boris['accepted']), (1, 0, 1))
        self.assertIsNone(boris['change_pct'])

    def test_readers_are_listed_last(self):
        rows = self._load()['rows']

        self.assertEqual(rows[-1]['name'], 'Смирнова Вера')
        self.assertTrue(rows[-1]['is_reader'])
        self.assertNotIn('emp_admin', [row['name'] for row in rows])

    def test_totals_exclude_auto_close(self):
        totals = self._load()['totals']

        self.assertEqual((totals['requests'], totals['files'], totals['offers']), (4, 3, 3))
        self.assertEqual((totals['accepted'], totals['rejected']), (1, 0))
        self.assertEqual(totals['per_week'], Decimal(4) / (Decimal(90) / Decimal(7)))

    def test_longer_period_and_monthly_chart(self):
        load = self._load(period='365')

        self.assertEqual(load['totals']['requests'], 6)
        self.assertEqual(load['chart']['granularity'], 'month')
        self.assertEqual(sum(sum(series['data']) for series in load['chart']['series']), 6)

    def test_weekly_chart_and_stable_colors(self):
        load = self._load()

        self.assertEqual(load['chart']['granularity'], 'week')
        colors = {series['label']: series['color'] for series in load['chart']['series']}
        # Цвет закреплён за сотрудником (по порядку id), не за местом в таблице.
        self.assertEqual(colors['Иванова Анна'], service.SERIES_COLORS[0])
        self.assertEqual(colors['Петров Борис'], service.SERIES_COLORS[1])

    def test_custom_dates(self):
        start = (timezone.localdate() - timedelta(days=6)).isoformat()
        load = self._load(start_date=start)

        self.assertEqual(load['totals']['requests'], 3)

    def test_page_renders_for_admin_only(self):
        response = self.client.get(reverse('summaries:analytics_managers'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/analytics_employees.html')
        self.assertContains(response, 'Нагрузка за период')
        self.assertContains(response, 'только просмотр')

        self.client.login(username='anna', password='p')
        self.assertEqual(self.client.get(reverse('summaries:analytics_managers')).status_code, 403)

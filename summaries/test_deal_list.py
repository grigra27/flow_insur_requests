from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary


class DealListViewTests(TestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name='Администраторы')
        self.users_group, _ = Group.objects.get_or_create(name='Пользователи')
        self.admin_user = User.objects.create_user(
            username='deal_list_admin',
            email='deal_list_admin@example.com',
            password='testpass123',
            first_name='Иван',
            last_name='Петров',
        )
        self.admin_user.groups.add(self.admin_group)

        self.regular_user = User.objects.create_user(
            username='deal_list_regular',
            email='deal_list_regular@example.com',
            password='testpass123',
        )
        self.regular_user.groups.add(self.users_group)

        self.client.login(username='deal_list_admin', password='testpass123')

    def _create_summary(
        self,
        *,
        dfa_number,
        branch,
        client_name,
        created_by=None,
        insurance_type='КАСКО',
        status='completed_accepted',
        selected_company='Абсолют',
        selected_franchise_variant=1,
        deal_status='new',
    ):
        created_by = created_by or self.admin_user
        request_obj = InsuranceRequest.objects.create(
            created_by=created_by,
            client_name=client_name,
            inn='1234567890',
            insurance_type=insurance_type,
            insurance_period='1 год',
            dfa_number=dfa_number,
            branch=branch,
            deal_status=deal_status,
        )
        return InsuranceSummary.objects.create(
            request=request_obj,
            status=status,
            selected_company=selected_company,
            selected_franchise_variant=selected_franchise_variant,
        )

    def _add_offer(self, summary, company_name='Абсолют', premium='10000.00', year=1):
        return InsuranceOffer.objects.create(
            summary=summary,
            company_name=company_name,
            insurance_year=year,
            insurance_sum=Decimal('1000000.00'),
            franchise_1=Decimal('0'),
            premium_with_franchise_1=Decimal(premium),
        )

    def test_deal_list_available_for_admin_group(self):
        response = self.client.get(reverse('summaries:deal_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/deal_list.html')
        self.assertContains(response, 'Сделки')

        app_navigation = response.context['app_navigation']
        self.assertEqual(app_navigation['current_section']['label'], 'Сделки')
        self.assertEqual(app_navigation['current_context_label'], 'Сделки')

    def test_deal_list_available_for_regular_user_group(self):
        self.client.logout()
        self.client.login(username='deal_list_regular', password='testpass123')

        response = self.client.get(reverse('summaries:deal_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'summaries/deal_list.html')

    def test_deal_menu_item_visible_for_regular_user(self):
        self.client.logout()
        self.client.login(username='deal_list_regular', password='testpass123')

        response = self.client.get(reverse('summaries:summary_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('summaries:deal_list'))

    def test_summary_list_filters_by_search_date_type_and_manager(self):
        second_manager = User.objects.create_user(
            username='summary_filter_manager',
            email='summary_filter_manager@example.com',
            password='testpass123',
            first_name='Петр',
            last_name='Иванов',
        )
        second_manager.groups.add(self.users_group)

        target_summary = self._create_summary(
            dfa_number='DFA-SUM-01',
            branch='Москва',
            client_name='Клиент Целевой',
            insurance_type='КАСКО',
            created_by=self.admin_user,
            status='collecting',
            selected_company='Абсолют',
        )
        other_summary = self._create_summary(
            dfa_number='DFA-SUM-02',
            branch='Москва',
            client_name='Клиент Другой',
            insurance_type='страхование имущества',
            created_by=second_manager,
            status='ready',
            selected_company='ВСК',
        )

        InsuranceSummary.objects.filter(pk=target_summary.pk).update(
            created_at=timezone.now() - timedelta(days=1),
        )
        InsuranceSummary.objects.filter(pk=other_summary.pk).update(
            created_at=timezone.now() - timedelta(days=15),
        )

        response = self.client.get(
            reverse('summaries:summary_list'),
            {
                'search': 'Целевой',
                'start_date': (timezone.localdate() - timedelta(days=3)).isoformat(),
                'end_date': timezone.localdate().isoformat(),
                'insurance_type': 'КАСКО',
                'manager': str(self.admin_user.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['summaries'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, target_summary.id)

    def test_summary_list_manager_filter_has_unique_users(self):
        second_manager = User.objects.create_user(
            username='summary_unique_manager',
            email='summary_unique_manager@example.com',
            password='testpass123',
            first_name='Петр',
            last_name='Сидоров',
        )
        second_manager.groups.add(self.users_group)

        for index in range(3):
            self._create_summary(
                dfa_number=f'DFA-SUM-A-{index}',
                branch='Москва',
                client_name=f'Свод A {index}',
                created_by=self.admin_user,
                status='collecting',
            )

        for index in range(2):
            self._create_summary(
                dfa_number=f'DFA-SUM-B-{index}',
                branch='Москва',
                client_name=f'Свод B {index}',
                created_by=second_manager,
                status='ready',
            )

        response = self.client.get(reverse('summaries:summary_list'))
        self.assertEqual(response.status_code, 200)

        manager_choices = [
            value for value, _ in response.context['filter_form'].fields['manager'].choices
            if value
        ]
        self.assertEqual(len(manager_choices), 2)
        self.assertEqual(len(set(manager_choices)), 2)
        self.assertIn(str(self.admin_user.id), manager_choices)
        self.assertIn(str(second_manager.id), manager_choices)

    def test_deal_list_shows_only_real_completed_deals(self):
        valid_summary = self._create_summary(
            dfa_number='DFA-1001',
            branch='Москва',
            client_name='ООО Валидная сделка',
        )
        self._add_offer(valid_summary, company_name='Абсолют', premium='11000.00')

        non_completed_summary = self._create_summary(
            dfa_number='DFA-1002',
            branch='Москва',
            client_name='ООО Не завершена',
            status='collecting',
            selected_company=None,
        )
        self._add_offer(non_completed_summary, company_name='Абсолют', premium='12000.00')

        completed_without_selected_company = self._create_summary(
            dfa_number='DFA-1003',
            branch='Москва',
            client_name='ООО Без выбранной СК',
            selected_company='',
        )
        self._add_offer(completed_without_selected_company, company_name='Абсолют', premium='13000.00')

        response = self.client.get(reverse('summaries:deal_list'))
        self.assertEqual(response.status_code, 200)

        rows = response.context['deals'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['summary'].id, valid_summary.id)

    def test_deal_list_filters_by_branch_and_search(self):
        moscow_summary = self._create_summary(
            dfa_number='DFA-MSK-01',
            branch='Москва',
            client_name='Клиент Москва',
        )
        self._add_offer(moscow_summary, premium='14000.00')

        spb_summary = self._create_summary(
            dfa_number='DFA-SPB-01',
            branch='Санкт-Петербург',
            client_name='Клиент СПб',
        )
        self._add_offer(spb_summary, premium='15000.00')

        response = self.client.get(reverse('summaries:deal_list'), {'branch': 'Москва'})
        self.assertEqual(response.status_code, 200)
        rows = response.context['deals'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['summary'].id, moscow_summary.id)

        response = self.client.get(reverse('summaries:deal_list'), {'search': 'DFA-SPB-01'})
        self.assertEqual(response.status_code, 200)
        rows = response.context['deals'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['summary'].id, spb_summary.id)

    def test_deal_list_default_sort_uses_completed_at_desc(self):
        older_summary = self._create_summary(
            dfa_number='DFA-OLD-01',
            branch='Москва',
            client_name='Старая сделка',
        )
        newer_summary = self._create_summary(
            dfa_number='DFA-NEW-01',
            branch='Москва',
            client_name='Новая сделка',
        )
        self._add_offer(older_summary, premium='17000.00')
        self._add_offer(newer_summary, premium='18000.00')

        older_summary.completed_at = timezone.now() - timedelta(days=5)
        older_summary.save(update_fields=['completed_at'])
        newer_summary.completed_at = timezone.now() - timedelta(days=1)
        newer_summary.save(update_fields=['completed_at'])

        response = self.client.get(reverse('summaries:deal_list'))
        self.assertEqual(response.status_code, 200)
        rows = response.context['deals'].object_list
        self.assertEqual(rows[0]['summary'].id, newer_summary.id)
        self.assertEqual(rows[1]['summary'].id, older_summary.id)

    def test_deal_list_row_keeps_deal_summary_link_without_actions_column(self):
        summary = self._create_summary(
            dfa_number='DFA-LINKS-01',
            branch='Москва',
            client_name='Клиент со ссылками',
        )
        self._add_offer(summary, premium='19000.00')

        response = self.client.get(reverse('summaries:deal_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('summaries:deal_summary', args=[summary.pk]))
        self.assertNotContains(response, 'btn-group btn-group-sm')
        self.assertNotContains(response, 'title="Свод"')
        self.assertNotContains(response, 'title="Заявка"')
        self.assertNotContains(response, 'Действия')
        self.assertNotContains(response, '>Лет<')

    def test_deal_list_shows_price_range_position_for_middle_choice(self):
        summary = self._create_summary(
            dfa_number='DFA-RANGE-01',
            branch='Москва',
            client_name='Клиент диапазона',
            selected_company='Абсолют',
            selected_franchise_variant=1,
        )
        self._add_offer(summary, company_name='Альфа', premium='100.00')
        self._add_offer(summary, company_name='Абсолют', premium='120.00')
        self._add_offer(summary, company_name='ВСК', premium='140.00')

        response = self.client.get(reverse('summaries:deal_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Линейка предложений')
        self.assertContains(response, '2 / 3')
        self.assertContains(response, 'позиция 50%')
        self.assertContains(response, 'left: 50.0%;')

    def test_deal_list_manager_filter_has_unique_users(self):
        second_manager = User.objects.create_user(
            username='deal_list_second_manager',
            email='deal_list_second_manager@example.com',
            password='testpass123',
            first_name='Петр',
            last_name='Сидоров',
        )
        second_manager.groups.add(self.users_group)

        for index in range(3):
            summary = self._create_summary(
                dfa_number=f'DFA-MANAGER-A-{index}',
                branch='Москва',
                client_name=f'Клиент A {index}',
                created_by=self.admin_user,
            )
            self._add_offer(summary, company_name='Абсолют', premium='11000.00')

        for index in range(2):
            summary = self._create_summary(
                dfa_number=f'DFA-MANAGER-B-{index}',
                branch='Москва',
                client_name=f'Клиент B {index}',
                created_by=second_manager,
            )
            self._add_offer(summary, company_name='Абсолют', premium='12000.00')

        response = self.client.get(reverse('summaries:deal_list'))

        self.assertEqual(response.status_code, 200)
        manager_choices = [
            value for value, _ in response.context['filter_form'].fields['manager'].choices
            if value
        ]
        self.assertEqual(len(manager_choices), 2)
        self.assertEqual(len(set(manager_choices)), 2)
        self.assertIn(str(self.admin_user.id), manager_choices)
        self.assertIn(str(second_manager.id), manager_choices)

    def test_change_summary_status_sets_and_resets_completed_at(self):
        summary = self._create_summary(
            dfa_number='DFA-STATUS-01',
            branch='Москва',
            client_name='Клиент статуса',
            status='collecting',
            selected_company=None,
            selected_franchise_variant=None,
        )
        self._add_offer(summary, company_name='Абсолют', premium='12345.00')

        change_status_url = reverse('summaries:change_summary_status', args=[summary.pk])
        response = self.client.post(change_status_url, {
            'status': 'completed_accepted',
            'selected_company': 'Абсолют',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        summary.refresh_from_db()
        self.assertIsNotNone(summary.completed_at)

        response = self.client.post(change_status_url, {
            'status': 'ready',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        summary.refresh_from_db()
        self.assertIsNone(summary.completed_at)

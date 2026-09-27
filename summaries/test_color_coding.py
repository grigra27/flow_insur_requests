"""
Test for color coding functionality in summary detail template.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary, InsuranceOffer


class ColorCodingTest(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Add user to the required group
        from django.contrib.auth.models import Group
        user_group, created = Group.objects.get_or_create(name='Пользователи')
        self.user.groups.add(user_group)
        
        # Create a test insurance request
        self.request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            vehicle_info='Test Vehicle',
            created_by=self.user
        )
        
        # Create a test summary
        self.summary = InsuranceSummary.objects.create(
            request=self.request,
            status='collecting'
        )
        
        # Create test offers with different franchise variants
        self.offer1 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=1,
            insurance_sum=1000000.00,
            franchise_1=50000.00,
            premium_with_franchise_1=75000.00,
            franchise_2=100000.00,
            premium_with_franchise_2=65000.00
        )
        
        self.offer2 = InsuranceOffer.objects.create(
            summary=self.summary,
            company_name='Абсолют',
            insurance_year=2,
            insurance_sum=800000.00,
            franchise_1=40000.00,
            premium_with_franchise_1=60000.00,
            franchise_2=80000.00,
            premium_with_franchise_2=50000.00
        )

    def _detail(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk}))
        self.assertEqual(response.status_code, 200)
        return response

    def test_franchise_variant_1_color_coding(self):
        """Премии варианта 1 размечены классом и показаны основным цветом текста (редизайн карточки 2026-09)"""
        response = self._detail()
        self.assertContains(response, 'class="franchise-variant-1"')
        self.assertContains(response, 'color: var(--sd-ink) !important')

    def test_franchise_variant_2_color_coding(self):
        """Премии варианта 2 размечены классом и показаны основным цветом текста (редизайн карточки 2026-09)"""
        response = self._detail()
        self.assertContains(response, 'class="franchise-variant-2"')
        self.assertContains(response, 'color: var(--sd-ink) !important')

    def test_total_row_color_coding(self):
        """Итог многолетнего предложения — справа в заголовке компании (редизайн карточки 2026-09)"""
        response = self._detail()
        self.assertContains(response, 'og-company-total')
        self.assertContains(response, '<small>итого за срок</small>')

    def test_mobile_responsive_color_coding(self):
        """Адаптивные стили карточки на месте, итог на узком экране не прижимается вправо"""
        response = self._detail()
        self.assertContains(response, '@media (max-width: 576px)')
        self.assertContains(response, '@media (max-width: 768px)')
        content = response.content.decode('utf-8')
        mobile_start = content.find('@media (max-width: 767.98px) {\n    .sd-head')
        self.assertNotEqual(mobile_start, -1)
        self.assertIn('.og-company-total { margin-left: 0; }', content[mobile_start:])

    def test_color_coding_css_classes_defined(self):
        """Классы вариантов и заголовка компании определены в стилях страницы"""
        content = self._detail().content.decode('utf-8')

        self.assertIn('.franchise-variant-1,\n.franchise-variant-2 {', content)
        self.assertIn('font-weight: 600;', content)

        # Заголовок компании с итогом и строки годов (редизайн 2026-09)
        self.assertIn('.og-company-meta {', content)
        self.assertIn('.og-company-total {', content)
        self.assertIn('.og-year-row:hover td {', content)

    def test_no_bootstrap_table_info_class(self):
        """Test that Bootstrap table-info class is not used in total rows"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('summaries:summary_detail', kwargs={'pk': self.summary.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Check that table-info class is not present in the template
        self.assertNotIn('table-info', content)
        
        # Итог — в строке-заголовке компании, отдельной строки «Итого» нет
        self.assertIn('class="og-company-row"', content)

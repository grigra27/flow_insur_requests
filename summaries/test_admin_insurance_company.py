from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from insurance_requests.models import InsuranceRequest
from summaries.admin import InsuranceCompanyAdmin
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary


class InsuranceCompanyAdminTests(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username='company_admin',
            email='company_admin@example.com',
            password='testpass123',
        )
        self.model_admin = InsuranceCompanyAdmin(InsuranceCompany, AdminSite())

    def _build_admin_request(self):
        request = self.request_factory.get('/admin/summaries/insurancecompany/')
        request.user = self.admin_user
        return request

    def test_get_form_does_not_fail_when_name_is_readonly_for_company_with_offers(self):
        company = InsuranceCompany.objects.create(
            name='Тестовая СК',
            display_name='Тестовая СК',
        )
        insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент',
            inn='1234567890',
        )
        summary = InsuranceSummary.objects.create(request=insurance_request)
        InsuranceOffer.objects.create(
            summary=summary,
            company_name=company.name,
            insurance_sum=1000000,
            insurance_year=1,
        )

        request = self._build_admin_request()

        form_class = self.model_admin.get_form(request, obj=company)

        self.assertNotIn('name', form_class.base_fields)

    def test_get_readonly_fields_contains_name_only_once_for_company_with_offers(self):
        company = InsuranceCompany.objects.create(
            name='Тестовая СК 2',
            display_name='Тестовая СК 2',
        )
        insurance_request = InsuranceRequest.objects.create(
            client_name='Тестовый клиент 2',
            inn='1234567891',
        )
        summary = InsuranceSummary.objects.create(request=insurance_request)
        InsuranceOffer.objects.create(
            summary=summary,
            company_name=company.name,
            insurance_sum=900000,
            insurance_year=1,
        )

        request = self._build_admin_request()

        readonly_fields = self.model_admin.get_readonly_fields(request, obj=company)

        self.assertEqual(readonly_fields.count('name'), 1)

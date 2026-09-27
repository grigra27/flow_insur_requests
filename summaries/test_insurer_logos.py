from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceCompany, InsuranceOffer, InsuranceSummary
from summaries.services.insurer_logos import clear_cache, logo_urls


class InsurerLogoTests(TestCase):
    """Логотипы СК: коды из миграции, фильтр |insurer, заглушка-буква, сброс кэша."""

    def setUp(self):
        clear_cache()

    def render(self, template, **context):
        return Template('{% load summary_extras %}' + template).render(Context(context))

    def test_all_logo_codes_point_to_existing_files(self):
        import importlib
        codes = importlib.import_module('summaries.migrations.0025_insurancecompany_logo_codes').LOGO_CODES.values()
        # компании из миграций получают коды (Югорию на проде добавили вручную — её в тестовой базе нет)
        self.assertEqual(InsuranceCompany.objects.exclude(logo_code='').count(), InsuranceCompany.objects.filter(
            name__in=importlib.import_module('summaries.migrations.0025_insurancecompany_logo_codes').LOGO_CODES).count())
        for code in codes:
            self.assertTrue((Path(settings.BASE_DIR) / 'static' / 'img' / 'insurers' / f'{code}.png').exists(), code)

    def test_filter_renders_logo_and_name(self):
        html = self.render('{{ name|insurer }}', name='Альфа')
        self.assertIn('<span class="ins"><img class="ins-logo" src="/static/img/insurers/alfa.png"', html)
        self.assertIn('>Альфа</span>', html)

    def test_filter_sizes_and_company_object(self):
        company = InsuranceCompany.objects.get(name='ВСК')
        self.assertIn('ins-logo--sm', self.render("{{ c|insurer:'sm' }}", c=company))
        self.assertIn('ins-logo--lg', self.render("{{ c|insurer:'lg' }}", c=company))

    def test_company_without_logo_gets_monogram(self):
        html = self.render('{{ name|insurer }}', name='другое')
        self.assertIn('ins-logo--mono', html)
        self.assertIn('>Д</span>другое', html)

    def test_joined_best_companies_get_a_logo_each(self):
        html = self.render('{{ names|insurer }}', names='Альфа, ВСК')
        self.assertEqual(html.count('class="ins-logo'), 2)

    def test_name_is_escaped(self):
        html = self.render('{{ name|insurer }}', name='<b>x</b>')
        self.assertNotIn('<b>x</b>', html)

    def test_cache_is_cleared_when_company_changes(self):
        self.assertIn('Альфа', logo_urls())
        InsuranceCompany.objects.filter(name='Альфа').update(logo_code='')
        company = InsuranceCompany.objects.get(name='Альфа')
        company.save()
        self.assertNotIn('Альфа', logo_urls())


class InsurerLogoPagesTests(TestCase):
    def setUp(self):
        clear_cache()
        group, _ = Group.objects.get_or_create(name='Администраторы')
        self.user = User.objects.create_user(username='logo_admin', password='testpass123')
        self.user.groups.add(group)
        self.client.login(username='logo_admin', password='testpass123')
        request_obj = InsuranceRequest.objects.create(
            created_by=self.user, client_name='ООО "Клиент"', inn='1234567890', dfa_number='ТС-1',
            insurance_type='КАСКО', status='emails_sent',
        )
        self.summary = InsuranceSummary.objects.create(
            request=request_obj, status='completed_accepted', selected_company='Альфа', selected_franchise_variant=1,
        )
        InsuranceOffer.objects.create(
            summary=self.summary, company_name='Альфа', insurance_year=1, insurance_sum=Decimal('1000000'),
            franchise_1=Decimal('0'), premium_with_franchise_1=Decimal('50000'),
        )

    def test_logos_on_summary_pages(self):
        for url in (
            reverse('summaries:summary_list'),
            reverse('summaries:summary_detail', args=[self.summary.pk]),
            reverse('summaries:deal_list'),
            reverse('summaries:deal_summary', args=[self.summary.pk]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, 'img/insurers/alfa.png', msg_prefix=url)

    def test_offer_form_gets_logo_map_for_select(self):
        response = self.client.get(reverse('summaries:add_offer', args=[self.summary.pk]))
        self.assertContains(response, 'id="insurer-logo-urls"')
        self.assertContains(response, 'id="company-logo"')

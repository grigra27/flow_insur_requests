from django.test import RequestFactory, TestCase, override_settings

from onlineservice.context_processors import navigation_context


class LandingContextProcessorTests(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()

    def test_navigation_context_works_without_request_user(self):
        request = self.request_factory.get('/')

        context = navigation_context(request)

        self.assertIn('app_navigation', context)
        self.assertIn('app_layout', context)

    @override_settings(
        MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
        SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su'],
        ALLOWED_HOSTS=['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su', 'testserver'],
    )
    def test_main_domain_root_serves_landing_page_without_500(self):
        response = self.client.get('/', HTTP_HOST='insflow.ru')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'здесь есть флоу')

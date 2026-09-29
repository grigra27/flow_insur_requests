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


@override_settings(
    MAIN_DOMAINS=['insflow.ru', 'insflow.tw1.su'],
    SUBDOMAINS=['zs.insflow.ru', 'zs.insflow.tw1.su'],
    ALLOWED_HOSTS=['insflow.ru', 'insflow.tw1.su', 'zs.insflow.ru', 'zs.insflow.tw1.su', 'testserver'],
)
class ErrorPagesTests(TestCase):
    """Русские страницы ошибок в стиле приложения."""

    def _login(self):
        from django.contrib.auth.models import Group, User
        user = User.objects.create_user(username='err_user', password='pwd')
        user.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        self.client.force_login(user)

    def test_app_404_is_russian_page(self):
        self._login()
        response = self.client.get('/requests/no-such-page/', HTTP_HOST='zs.insflow.ru')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Страница не найдена', status_code=404)
        self.assertContains(response, 'К списку заявок', status_code=404)
        self.assertNotContains(response, 'Not Found', status_code=404)

    def test_main_domain_404_points_to_app(self):
        response = self.client.get('/requests/', HTTP_HOST='insflow.ru')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Страница не найдена', status_code=404)
        self.assertContains(response, 'zs.insflow.ru', status_code=404)
        self.assertNotContains(response, 'Page Not Found', status_code=404)

    def test_500_template_renders_without_context(self):
        from django.template import loader
        html = loader.get_template('500.html').render()
        self.assertIn('Что-то пошло не так', html)
        self.assertIn('Ошибка 500', html)

    def test_access_denied_page(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user(username='no_group', password='pwd')
        self.client.force_login(user)
        response = self.client.get('/requests/', HTTP_HOST='zs.insflow.ru')
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Доступ запрещен', status_code=403)
        self.assertContains(response, 'Неопределенная роль', status_code=403)
        self.assertContains(response, 'bi-lock', status_code=403)

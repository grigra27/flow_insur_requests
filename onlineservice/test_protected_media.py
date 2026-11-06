"""Regression coverage for authenticated delivery of uploaded client documents."""

from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, quote, urlsplit

from django.contrib.auth.models import Group, User
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from insurance_requests.middleware import AuthenticationMiddleware


STAFF_HOSTS = ('zs.insflow.ru', 'zs.insflow.tw1.su')
MAIN_HOSTS = ('insflow.ru', 'insflow.tw1.su')


@override_settings(
    DEBUG=False,
    ENABLE_HTTPS=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=['testserver', *STAFF_HOSTS, *MAIN_HOSTS],
    MAIN_DOMAINS=list(MAIN_HOSTS),
    SUBDOMAINS=list(STAFF_HOSTS),
    PROTECTED_MEDIA_USE_X_ACCEL_REDIRECT=True,
)
class ProtectedMediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username='media-operator')
        cls.operator.groups.add(Group.objects.get_or_create(name='Пользователи')[0])
        cls.administrator = User.objects.create_user(username='media-administrator')
        cls.administrator.groups.add(
            Group.objects.get_or_create(name='Администраторы')[0]
        )
        cls.superuser = User.objects.create_user(
            username='media-superuser', is_superuser=True, is_staff=True
        )
        cls.unprivileged = User.objects.create_user(username='media-no-role')
        cls.inactive = User.objects.create_user(
            username='media-inactive', is_active=False, is_superuser=True
        )

    def setUp(self):
        self.temporary_media = TemporaryDirectory(prefix='insflow-private-media-test-')
        self.addCleanup(self.temporary_media.cleanup)
        self.media_root = Path(self.temporary_media.name)
        self.media_settings = override_settings(MEDIA_ROOT=self.media_root)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.relative_path = 'applications/example.pdf'
        self.payload = b'%PDF-1.4\nprivate client document\n'
        self._write_file(self.relative_path)

    def _write_file(self, relative_path):
        path = self.media_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.payload)
        return path

    def _url(self, relative_path=None):
        return reverse(
            'protected_media',
            kwargs={'path': relative_path or self.relative_path},
        )

    def _assert_private(self, response):
        directives = {
            value.strip().lower()
            for value in response.get('Cache-Control', '').split(',')
        }
        self.assertIn('private', directives)
        self.assertIn('no-store', directives)

    def _direct_request(self, path, user=None, method='get'):
        """Bypass URL normalization when testing hostile file path arguments."""
        request = getattr(RequestFactory(), method)(
            '/media/', HTTP_HOST=STAFF_HOSTS[0]
        )
        request.user = user or self.operator
        view = resolve(self._url()).func
        try:
            return view(request, path=path).status_code
        except Http404:
            return 404

    def test_media_is_not_in_authentication_middleware_public_allowlist(self):
        middleware = AuthenticationMiddleware(lambda request: None)
        self.assertFalse(middleware._is_public_url('/media/example.pdf'))
        self.assertFalse(middleware._is_public_url('/media/nested/example.xlsx'))

    def test_anonymous_requests_cannot_download_from_either_staff_host(self):
        for host in STAFF_HOSTS:
            for method in ('get', 'head'):
                with self.subTest(host=host, method=method):
                    response = getattr(self.client, method)(self._url(), HTTP_HOST=host)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response['Location'].startswith('/login/'))
                    self.assertNotIn('X-Accel-Redirect', response)
                    self._assert_private(response)

    def test_anonymous_redirect_preserves_encoded_filename_and_query_string(self):
        relative_path = 'заявки/Документ #1? 100%.pdf'
        requested_url = self._url(relative_path) + '?download=1&format=original'
        response = self.client.get(requested_url, HTTP_HOST=STAFF_HOSTS[0])
        self.assertEqual(response.status_code, 302)
        redirect_query = parse_qs(urlsplit(response['Location']).query)
        self.assertEqual(redirect_query, {'next': [requested_url]})
        self._assert_private(response)

    def test_authenticated_user_without_required_role_is_forbidden(self):
        self.client.force_login(self.unprivileged)
        for host in STAFF_HOSTS:
            with self.subTest(host=host):
                response = self.client.get(self._url(), HTTP_HOST=host)
                self.assertEqual(response.status_code, 403)
                self.assertNotIn('X-Accel-Redirect', response)

    def test_active_roles_and_superuser_can_download_on_both_staff_hosts(self):
        for user in (self.operator, self.administrator, self.superuser):
            self.client.force_login(user)
            for host in STAFF_HOSTS:
                with self.subTest(user=user.username, host=host):
                    response = self.client.get(self._url(), HTTP_HOST=host)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response['X-Accel-Redirect'],
                        '/_protected_media/' + self.relative_path,
                    )
                    self.assertEqual(response.content, b'')
                    self._assert_private(response)

    def test_inactive_superuser_is_rejected_by_view_itself(self):
        self.assertIn(
            self._direct_request(self.relative_path, user=self.inactive),
            (302, 403),
        )

    def test_x_accel_response_preserves_mime_size_and_inline_disposition(self):
        self.client.force_login(self.operator)
        response = self.client.get(self._url(), HTTP_HOST=STAFF_HOSTS[0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(response['Content-Length'], str(len(self.payload)))
        self.assertTrue(response['Content-Disposition'].startswith('inline;'))
        self.assertEqual(response.content, b'')
        self._assert_private(response)

    def test_x_accel_quotes_unicode_spaces_and_reserved_characters_once(self):
        relative_path = 'заявки/Документ #1? 100%.pdf'
        self._write_file(relative_path)
        self.client.force_login(self.operator)
        for host in STAFF_HOSTS:
            with self.subTest(host=host):
                response = self.client.get(self._url(relative_path), HTTP_HOST=host)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response['X-Accel-Redirect'],
                    '/_protected_media/' + quote(relative_path, safe='/'),
                )
                self.assertEqual(response['Content-Length'], str(len(self.payload)))
                self._assert_private(response)

    def test_head_preserves_x_accel_headers_without_a_body(self):
        self.client.force_login(self.operator)
        for host in STAFF_HOSTS:
            with self.subTest(host=host):
                response = self.client.head(self._url(), HTTP_HOST=host)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b'')
                self.assertEqual(response['Content-Length'], str(len(self.payload)))
                self.assertEqual(
                    response['X-Accel-Redirect'],
                    '/_protected_media/' + self.relative_path,
                )
                self._assert_private(response)

    def test_percent_encoded_characters_in_a_filename_are_not_decoded_twice(self):
        relative_path = 'applications/%2e%2e%2fexample.pdf'
        self._write_file(relative_path)
        self.client.force_login(self.operator)
        response = self.client.get(self._url(relative_path), HTTP_HOST=STAFF_HOSTS[0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['X-Accel-Redirect'],
            '/_protected_media/applications/%252e%252e%252fexample.pdf',
        )

    def test_range_request_still_requires_auth_and_delegates_to_nginx(self):
        for host in STAFF_HOSTS:
            with self.subTest(host=host, authenticated=False):
                response = self.client.get(
                    self._url(), HTTP_HOST=host, HTTP_RANGE='bytes=0-4'
                )
                self.assertEqual(response.status_code, 302)
                self.assertNotIn('X-Accel-Redirect', response)
        self.client.force_login(self.operator)
        for host in STAFF_HOSTS:
            with self.subTest(host=host, authenticated=True):
                response = self.client.get(
                    self._url(), HTTP_HOST=host, HTTP_RANGE='bytes=0-4'
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response['X-Accel-Redirect'],
                    '/_protected_media/' + self.relative_path,
                )
                self.assertEqual(response.content, b'')
                self._assert_private(response)

    @override_settings(PROTECTED_MEDIA_USE_X_ACCEL_REDIRECT=False)
    def test_local_delivery_streams_original_bytes_with_private_headers(self):
        self.client.force_login(self.operator)
        for host in STAFF_HOSTS:
            with self.subTest(host=host):
                response = self.client.get(self._url(), HTTP_HOST=host)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.streaming)
                    self.assertNotIn('X-Accel-Redirect', response)
                    self.assertEqual(response['Content-Type'], 'application/pdf')
                    self.assertEqual(response['Content-Length'], str(len(self.payload)))
                    self.assertTrue(response['Content-Disposition'].startswith('inline;'))
                    self.assertEqual(b''.join(response.streaming_content), self.payload)
                    self._assert_private(response)
                finally:
                    response.close()

    @override_settings(PROTECTED_MEDIA_USE_X_ACCEL_REDIRECT=False)
    def test_local_head_returns_original_size_without_document_bytes(self):
        self.client.force_login(self.operator)
        response = self.client.head(self._url(), HTTP_HOST=STAFF_HOSTS[0])
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Length'], str(len(self.payload)))
            self.assertNotIn('X-Accel-Redirect', response)
            self.assertEqual(b''.join(response.streaming_content), b'')
            self._assert_private(response)
        finally:
            response.close()

    def test_main_domains_never_serve_uploaded_documents(self):
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.operator)
            for host in MAIN_HOSTS:
                with self.subTest(host=host, authenticated=authenticated):
                    response = self.client.get(self._url(), HTTP_HOST=host)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn('X-Accel-Redirect', response)

    def test_missing_files_and_directories_return_not_found(self):
        self.client.force_login(self.operator)
        for relative_path in ('applications/missing.pdf', 'applications/'):
            with self.subTest(path=relative_path):
                response = self.client.get(self._url(relative_path), HTTP_HOST=STAFF_HOSTS[0])
                self.assertEqual(response.status_code, 404)
                self.assertNotIn('X-Accel-Redirect', response)

    def test_parent_traversal_and_absolute_paths_are_rejected(self):
        for path in (
            '../outside.pdf',
            'applications/../../outside.pdf',
            'applications/../applications/example.pdf',
            '/etc/passwd',
            str(self.media_root / self.relative_path),
            'applications\\example.pdf',
            'applications/example.pdf\x00',
        ):
            with self.subTest(path=path):
                self.assertEqual(self._direct_request(path), 404)

    def test_symlink_cannot_escape_media_root(self):
        with TemporaryDirectory(prefix='insflow-outside-media-test-') as outside:
            outside_file = Path(outside) / 'outside.pdf'
            outside_file.write_bytes(self.payload)
            (self.media_root / 'escape.pdf').symlink_to(outside_file)
            (self.media_root / 'escape-directory').symlink_to(outside, target_is_directory=True)
            for path in ('escape.pdf', 'escape-directory/outside.pdf'):
                with self.subTest(path=path):
                    self.assertEqual(self._direct_request(path), 404)

    def test_only_get_and_head_are_allowed(self):
        self.client.force_login(self.operator)
        for method in ('post', 'put', 'patch', 'delete', 'options'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self._url(), HTTP_HOST=STAFF_HOSTS[0])
                self.assertEqual(response.status_code, 405)
                self.assertEqual(
                    {value.strip() for value in response['Allow'].split(',')},
                    {'GET', 'HEAD'},
                )
                self.assertNotIn('X-Accel-Redirect', response)

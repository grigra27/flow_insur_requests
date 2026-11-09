import struct
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.test import TestCase, override_settings


class PageHead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}
        self.icons = set()
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and 'property' in attrs:
            self.values[attrs['property']] = attrs.get('content')
        elif tag == 'link' and 'icon' in attrs.get('rel', '').split():
            self.icons.add(attrs['href'])
        elif tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs['href']


@override_settings(MAIN_DOMAINS=['insflow.ru'], ALLOWED_HOSTS=['insflow.ru'])
class PublicCaseTests(TestCase):
    def test_anonymous_crawler_can_read_each_pages_declared_cover(self):
        headers = {'HTTP_HOST': 'insflow.ru', 'HTTP_USER_AGENT': 'LinkedInBot/1.0'}
        image_paths = set()
        for page in ('/', '/case/'):
            with self.subTest(page=page):
                response = self.client.get(page, secure=True, **headers)
                self.assertEqual(response.status_code, 200)
                html = b''.join(response.streaming_content) if response.streaming else response.content
                metadata = PageHead()
                metadata.feed(html.decode('utf-8').split('</head>', 1)[0])
                tags = metadata.values
                self.assertEqual(metadata.canonical, 'https://insflow.ru' + page)
                self.assertEqual(tags['og:url'], metadata.canonical)
                for tag in ('og:title', 'og:description', 'og:image:alt'):
                    self.assertTrue(tags[tag])
                image_url = urlsplit(tags['og:image'])
                self.assertEqual((image_url.scheme, image_url.netloc), ('https', 'insflow.ru'))
                cover = self.client.get(image_url.path, secure=True, **headers)
                self.assertEqual(cover.status_code, 200)
                self.assertEqual(cover['Content-Type'], tags['og:image:type'])
                png = b''.join(cover.streaming_content)
                self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                self.assertEqual(struct.unpack('>II', png[16:24]),
                                 (int(tags['og:image:width']), int(tags['og:image:height'])))
                image_paths.add(image_url.path)
        self.assertEqual(len(image_paths), 2)

    def test_landing_and_case_declare_the_same_public_favicon(self):
        headers = {'HTTP_HOST': 'insflow.ru'}
        for page in ('/', '/case/'):
            with self.subTest(page=page):
                response = self.client.get(page, secure=True, **headers)
                self.assertEqual(response.status_code, 200)
                html = b''.join(response.streaming_content) if response.streaming else response.content
                head = PageHead()
                head.feed(html.decode().split('</head>', 1)[0])
                self.assertIn('/favicon.svg', head.icons)
                self.assertLessEqual(head.icons, {'/favicon.svg', '/favicon.ico'})
        for path, mime in (('/favicon.svg', 'image/svg+xml'), ('/favicon.ico', 'image/x-icon')):
            with self.subTest(path=path):
                response = self.client.get(path, secure=True, **headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], mime)
                self.assertTrue(b''.join(response.streaming_content))

    def test_publication_is_limited_to_public_files(self):
        headers = {'HTTP_HOST': 'insflow.ru'}
        redirect = self.client.get('/case?ref=profile', secure=True, **headers)
        self.assertEqual(redirect.status_code, 301)
        self.assertEqual(redirect['Location'], '/case/?ref=profile')
        self.assertEqual(self.client.head('/case/cover-v3.png', secure=True, **headers).status_code, 200)
        self.assertEqual(self.client.post('/case/', secure=True, **headers).status_code, 405)
        self.assertEqual(self.client.get('/case/artwork/cover.html', secure=True, **headers).status_code, 404)

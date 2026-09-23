"""
Тесты для команды send_backup_to_vk.

Не лезем в реальный VK API — мокаем requests.post. Не вызываем pg_dump —
для всех сценариев работаем через --skip-create и заранее подготовленные файлы.
"""
import os
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from backup.management.commands.send_backup_to_vk import Command


def _ok_response(payload):
    """Хелпер: возвращает MagicMock, имитирующий requests.Response с .json()."""
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = payload
    return m


def _http_response(status_code, payload=None):
    """Хелпер: ответ с конкретным HTTP-статусом (для проверки ретраев)."""
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = payload if payload is not None else {}
    if 400 <= status_code < 600:
        m.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f'{status_code} Client Error', response=m
        )
    else:
        m.raise_for_status.return_value = None
    return m


def _upload_server_response(node='c903718'):
    url = f'https://pu.vk.com/{node}/upload.php'
    return _ok_response({'response': {'upload_url': url}})


def _save_doc_response():
    return _ok_response({'response': {'type': 'doc', 'doc': {'id': 99, 'owner_id': -7}}})


def _messages_send_response():
    return _ok_response({'response': 1001})


@override_settings(
    VK_BACKUP_TOKEN='test-token',
    VK_BACKUP_PEER_ID='12345',
    VK_API_VERSION='5.199',
)
class VkCommandTestBase(TestCase):
    """Общая обвязка: свой output_dir с одним дампом на каждый тест."""

    def setUp(self):
        from tempfile import mkdtemp
        self.tmp_dir = mkdtemp(prefix='vk_backup_test_')
        self.dump_path = os.path.join(self.tmp_dir, 'pgdump_20260101_030000.dump')
        with open(self.dump_path, 'wb') as f:
            f.write(b'fake-pgdump-content')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def run_command(self, *extra_args, **kwargs):
        return call_command(
            'send_backup_to_vk',
            f'--output-dir={self.tmp_dir}',
            '--skip-create',
            *extra_args,
            **kwargs,
        )


@override_settings(
    VK_BACKUP_TOKEN='test-token',
    VK_BACKUP_PEER_ID='12345',
    VK_API_VERSION='5.199',
)
class SendBackupToVkTests(VkCommandTestBase):

    # ---------- happy path

    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_sends_existing_backup_via_vk(self, mock_post):
        mock_post.side_effect = [
            _ok_response({'response': {'upload_url': 'https://vk.example/upload'}}),
            _ok_response({'file': 'uploaded-file-token'}),
            _ok_response({'response': {'type': 'doc', 'doc': {'id': 99, 'owner_id': -7}}}),
            _ok_response({'response': 1001}),
        ]

        call_command(
            'send_backup_to_vk',
            f'--output-dir={self.tmp_dir}',
            '--skip-create',
            stdout=StringIO(),
        )

        self.assertEqual(mock_post.call_count, 4)
        getserver_call = mock_post.call_args_list[0]
        self.assertIn('docs.getMessagesUploadServer', getserver_call.args[0])
        self.assertEqual(getserver_call.kwargs['data']['type'], 'doc')
        self.assertEqual(getserver_call.kwargs['data']['peer_id'], '12345')
        self.assertEqual(getserver_call.kwargs['data']['access_token'], 'test-token')

        save_call = mock_post.call_args_list[2]
        self.assertIn('docs.save', save_call.args[0])

        send_call = mock_post.call_args_list[3]
        self.assertIn('messages.send', send_call.args[0])
        self.assertEqual(send_call.kwargs['data']['attachment'], 'doc-7_99')
        self.assertEqual(send_call.kwargs['data']['peer_id'], '12345')

    # ---------- size limit

    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_oversized_file_aborts_and_notifies(self, mock_post):
        # Перезаписываем файл, чтобы он "превышал" лимит — патчим os.path.getsize
        mock_post.return_value = _ok_response({'response': 1001})

        with patch(
            'backup.management.commands.send_backup_to_vk.os.path.getsize',
            return_value=300 * 1024 * 1024,
        ):
            with self.assertRaises(CommandError):
                call_command(
                    'send_backup_to_vk',
                    f'--output-dir={self.tmp_dir}',
                    '--skip-create',
                    stdout=StringIO(),
                    stderr=StringIO(),
                )

        # Должен был быть один вызов — уведомление об ошибке через messages.send
        self.assertEqual(mock_post.call_count, 1)
        notify_call = mock_post.call_args
        self.assertIn('messages.send', notify_call.args[0])
        self.assertIn('190 МБ', notify_call.kwargs['data']['message'])

    # ---------- missing config

    @override_settings(VK_BACKUP_TOKEN='', VK_BACKUP_PEER_ID='')
    def test_missing_credentials_raises(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                'send_backup_to_vk',
                f'--output-dir={self.tmp_dir}',
                '--skip-create',
                stdout=StringIO(),
                stderr=StringIO(),
            )
        self.assertIn('VK_BACKUP_TOKEN', str(ctx.exception))

    # ---------- VK API error path

    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_vk_error_triggers_failure_notification(self, mock_post):
        # Первый вызов docs.getMessagesUploadServer возвращает ошибку.
        # Второй (notify) — успешный, чтобы не упасть в except внутри _notify_failure.
        mock_post.side_effect = [
            _ok_response({'error': {'error_code': 5, 'error_msg': 'Auth failed'}}),
            _ok_response({'response': 1001}),
        ]

        with self.assertRaises(CommandError):
            call_command(
                'send_backup_to_vk',
                f'--output-dir={self.tmp_dir}',
                '--skip-create',
                stdout=StringIO(),
                stderr=StringIO(),
            )

        self.assertEqual(mock_post.call_count, 2)
        notify_call = mock_post.call_args_list[1]
        self.assertIn('messages.send', notify_call.args[0])
        self.assertIn('Auth failed', notify_call.kwargs['data']['message'])

    # ---------- no files at all

    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_no_files_to_send(self, mock_post):
        os.unlink(self.dump_path)
        mock_post.return_value = _ok_response({'response': 1001})

        with self.assertRaises(CommandError) as ctx:
            call_command(
                'send_backup_to_vk',
                f'--output-dir={self.tmp_dir}',
                '--skip-create',
                stdout=StringIO(),
                stderr=StringIO(),
            )
        self.assertIn('Не найден', str(ctx.exception))


def _api_calls(mock_post):
    """Индексы вызовов, пришедших в api.vk.com/method/<метод>."""
    return [
        call.args[0].rsplit('/', 1)[-1]
        for call in mock_post.call_args_list
        if '/method/' in call.args[0]
    ]


@override_settings(
    VK_BACKUP_TOKEN='test-token',
    VK_BACKUP_PEER_ID='12345',
    VK_API_VERSION='5.199',
)
class UploadRetryTests(VkCommandTestBase):
    """Ретраи этапа «загрузка файла на приёмную ноду VK»."""

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_retries_upload_on_http_405(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            _upload_server_response('c903718'),
            _http_response(405),
            _upload_server_response('c902018'),
            _ok_response({'file': 'uploaded-file-token'}),
            _save_doc_response(),
            _messages_send_response(),
        ]

        self.run_command(stdout=StringIO())

        self.assertEqual(
            _api_calls(mock_post),
            ['docs.getMessagesUploadServer', 'docs.getMessagesUploadServer',
             'docs.save', 'messages.send'],
        )
        # Повторная попытка обязана идти на свежеполученный URL, а не на тот же.
        upload_urls = [
            call.args[0] for call in mock_post.call_args_list
            if 'upload.php' in call.args[0]
        ]
        self.assertEqual(upload_urls, [
            'https://pu.vk.com/c903718/upload.php',
            'https://pu.vk.com/c902018/upload.php',
        ])
        self.assertEqual(mock_sleep.call_count, 1)
        delay = mock_sleep.call_args.args[0]
        self.assertGreaterEqual(delay, 15 * 0.8)
        self.assertLessEqual(delay, 15 * 1.2)

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_retries_upload_on_payload_error(self, mock_post, mock_sleep):
        # {'error': 'not saved'} — самый частый класс сбоя в проде.
        mock_post.side_effect = [
            _upload_server_response(),
            _ok_response({'error': 'not saved', 'error_descr': 'not saved'}),
            _upload_server_response(),
            _ok_response({'file': 'uploaded-file-token'}),
            _save_doc_response(),
            _messages_send_response(),
        ]

        self.run_command(stdout=StringIO())

        self.assertEqual(mock_sleep.call_count, 1)

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_backoff_grows_exponentially(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            _upload_server_response(), _http_response(502),
            _upload_server_response(), _http_response(502),
            _upload_server_response(), _http_response(502),
            _upload_server_response(), _ok_response({'file': 'tok'}),
            _save_doc_response(), _messages_send_response(),
        ]

        self.run_command('--upload-attempts=4', '--retry-base-delay=10', stdout=StringIO())

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertEqual(len(delays), 3)
        for delay, expected in zip(delays, (10, 20, 40)):
            self.assertGreaterEqual(delay, expected * 0.8)
            self.assertLessEqual(delay, expected * 1.2)

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_single_attempt_disables_retry(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            _upload_server_response(),
            _http_response(405),
            _messages_send_response(),  # уведомление о провале
        ]

        with self.assertRaises(CommandError):
            self.run_command('--upload-attempts=1', stdout=StringIO(), stderr=StringIO())

        self.assertEqual(mock_sleep.call_count, 0)
        self.assertEqual(mock_post.call_count, 3)

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_exhausted_attempts_notifies_once_with_attempt_count(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            _upload_server_response(), _http_response(405),
            _upload_server_response(), _http_response(405),
            _upload_server_response(), _http_response(405),
            _messages_send_response(),
        ]

        with self.assertRaises(CommandError) as ctx:
            self.run_command('--upload-attempts=3', stdout=StringIO(), stderr=StringIO())

        self.assertIn('попыток загрузки: 3', str(ctx.exception))
        notify_call = mock_post.call_args_list[-1]
        self.assertIn('messages.send', notify_call.args[0])
        self.assertIn('VK отклонил загрузку (HTTP 405), попыток: 3',
                      notify_call.kwargs['data']['message'])
        # 3 попытки => только 2 паузы, и ровно одно уведомление о провале.
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(
            sum(1 for c in mock_post.call_args_list if 'messages.send' in c.args[0]), 1
        )

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_vk_api_permission_error_is_not_retried(self, mock_post, mock_sleep):
        # code=15 Access denied (28.06, 30.06, 02.07 в проде) — ретраем не лечится.
        mock_post.side_effect = [
            _ok_response({'error': {'error_code': 15, 'error_msg': 'Access denied'}}),
            _messages_send_response(),
        ]

        with self.assertRaises(CommandError):
            self.run_command(stdout=StringIO(), stderr=StringIO())

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 0)

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_total_timeout_budget_stops_retries(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            _upload_server_response(), _http_response(405), _messages_send_response(),
        ]

        with self.assertRaises(CommandError):
            self.run_command('--upload-attempts=5', '--total-timeout=0',
                             stdout=StringIO(), stderr=StringIO())

        self.assertEqual(mock_sleep.call_count, 0)
        self.assertEqual(
            sum(1 for c in mock_post.call_args_list
                if 'getMessagesUploadServer' in c.args[0]), 1
        )

    @patch('backup.management.commands.send_backup_to_vk.time.sleep')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_dump_created_once_despite_upload_retries(self, mock_post, mock_sleep):
        # Деградация VK не должна превращать суточный прогон в N дампов.
        mock_post.side_effect = [
            _upload_server_response(), _http_response(405),
            _upload_server_response(), _ok_response({'file': 'tok'}),
            _save_doc_response(), _messages_send_response(),
        ]

        with patch.object(Command, '_create_backup') as mock_create:
            call_command(
                'send_backup_to_vk',
                f'--output-dir={self.tmp_dir}',
                '--upload-attempts=4',
                stdout=StringIO(),
            )

        mock_create.assert_called_once_with(self.tmp_dir, 14)
        self.assertEqual(mock_sleep.call_count, 1)

    def test_empty_env_value_falls_back_to_default(self):
        # docker-compose подставляет ${VAR:-default}, но пустая строка в .env
        # не должна превращать суточный прогон в ValueError.
        from backup.management.commands import send_backup_to_vk as mod

        with patch.dict(os.environ, {'VK_UPLOAD_ATTEMPTS': '', 'VK_RETRY_BASE_DELAY': 'oops'}):
            self.assertEqual(mod._env_number('VK_UPLOAD_ATTEMPTS', 4), 4)
            self.assertEqual(mod._env_number('VK_RETRY_BASE_DELAY', 15, float), 15)
        with patch.dict(os.environ, {'VK_UPLOAD_ATTEMPTS': '7'}):
            self.assertEqual(mod._env_number('VK_UPLOAD_ATTEMPTS', 4), 7)


FROZEN_NOON = datetime(2026, 9, 23, 3, 0, 5)


@override_settings(
    VK_BACKUP_TOKEN='test-token',
    VK_BACKUP_PEER_ID='12345',
    VK_API_VERSION='5.199',
)
class VkMessageTextTests(VkCommandTestBase):
    """Тексты, которые читает человек в личке VK."""

    def sent_message(self, mock_post):
        return mock_post.call_args_list[-1].kwargs['data']['message']

    @patch('backup.management.commands.send_backup_to_vk.timezone.localtime')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_success_message_is_human_readable(self, mock_post, mock_localtime):
        mock_localtime.return_value = FROZEN_NOON
        mock_post.side_effect = [
            _upload_server_response(),
            _ok_response({'file': 'tok'}),
            _save_doc_response(),
            _messages_send_response(),
        ]

        with patch(
            'backup.management.commands.send_backup_to_vk.os.path.getsize',
            return_value=9_923_433,
        ):
            self.run_command(stdout=StringIO())

        self.assertEqual(
            self.sent_message(mock_post),
            '📦 Резервная копия базы «флоу / заявки» — 23 сентября, 03:00\n'
            '9,5 МБ · pgdump_20260101_030000.dump',
        )

    @patch('backup.management.commands.send_backup_to_vk.timezone.localtime')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_failure_message_says_copy_is_safe(self, mock_post, mock_localtime):
        # Дамп на сервере есть — подведена только доставка во внешнее хранилище.
        mock_localtime.return_value = FROZEN_NOON
        mock_post.side_effect = [
            _upload_server_response(), _http_response(405), _messages_send_response(),
        ]

        with self.assertRaises(CommandError):
            self.run_command('--upload-attempts=1', stdout=StringIO(), stderr=StringIO())

        self.assertEqual(
            self.sent_message(mock_post),
            '⚠️ Копия базы «флоу / заявки» за 23 сентября не дошла в VK\n'
            'На сервере цела — под вопросом только внешняя копия.\n'
            'Причина: VK отклонил загрузку (HTTP 405)',
        )

    @patch('backup.management.commands.send_backup_to_vk.timezone.localtime')
    @patch('backup.management.commands.send_backup_to_vk.requests.post')
    def test_failure_message_warns_when_no_copy_at_all(self, mock_post, mock_localtime):
        # Ни дампа, ни JSON-файла: это не «не дошло», это вообще нет копии.
        mock_localtime.return_value = FROZEN_NOON
        os.unlink(self.dump_path)
        mock_post.side_effect = [_messages_send_response()]

        with self.assertRaises(CommandError):
            self.run_command(stdout=StringIO(), stderr=StringIO())

        message = self.sent_message(mock_post)
        self.assertIn('не создана', message)
        self.assertIn('Ни на сервере, ни в VK', message)
        self.assertIn('Не найден ни один бэкап', message)
        self.assertNotIn('На сервере цела', message)

    def test_no_technical_noise_in_texts(self):
        from backup.management.commands import send_backup_to_vk as mod

        cases = {
            "VK upload error: {'error': 'not saved', 'error_descr': 'not saved'}":
                'VK не сохранил файл',
            "VK upload error: {'error': 'no_free_space/var/www/pi'}":
                'в VK закончилось место',
            "VK upload error: {'error': 'no_file'}":
                'файл не дошёл до VK',
            'HTTP 502 при загрузке на https://pu.vk.com/c903718 (попыток загрузки: 4)':
                'VK отклонил загрузку (HTTP 502), попыток: 4',
            'VK API error in docs.save: code=15 msg=Access denied':
                'VK не даёт отправлять — проверьте права токена',
        }
        for raw, expected in cases.items():
            self.assertEqual(mod._humanize_error(Exception(raw)), expected)

    def test_size_is_rendered_without_trailing_zero(self):
        from backup.management.commands import send_backup_to_vk as mod

        self.assertEqual(mod._human_size(9_923_433), '9,5 МБ')
        self.assertEqual(mod._human_size(10 * 1024 * 1024), '10 МБ')
        self.assertEqual(mod._human_size(1024 * 1024), '1 МБ')

    def test_date_uses_localtime_not_container_utc(self):
        # Часы контейнера в UTC: naive datetime.now() показал бы минус 3 часа.
        from backup.management.commands import send_backup_to_vk as mod

        with patch.object(mod.timezone, 'localtime', return_value=FROZEN_NOON):
            self.assertEqual(mod._human_datetime(), '23 сентября, 03:00')
            self.assertEqual(mod._human_datetime(with_time=False), '23 сентября')

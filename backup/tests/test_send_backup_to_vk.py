"""
Тесты для команды send_backup_to_vk.

Не лезем в реальный VK API — мокаем requests.post. Не вызываем pg_dump —
для всех сценариев работаем через --skip-create и заранее подготовленные файлы.
"""
import os
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


def _ok_response(payload):
    """Хелпер: возвращает MagicMock, имитирующий requests.Response с .json()."""
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = payload
    return m


@override_settings(
    VK_BACKUP_TOKEN='test-token',
    VK_BACKUP_PEER_ID='12345',
    VK_API_VERSION='5.199',
)
class SendBackupToVkTests(TestCase):
    def setUp(self):
        # Каждый тест получает свой output_dir внутри Django-овского tmp.
        from tempfile import mkdtemp
        self.tmp_dir = mkdtemp(prefix='vk_backup_test_')
        self.dump_path = os.path.join(self.tmp_dir, 'pgdump_20260101_030000.dump')
        with open(self.dump_path, 'wb') as f:
            f.write(b'fake-pgdump-content')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

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

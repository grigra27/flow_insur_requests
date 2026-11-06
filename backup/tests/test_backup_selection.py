"""Select this run's finished backup and never silently upload an older copy."""

import gzip
import os
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from backup.management.commands.send_backup_to_vk import Command


@override_settings(VK_BACKUP_TOKEN='test-token', VK_BACKUP_PEER_ID='12345')
class BackupSelectionTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='backup-selection-test-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.stdout = StringIO()
        network = patch(
            'backup.management.commands.send_backup_to_vk.requests.post',
            side_effect=AssertionError('Unexpected network request'),
        )
        self.network = network.start()
        self.addCleanup(network.stop)

    def _file(self, name, content=b'PGDMP-current', mtime=None):
        path = self.directory / name
        path.write_bytes(content)
        if mtime is not None:
            os.utime(path, ns=(mtime, mtime))
        return str(path)

    def _run(self, **options):
        defaults = dict(
            output_dir=str(self.directory),
            keep=14,
            no_notify=True,
            stdout=self.stdout,
            stderr=StringIO(),
        )
        defaults.update(options)
        return call_command('send_backup_to_vk', **defaults)

    def _sent_path(self, send):
        send.assert_called_once()
        return send.call_args.args[0]

    def _response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        return response

    def test_current_pg_dump_is_used_even_with_future_named_newer_old_copy(self):
        current = self._file('pgdump_current.dump', mtime=100)
        self._file('pgdump_99991231_235959.dump', b'old-copy', mtime=900)
        self._file('backup_99991231_235959.json', b'[{"old": true}]', mtime=1000)
        with patch(
            'backup.management.commands.send_backup_to_vk.call_command',
            return_value=current,
        ) as create, patch.object(Command, '_send_to_vk') as send, patch.object(
            Command, '_select_file_to_send', side_effect=AssertionError('Unexpected old-file search')
        ):
            self._run()
        self.assertEqual(self._sent_path(send), current)
        self.assertEqual(create.call_count, 1)
        self.network.assert_not_called()

    def test_pg_failure_sends_returned_json_instead_of_old_or_partial_dump(self):
        self._file('pgdump_99991231_235959.dump', b'old-copy')
        raw = b'[{"model": "example.current", "pk": 42}]'

        def create(command, *arguments):
            if arguments[arguments.index('--format') + 1] == 'pgdump':
                self._file('pgdump_partial.dump', b'PGDMP-incomplete')
                raise CommandError('Forced pg_dump failure')
            return self._file('backup_current.json', raw)

        with patch(
            'backup.management.commands.send_backup_to_vk.call_command', side_effect=create
        ) as create_mock, patch.object(Command, '_send_to_vk') as send:
            self._run()
        self.assertEqual(create_mock.call_count, 2)
        self.assertEqual(self._sent_path(send), str(self.directory / 'backup_current.json.gz'))
        with gzip.open(self._sent_path(send), 'rb') as compressed:
            self.assertEqual(compressed.read(), raw)
        self.assertIn('не заменяет полный pg_dump', self.stdout.getvalue())
        self.network.assert_not_called()

    def test_both_creation_failures_never_upload_an_existing_good_copy(self):
        old = self._file('pgdump_old.dump', b'old-good-copy')
        with patch(
            'backup.management.commands.send_backup_to_vk.call_command',
            side_effect=CommandError('Cannot create current backup'),
        ) as create, patch.object(Command, '_send_to_vk') as send:
            with self.assertRaises(CommandError):
                self._run()
        self.assertEqual(create.call_count, 2)
        send.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(Path(old).read_bytes(), b'old-good-copy')

    def test_invalid_returned_artifacts_fail_closed_without_old_file_search(self):
        self._file('pgdump_old.dump')
        empty = self._file('backup_empty.json', b'')
        for result in (None, str(self.directory / 'missing.dump'), empty, self.directory):
            with self.subTest(result=result), patch(
                'backup.management.commands.send_backup_to_vk.call_command',
                return_value=result,
            ) as create, patch.object(Command, '_send_to_vk') as send, patch.object(
                Command, '_select_file_to_send', side_effect=AssertionError('Unexpected old-file search')
            ):
                with self.assertRaises(CommandError):
                    self._run()
                self.assertEqual(create.call_count, 2)
                send.assert_not_called()
        self.network.assert_not_called()

    def test_invalid_pg_return_falls_back_to_exact_valid_json_result(self):
        current = self._file('backup_current.json', b'[]')
        self._file('pgdump_old.dump')
        with patch(
            'backup.management.commands.send_backup_to_vk.call_command',
            side_effect=[str(self.directory / 'missing.dump'), current],
        ), patch.object(Command, '_send_to_vk') as send:
            self._run()
        self.assertEqual(self._sent_path(send), current + '.gz')

    def test_skip_create_selects_newest_json_by_mtime_across_formats(self):
        self._file('pgdump_99991231_235959.dump', mtime=100)
        current = self._file('backup_20200101_000000.json', b'[]', mtime=200)
        with patch(
            'backup.management.commands.send_backup_to_vk.call_command',
            side_effect=AssertionError('skip-create must not create a backup'),
        ), patch.object(Command, '_send_to_vk') as send:
            self._run(skip_create=True)
        self.assertEqual(self._sent_path(send), current + '.gz')

    def test_skip_create_selects_newest_dump_despite_future_json_filename(self):
        self._file('backup_99991231_235959.json', b'[]', mtime=100)
        current = self._file('pgdump_20200101_000000.dump', mtime=200)
        with patch.object(Command, '_send_to_vk') as send:
            self._run(skip_create=True)
        self.assertEqual(self._sent_path(send), current)

    def test_skip_create_prefers_full_dump_when_modification_times_are_equal(self):
        self._file('backup_99991231_235959.json', b'[]', mtime=100)
        current = self._file('pgdump_20200101_000000.dump', mtime=100)
        with patch.object(Command, '_send_to_vk') as send:
            self._run(skip_create=True)
        self.assertEqual(self._sent_path(send), current)

    def test_skip_create_ignores_temporary_and_empty_files(self):
        for name, content in (
            ('.pgdump_unfinished.dump.part', b'incomplete'),
            ('pgdump_unfinished.dump.part', b'incomplete'),
            ('.backup_unfinished.json.part', b'incomplete'),
            ('pgdump_empty.dump', b''),
            ('backup_empty.json', b''),
            ('backup_orphan.json.gz', b'stale-gzip-without-source'),
        ):
            self._file(name, content)
        with patch.object(Command, '_send_to_vk') as send:
            with self.assertRaises(CommandError):
                self._run(skip_create=True)
        send.assert_not_called()
        self.network.assert_not_called()

    def test_json_gzip_is_rebuilt_even_when_a_stale_gzip_already_exists(self):
        raw = b'[{"current": true}]'
        current = self._file('backup_current.json', raw)
        with gzip.open(current + '.gz', 'wb') as compressed:
            compressed.write(b'[{"stale": true}]')
        with patch(
            'backup.management.commands.send_backup_to_vk.call_command', return_value=current
        ), patch.object(Command, '_send_to_vk') as send:
            self._run()
        with gzip.open(self._sent_path(send), 'rb') as compressed:
            self.assertEqual(compressed.read(), raw)
        self.assertFalse(list(self.directory.glob('*.part')))

    def test_gzip_failure_cleans_temporary_file_and_reports_raw_copy_exists(self):
        raw = b'[{"current": true}]'
        current = self._file('backup_current.json', raw)

        def fail_compression(source, destination):
            destination.write(b'partial-compression')
            raise OSError('Forced compression failure')

        with patch(
            'backup.management.commands.send_backup_to_vk.call_command', return_value=current
        ), patch(
            'backup.management.commands.send_backup_to_vk.shutil.copyfileobj',
            side_effect=fail_compression,
        ), patch.object(Command, '_send_to_vk') as send, patch.object(
            Command, '_notify_failure'
        ) as notify:
            with self.assertRaises(CommandError):
                self._run(no_notify=False)
        send.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(Path(current).read_bytes(), raw)
        self.assertFalse(Path(current + '.gz').exists())
        self.assertFalse(list(self.directory.glob('*.part')))
        notify.assert_called_once()
        self.assertIs(notify.call_args.args[-1], True)

    def test_vk_message_warns_for_json_while_full_dump_message_stays_unchanged(self):
        frozen = datetime(2026, 9, 23, 3, 0, 5)
        for filename, content, is_json in (
            ('pgdump_current.dump', b'PGDMP-current', False),
            ('backup_current.json', b'[]', True),
        ):
            current = self._file(filename, content)
            self.network.reset_mock()
            self.network.side_effect = [
                self._response({'response': {'upload_url': 'https://vk.example/upload'}}),
                self._response({'file': 'fake-upload-token'}),
                self._response({'response': {'doc': {'id': 99, 'owner_id': -7}}}),
                self._response({'response': 1001}),
            ]
            with self.subTest(filename=filename), patch(
                'backup.management.commands.send_backup_to_vk.call_command',
                return_value=current,
            ), patch(
                'backup.management.commands.send_backup_to_vk.timezone.localtime',
                return_value=frozen,
            ):
                self._run()
            self.assertEqual(self.network.call_count, 4)
            message = self.network.call_args.kwargs['data']['message']
            if is_json:
                self.assertIn('Аварийная JSON-выгрузка', message)
                self.assertIn('Без пользователей, групп и прав.', message)
                self.assertIn('Не заменяет полный pg_dump.', message)
            else:
                self.assertEqual(
                    message,
                    '📦 Резервная копия базы «флоу / заявки» — 23 сентября, 03:00\n'
                    '0 МБ · pgdump_current.dump',
                )

    def test_json_failure_notification_describes_retained_limited_export(self):
        current = self._file('backup_current.json', b'[]')
        self.network.side_effect = [self._response({'response': 1001})]
        with patch(
            'backup.management.commands.send_backup_to_vk.call_command', return_value=current
        ), patch.object(Command, '_gzip_json', side_effect=OSError('Compression failed')):
            with self.assertRaises(CommandError):
                self._run(no_notify=False)
        self.assertEqual(self.network.call_count, 1)
        self.assertTrue(self.network.call_args.args[0].endswith('/messages.send'))
        message = self.network.call_args.kwargs['data']['message']
        self.assertIn('JSON сохранён на сервере', message)
        self.assertIn('не содержит пользователей, групп и прав', message)
        self.assertIn('не заменяет полный pg_dump', message)
        self.assertNotIn('Ни на сервере, ни в VK', message)

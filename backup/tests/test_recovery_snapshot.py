"""Recovery data snapshots fail closed without touching PostgreSQL or a network.

PostgreSQL transactions and command-line utilities are mocked. Media trees,
archive publication, hashes, permissions, and mutation checks use real private
temporary files; no project or production documents are read.
"""

from contextlib import contextmanager
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command, CommandError
from django.db import models
from django.test import SimpleTestCase

from backup import recovery_snapshot as snapshot


COMMAND = 'backup.management.commands.create_recovery_snapshot'
ARCHIVE = b'PGDMP\x01\x0f\x00complete custom archive fixture'
PASSWORD = 'fixture-password-never-in-argv-or-errors'
SNAPSHOT_ID = '00000003-0000001B-1'


class RecoverySnapshotTests(SimpleTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='insflow-recovery-data-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.media = self.root / 'source-media'
        self.media.mkdir()
        self.output = self.root / 'snapshots'
        self.output.mkdir()
        self.observed_processes = []

    def _media_file(self, name='documents/request.xlsx', payload=b'fixture workbook'):
        path = self.media / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    @contextmanager
    def _postgres(self, references=(), utility=None):
        state = {'transaction': False, 'sql': []}
        previous_ready = set(self.output.glob('recovery_*'))
        cursor = MagicMock()

        def execute(sql, params=None):
            self.assertTrue(state['transaction'])
            state['sql'].append(sql)

        def fetchone():
            if state['sql'][-1] == 'SELECT pg_export_snapshot()':
                return (SNAPSHOT_ID,)
            return (7,)

        cursor.execute.side_effect = execute
        cursor.fetchone.side_effect = fetchone
        connection = MagicMock()
        connection.vendor = 'postgresql'
        connection.in_atomic_block = False
        connection.alias = 'default'
        connection.ops.quote_name.side_effect = lambda value: '"' + value + '"'
        connection.introspection.table_names.return_value = ['fixture_record']
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.settings_dict = {
            'NAME': 'fixture-database', 'USER': 'fixture-user',
            'PASSWORD': PASSWORD, 'HOST': 'database.invalid', 'PORT': '5432',
        }

        @contextmanager
        def atomic(*, using):
            self.assertEqual(using, 'default')
            state['transaction'] = True
            try:
                yield
            finally:
                state['transaction'] = False

        def successful_utility(arguments, **kwargs):
            self.observed_processes.append((arguments, kwargs))
            executable = Path(arguments[0]).name
            if executable == 'pg_dump':
                self.assertTrue(state['transaction'])
                self.assertEqual(arguments[arguments.index('--snapshot') + 1], SNAPSHOT_ID)
                self.assertEqual(kwargs['env']['PGPASSWORD'], PASSWORD)
                self.assertIn('default_transaction_read_only=on', kwargs['env']['PGOPTIONS'])
                self.assertNotIn(PASSWORD, repr(arguments))
                target = Path(arguments[arguments.index('--file') + 1])
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertTrue(target.parent.name.endswith('.part'))
                self.assertEqual(set(self.output.glob('recovery_*')), previous_ready)
                target.write_bytes(ARCHIVE)
            else:
                self.assertEqual(executable, 'pg_restore')
                self.assertEqual(arguments[1], '--file=/dev/null')
                self.assertNotIn('--dbname', arguments)
                self.assertFalse(any(key.startswith('PG') for key in kwargs['env']))
                self.assertFalse(state['transaction'])
            return subprocess.CompletedProcess(arguments, 0, stdout=b'', stderr=b'')

        with patch.object(snapshot, 'connection', connection), patch.object(
            snapshot.transaction, 'atomic', side_effect=atomic,
        ), patch.object(snapshot, '_file_references', return_value=set(references)), patch.object(
            snapshot.shutil, 'which', side_effect=lambda name: '/fixture/bin/' + name,
        ), patch.object(snapshot.subprocess, 'run', side_effect=utility or successful_utility):
            yield state, cursor, connection

    def _create(self):
        return Path(snapshot.create_recovery_snapshot(self.output, media_root=self.media))

    def _assert_no_publication(self):
        self.assertEqual(list(self.output.iterdir()), [])

    def test_snapshot_uses_exported_read_only_transaction_and_verifies_entire_dump(self):
        with self._postgres() as (state, cursor, connection):
            ready = self._create()

        self.assertEqual(state['sql'][:2], [
            'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY',
            'SELECT pg_export_snapshot()',
        ])
        self.assertEqual(state['sql'][2:], ['SELECT COUNT(*) FROM "fixture_record"'])
        connection.introspection.table_names.assert_called_once_with(cursor=cursor)
        self.assertEqual([Path(call[0][0]).name for call in self.observed_processes], [
            'pg_dump', 'pg_restore',
        ])
        self.assertEqual(ready.parent, self.output)
        self.assertEqual(list(self.output.iterdir()), [ready])
        manifest = json.loads((ready / 'manifest.json').read_text())
        self.assertEqual(manifest['database']['table_counts'], {'fixture_record': 7})
        self.assertEqual(manifest['database']['snapshot_id'], SNAPSHOT_ID)
        self.assertEqual(manifest['database']['sequence_values_source'], 'database.dump')
        self.assertEqual(manifest['database']['sha256'], hashlib.sha256(ARCHIVE).hexdigest())
        self.assertEqual(manifest['database']['size'], len(ARCHIVE))
        self.assertEqual(manifest['media']['file_count'], 0)
        self.assertTrue((ready / 'media').is_dir())
        encoded_manifest = (ready / 'manifest.json').read_bytes()
        self.assertEqual((ready / 'READY').read_text(), hashlib.sha256(encoded_manifest).hexdigest() + '\n')
        self.assertEqual(stat.S_IMODE(ready.stat().st_mode), 0o700)
        for path in [ready / 'database.dump', ready / 'manifest.json', ready / 'READY']:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertNotIn(PASSWORD, encoded_manifest.decode())

    def test_copies_referenced_and_unreferenced_files_with_exact_hashes(self):
        reference = 'Заявки/2026/ноябрь/пример #1.xlsx'
        self._media_file(reference, b'referenced bytes')
        self._media_file('orphan.bin', b'unreferenced retained bytes')
        real_copy = snapshot._copy_media

        with self._postgres([reference]) as (state, _, _):
            def copy_while_exporter_alive(*args):
                self.assertTrue(state['transaction'])
                return real_copy(*args)
            with patch.object(snapshot, '_copy_media', side_effect=copy_while_exporter_alive):
                ready = self._create()

        manifest = json.loads((ready / 'manifest.json').read_text())
        self.assertEqual(manifest['schema_version'], 'insflow.recovery-data.v1')
        self.assertEqual(manifest['media']['referenced_files'], [reference])
        self.assertEqual(manifest['media']['file_count'], 2)
        self.assertEqual(manifest['media']['total_bytes'], 43)
        for entry in manifest['media']['files']:
            original = (self.media / entry['path']).read_bytes()
            copied = ready / 'media' / entry['path']
            self.assertEqual(copied.read_bytes(), original)
            self.assertEqual(entry['size'], len(original))
            self.assertEqual(entry['sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(stat.S_IMODE(copied.stat().st_mode), 0o600)
        for directory in [path for path in (ready / 'media').rglob('*') if path.is_dir()]:
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

    def test_missing_referenced_file_cleans_staging_and_preserves_prior_ready_snapshot(self):
        previous = self.output / 'recovery_previous'
        previous.mkdir()
        (previous / 'READY').write_text('previous verified snapshot')
        with self._postgres(['missing/customer.xlsx']):
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'referenced media file is missing'):
                self._create()
        self.assertEqual(list(self.output.iterdir()), [previous])
        self.assertEqual((previous / 'READY').read_text(), 'previous verified snapshot')

    def test_file_or_directory_symlink_never_leaks_outside_media(self):
        outside = self.root / 'outside-secret.txt'
        outside.write_bytes(b'fixture private data')
        for target in [outside, self.root]:
            with self.subTest(directory=target.is_dir()):
                link = self.media / 'link'
                link.symlink_to(target, target_is_directory=target.is_dir())
                try:
                    with self._postgres():
                        with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'symbolic link'):
                            self._create()
                    self._assert_no_publication()
                finally:
                    link.unlink()

    def test_symlink_media_root_is_rejected(self):
        actual = self.root / 'actual-media'
        self.media.rename(actual)
        self.media.symlink_to(actual, target_is_directory=True)
        with self._postgres():
            with self.assertRaises(snapshot.RecoverySnapshotError):
                self._create()
        self._assert_no_publication()

    def test_mutating_file_during_copy_cancels_entire_snapshot(self):
        source = self._media_file(payload=b'original document')
        copy = snapshot._copy_file_data

        def mutate(input_stream, output_stream):
            result = copy(input_stream, output_stream)
            source.write_bytes(b'changed document with different size')
            return result

        with self._postgres(['documents/request.xlsx']), patch.object(
            snapshot, '_copy_file_data', side_effect=mutate,
        ):
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'changed while copying'):
                self._create()
        self._assert_no_publication()

    def test_file_added_during_copy_cancels_entire_snapshot(self):
        self._media_file()
        copy = snapshot._copy_file_data

        def add_file(input_stream, output_stream):
            result = copy(input_stream, output_stream)
            self._media_file('newly-uploaded.xlsx', b'new upload')
            return result

        with self._postgres(), patch.object(snapshot, '_copy_file_data', side_effect=add_file):
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'tree changed'):
                self._create()
        self._assert_no_publication()

    def test_file_replaced_by_symlink_between_scan_and_open_is_rejected(self):
        source = self._media_file()
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'must not copy this')
        open_file = snapshot._open_media_file

        def swap(root_descriptor, relative):
            source.unlink()
            source.symlink_to(outside)
            return open_file(root_descriptor, relative)

        with self._postgres(), patch.object(snapshot, '_open_media_file', side_effect=swap):
            with self.assertRaises(snapshot.RecoverySnapshotError):
                self._create()
        self._assert_no_publication()

    def test_nonregular_media_file_is_rejected(self):
        os.mkfifo(self.media / 'pipe')
        with self._postgres():
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'unsupported file type'):
                self._create()
        self._assert_no_publication()

    def test_file_replaced_by_fifo_between_scan_and_open_is_rejected_without_blocking(self):
        source = self._media_file()
        open_file = snapshot._open_media_file

        def swap(root_descriptor, relative):
            source.unlink()
            os.mkfifo(source)
            return open_file(root_descriptor, relative)

        with self._postgres(), patch.object(snapshot, '_open_media_file', side_effect=swap):
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'changed before copying'):
                self._create()
        self._assert_no_publication()

    def test_pgdump_failure_after_partial_write_cleans_staging_without_stderr_leak(self):
        def failed(arguments, **kwargs):
            target = Path(arguments[arguments.index('--file') + 1])
            target.write_bytes(b'PGDMP partial')
            return subprocess.CompletedProcess(arguments, 1, stderr=PASSWORD.encode())

        with self._postgres(utility=failed):
            with self.assertRaises(snapshot.RecoverySnapshotError) as caught:
                self._create()
        self.assertNotIn(PASSWORD, str(caught.exception))
        self._assert_no_publication()

    def test_pgdump_exception_is_sanitized_and_cleans_staging(self):
        with self._postgres(utility=MagicMock(side_effect=OSError(PASSWORD))):
            with self.assertRaises(snapshot.RecoverySnapshotError) as caught:
                self._create()
        self.assertNotIn(PASSWORD, str(caught.exception))
        self._assert_no_publication()

    def test_empty_or_wrong_header_dump_never_reaches_pgrestore_or_ready(self):
        for payload in [b'', b'PGDMP', b'WRONG invalid custom dump']:
            with self.subTest(payload=payload):
                calls = []

                def invalid(arguments, **kwargs):
                    calls.append(arguments)
                    Path(arguments[arguments.index('--file') + 1]).write_bytes(payload)
                    return subprocess.CompletedProcess(arguments, 0)

                with self._postgres(utility=invalid):
                    with self.assertRaises(snapshot.RecoverySnapshotError):
                        self._create()
                self.assertEqual(len(calls), 1)
                self._assert_no_publication()

    def test_full_archive_validation_failure_never_publishes_ready(self):
        def corrupt_archive(arguments, **kwargs):
            if Path(arguments[0]).name == 'pg_dump':
                Path(arguments[arguments.index('--file') + 1]).write_bytes(ARCHIVE)
                return subprocess.CompletedProcess(arguments, 0)
            self.assertEqual(arguments[1], '--file=/dev/null')
            return subprocess.CompletedProcess(arguments, 1, stderr=b'truncated archive')

        with self._postgres(utility=corrupt_archive):
            with self.assertRaises(snapshot.RecoverySnapshotError):
                self._create()
        self._assert_no_publication()

    def test_missing_postgresql_utility_never_publishes_ready(self):
        for missing in ['pg_dump', 'pg_restore']:
            with self.subTest(missing=missing), self._postgres():
                with patch.object(snapshot.shutil, 'which', side_effect=lambda name: None if name == missing else '/fixture/bin/' + name):
                    with self.assertRaisesMessage(snapshot.RecoverySnapshotError, missing + ' is required'):
                        self._create()
                self._assert_no_publication()

    def test_database_and_cursor_exception_is_sanitized_and_cleans_staging(self):
        with self._postgres() as (_, cursor, _):
            cursor.execute.side_effect = RuntimeError(PASSWORD)
            with self.assertRaises(snapshot.RecoverySnapshotError) as caught:
                self._create()
        self.assertNotIn(PASSWORD, str(caught.exception))
        self._assert_no_publication()

    def test_rejects_non_postgres_nested_transaction_and_output_under_media(self):
        with self._postgres() as (_, _, connection):
            connection.vendor = 'sqlite'
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'require PostgreSQL'):
                self._create()
            connection.vendor = 'postgresql'
            connection.in_atomic_block = True
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'standalone transaction'):
                self._create()
            connection.in_atomic_block = False
            with self.assertRaisesMessage(snapshot.RecoverySnapshotError, 'outside the media root'):
                snapshot.create_recovery_snapshot(self.media / 'backups', media_root=self.media)
        self._assert_no_publication()

    def test_filefield_references_include_all_registered_filefields_once(self):
        first = models.FileField()
        first.column = 'document_file'
        second = models.FileField()
        second.column = 'template_file'
        title = models.CharField()
        title.column = 'title'
        model = SimpleNamespace(_meta=SimpleNamespace(
            db_table='fixture_record', concrete_fields=[first, second, title],
        ))
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [('documents/request.xlsx',), ('documents/request.xlsx',)],
            [('templates/основной.xlsx',)],
        ]
        with self._postgres(), patch.object(snapshot.apps, 'get_models', return_value=[model, model]):
            # _postgres patches this helper only for full-snapshot tests.
            references = self._original_file_references(cursor, {'fixture_record'})
        self.assertEqual(references, {'documents/request.xlsx', 'templates/основной.xlsx'})
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(cursor.execute.call_args_list[0].args[1], [''])

    _original_file_references = staticmethod(snapshot._file_references)

    def test_unsafe_database_references_are_rejected_without_echoing_customer_names(self):
        for reference in ['/private/customer.xlsx', '../customer.xlsx', 'a/../../customer.xlsx',
                          'a\\customer.xlsx', 'a\x00customer.xlsx', '', '.']:
            with self.subTest(reference=reference):
                with self.assertRaises(snapshot.RecoverySnapshotError) as caught:
                    snapshot._safe_reference(reference)
                self.assertNotIn('customer', str(caught.exception))

    def test_command_returns_exact_path_or_machine_json_without_progress_output(self):
        path = '/private/recovery_ready'
        with patch(COMMAND + '.create_recovery_snapshot', return_value=path):
            output = StringIO()
            result = call_command('create_recovery_snapshot', output_dir='/private', stdout=output)
            self.assertEqual(result, path)
            self.assertEqual(output.getvalue(), path + '\n')
            output = StringIO()
            result = call_command('create_recovery_snapshot', output_dir='/private', as_json=True, stdout=output)
            self.assertIsNone(result)
            self.assertEqual(json.loads(output.getvalue()), {
                'status': 'ready', 'snapshot_path': path,
                'manifest_path': '/private/recovery_ready/manifest.json',
            })
            self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_command_failure_does_not_claim_a_ready_path(self):
        output = StringIO()
        with patch(COMMAND + '.create_recovery_snapshot', side_effect=snapshot.RecoverySnapshotError('Snapshot failed.')):
            with self.assertRaisesMessage(CommandError, 'Snapshot failed.'):
                call_command('create_recovery_snapshot', stdout=output)
        self.assertEqual(output.getvalue(), '')

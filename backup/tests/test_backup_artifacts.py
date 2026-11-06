"""Backup files are published only after successful, nonempty creation.

All archives and SQLite sources are temporary fixtures. PostgreSQL commands and
JSON serialization are mocked; these tests never contact a database or network.
"""

import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


MODULE = 'backup.management.commands.backup_db'
PG_PAYLOAD = b'PGDMP\x01\x0f\x00verified archive fixture'


class BackupArtifactTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='insflow-backup-artifact-test-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.output = self.directory / 'archives'
        self.output.mkdir()

    @contextmanager
    def _database(self, engine='django.db.backends.postgresql', name='fixture'):
        configuration = {
            'ENGINE': engine,
            'NAME': str(name),
            'USER': 'fixture-user',
            'PASSWORD': 'fixture-password',
            'HOST': 'database.invalid',
            'PORT': '5432',
        }
        # The command reads settings directly. No connection is established.
        with patch.dict(settings.DATABASES, {'default': configuration}):
            yield

    def _run(self, fmt='pgdump', keep=0):
        return call_command(
            'backup_db',
            format=fmt,
            output_dir=str(self.output),
            keep=keep,
            stdout=StringIO(),
            stderr=StringIO(),
        )

    def _old_dump(self, name='pgdump_20200101_030000.dump'):
        path = self.output / name
        path.write_bytes(PG_PAYLOAD)
        return path

    def _assert_temporary_target(self, path):
        path = Path(path)
        self.assertEqual(path.parent, self.output)
        self.assertTrue(path.name.endswith('.part'), path.name)
        return path

    def _assert_one_temporary_file(self):
        temporary = [path for path in self.output.iterdir() if path.name.endswith('.part')]
        self.assertEqual(len(temporary), 1)
        return self._assert_temporary_target(temporary[0])

    def _successful_pgdump(self, observed=None):
        def run(arguments, **kwargs):
            if '-f' in arguments:
                target = self._assert_temporary_target(
                    arguments[arguments.index('-f') + 1]
                )
                # A sender scanning final names cannot see this in-progress dump.
                self.assertFalse(list(self.output.glob('pgdump_*.dump')))
                target.write_bytes(PG_PAYLOAD)
                if observed is not None:
                    observed.append(target)
            return subprocess.CompletedProcess(arguments, 0, stdout='', stderr='')
        return run

    def test_pgdump_publishes_nonempty_file_and_returns_exact_final_path(self):
        temporary_paths = []
        with self._database(), patch(MODULE + '.shutil.which', return_value='/bin/pg_dump'), patch(
            MODULE + '.subprocess.run', side_effect=self._successful_pgdump(temporary_paths)
        ):
            result = self._run()

        self.assertIsNotNone(result)
        final = Path(result)
        self.assertEqual(final.parent, self.output)
        self.assertTrue(final.name.startswith('pgdump_'))
        self.assertTrue(final.name.endswith('.dump'))
        self.assertEqual(final.read_bytes(), PG_PAYLOAD)
        self.assertEqual(list(self.output.iterdir()), [final])
        self.assertEqual(len(temporary_paths), 1)
        self.assertFalse(temporary_paths[0].exists())

    def test_json_publishes_only_after_dumpdata_and_returns_exact_path(self):
        payload = '[{"model": "fixture.record", "pk": 1, "fields": {}}]'

        def dumpdata(command, *args, **kwargs):
            self.assertEqual(command, 'dumpdata')
            self._assert_one_temporary_file()
            self.assertFalse(list(self.output.glob('backup_*.json')))
            kwargs['stdout'].write(payload)

        with patch(MODULE + '.call_command', side_effect=dumpdata):
            result = self._run('json')

        self.assertIsNotNone(result)
        final = Path(result)
        self.assertEqual(final.read_text(encoding='utf-8'), payload)
        self.assertTrue(final.name.startswith('backup_'))
        self.assertTrue(final.name.endswith('.json'))
        self.assertEqual(list(self.output.iterdir()), [final])

    def test_sqlite_returns_a_published_copy_without_modifying_source(self):
        source = self.directory / 'source.sqlite3'
        payload = b'SQLite format 3\x00fixture source bytes'
        source.write_bytes(payload)
        real_copy = shutil.copy2

        def copy(src, dst, *args, **kwargs):
            self._assert_temporary_target(dst)
            self.assertFalse(list(self.output.glob('db_backup_*.sqlite3')))
            return real_copy(src, dst, *args, **kwargs)

        with self._database('django.db.backends.sqlite3', source), patch(
            MODULE + '.shutil.copy2', side_effect=copy
        ):
            result = self._run('sqlite')

        self.assertIsNotNone(result)
        final = Path(result)
        self.assertTrue(final.name.startswith('db_backup_'))
        self.assertTrue(final.name.endswith('.sqlite3'))
        self.assertEqual(final.read_bytes(), payload)
        self.assertEqual(source.read_bytes(), payload)
        self.assertEqual(list(self.output.iterdir()), [final])

    def test_failed_pgdump_removes_partial_file_and_preserves_good_backup(self):
        good = self._old_dump()

        def failing_dump(arguments, **kwargs):
            target = self._assert_temporary_target(
                arguments[arguments.index('-f') + 1]
            )
            target.write_bytes(b'PGDMP incomplete')
            return subprocess.CompletedProcess(arguments, 1, stdout='', stderr='injected dump failure')

        with self._database(), patch(MODULE + '.shutil.which', return_value='/bin/pg_dump'), patch(
            MODULE + '.subprocess.run', side_effect=failing_dump
        ):
            with self.assertRaises(CommandError):
                self._run(keep=1)

        self.assertEqual(list(self.output.iterdir()), [good])
        self.assertEqual(good.read_bytes(), PG_PAYLOAD)

    def test_pgdump_process_exception_removes_temporary_output(self):
        good = self._old_dump()

        def interrupted_dump(arguments, **kwargs):
            target = self._assert_temporary_target(
                arguments[arguments.index('-f') + 1]
            )
            target.write_bytes(b'partial bytes')
            raise OSError('injected process failure')

        with self._database(), patch(MODULE + '.shutil.which', return_value='/bin/pg_dump'), patch(
            MODULE + '.subprocess.run', side_effect=interrupted_dump
        ):
            with self.assertRaises((CommandError, OSError)):
                self._run(keep=1)

        self.assertEqual(list(self.output.iterdir()), [good])

    def test_zero_byte_success_is_rejected_without_rotation(self):
        good = self._old_dump()

        def empty_dump(arguments, **kwargs):
            target = self._assert_temporary_target(
                arguments[arguments.index('-f') + 1]
            )
            target.write_bytes(b'')
            return subprocess.CompletedProcess(arguments, 0, stdout='', stderr='')

        with self._database(), patch(MODULE + '.shutil.which', return_value='/bin/pg_dump'), patch(
            MODULE + '.subprocess.run', side_effect=empty_dump
        ):
            with self.assertRaises(CommandError):
                self._run(keep=1)

        self.assertEqual(list(self.output.iterdir()), [good])

    def test_json_exception_cleans_partial_output_and_keeps_old_json(self):
        good = self.output / 'backup_20200101_030000.json'
        good.write_text('[]', encoding='utf-8')

        def failing_json(command, *args, **kwargs):
            self._assert_one_temporary_file()
            kwargs['stdout'].write('[{"partial":')
            raise CommandError('injected serialization failure')

        with patch(MODULE + '.call_command', side_effect=failing_json):
            with self.assertRaises(CommandError):
                self._run('json', keep=1)

        self.assertEqual(list(self.output.iterdir()), [good])
        self.assertEqual(good.read_text(encoding='utf-8'), '[]')

    def test_zero_byte_json_is_not_published(self):
        with patch(MODULE + '.call_command'):
            with self.assertRaises(CommandError):
                self._run('json')
        self.assertFalse(list(self.output.iterdir()))

    def test_sqlite_copy_exception_removes_partial_output(self):
        source = self.directory / 'source.sqlite3'
        source.write_bytes(b'SQLite format 3\x00source bytes')
        good = self.output / 'db_backup_20200101_030000.sqlite3'
        good.write_bytes(b'previous good backup')

        def failing_copy(src, dst, *args, **kwargs):
            target = self._assert_temporary_target(dst)
            target.write_bytes(b'partial copy')
            raise OSError('injected copy failure')

        with self._database('django.db.backends.sqlite3', source), patch(
            MODULE + '.shutil.copy2', side_effect=failing_copy
        ):
            with self.assertRaises((CommandError, OSError)):
                self._run('sqlite', keep=1)

        self.assertEqual(list(self.output.iterdir()), [good])
        self.assertEqual(source.read_bytes(), b'SQLite format 3\x00source bytes')

    def test_zero_byte_sqlite_copy_is_not_published(self):
        source = self.directory / 'empty.sqlite3'
        source.write_bytes(b'')
        with self._database('django.db.backends.sqlite3', source):
            with self.assertRaises(CommandError):
                self._run('sqlite')
        self.assertFalse(list(self.output.iterdir()))

    def test_rotation_happens_after_publication_and_ignores_temporary_files(self):
        older = self._old_dump('pgdump_20200101_030000.dump')
        newest_old = self._old_dump('pgdump_20200102_030000.dump')
        unfinished = self.output / 'pgdump_20991231_030000.dump.part'
        unfinished.write_bytes(b'not committed')

        def complete_dump(arguments, **kwargs):
            if '-f' in arguments:
                self.assertTrue(older.exists())
                self.assertTrue(newest_old.exists())
                target = self._assert_temporary_target(
                    arguments[arguments.index('-f') + 1]
                )
                target.write_bytes(PG_PAYLOAD)
            return subprocess.CompletedProcess(arguments, 0, stdout='', stderr='')

        with self._database(), patch(MODULE + '.shutil.which', return_value='/bin/pg_dump'), patch(
            MODULE + '.subprocess.run', side_effect=complete_dump
        ):
            final = Path(self._run(keep=1))

        self.assertEqual(final.read_bytes(), PG_PAYLOAD)
        self.assertFalse(older.exists())
        self.assertFalse(newest_old.exists())
        self.assertTrue(unfinished.exists())
        self.assertEqual(set(self.output.iterdir()), {final, unfinished})

    def test_two_backups_with_frozen_clock_do_not_overwrite_each_other(self):
        moment = datetime(2026, 11, 6, 3, 0, 6, 100)

        def complete_dump(arguments, **kwargs):
            if '-f' in arguments:
                self._assert_temporary_target(arguments[arguments.index('-f') + 1]).write_bytes(PG_PAYLOAD)
            return subprocess.CompletedProcess(arguments, 0, stdout='', stderr='')

        with self._database(), patch(MODULE + '.datetime') as clock, patch(
            MODULE + '.shutil.which', return_value='/bin/pg_dump'
        ), patch(MODULE + '.subprocess.run', side_effect=complete_dump):
            clock.now.return_value = moment
            first = Path(self._run())
            second = Path(self._run())

        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), PG_PAYLOAD)
        self.assertEqual(second.read_bytes(), PG_PAYLOAD)
        self.assertEqual(set(self.output.iterdir()), {first, second})

    def test_failed_atomic_publish_cleans_temporary_file_and_keeps_old_backup(self):
        good = self.output / 'backup_20200101_030000.json'
        good.write_text('[]', encoding='utf-8')

        def dumpdata(command, *args, **kwargs):
            kwargs['stdout'].write('[{"complete": true}]')

        with patch(MODULE + '.call_command', side_effect=dumpdata), patch(
            MODULE + '.os.replace', side_effect=OSError('injected publish failure')
        ):
            with self.assertRaises((CommandError, OSError)):
                self._run('json', keep=1)

        self.assertEqual(list(self.output.iterdir()), [good])

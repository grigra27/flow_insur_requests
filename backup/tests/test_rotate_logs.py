"""
Тесты для команды rotate_logs.
"""
import gzip
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


class RotateLogsTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, size):
        path = self.dir / name
        path.write_bytes(b'x' * size)
        return path

    def _run(self, *args):
        out = StringIO()
        call_command('rotate_logs', f'--log-dir={self.dir}', '--max-mb=0.001', *args, stdout=out)
        return out.getvalue()

    def test_big_file_is_compressed_and_truncated(self):
        big = self._write('domain_routing.log', 5000)
        small = self._write('landing.log', 10)

        self._run()

        self.assertEqual(big.stat().st_size, 0)
        with gzip.open(self.dir / 'domain_routing.log.1.gz', 'rb') as f:
            self.assertEqual(f.read(), b'x' * 5000)
        self.assertEqual(small.stat().st_size, 10)
        self.assertFalse((self.dir / 'landing.log.1.gz').exists())

    def test_archives_shift_and_oldest_is_dropped(self):
        path = self.dir / 'django.log'
        for generation in (b'a', b'b', b'c'):
            path.write_bytes(generation * 5000)
            self._run('--keep=2')

        with gzip.open(self.dir / 'django.log.1.gz', 'rb') as f:
            self.assertEqual(f.read(1), b'c')
        with gzip.open(self.dir / 'django.log.2.gz', 'rb') as f:
            self.assertEqual(f.read(1), b'b')
        self.assertFalse((self.dir / 'django.log.3.gz').exists())

    def test_writer_keeps_appending_to_same_file_after_rotation(self):
        path = self._write('https.log', 5000)
        # Как FileHandler: файл открыт в режиме append до ротации
        with open(path, 'ab') as writer:
            self._run()
            writer.write(b'after')
            writer.flush()

        self.assertEqual(path.read_bytes(), b'after')

    def test_dry_run_changes_nothing(self):
        path = self._write('security.log', 5000)

        output = self._run('--dry-run')

        self.assertEqual(path.stat().st_size, 5000)
        self.assertFalse((self.dir / 'security.log.1.gz').exists())
        self.assertIn('security.log', output)

    def test_archives_are_not_rotated_themselves(self):
        self._write('django.log.1.gz', 5000)

        self._run()

        self.assertFalse((self.dir / 'django.log.1.gz.1.gz').exists())

    def test_invalid_args(self):
        with self.assertRaises(CommandError):
            call_command('rotate_logs', f'--log-dir={self.dir}', '--keep=0', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('rotate_logs', f'--log-dir={self.dir / "missing"}', stdout=StringIO())

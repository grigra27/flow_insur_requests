import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import open_recovery_backup_macos as opener


class OpenRecoveryBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'output'
        self.output.mkdir()
        self.age = self.root / 'age'
        self.age.write_bytes(b'fake binary')
        self.age.chmod(0o700)
        self.password = 'GUI-PASSWORD-CANARY'
        self.zip = self.root / 'backup.zip'
        header = b'age-encryption.org/v1\n-> scrypt ' + b'A' * 22 + b' 18\n' + b'B' * 100
        with zipfile.ZipFile(self.zip, 'w') as archive:
            archive.writestr('README.txt', 'generic instructions')
            archive.writestr('payload.tar.age', header)
        self.files = {
            'database.dump': b'PGDMP fixture', 'snapshot_manifest.json': b'{}',
            'source.tar': b'source fixture', 'config/.env': b'SECRET_KEY=config-canary',
            'config/docker-compose.yml': b'services: {}', 'config/nginx.conf': b'server {}',
            'config/tls.tar': b'tls fixture', 'config/runtime.json': b'{}',
            'media/Report.txt': b'UPPER', 'media/report.txt': b'lower',
        }

    def tar_bytes(self, corrupt=False, unsafe=False):
        metadata = {'schema_version': 'insflow.recovery-bundle.v1', 'backup_id': 'test-backup',
                    'app_build_sha': 'a' * 40, 'media_files': 2,
                    'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                              for name, data in self.files.items()}}
        if corrupt:
            metadata['files']['database.dump']['sha256'] = '0' * 64
        output = BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            for name, data in {**self.files, 'manifest.json': json.dumps(metadata).encode()}.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, BytesIO(data))
            if unsafe:
                info = tarfile.TarInfo('../outside')
                info.size = 1
                archive.addfile(info, BytesIO(b'x'))
        return output.getvalue()

    def decrypt(self, arguments, password, **options):
        self.assertNotIn(self.password, ' '.join(arguments))
        self.assertEqual(password, self.password)
        self.assertEqual(options['expected_prompts'], 1)
        Path(arguments[arguments.index('--output') + 1]).write_bytes(self.tar_bytes())

    def test_open_validates_case_distinct_linux_names_without_extracting_media(self):
        with patch.object(opener, 'run_age_with_password', side_effect=self.decrypt):
            output, report = opener.open_backup(self.zip, self.output, self.password, self.age)
        self.assertEqual(report['verified_files'], 10)
        self.assertEqual(report['media_files'], 2)
        self.assertEqual({p.name for p in output.iterdir()}, {'payload.tar', 'Проверка.txt'})
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertEqual((output / 'payload.tar').stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.password, (output / 'Проверка.txt').read_text())
        self.assertFalse((output / 'media').exists())

    def test_incorrect_password_removes_partial_plaintext_and_preserves_source(self):
        before = self.zip.read_bytes()
        def fail(arguments, *args, **kwargs):
            Path(arguments[arguments.index('--output') + 1]).write_bytes(b'partial')
            raise opener.AgeProcessError('failed')
        with patch.object(opener, 'run_age_with_password', side_effect=fail):
            with self.assertRaises(opener.OpenBackupError) as caught:
                opener.open_backup(self.zip, self.output, self.password, self.age)
        self.assertNotIn(self.password, str(caught.exception))
        self.assertFalse(list(self.output.iterdir()))
        self.assertEqual(self.zip.read_bytes(), before)

    def test_checksum_failure_removes_plaintext_output(self):
        def corrupt(arguments, *args, **kwargs):
            Path(arguments[arguments.index('--output') + 1]).write_bytes(self.tar_bytes(corrupt=True))
        with patch.object(opener, 'run_age_with_password', side_effect=corrupt):
            with self.assertRaises(opener.OpenBackupError):
                opener.open_backup(self.zip, self.output, self.password, self.age)
        self.assertFalse(list(self.output.iterdir()))

    def test_traversal_member_is_rejected_without_extraction(self):
        target = self.root / 'unsafe.tar'
        target.write_bytes(self.tar_bytes(unsafe=True))
        with self.assertRaises(opener.OpenBackupError):
            opener.validate_tar(target)
        self.assertFalse((self.root / 'outside').exists())

    def test_legacy_key_copy_is_distinguished_from_wrong_password(self):
        with zipfile.ZipFile(self.zip, 'w') as archive:
            archive.writestr('README.txt', 'legacy')
            archive.writestr('payload.tar.age', b'age-encryption.org/v1\n-> X25519 ' + b'A' * 100)
        with patch.object(opener, 'run_age_with_password') as decrypt:
            with self.assertRaisesRegex(opener.OpenBackupError, 'прежняя копия'):
                opener.open_backup(self.zip, self.output, self.password, self.age)
        decrypt.assert_not_called()
        self.assertFalse(list(self.output.iterdir()))

    def test_unexpected_zip_member_never_reaches_decryption(self):
        with zipfile.ZipFile(self.zip, 'a') as archive:
            archive.writestr('unexpected-private-file', b'secret')
        with patch.object(opener, 'run_age_with_password') as decrypt:
            with self.assertRaises(opener.OpenBackupError):
                opener.open_backup(self.zip, self.output, self.password, self.age)
        decrypt.assert_not_called()
        self.assertFalse(list(self.output.iterdir()))

    def test_cancelled_file_picker_does_not_request_password(self):
        with patch.object(opener, 'choose_archive', side_effect=opener.Cancelled), \
                patch.object(opener, 'ask_password') as password:
            self.assertEqual(opener.main(), 0)
        password.assert_not_called()

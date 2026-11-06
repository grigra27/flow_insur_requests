"""Host bundle tests use only temporary files, fake Docker/Git and a fake age CLI."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import create_recovery_bundle as bundle


class RecoveryBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='insflow-bundle-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'; self.project.mkdir()
        (self.project / 'nginx-timeweb').mkdir()
        self.canary = 'PRIVATE-CONFIG-CANARY-DO-NOT-LOG'
        (self.project / '.env').write_text('SECRET_KEY=' + self.canary + '\n')
        (self.project / 'docker-compose.yml').write_text('services: {}\n')
        (self.project / 'nginx-timeweb/default.conf').write_text('server {}\n')
        self.state = self.root / 'state'
        self.recipient = self.root / 'recipient.txt'; self.recipient.write_text('age1' + 'q' * 58 + '\n')
        self.age = self.root / 'age'
        self.age.write_text('#!/usr/bin/env python3\nimport hashlib,sys\nfrom pathlib import Path\n'
                            'data=sys.stdin.buffer.read()\n'
                            'Path(sys.argv[sys.argv.index("-o")+1]).write_bytes(b"age-encryption.org/v1\\n"+hashlib.sha256(data).digest())\n')
        self.age.chmod(0o700)
        self.commit = 'a' * 40
        self.snapshot_name = 'recovery_20261106T220000_123456Z_' + 'b' * 32
        self.container_snapshot = '/app/backups/recovery/' + self.snapshot_name
        self.snapshot = self.root / 'snapshot'; self.snapshot.mkdir()
        (self.snapshot / 'media').mkdir(); (self.snapshot / 'media/document.bin').write_bytes(b'document')
        (self.snapshot / 'database.dump').write_bytes(b'PGDMP-test-dump')
        self.snapshot_manifest = {
            'schema_version': 'insflow.recovery-data.v1', 'app_build_sha': self.commit,
            'database': {'file': 'database.dump', 'size': 15, 'sha256': bundle.sha256(self.snapshot / 'database.dump')},
            'media': {'directory': 'media', 'file_count': 1, 'total_bytes': 8,
                      'referenced_files': ['document.bin'],
                      'files': [{'path': 'document.bin', 'size': 8, 'sha256': bundle.sha256(self.snapshot / 'media/document.bin')}]},
        }
        self.snapshot_manifest['database']['size'] = (self.snapshot / 'database.dump').stat().st_size
        self.write_manifest()
        self.commands = []
        patcher = patch.object(bundle, 'run', side_effect=self.fake_run)
        patcher.start(); self.addCleanup(patcher.stop)
        cron = patch.object(bundle, 'insflow_cron', return_value=b'15 3 * * * wrapper # insflow-recovery-vk\n')
        cron.start(); self.addCleanup(cron.stop)

    def write_manifest(self):
        raw = json.dumps(self.snapshot_manifest).encode()
        (self.snapshot / 'manifest.json').write_bytes(raw)
        (self.snapshot / 'READY').write_text(hashlib.sha256(raw).hexdigest() + '\n')

    def tar_fixture(self, output, unsafe=False):
        with tarfile.open(fileobj=output, mode='w') as archive:
            info = tarfile.TarInfo('../outside' if unsafe else 'letsencrypt/archive/example/cert1.pem')
            content = b'TLS-private-canary'; info.size = len(content)
            archive.addfile(info, BytesIO(content))

    def fake_run(self, args, output=None):
        self.commands.append(args)
        if args[:2] == ['docker', 'inspect']:
            return json.dumps({'container_id': 'container-1', 'image_id': 'sha256:image',
                               'running': True, 'paused': False,
                               'mounts': [{'Destination': '/app/backups', 'Source': '/private-docker-volume',
                                           'Type': 'volume', 'RW': True}]}).encode()
        if args[:3] == ['docker', 'image', 'inspect']:
            return b'["registry.invalid/image@sha256:digest"]'
        if args[:3] == ['docker', 'exec', bundle.NGINX]:
            self.tar_fixture(output); return None
        if args[:3] == ['docker', 'exec', bundle.WEB]:
            if 'create_recovery_snapshot' in args:
                return json.dumps({'status': 'ready', 'snapshot_path': self.container_snapshot,
                                   'manifest_path': self.container_snapshot + '/manifest.json'}).encode()
            if 'freeze' in args:
                return b'Django==5.2.19\ndjango-easy-audit==1.3.9\n'
            if 'rm' in args:
                return b''
            return json.dumps({'build_sha': self.commit, 'django_version': '5.2.19', 'python_version': '3.11'}).encode()
        if args[:2] == ['docker', 'cp']:
            shutil.copytree(self.snapshot, args[-1]); return b''
        if args[0] == 'git':
            if 'rev-parse' in args:
                return self.commit.encode()
            if 'archive' in args:
                with tarfile.open(fileobj=output, mode='w') as archive:
                    info = tarfile.TarInfo('README.md'); info.size = 6
                    archive.addfile(info, BytesIO(b'source'))
                return None
            return b''
        raise AssertionError('Unexpected fixture command')

    def create(self):
        return bundle.create_bundle(self.project, self.state, self.age, self.recipient)

    def assert_unpublished(self):
        self.assertFalse(list(self.state.glob('exports/*.zip')))
        self.assertFalse(list(self.state.glob('exports/*.part')))
        self.assertFalse(list(self.state.glob('build-*')))

    def test_finished_zip_has_only_ciphertext_and_generic_readme(self):
        seen = {}; original = bundle.encrypt_payload
        def capture(payload, *args):
            seen['manifest'] = json.loads((payload / 'manifest.json').read_text())
            seen['names'] = {path.name for path in payload.iterdir()}
            original(payload, *args)
        with patch.object(bundle, 'encrypt_payload', side_effect=capture):
            result = self.create()
        archive_path = Path(result['archive_path'])
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['archive_format'], 'age-zip')
        self.assertEqual(result['sha256'], bundle.sha256(archive_path))
        self.assertEqual(result['size'], archive_path.stat().st_size)
        self.assertEqual(archive_path.stat().st_mode & 0o777, 0o600)
        self.assertTrue({'database.dump', 'media', 'snapshot_manifest.json', 'config', 'source.tar', 'manifest.json'}.issubset(seen['names']))
        self.assertEqual(seen['manifest']['files']['config/.env']['sha256'], bundle.sha256(self.project / '.env'))
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(archive.namelist(), ['payload.tar.age', 'README.txt'])
            self.assertTrue(all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist()))
            self.assertNotIn(self.canary.encode(), archive.read('README.txt'))
            self.assertNotIn(self.canary.encode(), archive.read('payload.tar.age'))
        self.assertTrue(any(args[-1] == self.container_snapshot and 'rm' in args for args in self.commands))

    def test_missing_required_configuration_does_not_publish_or_print_values(self):
        (self.project / 'docker-compose.yml').unlink()
        with self.assertRaises(bundle.BundleError) as error:
            self.create()
        self.assertNotIn(self.canary, str(error.exception)); self.assert_unpublished()

    def test_configuration_changed_during_encryption_is_rejected(self):
        original = bundle.encrypt_payload
        def changed(*args):
            original(*args); (self.project / '.env').write_text('SECRET_KEY=changed\n')
        with patch.object(bundle, 'encrypt_payload', side_effect=changed), self.assertRaises(bundle.BundleError):
            self.create()
        self.assert_unpublished()

    def test_age_failure_never_leaks_stderr_or_leaves_final_zip(self):
        self.age.write_text('#!/usr/bin/env python3\nimport sys\nsys.stderr.write(' + repr(self.canary) + ')\nsys.exit(9)\n')
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bundle.main(['--project-dir', str(self.project), '--state-dir', str(self.state),
                                '--age-binary', str(self.age), '--recipient-file', str(self.recipient)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())['status'], 'error')
        self.assertNotIn(self.canary, out.getvalue() + err.getvalue()); self.assert_unpublished()

    def test_corrupt_ready_marker_is_rejected(self):
        (self.snapshot / 'READY').write_text('bad\n')
        with self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_changed_document_is_rejected(self):
        (self.snapshot / 'media/document.bin').write_bytes(b'tampered')
        with self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_private_identity_is_not_a_valid_public_recipient(self):
        self.recipient.write_text('AGE-SECRET-KEY-1-' + self.canary)
        with self.assertRaises(bundle.BundleError) as error: self.create()
        self.assertNotIn(self.canary, str(error.exception)); self.assert_unpublished()

    def test_media_directory_symlink_is_rejected_before_host_files_are_read(self):
        shutil.rmtree(self.snapshot / 'media')
        (self.snapshot / 'media').symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_failed_new_export_preserves_old_archive_without_returning_it(self):
        result = self.create(); old = Path(result['archive_path']); digest = bundle.sha256(old)
        self.recipient.unlink(); out = StringIO()
        with redirect_stdout(out):
            code = bundle.main(['--project-dir', str(self.project), '--state-dir', str(self.state),
                                '--age-binary', str(self.age), '--recipient-file', str(self.recipient)])
        self.assertEqual(code, 1); self.assertEqual(bundle.sha256(old), digest)
        self.assertNotIn('archive_path', json.loads(out.getvalue()))
        self.assertEqual([path.resolve() for path in self.state.glob('exports/*.zip')], [old])

    def test_runtime_configuration_overrides_are_captured_and_source_modes_ignored(self):
        original = self.fake_run
        def changed_config(args, output=None):
            if args[0] == 'git' and 'diff' in args:
                self.assertIn('core.fileMode=false', args)
                return b'docker-compose.yml\0nginx-timeweb/default.conf\0'
            return original(args, output)
        with patch.object(bundle, 'run', side_effect=changed_config):
            self.assertEqual(self.create()['status'], 'ready')

    def test_unexpected_application_source_changes_are_rejected(self):
        original = self.fake_run
        def changed_code(args, output=None):
            if args[0] == 'git' and 'diff' in args:
                return b'insurance_requests/views.py\0'
            return original(args, output)
        with patch.object(bundle, 'run', side_effect=changed_code), self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_size_limit_prevents_atomic_publication(self):
        with patch.object(bundle, 'MAX_ARCHIVE_BYTES', 10), self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_unsafe_producer_path_is_never_copied_or_removed(self):
        self.container_snapshot = '/app/backups/recovery/../../important'
        with self.assertRaises(bundle.BundleError): self.create()
        self.assertFalse(any(args[:2] == ['docker', 'cp'] or 'rm' in args for args in self.commands))
        self.assert_unpublished()

    def test_unsafe_tls_archive_is_rejected_before_snapshot(self):
        original = self.fake_run
        def unsafe(args, output=None):
            if args[:3] == ['docker', 'exec', bundle.NGINX]:
                self.tar_fixture(output, unsafe=True); return None
            return original(args, output)
        with patch.object(bundle, 'run', side_effect=unsafe), self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_source_or_container_change_prevents_publication(self):
        original = bundle.runtime
        calls = []
        def replaced():
            info = original(); calls.append(1)
            if len(calls) > 1: info['container_id'] = 'replaced'
            return info
        with patch.object(bundle, 'runtime', side_effect=replaced), self.assertRaises(bundle.BundleError): self.create()
        self.assert_unpublished()

    def test_mount_order_change_preserves_runtime_and_all_metadata(self):
        mounts = [
            {'Destination': '/app/media', 'Source': '/media-volume', 'Type': 'volume',
             'RW': True, 'Mode': 'rw', 'Driver': 'local', 'Propagation': ''},
            {'Destination': '/app/backups', 'Source': '/backup-volume', 'Type': 'volume',
             'RW': True, 'Mode': 'rw', 'Driver': 'local', 'Propagation': ''},
            {'Destination': '/app/staticfiles', 'Source': '/static-volume', 'Type': 'volume',
             'RW': False, 'Mode': 'ro', 'Driver': 'local', 'Propagation': ''},
        ]
        calls = []
        def reordered(args, output=None):
            result = self.fake_run(args, output)
            if args[:2] == ['docker', 'inspect']:
                info = json.loads(result)
                info['mounts'] = mounts if len(calls) % 2 == 0 else list(reversed(mounts))
                calls.append(1)
                return json.dumps(info).encode()
            return result
        with patch.object(bundle, 'run', side_effect=reordered):
            before, after = bundle.runtime(), bundle.runtime()
            self.assertEqual(before, after)
            self.assertCountEqual(before['mounts'], mounts)
            self.assertEqual(self.create()['status'], 'ready')

    def test_changed_mount_source_or_access_still_prevents_publication(self):
        for field, value in [('Source', '/replacement-volume'), ('RW', False)]:
            with self.subTest(field=field):
                calls = []
                def changed(args, output=None):
                    result = self.fake_run(args, output)
                    if args[:2] == ['docker', 'inspect']:
                        info = json.loads(result)
                        if calls:
                            info['mounts'][0][field] = value
                        calls.append(1)
                        return json.dumps(info).encode()
                    return result
                with patch.object(bundle, 'run', side_effect=changed), self.assertRaisesRegex(
                    bundle.BundleError, 'Recovery sources changed before publication'
                ):
                    self.create()
                self.assert_unpublished()

    def test_successful_cli_emits_only_safe_machine_json(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bundle.main(['--project-dir', str(self.project), '--state-dir', str(self.state),
                                '--age-binary', str(self.age), '--recipient-file', str(self.recipient)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['status'], 'ready')
        self.assertNotIn(self.canary, out.getvalue() + err.getvalue())

    def password_fixture(self, raw=None, path=None):
        self.password = 'Пароль-Canary8/' + self.canary
        self.password_file = path or self.root / 'archive-password'
        self.password_file.parent.mkdir(parents=True, exist_ok=True)
        self.password_file.write_bytes(raw if raw is not None else (self.password + '\n').encode())
        self.password_file.chmod(0o600)
        return self.password_file

    def create_password_bundle(self):
        return bundle.create_bundle(self.project, self.state, age_binary=self.age,
                                    archive_format='age-passphrase', password_file=self.password_file)

    @contextmanager
    def fake_passphrase_age(self, *, fail=None):
        calls, observed = [], {}
        existing_exports = set(self.state.glob('exports/*.zip'))

        def invoke(arguments, password, **options):
            calls.append((arguments, options))
            self.assertNotIn(self.password, repr(arguments))
            self.assertEqual(password, self.password)
            self.assertEqual(options['timeout'], 600)
            operation = arguments[1]
            if operation == '--passphrase':
                self.assertEqual(options['expected_prompts'], 2)
                tar_path = Path(arguments[-1])
                self.assertEqual(tar_path.name, 'payload.tar')
                self.assertEqual(tar_path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn(self.password.encode(), tar_path.read_bytes())
                observed['tar_size'] = tar_path.stat().st_size
                with tarfile.open(tar_path) as archive:
                    observed['names'] = archive.getnames()
                    observed['manifest'] = json.load(archive.extractfile('manifest.json'))
                destination = Path(arguments[arguments.index('--output') + 1])
                self.assertEqual(destination.name, 'payload.tar.age')
                self.assertEqual(set(self.state.glob('exports/*.zip')), existing_exports)
                prefix = b'age-encryption.org/v1\n-> scrypt ' + b'A' * 22 + b' 18\n'
                payload = prefix + hashlib.sha256(tar_path.read_bytes()).digest()
                if fail == 'header':
                    payload = b'not encrypted\n'
                if fail == 'stanza':
                    payload = b'age-encryption.org/v1\n-> X25519 ' + b'A' * 43 + b'\n'
                if fail == 'empty':
                    payload = b''
                destination.write_bytes(payload)
                if fail == 'exception':
                    raise OSError(self.password)
                if fail == 'encryption':
                    raise bundle.AgeProcessError(self.password)
                return None
            self.assertEqual(operation, '--decrypt')
            self.assertEqual(options['expected_prompts'], 1)
            self.assertEqual(arguments[arguments.index('--output') + 1], os.devnull)
            self.assertEqual(Path(arguments[-1]).name, 'payload.tar.age')
            if fail == 'authentication':
                raise bundle.AgeProcessError(self.password)
            return None

        with patch.object(bundle, 'run_age_with_password', side_effect=invoke):
            yield calls, observed

    def test_password_archive_contains_one_tar_and_is_fully_validated_before_publication(self):
        self.password_fixture()
        with self.fake_passphrase_age() as (calls, observed):
            result = self.create_password_bundle()
        archive = Path(result['archive_path'])
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['archive_format'], 'age-passphrase')
        self.assertEqual(archive.suffix, '.zip')
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result['sha256'], bundle.sha256(archive))
        self.assertEqual([args[1] for args, unused in calls], ['--passphrase', '--decrypt'])
        self.assertEqual(observed['manifest']['schema_version'], 'insflow.recovery-bundle.v1')
        self.assertEqual(observed['manifest']['encryption'], 'age-scrypt')
        self.assertIn('media/document.bin', observed['names'])
        self.assertIn('config/.env', observed['names'])
        self.assertNotIn('archive-password', observed['names'])
        self.assertNotIn(self.password, json.dumps(result))
        with zipfile.ZipFile(archive) as outer:
            self.assertEqual(outer.namelist(), ['payload.tar.age', 'README.txt'])
            self.assertEqual(outer.read('README.txt').decode(), bundle.PASSWORD_README)
            self.assertNotIn(self.password.encode(), outer.read('README.txt'))
            self.assertTrue(all(item.compress_type == zipfile.ZIP_STORED for item in outer.infolist()))
        self.assertFalse(list(self.state.glob('build-*')))
        self.assertFalse(list(self.state.glob('exports/*.part')))

    def test_password_archive_cli_works_without_recipient_and_omits_secret(self):
        self.password_fixture()
        out, err = StringIO(), StringIO()
        with self.fake_passphrase_age(), redirect_stdout(out), redirect_stderr(err):
            code = bundle.main(['--project-dir', str(self.project), '--state-dir', str(self.state),
                                '--archive-format', 'age-passphrase', '--age-binary', str(self.age),
                                '--password-file', str(self.password_file)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['archive_format'], 'age-passphrase')
        self.assertNotIn(self.password, out.getvalue() + err.getvalue())

    def test_password_validation_allows_unicode_and_only_one_optional_final_lf(self):
        for suffix in ('', '\n'):
            with self.subTest(final_lf=bool(suffix)):
                value = 'Пароль8!'
                path = self.password_fixture((value + suffix).encode('utf-8'))
                self.assertEqual(bundle.read_password_file(path), value)
        for raw in (b'', b'1234567', b'12345678\r\n', b'12345678\n\n', b'1234\n5678',
                    b'1234\x005678', b'1234\t5678', b'12345678\xff', b'1234\x7f5678', b'x' * 4097):
            with self.subTest(raw=raw):
                path = self.password_fixture(raw)
                with self.assertRaises(bundle.BundleError):
                    bundle.read_password_file(path)
        for value in ('1234\u20285678', '1234\u200d5678', 'x' * 4096):
            path = self.password_fixture((value + '\n').encode())
            self.assertEqual(bundle.read_password_file(path), value)

    def test_password_file_requires_owner_mode_0600_regular_file_and_no_symlink(self):
        path = self.password_fixture()
        for mode in (0o644, 0o400, 0o700):
            path.chmod(mode)
            with self.subTest(mode=mode), self.assertRaises(bundle.BundleError):
                bundle.read_password_file(path)
        path.chmod(0o600)
        with patch.object(bundle.os, 'geteuid', return_value=path.stat().st_uid + 1):
            with self.assertRaises(bundle.BundleError):
                bundle.read_password_file(path)
        link = self.root / 'password-link'; link.symlink_to(path)
        with self.assertRaises(bundle.BundleError):
            bundle.read_password_file(link)
        fifo = self.root / 'password-pipe'; os.mkfifo(fifo, mode=0o600)
        with self.assertRaises(bundle.BundleError):
            bundle.read_password_file(fifo)

    def test_password_inside_project_is_rejected_before_snapshot_or_archiving(self):
        self.password_fixture(path=self.project / 'password')
        with self.fake_passphrase_age() as (calls, _), self.assertRaises(bundle.BundleError):
            self.create_password_bundle()
        self.assertFalse(calls)
        self.assertFalse(any('create_recovery_snapshot' in args for args in self.commands))
        self.assert_unpublished()

    def test_password_permissions_changed_after_open_are_rejected(self):
        path = self.password_fixture()
        original = os.open
        def opened_with_changed_permissions(*args, **kwargs):
            descriptor = original(*args, **kwargs)
            path.chmod(0o644)
            return descriptor
        with patch.object(bundle.os, 'open', side_effect=opened_with_changed_permissions):
            with self.assertRaises(bundle.BundleError):
                bundle.read_password_file(path)

    def test_password_inside_web_mount_is_rejected_even_outside_project(self):
        self.password_fixture(path=self.root / 'mounted-media' / 'password')
        original = self.fake_run
        def mounted(args, output=None):
            result = original(args, output)
            if args[:2] == ['docker', 'inspect']:
                data = json.loads(result)
                data['mounts'].append({'Destination': '/app/media', 'Source': str(self.password_file.parent),
                                       'Type': 'bind', 'RW': True})
                return json.dumps(data).encode()
            return result
        with patch.object(bundle, 'run', side_effect=mounted), self.fake_passphrase_age() as (calls, _):
            with self.assertRaises(bundle.BundleError):
                self.create_password_bundle()
        self.assertFalse(calls)
        self.assert_unpublished()

    def test_password_hardlinked_to_archived_config_is_rejected(self):
        self.password_fixture()
        self.password_file.unlink()
        (self.project / '.env').chmod(0o600)
        os.link(self.project / '.env', self.password_file)
        with self.assertRaises(bundle.BundleError):
            self.create_password_bundle()
        self.assert_unpublished()

    def test_encryption_and_authentication_failures_clean_partial_plaintext_and_exports(self):
        self.password_fixture()
        for failure in ('encryption', 'exception', 'authentication', 'header', 'stanza', 'empty'):
            with self.subTest(failure=failure), self.fake_passphrase_age(fail=failure):
                with self.assertRaises(bundle.BundleError) as error:
                    self.create_password_bundle()
                self.assertNotIn(self.password, str(error.exception))
                self.assert_unpublished()

    def test_password_change_during_creation_prevents_publication(self):
        self.password_fixture()
        original = bundle.encrypt_passphrase_payload
        def changed(*args):
            original(*args)
            self.password_file.write_text('different-password8')
        with self.fake_passphrase_age(), patch.object(bundle, 'encrypt_passphrase_payload', side_effect=changed):
            with self.assertRaises(bundle.BundleError):
                self.create_password_bundle()
        self.assert_unpublished()

    def test_failed_password_export_preserves_previous_good_archive_without_fallback(self):
        old = Path(self.create()['archive_path'])
        old_hash = bundle.sha256(old)
        self.password_fixture()
        out, err = StringIO(), StringIO()
        with self.fake_passphrase_age(fail='authentication'), redirect_stdout(out), redirect_stderr(err):
            code = bundle.main(['--project-dir', str(self.project), '--state-dir', str(self.state),
                                '--archive-format', 'age-passphrase', '--age-binary', str(self.age),
                                '--password-file', str(self.password_file)])
        self.assertEqual(code, 1)
        self.assertNotIn('archive_path', json.loads(out.getvalue()))
        self.assertNotIn(self.password, out.getvalue() + err.getvalue())
        self.assertEqual(bundle.sha256(old), old_hash)
        self.assertEqual([path.resolve() for path in (self.state / 'exports').iterdir()], [old])
        self.assertFalse(list(self.state.glob('build-*')))

    def test_password_archive_size_guard_cleans_part_without_publishing(self):
        self.password_fixture()
        with self.fake_passphrase_age(), patch.object(bundle, 'MAX_ARCHIVE_BYTES', 10):
            with self.assertRaises(bundle.BundleError):
                self.create_password_bundle()
        self.assert_unpublished()


class RecoveryCronSetupTests(unittest.TestCase):
    def test_invalid_existing_configuration_is_not_silently_skipped_or_logged(self):
        script = Path(bundle.__file__).with_name('recovery-cron-setup.sh')
        with TemporaryDirectory() as directory:
            config = Path(directory) / '.config/insflow-recovery/config.json'
            config.parent.mkdir(parents=True, mode=0o700)
            canary = 'PRIVATE-CRON-CONFIG-CANARY'
            config.write_text(json.dumps({'age_binary': canary, 'recipient_file': canary})); config.chmod(0o600)
            env = {**os.environ, 'HOME': directory}
            result = subprocess.run(['bash', str(script), '--allow-unconfigured'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(canary, result.stdout + result.stderr)

    def test_missing_configuration_skips_only_when_explicitly_allowed(self):
        script = Path(bundle.__file__).with_name('recovery-cron-setup.sh')
        with TemporaryDirectory() as directory:
            env = {**os.environ, 'HOME': directory}
            skipped = subprocess.run(['bash', str(script), '--allow-unconfigured'], env=env, capture_output=True)
            failed = subprocess.run(['bash', str(script)], env=env, capture_output=True)
        self.assertEqual(skipped.returncode, 0)
        self.assertNotEqual(failed.returncode, 0)

    def test_installer_preserves_other_jobs_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); scripts = root / 'project/scripts'; scripts.mkdir(parents=True)
            for name in ['recovery-cron-setup.sh', 'cron-common.sh']:
                shutil.copy2(Path(bundle.__file__).with_name(name), scripts / name)
            (scripts / 'cron-send-recovery-to-vk.sh').write_text('#!/bin/sh\nexit 0\n')
            age = root / 'age'; age.write_text('#!/bin/sh\nexit 0\n'); age.chmod(0o700)
            recipient = root / 'recipient'; recipient.write_text('age1' + 'q' * 58)
            config = root / '.config/insflow-recovery/config.json'
            config.parent.mkdir(parents=True, mode=0o700)
            config.write_text(json.dumps({'age_binary': str(age), 'recipient_file': str(recipient), 'state_dir': str(root / 'state')})); config.chmod(0o600)
            tab = root / 'tab'; tab.write_text('0 1 * * * other-job # other-marker\n')
            executable = root / 'crontab'; executable.write_text('#!/bin/sh\nif [ "$1" = "-l" ]; then cat "$TEST_TAB"; else cat > "$TEST_TAB"; fi\n'); executable.chmod(0o700)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'HOME': str(root), 'TEST_TAB': str(tab)}
            for unused in range(2):
                result = subprocess.run(['bash', str(scripts / 'recovery-cron-setup.sh')], env=env, capture_output=True)
                self.assertEqual(result.returncode, 0)
            content = tab.read_text()
            self.assertEqual(content.count('# insflow-recovery-vk'), 1)
            self.assertIn('other-job # other-marker', content)
            self.assertIn('15 3 * * *', content)

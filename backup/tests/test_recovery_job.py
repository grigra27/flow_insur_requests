import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


SPEC = importlib.util.spec_from_file_location(
    'recovery_job_under_test', settings.BASE_DIR / 'scripts/run_recovery_backup.py')
job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(job)


class RecoveryJobTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / 'state'
        for folder in ('exports', 'receipts', 'runs'):
            (self.state / folder).mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state.chmod(0o700)
        self.age = self.root / 'age'
        self.age.write_bytes(b'placeholder')
        self.recipient = self.root / 'recipient.txt'
        self.recipient.write_text('age1-public-test-recipient')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(dict(age_binary=str(self.age),
            recipient_file=str(self.recipient), state_dir=str(self.state), keep_local=1)))
        self.config.chmod(0o600)
        self.archive = self.state / 'exports' / 'recovery_current.zip'
        self.archive.write_bytes(b'validated encrypted archive')
        self.bundle = dict(status='ready', archive_path=str(self.archive),
                           backup_id='recovery_current', sha256=job.digest(self.archive),
                           size=self.archive.stat().st_size)
        self.receipt = dict(schema_version=1, archive_name=self.archive.name,
                            sha256=self.bundle['sha256'], size=self.bundle['size'],
                            document=dict(owner_id=-1, id=2, access_key='private-canary'),
                            message_id=3)
        self.old = self.state / 'exports' / 'recovery_old.zip'
        self.old.write_bytes(b'last verified copy')
        job.atomic_json(self.state / 'receipts/recovery_old.json',
                        dict(archive_name=self.old.name, verified_download=True,
                             completed_at_utc='2025-01-01T00:00:00+00:00'))
        job.atomic_json(self.state / 'last_success.json', {'backup_id': 'old'})

    def execute(self, management=None, receipt=None):
        def default(command, arguments, stage):
            if command == 'send_recovery_to_vk' and '--notify-failure' in arguments:
                return {'status': 'notified'}
            return {'status': 'sent' if command == 'send_recovery_to_vk' else 'downloaded',
                    'sha256': self.bundle['sha256'], 'bytes': self.bundle['size']}
        with mock.patch.object(job, 'produce', return_value=self.bundle), \
                mock.patch.object(job, 'copy_to_web'), \
                mock.patch.object(job, 'cleanup_remote'), \
                mock.patch.object(job, 'management', side_effect=management or default), \
                mock.patch.object(job, 'run', return_value=json.dumps(receipt or self.receipt).encode()):
            return job.run_job(self.root, self.config)

    def test_success_requires_external_readback_and_then_rotates_verified_copies(self):
        result = self.execute()
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['verified_download'])
        self.assertFalse(self.old.exists())
        self.assertTrue(self.archive.exists())
        marker = json.loads((self.state / 'last_success.json').read_text())
        self.assertEqual(marker['sha256'], self.bundle['sha256'])
        self.assertTrue(marker['temporary_delivery_files_removed'])
        receipt = self.state / 'receipts/recovery_current.json'
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('private-canary', json.dumps(result))

    def test_failed_external_readback_preserves_last_success_and_good_copy(self):
        def failing(command, arguments, stage):
            if command == 'download_recovery_from_vk':
                raise job.JobError('upload')
            return {'status': 'sent', 'sha256': self.bundle['sha256']}
        result = self.execute(management=failing)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(self.archive.exists())
        self.assertTrue(self.old.exists())
        self.assertEqual(json.loads((self.state / 'last_success.json').read_text()),
                         {'backup_id': 'old'})

    def test_clock_rollback_preserves_current_archive_receipt_and_success_marker(self):
        # The prior verified receipt is dated 2025; the current run's clock
        # moved back to 2020. keep_local=1 must still retain this new copy.
        with mock.patch.object(job, 'now', return_value='2020-01-01T00:00:00+00:00'):
            result = self.execute()
        self.assertEqual(result['status'], 'success')
        marker = json.loads((self.state / 'last_success.json').read_text())
        self.assertEqual(marker['completed_at_utc'], '2020-01-01T00:00:00+00:00')
        self.assertEqual(marker['archive_name'], self.archive.name)
        self.assertTrue((self.state / 'exports' / marker['archive_name']).is_file())
        receipt = self.state / 'receipts' / (marker['backup_id'] + '.json')
        self.assertTrue(receipt.is_file())
        self.assertTrue(json.loads(receipt.read_text())['verified_download'])
        self.assertFalse(self.old.exists())

    def test_unexpected_receipt_digest_cannot_mark_success(self):
        receipt = dict(self.receipt, sha256='0' * 64)
        result = self.execute(receipt=receipt)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(self.old.exists())
        self.assertFalse((self.state / 'receipts/recovery_current.json').exists())

    def test_snapshot_failure_does_not_deliver_or_rotate(self):
        with mock.patch.object(job, 'produce', side_effect=job.JobError('snapshot')), \
                mock.patch.object(job, 'management', return_value={'status': 'notified'}) as api, \
                mock.patch.object(job, 'prune_verified') as prune:
            result = job.run_job(self.root, self.config)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(api.call_count, 1)
        self.assertIn('--notify-failure', api.call_args.args[1])
        prune.assert_not_called()
        self.assertTrue(self.old.exists())

    def test_busy_lock_does_not_start_another_snapshot(self):
        with mock.patch.object(job.fcntl, 'flock', side_effect=BlockingIOError), \
                mock.patch.object(job, 'produce') as produce:
            result = job.run_job(self.root, self.config)
        self.assertEqual(result, {'status': 'busy', 'exit_code': 75})
        produce.assert_not_called()

    def test_configuration_permissions_are_required(self):
        self.config.chmod(0o644)
        with self.assertRaises(job.JobError) as caught:
            job.run_job(self.root, self.config)
        self.assertEqual(caught.exception.stage, 'configuration')

    def test_transport_stderr_is_never_exposed(self):
        with mock.patch.object(job.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 1, b'', b'https://private.invalid/?token=SECRET-CANARY')):
            with self.assertRaises(job.JobError) as caught:
                job.run(['ignored'], 'upload')
        self.assertNotIn('SECRET-CANARY', str(caught.exception))
        self.assertNotIn('private.invalid', str(caught.exception))

    def test_invalid_local_archive_cannot_reach_docker(self):
        config = job.load_config(self.config, self.root)
        changed = dict(self.bundle, sha256='0' * 64)
        with mock.patch.object(job, 'run', return_value=json.dumps(changed).encode()):
            with self.assertRaises(job.JobError):
                job.produce(config)

    def test_failed_pending_copies_are_bounded_without_deleting_verified_copy(self):
        failed = self.state / 'exports/recovery_failed.zip'
        failed.write_bytes(b'older unsent')
        job.atomic_json(self.state / 'runs/failed.json',
                        {'status': 'failed', 'archive_name': failed.name})
        job.bound_pending(self.state, self.archive)
        self.assertFalse(failed.exists())
        self.assertTrue(self.old.exists())
        self.assertTrue(self.archive.exists())

    def test_retention_problem_does_not_hide_successful_external_copy(self):
        with mock.patch.object(job, 'prune_verified', side_effect=PermissionError):
            result = self.execute()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['retention_warning_class'], 'PermissionError')

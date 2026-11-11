"""Pure-stdlib status reporter tests; all source files are temporary fixtures."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from scripts.monitoring import report_backup_status as reporter


CANARY = 'SECRET_STATUS_CANARY_MUST_NOT_ESCAPE'


class BackupStatusReportTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='backup-status-report-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.project = self.root / 'project'
        (self.project / 'logs').mkdir(parents=True)
        self.state = self.root / 'state'
        (self.state / 'runs').mkdir(parents=True)
        self.log = self.project / 'logs' / 'cron_send_backup_to_vk.log'
        self.good = dict(status='success', started_at_utc='2026-11-10T00:15:00+00:00',
                         completed_at_utc='2026-11-10T00:16:00+00:00',
                         verified_download=True, temporary_delivery_files_removed=True)

    def write_json(self, path, value, mtime=None):
        path.write_text(json.dumps(value))
        if mtime is not None:
            os.utime(path, (mtime, mtime))

    def collect(self):
        return reporter.collect_status(self.project, self.state)

    def test_successful_jobs_are_allowlisted_and_never_expose_private_metadata(self):
        raw = dict(self.good, archive_name=CANARY, password=CANARY, error=CANARY,
                   document={'access_key': CANARY}, absolute_path=CANARY)
        self.write_json(self.state / 'last_success.json', raw)
        self.write_json(self.state / 'runs' / 'current.json', raw)
        self.log.write_text('2026-11-11 03:00:00 - START send_backup_to_vk (USE_DOCKER=1)\n'
                            + CANARY + '\n2026-11-11 03:02:00 - END success\n')
        result = self.collect()
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['jobs']['recovery'], {'latest': self.good, 'last_success': self.good})
        self.assertEqual(result['jobs']['database'], {
            'latest': {'status': 'success', 'completed_at_utc': '2026-11-11T00:02:00+00:00'},
            'last_success_at_utc': '2026-11-11T00:02:00+00:00'})
        self.assertIsNotNone(reporter._utc_timestamp(result['observed_at_utc']))
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_latest_recovery_failure_does_not_replace_old_last_good(self):
        self.write_json(self.state / 'last_success.json', self.good)
        self.write_json(self.state / 'runs' / 'old.json', self.good, mtime=100)
        failed = {'status': 'failed', 'completed_at_utc': '2026-11-11T00:17:00Z',
                  'phase': 'upload', 'error_class': CANARY}
        self.write_json(self.state / 'runs' / 'new.json', failed, mtime=200)
        recovery = self.collect()['jobs']['recovery']
        self.assertEqual(recovery['last_success'], self.good)
        self.assertEqual(recovery['latest'], {
            'status': 'failed', 'completed_at_utc': '2026-11-11T00:17:00+00:00', 'phase': 'upload'})

    def test_cleanup_false_and_retention_warning_remain_visible(self):
        run = dict(self.good, temporary_delivery_files_removed=False,
                   retention_warning_class='PermissionError')
        self.write_json(self.state / 'last_success.json', run)
        self.write_json(self.state / 'runs' / 'current.json', run)
        result = self.collect()['jobs']['recovery']
        self.assertFalse(result['latest']['temporary_delivery_files_removed'])
        self.assertFalse(result['last_success']['temporary_delivery_files_removed'])
        self.assertEqual(result['latest']['retention_warning_class'], 'PermissionError')

    def test_database_failure_preserves_last_success_in_bounded_history(self):
        self.log.write_text('2026-11-10 03:00:00 - START send_backup_to_vk\n'
                            '2026-11-10 03:01:00 - END success\n'
                            '2026-11-11 03:00:00 - START send_backup_to_vk (USE_DOCKER=1)\n'
                            '2026-11-11 03:04:00 - END failed (exit_code=1)\n')
        database = self.collect()['jobs']['database']
        self.assertEqual(database['latest'], {
            'status': 'failed', 'completed_at_utc': '2026-11-11T00:04:00+00:00'})
        self.assertEqual(database['last_success_at_utc'], '2026-11-10T00:01:00+00:00')

    def test_database_started_without_end_is_running_not_previous_green(self):
        self.log.write_text('2026-11-10 03:00:00 - START send_backup_to_vk\n'
                            '2026-11-10 03:01:00 - END success\n'
                            '2026-11-11 03:00:00 - START send_backup_to_vk (USE_DOCKER=1)\n')
        database = self.collect()['jobs']['database']
        self.assertEqual(database['latest'], {
            'status': 'running', 'started_at_utc': '2026-11-11T00:00:00+00:00'})
        self.assertEqual(database['last_success_at_utc'], '2026-11-10T00:01:00+00:00')

    def test_missing_or_malformed_inputs_fail_closed_without_exception_text(self):
        self.assertEqual(self.collect()['jobs'], {
            'database': {'latest': {'status': 'unknown'}, 'last_success_at_utc': None},
            'recovery': {'latest': {'status': 'unknown'}, 'last_success': {'status': 'unknown'}}})
        self.log.write_text(CANARY + '\n2026-99-99 03:00:00 - END success\n')
        (self.state / 'last_success.json').write_text(CANARY)
        (self.state / 'runs' / 'bad.json').write_text('[')
        result = self.collect()
        self.assertEqual(result['jobs']['database']['latest'], {'status': 'unknown'})
        self.assertEqual(result['jobs']['recovery']['latest'], {'status': 'unknown'})
        self.assertEqual(result['jobs']['recovery']['last_success'], {'status': 'unknown'})
        self.assertNotIn(CANARY, json.dumps(result))

    def test_malformed_newest_result_never_falls_back_to_old_success(self):
        for number in range(7):
            self.write_json(self.state / 'runs' / f'{number}.json', self.good, mtime=number + 100)
        newest = self.state / 'runs' / '6.json'
        newest.write_text('{malformed')
        os.utime(newest, (500, 500))
        result = self.collect()['jobs']['recovery']['latest']
        self.assertEqual(result, {'status': 'unknown'})

    def test_invalid_allowlisted_values_do_not_leak_into_output(self):
        invalid = [dict(self.good, phase=CANARY), dict(self.good, retention_warning_class=CANARY),
                   dict(self.good, status=CANARY), dict(self.good, completed_at_utc=CANARY),
                   dict(self.good, completed_at_utc='2026-11-11T00:16:00'),
                   dict(self.good, verified_download=CANARY), ['not a status object'],
                   {'status': 'success'}, {'status': 'running'}]
        for value in invalid:
            with self.subTest(kind=type(value).__name__):
                self.write_json(self.state / 'last_success.json', value)
                result = self.collect()
                self.assertEqual(result['jobs']['recovery']['last_success'], {'status': 'unknown'})
                self.assertNotIn(CANARY, json.dumps(result))

    def test_file_read_errors_are_unknown_and_not_returned(self):
        self.write_json(self.state / 'last_success.json', self.good)
        with mock.patch.object(reporter.os, 'open', side_effect=PermissionError(CANARY)):
            result = self.collect()
        self.assertEqual(result['jobs']['recovery']['last_success'], {'status': 'unknown'})
        self.assertNotIn(CANARY, json.dumps(result))

    def test_symlink_and_fifo_sources_are_not_followed_or_blocked(self):
        target = self.root / 'private.json'
        self.write_json(target, dict(self.good, password=CANARY))
        (self.state / 'last_success.json').symlink_to(target)
        self.log.symlink_to(target)
        os.mkfifo(self.state / 'runs' / 'pipe.json')
        result = self.collect()
        self.assertEqual(result['jobs']['recovery']['latest'], {'status': 'unknown'})
        self.assertEqual(result['jobs']['recovery']['last_success'], {'status': 'unknown'})
        self.assertEqual(result['jobs']['database']['latest'], {'status': 'unknown'})

    def test_status_files_and_database_tail_are_bounded(self):
        (self.state / 'last_success.json').write_bytes(b' ' * (reporter.MAX_STATUS_BYTES + 1))
        old = b'2026-11-10 03:01:00 - END success\n'
        recent = (b'\n2026-11-11 03:00:00 - START send_backup_to_vk\n'
                  b'2026-11-11 03:04:00 - END failed (exit_code=1)\n')
        self.log.write_bytes(old + b'X' * (reporter.MAX_LOG_BYTES + 10) + recent)
        result = self.collect()
        self.assertEqual(result['jobs']['recovery']['last_success'], {'status': 'unknown'})
        self.assertEqual(result['jobs']['database']['latest']['status'], 'failed')
        self.assertIsNone(result['jobs']['database']['last_success_at_utc'])

    def test_cli_ignores_ssh_original_command_and_emits_only_json(self):
        expected = self.collect()
        out = StringIO()
        with mock.patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': '--state-dir /private/' + CANARY}), \
                mock.patch.object(reporter, 'collect_status', return_value=expected) as collect, \
                redirect_stdout(out):
            self.assertEqual(reporter.main([]), 0)
        collect.assert_called_once_with(reporter.DEFAULT_PROJECT_DIR, reporter.DEFAULT_STATE_DIR)
        self.assertEqual(json.loads(out.getvalue()), expected)
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertNotIn(CANARY, out.getvalue())


if __name__ == '__main__':
    unittest.main()

import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'external_backup_monitor', Path(__file__).resolve().parents[2] / 'scripts/monitoring/monitor_backups.py')
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class ExternalBackupMonitorTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 11, 1, 0, tzinfo=dt.timezone.utc)
        self.config = {'failure_threshold': 2, 'repeat_seconds': 21600,
                       'vk': {'token': 'SECRET-CANARY', 'peer_id': '1'}}

    def report(self):
        good = {'status': 'success', 'completed_at_utc': '2026-11-11T00:16:00+00:00',
                'verified_download': True, 'temporary_delivery_files_removed': True}
        return {'schema_version': 1, 'observed_at_utc': self.now.isoformat(), 'jobs': {
            'database': {'latest': {'status': 'success'},
                         'last_success_at_utc': '2026-11-11T00:01:00+00:00'},
            'recovery': {'latest': dict(good), 'last_success': dict(good)}}}

    def test_both_current_copies_are_healthy(self):
        self.assertTrue(all(v[0] for v in monitor.evaluate_report(self.report(), self.now).values()))

    def test_missing_nightly_copy_turns_down_after_grace(self):
        report = self.report()
        for key in ('latest', 'last_success'):
            report['jobs']['recovery'][key]['completed_at_utc'] = '2026-11-10T00:16:00+00:00'
        self.assertFalse(monitor.evaluate_report(report, self.now)['recovery'][0])

    def test_yesterday_copy_is_acceptable_before_today_deadline(self):
        now = self.now.replace(hour=0, minute=44)
        report = self.report()
        report['observed_at_utc'] = now.isoformat()
        for key in ('latest', 'last_success'):
            report['jobs']['recovery'][key]['completed_at_utc'] = '2026-11-10T00:16:00+00:00'
        self.assertTrue(monitor.evaluate_report(report, now)['recovery'][0])
        now += dt.timedelta(minutes=1)
        report['observed_at_utc'] = now.isoformat()
        self.assertFalse(monitor.evaluate_report(report, now)['recovery'][0])

    def test_database_deadline_is_separate(self):
        now = self.now.replace(hour=0, minute=30)
        report = self.report()
        report['observed_at_utc'] = now.isoformat()
        report['jobs']['database']['last_success_at_utc'] = '2026-11-10T00:01:00+00:00'
        result = monitor.evaluate_report(report, now)
        self.assertFalse(result['database'][0])
        self.assertTrue(result['recovery'][0])

    def test_partial_success_marker_during_cleanup_uses_previous_completed_run(self):
        now = self.now.replace(hour=0, minute=20)
        report = self.report()
        report['observed_at_utc'] = now.isoformat()
        report['jobs']['recovery']['latest']['completed_at_utc'] = '2026-11-10T00:16:00+00:00'
        del report['jobs']['recovery']['last_success']['temporary_delivery_files_removed']
        self.assertTrue(monitor.evaluate_report(report, now)['recovery'][0])

    def test_failed_run_is_not_hidden_by_old_success(self):
        report = self.report()
        report['jobs']['recovery']['latest'].update(status='failed', completed_at_utc='2026-11-11T00:17:00+00:00')
        self.assertFalse(monitor.evaluate_report(report, self.now)['recovery'][0])

    def test_unverified_or_unclean_copy_never_sends_green(self):
        for field, value in [('verified_download', False), ('temporary_delivery_files_removed', False),
                             ('retention_warning_class', 'OSError')]:
            with self.subTest(field=field):
                report = self.report()
                report['jobs']['recovery']['latest'][field] = value
                self.assertFalse(monitor.evaluate_report(report, self.now)['recovery'][0])

    def test_stale_report_and_future_copy_are_rejected(self):
        report = self.report()
        report['observed_at_utc'] = '2026-11-10T00:00:00+00:00'
        with self.assertRaises(monitor.MonitorError):
            monitor.evaluate_report(report, self.now)
        report = self.report()
        report['jobs']['database']['last_success_at_utc'] = '2026-11-12T00:01:00+00:00'
        self.assertFalse(monitor.evaluate_report(report, self.now)['database'][0])

    def test_second_network_failure_alerts_once_then_recovers(self):
        state = {}
        monitor.update_state(state, {'server': (False, 'Нет связи.')}, self.config, self.now)
        self.assertEqual(state['outbox'], [])
        monitor.update_state(state, {'server': (False, 'Нет связи.')}, self.config, self.now)
        self.assertEqual(len(state['outbox']), 1)
        monitor.update_state(state, {'server': (False, 'Нет связи.')}, self.config, self.now)
        self.assertEqual(len(state['outbox']), 1)
        monitor.update_state(state, {'server': (True, '')}, self.config, self.now)
        self.assertEqual([e['kind'] for e in state['outbox']], ['alert', 'recovery'])

    def test_backup_alert_is_immediate_and_normal_state_is_silent(self):
        state = {}
        monitor.update_state(state, {'recovery': (True, '')}, self.config, self.now)
        self.assertEqual(state['outbox'], [])
        monitor.update_state(state, {'recovery': (False, 'Нет копии.')}, self.config, self.now)
        self.assertEqual(len(state['outbox']), 1)

    def test_outbox_retry_preserves_id_and_failed_delivery(self):
        state = {}
        monitor.update_state(state, {'recovery': (False, 'Нет копии.')}, self.config, self.now)
        before = json.loads(json.dumps(state['outbox']))
        with tempfile.TemporaryDirectory() as folder:
            state_file = Path(folder) / 'state.json'
            failed = mock.Mock(side_effect=RuntimeError('SECRET-CANARY'))
            monitor.deliver_outbox(self.config, state, state_file, sender=failed)
            self.assertEqual(state['outbox'], before)
            self.assertNotIn('SECRET-CANARY', state_file.read_text())
            sender = mock.Mock()
            monitor.deliver_outbox(self.config, state, state_file, sender=sender)
            self.assertEqual(state['outbox'], [])
            self.assertEqual(sender.call_args.args[1]['random_id'], before[0]['random_id'])

    def test_repeat_after_six_hours_and_pending_failure_has_no_duplicates(self):
        state = {}
        bad = {'website': (False, 'Ошибка сайта.')}
        monitor.update_state(state, bad, self.config, self.now)
        monitor.update_state(state, bad, self.config, self.now)
        monitor.update_state(state, bad, self.config, self.now + dt.timedelta(hours=7))
        self.assertEqual(len(state['outbox']), 1)
        state['outbox'].clear()
        monitor.update_state(state, bad, self.config, self.now + dt.timedelta(hours=7))
        self.assertEqual(len(state['outbox']), 1)

    def test_vk_outage_and_flapping_keep_latest_incident_bounded(self):
        state = {}
        for index in range(200):
            now = self.now + dt.timedelta(minutes=index * 10)
            monitor.update_state(state, {'server': (False, 'Нет связи.')}, self.config, now)
            monitor.update_state(state, {'server': (False, 'Нет связи.')}, self.config, now)
            self.assertEqual(len(state['outbox']), 1)
            self.assertEqual(state['outbox'][0]['incident'], state['checks']['server']['incident'])
            monitor.update_state(state, {'server': (True, '')}, self.config, now)
            self.assertEqual([event['kind'] for event in state['outbox']], ['alert', 'recovery'])
        self.assertLess(len(json.dumps(state)), 10000)

    def test_check_only_never_changes_state_or_sends(self):
        with tempfile.TemporaryDirectory() as folder:
            config = dict(self.config, state_file=str(Path(folder) / 'state.json'))
            with mock.patch.object(monitor, 'collect_observations', return_value={'server': (True, '')}), \
                    mock.patch.object(monitor, 'send_vk') as sender:
                result = monitor.run_cycle(config, check_only=True)
            self.assertEqual(result['status'], 'checked_without_notifications')
            self.assertFalse(Path(config['state_file']).exists())
            sender.assert_not_called()

    def test_ssh_uses_restricted_identity_and_does_not_request_a_shell(self):
        config = {'ssh': {'host': 'example.test', 'port': 22, 'user': 'deploy',
                          'identity_file': '/etc/monitor/key', 'known_hosts_file': '/etc/monitor/hosts'}}
        result = mock.Mock(returncode=0, stdout=json.dumps(self.report()).encode())
        with mock.patch.object(monitor.subprocess, 'run', return_value=result) as run:
            monitor.probe_server(config)
        args = run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('IdentitiesOnly=yes', args)
        self.assertEqual(args[-1], 'backup-status')

    def test_vk_http_200_with_api_error_is_not_success(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"error":{"error_code":5,"error_msg":"SECRET-CANARY"}}'
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(monitor.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(monitor.MonitorError, '^vk_delivery_failed$'):
                monitor.send_vk(self.config, {'message': 'test', 'random_id': 1})

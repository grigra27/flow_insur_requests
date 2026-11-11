#!/usr/bin/env python3
"""Observe InsFlow from a separate host and send incident changes to VK."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import urllib.parse
import urllib.request
from uuid import uuid4
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
MSK = ZoneInfo('Europe/Moscow')
LABELS = {
    'server': 'Связь с основным сервером',
    'website': 'Доступность рабочего сайта',
    'database': 'Ночная копия БД, 03:00 МСК',
    'recovery': 'Полная ночная копия, 03:15 МСК',
}


class MonitorError(Exception):
    """Only constant error codes may leave the process."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.monitor-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_private_json(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or info.st_mode & 0o027 or info.st_size > 1024 * 1024):
        raise MonitorError('unsafe_configuration')
    return json.loads(path.read_text())


def load_config(path):
    config = read_private_json(path)
    ssh, vk = config['ssh'], config['vk']
    if (config.get('schema_version') != 1
            or not ssh['host'] or ssh['host'].startswith('-')
            or not ssh['user'] or ssh['user'].startswith('-')
            or not 1 <= int(ssh['port']) <= 65535
            or not vk['token'] or not str(vk['peer_id']).lstrip('-').isdigit()
            or not 1 <= config.get('failure_threshold', 2) <= 10
            or config.get('repeat_seconds', 21600) < 3600
            or not 1 <= len(config['http_urls']) <= 4):
        raise MonitorError('invalid_configuration')
    for url in config['http_urls']:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise MonitorError('invalid_configuration')
    for key in ('identity_file', 'known_hosts_file'):
        if not Path(ssh[key]).is_absolute():
            raise MonitorError('invalid_configuration')
    if not Path(config['state_file']).is_absolute():
        raise MonitorError('invalid_configuration')
    return config


def probe_server(config):
    ssh = config['ssh']
    args = ['ssh', '-T', '-i', ssh['identity_file'], '-p', str(ssh['port']),
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
            '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=5',
            '-o', 'ServerAliveCountMax=1', '-o', 'PasswordAuthentication=no',
            '-o', 'UserKnownHostsFile=' + ssh['known_hosts_file'],
            ssh['user'] + '@' + ssh['host'], 'backup-status']
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
        if result.returncode or len(result.stdout) > 65536:
            raise MonitorError('server_unreachable')
        report = json.loads(result.stdout)
        if not isinstance(report, dict) or report.get('schema_version') != 1:
            raise MonitorError('invalid_report')
        return report
    except MonitorError:
        raise
    except Exception:
        raise MonitorError('server_unreachable') from None


def probe_website(config):
    opener = urllib.request.build_opener(NoRedirect)
    for url in config['http_urls']:
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'InsFlow-External-Monitor/1'})
            with opener.open(request, timeout=10) as response:
                body = response.read(128 * 1024)
                if response.status != 200 or not body:
                    return False
                if urllib.parse.urlsplit(url).path == '/healthz/' and body.strip() != b'OK':
                    return False
        except Exception:
            return False
    return True


def expected_backup(now, minute):
    local = now.astimezone(MSK)
    scheduled = local.replace(hour=3, minute=minute, second=0, microsecond=0)
    if local < scheduled + dt.timedelta(minutes=30):
        scheduled -= dt.timedelta(days=1)
    return scheduled.astimezone(UTC)


def verified_recovery(record):
    return (record.get('status') == 'success' and record.get('verified_download') is True
            and record.get('temporary_delivery_files_removed') is True
            and not record.get('retention_warning_class'))


def evaluate_report(report, now):
    observed = timestamp(report.get('observed_at_utc'))
    if observed is None or abs((now - observed).total_seconds()) > 300:
        raise MonitorError('invalid_report_clock')
    observations = {}
    jobs = report.get('jobs')
    if not isinstance(jobs, dict):
        raise MonitorError('invalid_report')
    for name, minute in [('database', 0), ('recovery', 15)]:
        job = jobs.get(name, {})
        latest = job.get('latest', {})
        success = job.get('last_success', {})
        last_good = timestamp(job.get('last_success_at_utc') if name == 'database'
                              else success.get('completed_at_utc'))
        latest_end = timestamp(latest.get('completed_at_utc'))
        if any(t is not None and t > now + dt.timedelta(minutes=5) for t in [last_good, latest_end]):
            observations[name] = (False, 'Некорректное время в результате резервирования.')
            continue
        if name == 'recovery' and not verified_recovery(success):
            # The producer replaces last_success before cleanup, then writes the
            # finalized run and marker. During that short interval retain only
            # the previous fully verified completed run, subject to its deadline.
            last_good = timestamp(latest.get('completed_at_utc')) if verified_recovery(latest) else None
        if latest.get('status') == 'failed' and latest_end and (last_good is None or latest_end >= last_good):
            observations[name] = (False, 'Последний запуск завершился ошибкой.')
        elif name == 'recovery' and latest.get('status') == 'success' and not verified_recovery(latest):
            observations[name] = (False, 'Не подтверждены проверка доставки или завершающая очистка.')
        elif latest.get('status') == 'unknown':
            observations[name] = (False, 'Не удалось прочитать актуальный результат резервирования.')
        elif last_good is None or last_good < expected_backup(now, minute):
            observations[name] = (False, 'Нет подтверждённой ночной копии после допустимого срока.')
        else:
            observations[name] = (True, '')
    return observations


def collect_observations(config, now):
    observations = {}
    try:
        report = probe_server(config)
        observations.update(evaluate_report(report, now))
        observations['server'] = (True, '')
    except Exception:
        observations['server'] = (False, 'Нет связи с сервером или не получен актуальный отчёт.')
    observations['website'] = (probe_website(config), 'Рабочий сайт не отвечает корректно по HTTPS.')
    return observations


def queue_event(state, name, kind, incident, detail, now, prefix):
    # If VK is unreachable during repeated flapping, retain only the latest
    # incident per check: at most its alert and recovery. A later incident
    # supersedes unsent history; the current outage must never be discarded.
    state['outbox'] = [event for event in state['outbox']
                       if event['check'] != name or event['incident'] == incident]
    if any(event['check'] == name and event['incident'] == incident
           and event['kind'] == kind for event in state['outbox']):
        return
    event_id = uuid4().hex
    text = ('🔴 СБОЙ' if kind == 'alert' else '🟢 ВОССТАНОВЛЕНО')
    message = (f'{prefix}InsFlow · внешний контроль\n{text}: {LABELS[name]}\n'
               f'{detail}\n{now.astimezone(MSK):%d.%m.%Y %H:%M} МСК').replace('\n\n', '\n')
    random_id = int.from_bytes(hashlib.sha256(event_id.encode()).digest()[:4], 'big') & 0x7fffffff
    state['outbox'].append({'id': event_id, 'check': name, 'kind': kind,
                            'incident': incident, 'message': message, 'random_id': random_id or 1})


def update_state(state, observations, config, now, *, prefix=''):
    state.setdefault('schema_version', 1)
    state.setdefault('checks', {})
    state.setdefault('outbox', [])
    for name, (healthy, detail) in observations.items():
        item = state['checks'].setdefault(name, {'failures': 0, 'active': False})
        if healthy:
            item['failures'] = 0
            if item.get('active'):
                queue_event(state, name, 'recovery', item['incident'], '', now, prefix)
                item['active'] = False
            continue
        item['failures'] = min(item.get('failures', 0) + 1, 100)
        threshold = config.get('failure_threshold', 2) if name in ('server', 'website') else 1
        if item['failures'] < threshold:
            continue
        if not item.get('active'):
            item.update(active=True, incident=uuid4().hex, last_queued=None)
        last_queued = timestamp(item.get('last_queued'))
        repeat_due = last_queued is None or (now - last_queued).total_seconds() >= config.get('repeat_seconds', 21600)
        pending = any(e['check'] == name and e['incident'] == item['incident']
                      and e['kind'] == 'alert' for e in state['outbox'])
        if repeat_due and not pending:
            queue_event(state, name, 'alert', item['incident'], detail, now, prefix)
            item['last_queued'] = now.isoformat()
    state['checked_at_utc'] = now.isoformat()


def send_vk(config, event):
    vk = config['vk']
    payload = urllib.parse.urlencode({'access_token': vk['token'], 'peer_id': vk['peer_id'],
                                     'v': vk.get('api_version', '5.199'),
                                     'random_id': event['random_id'], 'message': event['message']}).encode()
    request = urllib.request.Request('https://api.vk.com/method/messages.send', data=payload)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
            result = json.loads(response.read(65536))
        if 'error' in result or type(result.get('response')) is not int or result['response'] <= 0:
            raise MonitorError('vk_delivery_failed')
    except Exception:
        raise MonitorError('vk_delivery_failed') from None


def deliver_outbox(config, state, state_file, *, sender=send_vk):
    delivered = 0
    for event in list(state['outbox'])[:4]:
        try:
            sender(config, event)
        except Exception:
            state['last_delivery_error'] = 'vk_delivery_failed'
            atomic_json(state_file, state)
            return delivered
        state['outbox'].remove(event)
        state.pop('last_delivery_error', None)
        state['last_delivered_at_utc'] = dt.datetime.now(UTC).isoformat()
        atomic_json(state_file, state)
        delivered += 1
    return delivered


def run_cycle(config, *, check_only=False):
    state_file = Path(config['state_file'])
    if not state_file.parent.is_dir():
        raise MonitorError('state_directory_missing')
    with (state_file.parent / 'monitor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'busy'}
        now = dt.datetime.now(UTC)
        observations = collect_observations(config, now)
        summary = {'checks': {key: 'up' if value[0] else 'down' for key, value in observations.items()}}
        if check_only:
            return dict(summary, status='checked_without_notifications')
        state = read_private_json(state_file) if state_file.exists() else {}
        update_state(state, observations, config, now)
        atomic_json(state_file, state)
        delivered = deliver_outbox(config, state, state_file)
        return dict(summary, status='checked', notifications_delivered=delivered,
                    notifications_pending=len(state['outbox']))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        result = run_cycle(load_config(args.config), check_only=args.check_only)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get('notifications_pending') else 0
    except Exception as error:
        # Do not print exception messages: HTTP and SSH exceptions may contain credentials.
        print(json.dumps({'status': 'error', 'error_code': str(error) if isinstance(error, MonitorError)
                          else 'monitor_failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

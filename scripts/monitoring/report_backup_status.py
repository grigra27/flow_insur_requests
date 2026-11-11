#!/usr/bin/env python3
"""Report bounded, non-secret backup status to a fixed SSH forced command."""
import argparse
from datetime import datetime, timezone
import heapq
import json
import os
from pathlib import Path
import re
import stat
from zoneinfo import ZoneInfo


DEFAULT_PROJECT_DIR = Path('/opt/insflow-system')
DEFAULT_STATE_DIR = Path('/home/deploy/.local/state/insflow-recovery')
MAX_STATUS_BYTES = 64 * 1024
MAX_LOG_BYTES = 512 * 1024
MAX_RUN_CANDIDATES = 5
RUN_STATUSES = {'success', 'failed', 'running', 'busy', 'unknown'}
PHASES = {'configuration', 'bundle', 'snapshot', 'encryption', 'upload',
          'cleanup', 'notification', 'retention', 'finalize'}
RETENTION_CLASSES = {'OSError', 'PermissionError', 'FileNotFoundError',
                     'NotADirectoryError', 'IsADirectoryError', 'BlockingIOError',
                     'InterruptedError', 'TimeoutError'}
RUN_FIELDS = {'status', 'started_at_utc', 'completed_at_utc', 'verified_download',
              'temporary_delivery_files_removed', 'retention_warning_class', 'phase'}
EVENT = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - '
    r'(?:(?P<start>START send_backup_to_vk)(?: \(USE_DOCKER=[01]\))?'
    r'|END (?P<end>success|failed)(?: \(exit_code=\d{1,3}\))?)$'
)


def _unknown():
    return {'status': 'unknown'}


def _read_file(path, limit, *, tail=False):
    """Never follow a status/log symlink or block opening a substituted FIFO."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            information = os.fstat(stream.fileno())
            if not stat.S_ISREG(information.st_mode):
                return None
            if not tail and information.st_size > limit:
                return None
            offset = max(0, information.st_size - limit) if tail else 0
            if offset:
                stream.seek(offset)
            data = stream.read(limit)
            if offset:
                # The first retained line may begin in the middle of a message.
                data = data.partition(b'\n')[2]
            return data
    except (OSError, ValueError):
        return None


def _utc_timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _clean_run(value):
    if not isinstance(value, dict) or value.get('status') not in RUN_STATUSES:
        return _unknown()
    result = {'status': value['status']}
    for key in RUN_FIELDS - {'status'}:
        if key not in value:
            continue
        item = value[key]
        if key in {'started_at_utc', 'completed_at_utc'}:
            item = _utc_timestamp(item)
            if item is None:
                return _unknown()
        elif key in {'verified_download', 'temporary_delivery_files_removed'}:
            if type(item) is not bool:
                return _unknown()
        elif key == 'phase':
            if item not in PHASES:
                return _unknown()
        elif key == 'retention_warning_class':
            if item not in RETENTION_CLASSES:
                return _unknown()
        result[key] = item
    if result['status'] in {'success', 'failed'} and 'completed_at_utc' not in result:
        return _unknown()
    if result['status'] == 'running' and 'started_at_utc' not in result:
        return _unknown()
    return result


def _read_run(path):
    raw = _read_file(path, MAX_STATUS_BYTES)
    if raw is None:
        return _unknown()
    try:
        return _clean_run(json.loads(raw))
    except (ValueError, TypeError, RecursionError):
        return _unknown()


def _latest_run(directory):
    def candidates():
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.endswith('.json'):
                    information = entry.stat(follow_symlinks=False)
                    yield information.st_mtime_ns, entry.name, Path(entry.path)
    try:
        recent = heapq.nlargest(MAX_RUN_CANDIDATES, candidates())
    except OSError:
        return _unknown()
    if not recent:
        return _unknown()
    # A malformed newest result must not make an older successful run look current.
    return _read_run(recent[0][2])


def _database_status(project_dir):
    result = {'latest': _unknown(), 'last_success_at_utc': None}
    raw = _read_file(project_dir / 'logs' / 'cron_send_backup_to_vk.log', MAX_LOG_BYTES, tail=True)
    if raw is None:
        return result
    try:
        moscow = ZoneInfo('Europe/Moscow')
        for line in raw.decode('utf-8', errors='replace').splitlines():
            event = EVENT.fullmatch(line)
            if not event:
                continue
            try:
                moment = datetime.strptime(event['timestamp'], '%Y-%m-%d %H:%M:%S')
                stamp = moment.replace(tzinfo=moscow).astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError):
                result['latest'] = _unknown()
                continue
            if event['start']:
                result['latest'] = {'status': 'running', 'started_at_utc': stamp}
            else:
                result['latest'] = {'status': event['end'], 'completed_at_utc': stamp}
                if event['end'] == 'success':
                    result['last_success_at_utc'] = stamp
    except (OSError, ValueError):
        return {'latest': _unknown(), 'last_success_at_utc': None}
    return result


def collect_status(project_dir=DEFAULT_PROJECT_DIR, state_dir=DEFAULT_STATE_DIR):
    """Read status only; no Django, database, subprocess, network or secret config."""
    recovery = {'latest': _unknown(), 'last_success': _unknown()}
    database = {'latest': _unknown(), 'last_success_at_utc': None}
    try:
        project_dir, state_dir = Path(project_dir), Path(state_dir)
        database = _database_status(project_dir)
        recovery['last_success'] = _read_run(state_dir / 'last_success.json')
        recovery['latest'] = _latest_run(state_dir / 'runs')
    except Exception:
        # Only a fixed schema crosses the SSH boundary, never diagnostic strings.
        pass
    return {'schema_version': 1, 'observed_at_utc': datetime.now(timezone.utc).isoformat(),
            'jobs': {'database': database, 'recovery': recovery}}


def _path_argument(value):
    if len(value.encode('utf-8')) > 4096 or '\x00' in value:
        raise argparse.ArgumentTypeError('Invalid status directory.')
    return Path(value)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=_path_argument, default=DEFAULT_PROJECT_DIR)
    parser.add_argument('--state-dir', type=_path_argument, default=DEFAULT_STATE_DIR)
    options = parser.parse_args(arguments)
    # SSH_ORIGINAL_COMMAND and stdin are deliberately never consulted. A forced
    # SSH key must call this script with a fixed command, without shell expansion.
    print(json.dumps(collect_status(options.project_dir, options.state_dir), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

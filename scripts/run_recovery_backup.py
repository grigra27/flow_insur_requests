#!/usr/bin/env python3
"""Create, deliver and read back one encrypted recovery copy; never log secrets."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from uuid import uuid4

WEB = 'insflow-system-web-1'
REMOTE = '/app/backups/recovery_delivery'
LIMIT = 190 * 1024 * 1024
SAFE_NAME = re.compile(r'^[A-Za-z0-9_.-]+$')
ARCHIVE_SUFFIXES = {'.zip'}


class JobError(Exception):
    def __init__(self, stage, code=1):
        self.stage, self.code = stage, code
        super().__init__(stage)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(arguments, stage, *, stdin=None, timeout=1200):
    try:
        result = subprocess.run(arguments, stdin=stdin, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise JobError(stage) from None
    if result.returncode:
        # stderr may contain credential-bearing service URLs. Do not retain it.
        raise JobError(stage, result.returncode) from None
    return result.stdout


def read_json(data, stage):
    try:
        return json.loads(data)
    except (TypeError, ValueError):
        raise JobError(stage) from None


def management(command, arguments, stage):
    return read_json(run(['docker', 'exec', WEB, 'python', 'manage.py', command,
                          *arguments], stage), stage)


def load_config(path, project_dir):
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
                or info.st_mode & 0o077 or info.st_uid != os.geteuid()):
            raise JobError('configuration')
        config = json.loads(path.read_text())
        archive_format = config.get('archive_format', 'age-zip')
        if archive_format not in ('age-zip', 'age-passphrase'):
            raise JobError('configuration')
        result = {'archive_format': archive_format,
                  'state_dir': Path(config['state_dir']).expanduser().resolve()}
        if archive_format == 'age-zip':
            for name in ('age_binary', 'recipient_file'):
                result[name] = Path(config[name]).expanduser().resolve()
                if not result[name].is_file():
                    raise JobError('configuration')
        else:
            result['age_binary'] = Path(config['age_binary']).expanduser().resolve()
            password_file = Path(config['password_file']).expanduser()
            secret_info = password_file.lstat()
            if (not password_file.is_absolute() or not stat.S_ISREG(secret_info.st_mode)
                    or password_file.is_symlink() or secret_info.st_uid != os.geteuid()
                    or secret_info.st_mode & 0o077
                    or not result['age_binary'].is_file()
                    or not os.access(result['age_binary'], os.X_OK)):
                raise JobError('configuration')
            # Keep the original path so the producer's O_NOFOLLOW check remains effective.
            result['password_file'] = password_file
        result['project_dir'] = project_dir.resolve()
        result['keep_local'] = int(config.get('keep_local', 14))
        if not 1 <= result['keep_local'] <= 60:
            raise JobError('configuration')
        return result
    except JobError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise JobError('configuration') from None


def produce(config):
    arguments = [
        sys.executable, str(config['project_dir'] / 'scripts/create_recovery_bundle.py'),
        '--project-dir', str(config['project_dir']), '--state-dir', str(config['state_dir']),
    ]
    archive_format = config.get('archive_format', 'age-zip')
    if archive_format == 'age-passphrase':
        arguments.extend(['--archive-format', 'age-passphrase', '--age-binary',
                          str(config['age_binary']), '--password-file', str(config['password_file'])])
    else:
        arguments.extend(['--age-binary', str(config['age_binary']),
                          '--recipient-file', str(config['recipient_file'])])
    result = read_json(run(arguments, 'bundle'), 'bundle')
    try:
        archive = Path(result['archive_path'])
        if (result['status'] != 'ready' or not SAFE_NAME.fullmatch(archive.name)
                or archive.suffix != '.zip'
                or archive.is_symlink()
                or archive.resolve().parent != (config['state_dir'] / 'exports').resolve()
                or not archive.is_file() or not 0 < archive.stat().st_size <= LIMIT
                or archive.stat().st_size != result['size'] or digest(archive) != result['sha256']
                or not SAFE_NAME.fullmatch(result['backup_id'])):
            raise JobError('bundle')
    except (OSError, KeyError, TypeError):
        raise JobError('bundle') from None
    return result


def copy_to_web(archive, destination, expected):
    code = """import os,sys,pathlib,hashlib
p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
t=p.with_name('.'+p.name+'.partial')
try:
 h=hashlib.sha256()
 with t.open('wb') as f:
  while True:
   block=sys.stdin.buffer.read(1024*1024)
   if not block: break
   f.write(block);h.update(block)
 os.chmod(t,0o600)
 if h.hexdigest()!=sys.argv[2]: raise RuntimeError('CiphertextDigestMismatch')
 os.replace(t,p)
finally:
 t.unlink(missing_ok=True)
"""
    with archive.open('rb') as stream:
        run(['docker', 'exec', '-i', WEB, 'python', '-c', code, destination, expected],
            'upload', stdin=stream)


def cleanup_remote(paths):
    if not paths:
        return
    code = """import pathlib,sys
for name in sys.argv[1:]:
 p=pathlib.Path(name)
 if p.parent!=pathlib.Path('/app/backups/recovery_delivery'): raise RuntimeError('InvalidCleanupPath')
 p.unlink(missing_ok=True)
"""
    run(['docker', 'exec', WEB, 'python', '-c', code, *paths], 'cleanup', timeout=45)


def prune_verified(state, keep, current_archive=None):
    receipts = []
    for path in (state / 'receipts').glob('*.json'):
        if path.is_symlink():
            continue
        try:
            entry = json.loads(path.read_text())
            if entry.get('verified_download') is True:
                receipts.append((entry['completed_at_utc'], path, entry))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    current_name = current_archive.name if current_archive is not None else None
    protected = [item for item in receipts if current_name is not None
                 and item[2].get('archive_name') == current_name]
    others = [item for item in receipts if current_name is None
              or item[2].get('archive_name') != current_name]
    remaining = max(0, keep - len(protected))
    # A clock rollback must not prune the copy just recorded in last_success.
    for _, receipt_path, entry in sorted(others, key=lambda item: item[0], reverse=True)[remaining:]:
        name = entry.get('archive_name', '')
        if SAFE_NAME.fullmatch(name) and Path(name).suffix in ARCHIVE_SUFFIXES:
            archive = state / 'exports' / name
            if archive.is_file() and not archive.is_symlink():
                archive.unlink()
            receipt_path.unlink()


def bound_pending(state, current_archive):
    """Bound failed ciphertexts; never remove a verified copy on a failed run."""
    verified = set()
    for path in (state / 'receipts').glob('*.json'):
        try:
            item = json.loads(path.read_text())
            if item.get('verified_download'):
                verified.add(item.get('archive_name'))
        except (OSError, ValueError):
            pass
    for path in (state / 'runs').glob('*.json'):
        try:
            item = json.loads(path.read_text())
            name = item.get('archive_name', '')
            if (item.get('status') == 'failed' and name and name not in verified
                    and SAFE_NAME.fullmatch(name) and Path(name).suffix in ARCHIVE_SUFFIXES
                    and name != current_archive.name):
                archive = state / 'exports' / name
                if archive.is_file() and not archive.is_symlink():
                    archive.unlink()
        except (OSError, ValueError):
            pass


def run_job(project_dir, config_path):
    config = load_config(config_path, project_dir)
    state = config['state_dir']
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.is_symlink() or state.stat().st_mode & 0o077:
        raise JobError('configuration')
    for name in ('exports', 'receipts', 'runs'):
        (state / name).mkdir(mode=0o700, exist_ok=True)
    with (state / 'job.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'busy', 'exit_code': 75}
        job_id = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid4().hex[:8]
        result = {'status': 'failed', 'job_id': job_id, 'started_at_utc': now()}
        remote_paths = []
        archive = None
        stage = 'bundle'
        try:
            bundle = produce(config)
            archive = Path(bundle['archive_path'])
            result.update(backup_id=bundle['backup_id'], archive_name=archive.name,
                          sha256=bundle['sha256'], bytes=bundle['size'])
            remote_zip = REMOTE + '/' + archive.name
            remote_receipt = REMOTE + '/' + bundle['backup_id'] + '.sent.json'
            remote_verify = REMOTE + '/' + bundle['backup_id'] + '.verified' + archive.suffix
            remote_paths = [remote_zip, remote_receipt, remote_verify]
            stage = 'upload'
            copy_to_web(archive, remote_zip, bundle['sha256'])
            sent = management('send_recovery_to_vk', [
                '--archive', remote_zip, '--expected-sha256', bundle['sha256'],
                '--receipt-file', remote_receipt, '--no-notify'], stage)
            if sent.get('status') not in ('sent', 'already_sent') or sent.get('sha256') != bundle['sha256']:
                raise JobError(stage)
            receipt = read_json(run(['docker', 'exec', WEB, 'cat', remote_receipt], stage), stage)
            if (receipt.get('sha256') != bundle['sha256'] or receipt.get('size') != bundle['size']
                    or receipt.get('archive_name') != archive.name):
                raise JobError(stage)
            atomic_json(state / 'receipts' / (bundle['backup_id'] + '.pending.json'), receipt)
            downloaded = management('download_recovery_from_vk', [
                '--receipt-file', remote_receipt, '--output-file', remote_verify], stage)
            if downloaded.get('sha256') != bundle['sha256'] or downloaded.get('bytes') != bundle['size']:
                raise JobError(stage)
            result.update(status='success', verified_download=True, completed_at_utc=now())
            receipt.update(backup_id=bundle['backup_id'], verified_download=True,
                           completed_at_utc=result['completed_at_utc'])
            atomic_json(state / 'receipts' / (bundle['backup_id'] + '.json'), receipt)
            (state / 'receipts' / (bundle['backup_id'] + '.pending.json')).unlink(missing_ok=True)
            atomic_json(state / 'last_success.json', result)
            try:
                prune_verified(state, config['keep_local'], current_archive=archive)
            except OSError as error:
                result['retention_warning_class'] = type(error).__name__
        except Exception as error:
            stage = error.stage if isinstance(error, JobError) else stage
            result.update(status='failed', phase=stage, error_class=type(error).__name__,
                          completed_at_utc=now())
            try:
                management('send_recovery_to_vk', ['--notify-failure', '--failure-code',
                           stage if stage in ('snapshot', 'bundle', 'encryption', 'upload') else 'bundle'],
                           'notification')
                result['failure_notification_sent'] = True
            except Exception:
                result['failure_notification_sent'] = False
        finally:
            try:
                cleanup_remote(remote_paths)
                result['temporary_delivery_files_removed'] = True
            except JobError:
                result['temporary_delivery_files_removed'] = False
            atomic_json(state / 'runs' / (job_id + '.json'), result)
            if result['status'] == 'success':
                atomic_json(state / 'last_success.json', result)
            if archive is not None:
                bound_pending(state, archive)
        return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--config', type=Path,
                        default=Path.home() / '.config/insflow-recovery/config.json')
    args = parser.parse_args()
    try:
        result = run_job(args.project_dir, args.config)
    except Exception as error:
        result = {'status': 'failed', 'phase': error.stage if isinstance(error, JobError)
                  else 'configuration', 'error_class': type(error).__name__}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'success' else result.get('exit_code', 1)


if __name__ == '__main__':
    raise SystemExit(main())

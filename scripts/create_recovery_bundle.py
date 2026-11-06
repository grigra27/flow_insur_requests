#!/usr/bin/env python3
"""Build one encrypted recovery ZIP as the deployment user; never send it."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from uuid import uuid4
import zipfile

WEB = 'insflow-system-web-1'
NGINX = 'insflow-system-nginx-1'
SNAPSHOT_PARENT = PurePosixPath('/app/backups/recovery')
SNAPSHOT_NAME = re.compile(r'recovery_\d{8}T\d{6}_\d{6}Z_[0-9a-f]{32}')
MAX_ARCHIVE_BYTES = 190 * 1024 * 1024
README = ('Encrypted InsFlow recovery bundle.\n'
          'Extract payload.tar.age and decrypt it using your separately stored age identity.\n'
          'The decrypted tar contains database, documents, configuration, source and integrity manifest.\n'
          'Keep the private identity separate. Verify all hashes before an isolated restore.\n')


class BundleError(RuntimeError):
    """Only static descriptions may cross the host CLI boundary."""


def run(arguments, output=None):
    try:
        result = subprocess.run(arguments, stdout=output or subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=600)
    except (OSError, subprocess.SubprocessError):
        raise BundleError('Recovery source command could not complete.') from None
    if result.returncode:
        raise BundleError('Recovery source command failed.')
    return result.stdout


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def regular(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise BundleError('Recovery input must be a regular file.')
    return {'size': info.st_size, 'sha256': sha256(path),
            'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}


def relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or '\x00' in value:
        raise BundleError('Recovery snapshot contains an unsafe path.')
    return path.as_posix()


def runtime():
    template = ('{"container_id":{{json .Id}},"image_id":{{json .Image}},'
                '"running":{{json .State.Running}},"paused":{{json .State.Paused}},'
                '"mounts":{{json .Mounts}}}')
    info = json.loads(run(['docker', 'inspect', '--format', template, WEB]))
    if not info['running'] or info['paused']:
        raise BundleError('Application is not ready for a recovery snapshot.')
    if not any(item['Destination'] == '/app/backups' for item in info['mounts']):
        raise BundleError('Application backup volume is missing.')
    metadata = ('import django,json,os,platform; print(json.dumps({'
                '"build_sha":os.environ.get("APP_BUILD_SHA",""),'
                '"django_version":django.get_version(),"python_version":platform.python_version()}))')
    info.update(json.loads(run(['docker', 'exec', WEB, 'python', '-c', metadata])))
    info['image_digests'] = json.loads(run(['docker', 'image', 'inspect', '--format', '{{json .RepoDigests}}', info['image_id']]))
    info['pip_freeze'] = sorted(run(['docker', 'exec', WEB, 'python', '-m', 'pip', '--disable-pip-version-check', 'freeze', '--all']).decode().splitlines())
    if not re.fullmatch(r'[0-9a-f]{40}', info['build_sha']):
        raise BundleError('Application build metadata is missing.')
    return info


def source_state(project):
    commit = run(['git', '-C', str(project), 'rev-parse', 'HEAD']).decode().strip()
    # Deployment chmod and separately captured runtime config are intentional.
    changed = run(['git', '-c', 'core.fileMode=false', '-C', str(project),
                   'diff', '--name-only', '-z', 'HEAD', '--']).decode().split('\0')
    allowed = {path.relative_to(project).as_posix() for path in config_inputs(project).values()}
    if any(name and name not in allowed for name in changed):
        raise BundleError('Tracked application source differs from its release.')
    return commit


def config_inputs(project):
    inputs = {'.env': project / '.env', 'docker-compose.yml': project / 'docker-compose.yml',
              'nginx.conf': project / 'nginx-timeweb/default.conf'}
    fallback = project / 'nginx-timeweb/default-acme.conf'
    if fallback.exists():
        inputs['nginx-acme.conf'] = fallback
    return inputs


def configuration_state(project):
    return {name: regular(path) for name, path in config_inputs(project).items()}


def insflow_cron():
    result = subprocess.run(['crontab', '-l'], capture_output=True, timeout=30)
    if result.returncode not in (0, 1):
        raise BundleError('Application cron metadata could not be read.')
    return b'\n'.join(line for line in result.stdout.splitlines()
                       if re.search(rb'#\s*insflow-[A-Za-z0-9_-]+', line)) + b'\n'


def tls_archive(destination):
    with Path(destination).open('wb') as target:
        run(['docker', 'exec', NGINX, 'tar', '-C', '/etc', '-cf', '-', 'letsencrypt'], target)
    names, targets = set(), []
    with tarfile.open(destination) as archive:
        for member in archive:
            name = relative(member.name)
            names.add(name)
            if name != 'letsencrypt' and not name.startswith('letsencrypt/'):
                raise BundleError('TLS archive is outside its allowlist.')
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise BundleError('TLS archive contains an unsupported entry.')
            if member.issym() or member.islnk():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname)) if member.issym() else posixpath.normpath(member.linkname)
                if target != 'letsencrypt' and not target.startswith('letsencrypt/'):
                    raise BundleError('TLS archive contains an unsafe link.')
                targets.append(target)
    if any(target not in names for target in targets):
        raise BundleError('TLS archive contains a missing link target.')
    return sha256(destination)


def verify_snapshot(directory, expected_build):
    if directory.is_symlink() or (directory / 'media').is_symlink():
        raise BundleError('Recovery snapshot layout contains a symlink.')
    regular(directory / 'manifest.json'); regular(directory / 'READY')
    raw = (directory / 'manifest.json').read_bytes()
    if (directory / 'READY').read_text().strip() != hashlib.sha256(raw).hexdigest():
        raise BundleError('Recovery snapshot readiness marker is invalid.')
    manifest = json.loads(raw)
    if manifest['schema_version'] != 'insflow.recovery-data.v1' or manifest['app_build_sha'] != expected_build:
        raise BundleError('Recovery snapshot belongs to a different application build.')
    if manifest['database']['file'] != 'database.dump' or manifest['media']['directory'] != 'media':
        raise BundleError('Recovery snapshot layout is invalid.')
    database = regular(directory / 'database.dump')
    if database['sha256'] != manifest['database']['sha256'] or database['size'] != manifest['database']['size']:
        raise BundleError('Recovery database checksum is invalid.')
    listed = {}
    for item in manifest['media']['files']:
        name = relative(item['path'])
        if name in listed:
            raise BundleError('Recovery snapshot contains duplicate media paths.')
        listed[name] = item
        candidate = directory / 'media'
        for part in PurePosixPath(name).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise BundleError('Recovery snapshot contains a media symlink.')
        actual = regular(candidate)
        if actual['sha256'] != item['sha256'] or actual['size'] != item['size']:
            raise BundleError('Recovery document checksum is invalid.')
    actual_names = set()
    for path in (directory / 'media').rglob('*'):
        if path.is_symlink():
            raise BundleError('Recovery snapshot contains a media symlink.')
        if path.is_file():
            actual_names.add(path.relative_to(directory / 'media').as_posix())
    if actual_names != set(listed) or not set(manifest['media']['referenced_files']).issubset(listed):
        raise BundleError('Recovery snapshot document inventory is incomplete.')
    if len(listed) != manifest['media']['file_count'] or sum(item['size'] for item in listed.values()) != manifest['media']['total_bytes']:
        raise BundleError('Recovery snapshot totals are invalid.')
    return manifest


def encrypt_payload(payload, destination, age_binary, recipient_file):
    process = subprocess.Popen([str(age_binary), '--encrypt', '-R', str(recipient_file), '-o', str(destination)],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=process.stdin, mode='w|') as archive:
            for path in sorted(payload.iterdir()):
                archive.add(path, arcname=path.name)
        process.stdin.close()
        if process.wait(timeout=300):
            raise BundleError('Recovery encryption failed.')
    finally:
        if not process.stdin.closed:
            try: process.stdin.close()
            except BrokenPipeError: pass
        if process.poll() is None:
            process.kill()
            process.wait()
    with destination.open('rb') as stream:
        if stream.readline(128) != b'age-encryption.org/v1\n':
            raise BundleError('Recovery encryption output is invalid.')


def create_bundle(project_dir, state_dir, age_binary, recipient_file):
    """Return this exact finished ZIP; failures never select or replace old files."""
    snapshot_path = None
    partial = None
    try:
        os.umask(0o077)
        project, state = Path(project_dir).resolve(), Path(state_dir).resolve()
        age, recipients = Path(age_binary).resolve(), Path(recipient_file).resolve()
        if not age.is_file() or not os.access(age, os.X_OK):
            raise BundleError('Recovery encryption executable is unavailable.')
        recipient_lines = [line.strip() for line in recipients.read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
        if not recipient_lines or any(not re.fullmatch(r'age1[0-9a-z]{58}', line) for line in recipient_lines):
            raise BundleError('Recovery public recipients file is invalid.')
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        if state.is_symlink() or state.stat().st_mode & 0o077:
            raise BundleError('Recovery state directory must be private.')
        exports = state / 'exports'; exports.mkdir(mode=0o700, exist_ok=True)
        if exports.is_symlink() or exports.stat().st_mode & 0o077:
            raise BundleError('Recovery exports directory must be private.')
        before = runtime(); commit = source_state(project)
        if commit != before['build_sha']:
            raise BundleError('Application and source release do not match.')
        if any(state.is_relative_to(Path(mount['Source'])) for mount in before['mounts']):
            raise BundleError('Private recovery staging must be outside application volumes.')
        initial_config = configuration_state(project); cron = insflow_cron()
        backup_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '_' + uuid4().hex
        with tempfile.TemporaryDirectory(prefix='build-', dir=state) as temporary:
            work = Path(temporary); payload = work / 'payload'; payload.mkdir()
            config = payload / 'config'; config.mkdir()
            tls_hash = tls_archive(config / 'tls.tar')
            response = json.loads(run(['docker', 'exec', WEB, 'python', 'manage.py', 'create_recovery_snapshot', '--json']))
            candidate = PurePosixPath(response['snapshot_path'])
            if response.get('status') != 'ready' or candidate.parent != SNAPSHOT_PARENT or not SNAPSHOT_NAME.fullmatch(candidate.name) or response.get('manifest_path') != str(candidate / 'manifest.json'):
                raise BundleError('Recovery producer returned an invalid snapshot path.')
            snapshot_path = str(candidate)
            copied = work / 'snapshot'; run(['docker', 'cp', WEB + ':' + snapshot_path, str(copied)])
            data = verify_snapshot(copied, before['build_sha'])
            shutil.move(copied / 'database.dump', payload / 'database.dump')
            shutil.move(copied / 'media', payload / 'media')
            shutil.copy2(copied / 'manifest.json', payload / 'snapshot_manifest.json')
            for name, path in config_inputs(project).items():
                shutil.copy2(path, config / name)
                copied_info = regular(config / name)
                if any(copied_info[key] != initial_config[name][key] for key in ('sha256', 'size', 'mode')):
                    raise BundleError('Recovery configuration changed during copying.')
            (config / 'insflow.crontab').write_bytes(cron)
            (config / 'runtime.json').write_text(json.dumps(before, ensure_ascii=False, indent=2))
            with (payload / 'source.tar').open('wb') as target:
                run(['git', '-C', str(project), 'archive', '--format=tar', commit], target)
            inventory = {path.relative_to(payload).as_posix(): regular(path) for path in sorted(payload.rglob('*')) if path.is_file()}
            manifest = {'schema_version': 'insflow.recovery-bundle.v1', 'backup_id': backup_id,
                        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'app_build_sha': commit,
                        'files': inventory, 'media_files': data['media']['file_count'],
                        'config_source_metadata': initial_config, 'encryption': 'age-X25519'}
            (payload / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            encrypted = work / 'payload.tar.age'
            encrypt_payload(payload, encrypted, age, recipients)
            if runtime() != before or source_state(project) != commit or configuration_state(project) != initial_config or insflow_cron() != cron or tls_archive(work / 'tls-check.tar') != tls_hash:
                raise BundleError('Recovery sources changed before publication.')
            if encrypted.stat().st_size > MAX_ARCHIVE_BYTES:
                raise BundleError('Encrypted recovery bundle exceeds the delivery size limit.')
            final = exports / ('insflow_recovery_' + backup_id + '.zip')
            partial = final.with_suffix('.zip.part')
            with partial.open('xb') as target:
                with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
                    archive.write(encrypted, 'payload.tar.age'); archive.writestr('README.txt', README)
                target.flush(); os.fsync(target.fileno())
            if partial.stat().st_size > MAX_ARCHIVE_BYTES:
                raise BundleError('Encrypted recovery ZIP exceeds the delivery size limit.')
            archive_digest, archive_size = sha256(partial), partial.stat().st_size
            run(['docker', 'exec', WEB, 'rm', '-rf', '--', snapshot_path]); snapshot_path = None
            os.replace(partial, final); partial = None
            return {'status': 'ready', 'backup_id': backup_id, 'archive_path': str(final),
                    'sha256': archive_digest, 'size': archive_size,
                    'created_at_utc': manifest['created_at_utc'], 'media_files': manifest['media_files']}
    except BundleError:
        raise
    except Exception:
        raise BundleError('Recovery bundle creation failed before publication.') from None
    finally:
        if partial is not None:
            try: partial.unlink(missing_ok=True)
            except OSError: pass
        if snapshot_path is not None:
            try: run(['docker', 'exec', WEB, 'rm', '-rf', '--', snapshot_path])
            except BundleError: pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument('--state-dir', default=str(Path.home() / '.local/state/insflow-recovery'))
    parser.add_argument('--age-binary', required=True); parser.add_argument('--recipient-file', required=True)
    args = parser.parse_args(argv)
    try:
        result = create_bundle(args.project_dir, args.state_dir, args.age_binary, args.recipient_file)
    except BundleError as error:
        print(json.dumps({'status': 'error', 'error': str(error)})); return 1
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    raise SystemExit(main())

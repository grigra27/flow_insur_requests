"""Create a verified PostgreSQL/media snapshot without choosing its destination.

The exported PostgreSQL snapshot ties table counts and FileField references to
the dump. Media is copied through no-follow file descriptors, and the complete
source tree must remain unchanged during copying. A directory becomes visible
as a recovery snapshot only after its dump and every required file are checked.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

import django
from django.apps import apps
from django.conf import settings
from django.db import connection, models, transaction


SCHEMA_VERSION = 'insflow.recovery-data.v1'
COPY_CHUNK_BYTES = 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 300


class RecoverySnapshotError(RuntimeError):
    """A snapshot could not be safely completed; no final directory is ready."""


def _private_write(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(COPY_CHUNK_BYTES), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_reference(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise RecoverySnapshotError('Unsafe media reference in the database.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise RecoverySnapshotError('Unsafe media reference in the database.')
    return path.as_posix()


def _file_references(cursor, table_names):
    """Read all registered FileFields with the same cursor/exporter transaction."""
    references = set()
    seen = set()
    quote = connection.ops.quote_name
    for model in apps.get_models():
        table = model._meta.db_table
        if table not in table_names:
            continue
        for field in model._meta.concrete_fields:
            key = (table, field.column)
            if not isinstance(field, models.FileField) or key in seen:
                continue
            seen.add(key)
            column = quote(field.column)
            cursor.execute(
                f'SELECT {column} FROM {quote(table)} '
                f'WHERE {column} IS NOT NULL AND {column} <> %s',
                [''],
            )
            references.update(_safe_reference(row[0]) for row in cursor.fetchall())
    return references


def _database_state(cursor):
    tables = sorted(connection.introspection.table_names(cursor=cursor))
    table_counts = {}
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM {connection.ops.quote_name(table)}')
        table_counts[table] = int(cursor.fetchone()[0])
    return table_counts, _file_references(cursor, set(tables))


def _run_process(arguments, *, env=None):
    try:
        result = subprocess.run(
            arguments, env=env, capture_output=True, timeout=PROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        # Driver errors may contain connection details. Keep them out of logs.
        raise RecoverySnapshotError('PostgreSQL backup utility could not complete.') from None
    if result.returncode:
        raise RecoverySnapshotError(
            f'PostgreSQL backup utility failed with exit code {result.returncode}.'
        )


def _dump_database(path, snapshot_id):
    executable = shutil.which('pg_dump')
    if not executable:
        raise RecoverySnapshotError('pg_dump is required for a recovery snapshot.')
    configuration = connection.settings_dict
    environment = os.environ.copy()
    # Database identity and its password are passed only via the environment.
    environment.update({
        'PGDATABASE': str(configuration.get('NAME') or ''),
        'PGHOST': str(configuration.get('HOST') or 'localhost'),
        'PGPORT': str(configuration.get('PORT') or '5432'),
        'PGUSER': str(configuration.get('USER') or ''),
        'PGPASSWORD': str(configuration.get('PASSWORD') or ''),
    })
    environment['PGOPTIONS'] = (
        environment.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on'
    ).strip()
    _private_write(path, b'')
    _run_process([
        executable, '--format=custom', '--file', str(path),
        '--snapshot', snapshot_id, '--no-password',
    ], env=environment)


def _validate_dump(path):
    if path.stat().st_size <= 5:
        raise RecoverySnapshotError('Recovery database archive is empty or incomplete.')
    with path.open('rb') as stream:
        if stream.read(5) != b'PGDMP':
            raise RecoverySnapshotError('Recovery database archive has an invalid header.')
    executable = shutil.which('pg_restore')
    if not executable:
        raise RecoverySnapshotError('pg_restore is required to validate a recovery snapshot.')
    environment = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    # No --dbname: parse the entire archive to SQL without connecting to any DB.
    _run_process([executable, '--file=/dev/null', str(path)], env=environment)


def _signature(information):
    return (
        information.st_dev, information.st_ino, information.st_size,
        information.st_mtime_ns, information.st_ctime_ns,
    )


def _directory_flags():
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _scan_media(root_descriptor):
    files = {}

    def walk(directory_descriptor, prefix):
        with os.scandir(directory_descriptor) as iterator:
            names = sorted(entry.name for entry in iterator)
        for name in names:
            relative = prefix + (name,)
            information = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
            if stat.S_ISLNK(information.st_mode):
                raise RecoverySnapshotError('Media contains a symbolic link; snapshot cancelled.')
            if stat.S_ISDIR(information.st_mode):
                child = os.open(name, _directory_flags(), dir_fd=directory_descriptor)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (information.st_dev, information.st_ino):
                        raise RecoverySnapshotError('Media directory changed during snapshot.')
                    walk(child, relative)
                finally:
                    os.close(child)
            elif stat.S_ISREG(information.st_mode):
                files[PurePosixPath(*relative).as_posix()] = _signature(information)
            else:
                raise RecoverySnapshotError('Media contains an unsupported file type.')

    walk(root_descriptor, ())
    return files


def _open_media_file(root_descriptor, relative):
    """Anchor every component to an opened directory; never follow symlinks."""
    directories = []
    current = root_descriptor
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current = os.open(part, _directory_flags(), dir_fd=current)
            directories.append(current)
        # A regular file can be replaced by a FIFO between scanning and open.
        # Nonblocking open lets the following fstat reject it without hanging.
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
    finally:
        for descriptor in reversed(directories):
            os.close(descriptor)


def _copy_file_data(source, destination):
    digest = hashlib.sha256()
    copied = 0
    for chunk in iter(lambda: source.read(COPY_CHUNK_BYTES), b''):
        destination.write(chunk)
        digest.update(chunk)
        copied += len(chunk)
    destination.flush()
    os.fsync(destination.fileno())
    return copied, digest.hexdigest()


def _copy_media(media_root, destination, references):
    root_descriptor = os.open(media_root, _directory_flags())
    try:
        root_identity = os.fstat(root_descriptor)
        original = _scan_media(root_descriptor)
        if not references.issubset(original):
            raise RecoverySnapshotError('A database-referenced media file is missing.')
        destination.mkdir(mode=0o700)
        manifest = []
        for relative, expected in sorted(original.items()):
            parts = PurePosixPath(relative).parts
            parent = destination
            for part in parts[:-1]:
                parent = parent / part
                parent.mkdir(mode=0o700, exist_ok=True)
            path = parent / parts[-1]
            descriptor = _open_media_file(root_descriptor, relative)
            with os.fdopen(descriptor, 'rb') as source:
                information = os.fstat(source.fileno())
                if not stat.S_ISREG(information.st_mode) or _signature(information) != expected:
                    raise RecoverySnapshotError('Media file changed before copying.')
                target = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(target, 'wb') as output:
                    size, digest = _copy_file_data(source, output)
                if _signature(os.fstat(source.fileno())) != expected or size != expected[2]:
                    raise RecoverySnapshotError('Media file changed while copying.')
            manifest.append({'path': relative, 'size': size, 'sha256': digest})
        if _scan_media(root_descriptor) != original:
            raise RecoverySnapshotError('Media tree changed while copying.')
        current_root = os.stat(media_root, follow_symlinks=False)
        if (current_root.st_dev, current_root.st_ino) != (root_identity.st_dev, root_identity.st_ino):
            raise RecoverySnapshotError('Media root changed while copying.')
        return manifest
    finally:
        os.close(root_descriptor)


def create_recovery_snapshot(output_dir, *, media_root=None):
    """Return the exact ready directory, or raise without publishing an archive."""
    if connection.vendor != 'postgresql':
        raise RecoverySnapshotError('Recovery snapshots require PostgreSQL.')
    if connection.in_atomic_block:
        raise RecoverySnapshotError('Recovery snapshots require a new standalone transaction.')
    media = Path(media_root if media_root is not None else settings.MEDIA_ROOT).absolute()
    output = Path(output_dir).absolute()
    if output.resolve().is_relative_to(media.resolve()):
        raise RecoverySnapshotError('Recovery snapshots must be stored outside the media root.')
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.recovery-', suffix='.part', dir=output))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    final = output / f'recovery_{stamp}_{uuid4().hex}'
    try:
        with transaction.atomic(using=connection.alias):
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                cursor.execute('SELECT pg_export_snapshot()')
                snapshot_id = cursor.fetchone()[0]
                if not isinstance(snapshot_id, str) or not snapshot_id:
                    raise RecoverySnapshotError('PostgreSQL did not export a snapshot.')
                table_counts, references = _database_state(cursor)
                database = staging / 'database.dump'
                _dump_database(database, snapshot_id)
                media_files = _copy_media(media, staging / 'media', references)
        _validate_dump(database)
        manifest = {
            'schema_version': SCHEMA_VERSION,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'app_build_sha': os.environ.get('APP_BUILD_SHA', 'unknown'),
            'django_version': django.get_version(),
            'database': {
                'file': 'database.dump', 'size': database.stat().st_size,
                'sha256': _sha256_file(database), 'snapshot_id': snapshot_id,
                'table_counts': table_counts,
                'sequence_values_source': 'database.dump',
            },
            'media': {
                'directory': 'media', 'file_count': len(media_files),
                'total_bytes': sum(item['size'] for item in media_files),
                'referenced_files': sorted(references), 'files': media_files,
            },
        }
        encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        _private_write(staging / 'manifest.json', encoded)
        _private_write(staging / 'READY', (hashlib.sha256(encoded).hexdigest() + '\n').encode('ascii'))
        os.rename(staging, final)
        return str(final)
    except RecoverySnapshotError:
        raise
    except Exception:
        raise RecoverySnapshotError('Recovery snapshot failed before publication.') from None
    finally:
        if staging.exists():
            shutil.rmtree(staging)

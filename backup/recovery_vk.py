"""Private receipts and VK transport for owner-encrypted recovery bundles."""
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo
import zipfile

import requests
from django.conf import settings

from .management.commands.send_backup_to_vk import (
    Command as DatabaseSender, RetryableUploadError, VK_FILE_SIZE_LIMIT,
)

AGE_HEADER = re.compile(
    rb'\Aage-encryption.org/v1\n(?:-> X25519 [A-Za-z0-9+/]{43}\n[A-Za-z0-9+/]{43}\n)+'
    rb'--- [A-Za-z0-9+/]{43}\n'
)
RETRY_DEFAULTS = dict(upload_attempts=4, retry_base_delay=15.0,
                      retry_max_delay=600.0, total_timeout=900.0)


class RecoveryError(Exception):
    """Contains only a fixed diagnostic code, never API responses or URLs."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_archive(path, expected_sha256):
    try:
        if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
            raise RecoveryError('expected_sha256_required')
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise RecoveryError('archive_not_regular_file')
        size = path.stat().st_size
        if not 0 < size <= VK_FILE_SIZE_LIMIT:
            raise RecoveryError('archive_size_limit')
        digest = sha256_file(path)
        if digest != expected_sha256.lower():
            raise RecoveryError('archive_sha256_mismatch')
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != 2 or {entry.filename for entry in entries} != {'payload.tar.age', 'README.txt'}:
                raise RecoveryError('archive_entries_invalid')
            if any(entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16)
                   or entry.flag_bits & 1 for entry in entries):
                raise RecoveryError('archive_entries_invalid')
            if archive.getinfo('README.txt').file_size > 65536 or not 32 < archive.getinfo('payload.tar.age').file_size <= VK_FILE_SIZE_LIMIT:
                raise RecoveryError('archive_member_size_limit')
            with archive.open('payload.tar.age') as payload:
                prefix = payload.read(4096)
            header = AGE_HEADER.match(prefix)
            if not header or archive.getinfo('payload.tar.age').file_size < header.end() + 32:
                raise RecoveryError('age_header_invalid')
            if archive.testzip() is not None:
                raise RecoveryError('archive_crc_invalid')
        return path, size, digest
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError('archive_invalid') from None


def atomic_json(path, payload):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.part', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def random_id(seed):
    return int.from_bytes(hashlib.sha256(('insflow-recovery:' + seed).encode()).digest()[:4],
                          'big', signed=True) or 1


@contextmanager
def quiet_http_logs():
    # urllib3 DEBUG output can include the signed bearer URL of an upload node.
    loggers = [logging.getLogger(name) for name in
               ('urllib3.connectionpool', 'urllib3.util.retry', 'requests.packages.urllib3.connectionpool')]
    previous = [logger.disabled for logger in loggers]
    try:
        for logger in loggers:
            logger.disabled = True
        yield
    finally:
        for logger, disabled in zip(loggers, previous):
            logger.disabled = disabled


def safe_error(error):
    if isinstance(error, RecoveryError):
        return str(error)
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    if type(status) is int and 100 <= status <= 599:
        return 'HTTP ' + str(status)
    match = re.search(r'\bHTTP ([1-5]\d{2})\b', str(error))
    if match:
        return 'HTTP ' + match.group(1)
    match = re.search(r'\bcode=(\d{1,6})\b', str(error))
    return 'VK code ' + match.group(1) if match else 'transport_failed'


class RecoveryVK(DatabaseSender):
    def __init__(self, options=None):
        super().__init__()
        self.options = dict(RETRY_DEFAULTS, **(options or {}))
        if any(not math.isfinite(float(self.options[key])) or float(self.options[key]) < 0
               for key in RETRY_DEFAULTS):
            raise RecoveryError('retry_options_invalid')
        self._deadline = time.monotonic() + self.options['total_timeout']
        self.token = getattr(settings, 'VK_BACKUP_TOKEN', '') or ''
        self.peer = str(getattr(settings, 'VK_BACKUP_PEER_ID', '') or '')
        if not self.token or not re.fullmatch(r'-?\d+', self.peer):
            raise RecoveryError('vk_configuration_missing')

    def _vk_call(self, method, token, params=None, timeout=60):
        if method not in {'docs.getMessagesUploadServer', 'docs.save', 'docs.getById', 'messages.send'}:
            raise RecoveryError('vk_method_not_allowed')
        try:
            with quiet_http_logs():
                result = super()._vk_call(method, token, params, timeout=max(1, min(timeout, self._remaining_time())))
            if method == 'docs.getMessagesUploadServer':
                parts = urlsplit(result.get('upload_url', '')) if isinstance(result, dict) else None
                if not parts or parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
                    raise RecoveryError('upload_requires_https')
            return result
        except Exception as error:
            raise RecoveryError('vk_call_failed:' + method + ':' + safe_error(error)) from None

    def _upload_once(self, file_path, token, peer_id):
        try:
            validate_archive(file_path, self.archive_sha256)
            with quiet_http_logs():
                return super()._upload_once(file_path, token, peer_id)
        except RetryableUploadError as error:
            raise RetryableUploadError(safe_error(error)) from None
        except Exception as error:
            raise RecoveryError(safe_error(error)) from None

    def notify_failure(self, code, seed=None):
        if code not in {'snapshot', 'bundle', 'encryption', 'upload'}:
            raise RecoveryError('failure_code_invalid')
        date = datetime.now(timezone.utc).date().isoformat()
        self._vk_call('messages.send', self.token, {
            'peer_id': self.peer, 'random_id': random_id('failure:' + (seed or date) + ':' + code),
            'message': '⚠️ Полная зашифрованная копия InsFlow не доставлена. '
                       'Этап: ' + {'snapshot': 'снимок данных', 'bundle': 'сборка архива',
                                  'encryption': 'шифрование', 'upload': 'передача в VK'}[code] + '. Требуется проверить состояние резервирования. '
                       'Прежние копии не удалялись.',
        })

    def send(self, archive, expected_sha256, receipt_file, no_notify=False):
        path, size, digest = validate_archive(archive, expected_sha256)
        receipt_file = Path(receipt_file)
        if not receipt_file.parent.is_dir() or receipt_file.is_symlink():
            raise RecoveryError('receipt_path_invalid')
        if receipt_file.exists():
            receipt = read_receipt(receipt_file)
            if receipt['sha256'] != digest or receipt['size'] != size or receipt['archive_name'] != path.name:
                raise RecoveryError('receipt_conflict')
            return {'status': 'already_sent', 'receipt_file': str(receipt_file), 'sha256': digest, 'bytes': size}
        self.archive_sha256 = digest
        try:
            uploaded = self._upload_with_retry(str(path), self.token, self.peer, self.options)
            saved = self._vk_call('docs.save', self.token, {'file': uploaded['file'], 'title': path.name})
            document = saved.get('doc') if isinstance(saved, dict) else saved[0] if isinstance(saved, list) and saved else None
            document = checked_document(document)
            attachment = 'doc{owner_id}_{id}'.format(**document)
            if document['access_key']:
                attachment += '_' + document['access_key']
            moment = datetime.now(timezone.utc)
            local_moment = moment.astimezone(ZoneInfo('Europe/Moscow'))
            message_id = self._vk_call('messages.send', self.token, {
                'peer_id': self.peer, 'random_id': random_id(digest), 'attachment': attachment,
                'message': '📦 Полная зашифрованная копия InsFlow: база данных, документы и настройки.\n'
                           + local_moment.strftime('%d.%m.%Y %H:%M МСК') + f' · {size} байт.\n'
                           + f'SHA-256: {digest}\n'
                           'Для восстановления нужен отдельный ключ владельца; в архиве и на сервере его нет.',
            })
            if type(message_id) is not int or message_id <= 0:
                raise RecoveryError('message_response_invalid')
        except Exception as error:
            if not no_notify:
                try:
                    self.notify_failure('upload', digest)
                except Exception:
                    pass
            raise RecoveryError(safe_error(error)) from None
        receipt = dict(schema_version=1, archive_name=path.name, sha256=digest, size=size,
                       sent_utc=moment.isoformat(), document=document, message_id=message_id)
        try:
            atomic_json(receipt_file, receipt)
        except Exception:
            raise RecoveryError('receipt_write_failed') from None
        return {'status': 'sent', 'receipt_file': str(receipt_file), 'sha256': digest, 'bytes': size}

    def download(self, receipt_file, output_file):
        receipt = read_receipt(receipt_file)
        output = Path(output_file)
        if not output.parent.is_dir() or output.is_symlink() or output.exists():
            raise RecoveryError('output_path_must_be_new')
        document = receipt['document']
        identifier = '{owner_id}_{id}'.format(**document)
        if document['access_key']:
            identifier += '_' + document['access_key']
        found = self._vk_call('docs.getById', self.token, {'docs': identifier})
        if not isinstance(found, list) or len(found) != 1:
            raise RecoveryError('document_metadata_invalid')
        actual = checked_document(found[0])
        if any(actual[key] != document[key] for key in ('owner_id', 'id')) or found[0].get('size') != receipt['size']:
            raise RecoveryError('document_metadata_mismatch')
        descriptor, temporary = tempfile.mkstemp(prefix='.' + output.name + '.', suffix='.part', dir=output.parent)
        response = None
        try:
            url = found[0].get('url', '')
            with quiet_http_logs():
                for redirect in range(6):
                    parts = urlsplit(url)
                    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
                        raise RecoveryError('download_requires_https')
                    if self._remaining_time() <= 0:
                        raise RecoveryError('download_timeout')
                    response = requests.get(url, stream=True, allow_redirects=False,
                                            timeout=(10, max(1, min(60, self._remaining_time()))))
                    if response.status_code not in (301, 302, 303, 307, 308):
                        response.raise_for_status()
                        break
                    next_url = urljoin(url, response.headers.get('Location', ''))
                    response.close()
                    response = None
                    url = next_url
                else:
                    raise RecoveryError('download_redirect_limit')
                digest, received = hashlib.sha256(), 0
                with os.fdopen(descriptor, 'wb') as destination:
                    descriptor = None
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if self._remaining_time() <= 0:
                            raise RecoveryError('download_timeout')
                        received += len(block)
                        if received > receipt['size']:
                            raise RecoveryError('download_size_mismatch')
                        digest.update(block)
                        destination.write(block)
                    destination.flush()
                    os.fsync(destination.fileno())
            if received != receipt['size'] or digest.hexdigest() != receipt['sha256']:
                raise RecoveryError('download_hash_or_size_mismatch')
            validate_archive(temporary, receipt['sha256'])
            os.chmod(temporary, 0o600)
            os.replace(temporary, output)
        except Exception as error:
            raise RecoveryError(safe_error(error)) from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if response is not None:
                response.close()
            Path(temporary).unlink(missing_ok=True)
        return {'status': 'downloaded', 'output_file': str(output), 'sha256': receipt['sha256'], 'bytes': receipt['size']}


def checked_document(document):
    if not isinstance(document, dict) or type(document.get('owner_id')) is not int or not document['owner_id'] or type(document.get('id')) is not int or document['id'] <= 0:
        raise RecoveryError('document_metadata_invalid')
    access = document.get('access_key', '')
    if not isinstance(access, str) or not re.fullmatch(r'[A-Za-z0-9_-]{0,512}', access):
        raise RecoveryError('document_access_key_invalid')
    return {key: document[key] for key in ('owner_id', 'id')} | {'access_key': access}


def read_receipt(path):
    try:
        path = Path(path)
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RecoveryError('receipt_not_private')
        receipt = json.loads(path.read_text())
        if receipt.get('schema_version') != 1 or not re.fullmatch(r'[0-9a-f]{64}', receipt.get('sha256', '')) or type(receipt.get('size')) is not int or not 0 < receipt['size'] <= VK_FILE_SIZE_LIMIT:
            raise RecoveryError('receipt_invalid')
        if not isinstance(receipt.get('archive_name'), str) or type(receipt.get('message_id')) is not int or receipt['message_id'] <= 0:
            raise RecoveryError('receipt_invalid')
        receipt['document'] = checked_document(receipt['document'])
        return receipt
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError('receipt_invalid') from None

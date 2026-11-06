#!/usr/bin/env python3
"""Open an InsFlow password backup on macOS without exposing its password."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime
from uuid import uuid4
import zipfile

if __package__:
    from .recovery_age import AgeProcessError, run_age_with_password
else:
    from recovery_age import AgeProcessError, run_age_with_password

MAX_ARCHIVE = 190 * 1024 * 1024
MAX_TAR = 256 * 1024 * 1024


class OpenBackupError(Exception):
    """A fixed user-facing message, never a password, filename or tool output."""


class Cancelled(Exception):
    pass


def applescript(source):
    result = subprocess.run(['osascript', '-e', source], capture_output=True)
    if result.returncode:
        raise Cancelled()
    return result.stdout.decode('utf-8').removesuffix('\n')


def message(text):
    applescript('display dialog ' + json.dumps(text, ensure_ascii=False)
                + ' with title "InsFlow — открыть бэкап" buttons {"ОК"} default button 1')


def choose_archive():
    return Path(applescript('POSIX path of (choose file with prompt '
                           '"Выберите ZIP-копию InsFlow, скачанную из VK")'))


def choose_folder():
    return Path(applescript('POSIX path of (choose folder with prompt '
                           '"Выберите папку для открытой резервной копии")'))


def ask_password():
    return applescript('text returned of (display dialog '
                       '"Введите пароль резервной копии InsFlow." '
                       'with title "InsFlow — пароль копии" default answer "" '
                       'with hidden answer buttons {"Отмена", "Открыть"} '
                       'default button "Открыть" cancel button "Отмена")')


def extract_ciphertext(archive_path, destination):
    info = archive_path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ARCHIVE:
        raise OpenBackupError('Выберите обычный ZIP-файл резервной копии InsFlow.')
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if (len(entries) != 2 or {x.filename for x in entries}
                    != {'payload.tar.age', 'README.txt'}
                    or any(x.is_dir() or stat.S_ISLNK(x.external_attr >> 16)
                           or x.flag_bits & 1 for x in entries)
                    or archive.getinfo('README.txt').file_size > 65536
                    or not 32 < archive.getinfo('payload.tar.age').file_size <= MAX_ARCHIVE):
                raise OpenBackupError('Формат выбранной копии не поддерживается.')
            with archive.open('payload.tar.age') as source, destination.open('xb') as target:
                prefix = source.read(4096)
                if prefix.startswith(b'age-encryption.org/v1\n-> X25519 '):
                    raise OpenBackupError('Это прежняя копия с ключом, созданная до перехода '
                                          'на пароль. Для неё сохранён старый ключ; '
                                          'см. инструкцию восстановления.')
                if not re.match(rb'\Aage-encryption.org/v1\n-> scrypt [A-Za-z0-9+/]{22} '
                                rb'(?:[1-9]|1[0-9]|20)\n', prefix):
                    raise OpenBackupError('Выбранный файл не является парольной копией InsFlow.')
                target.write(prefix)
                shutil.copyfileobj(source, target, 1024 * 1024)
            if archive.testzip() is not None:
                raise OpenBackupError('Контрольная сумма ZIP не совпала. Скачайте копию заново.')
    except OpenBackupError:
        raise
    except Exception:
        raise OpenBackupError('Не удалось прочитать ZIP. Возможно, файл повреждён.') from None


def safe_name(value):
    if not isinstance(value, str) or not value:
        raise OpenBackupError('В копии обнаружен небезопасный путь.')
    path = PurePosixPath(value)
    if (path.is_absolute()
            or '..' in path.parts or '\\' in value or '\x00' in value
            or path.as_posix() != value.rstrip('/')):
        raise OpenBackupError('В копии обнаружен небезопасный путь.')
    return path.as_posix()


def validate_tar(path):
    """Validate exact names as strings; never extract Linux media onto a Mac."""
    if not 0 < path.stat().st_size <= MAX_TAR:
        raise OpenBackupError('Неверный размер открытой копии.')
    try:
        with tarfile.open(path) as archive:
            members = {}
            total = 0
            for member in archive:
                name = safe_name(member.name)
                if (name in members or len(members) >= 100000
                        or not (member.isdir() or member.type in (tarfile.REGTYPE, tarfile.AREGTYPE))
                        or getattr(member, 'sparse', None)):
                    raise OpenBackupError('В копии обнаружена неподдерживаемая запись.')
                total += member.size
                if total > MAX_TAR:
                    raise OpenBackupError('Размер содержимого копии превышает допустимый.')
                members[name] = member
            metadata = members.get('manifest.json')
            if not metadata or not metadata.isfile() or metadata.size > 8 * 1024 * 1024:
                raise OpenBackupError('В копии отсутствует список контрольных сумм.')
            manifest = json.load(archive.extractfile(metadata))
            if manifest.get('schema_version') != 'insflow.recovery-bundle.v1':
                raise OpenBackupError('Версия формата копии не поддерживается.')
            actual = {name for name, member in members.items()
                      if member.isfile() and name != 'manifest.json'}
            expected = manifest['files']
            required = {'database.dump', 'snapshot_manifest.json', 'source.tar',
                        'config/.env', 'config/docker-compose.yml', 'config/nginx.conf',
                        'config/tls.tar', 'config/runtime.json'}
            if actual != set(expected) or not required.issubset(actual):
                raise OpenBackupError('Содержимое копии не совпало со списком файлов.')
            for name, item in expected.items():
                if safe_name(name) != name or members[name].size != item['size']:
                    raise OpenBackupError('Размер одного из файлов копии не совпал.')
                digest = hashlib.sha256()
                with archive.extractfile(members[name]) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(block)
                if digest.hexdigest() != item['sha256']:
                    raise OpenBackupError('Контрольная сумма одного из файлов не совпала.')
            return {'backup_id': manifest['backup_id'], 'app_build_sha': manifest['app_build_sha'],
                    'verified_files': len(expected), 'media_files': manifest['media_files']}
    except OpenBackupError:
        raise
    except Exception:
        raise OpenBackupError('Не удалось проверить содержимое копии.') from None


def open_backup(archive_path, output_parent, password, age_binary):
    """No UI here: the same operation can be verified without recording a secret."""
    archive_path, output_parent, age_binary = map(Path, (archive_path, output_parent, age_binary))
    if (not age_binary.is_file() or not os.access(age_binary, os.X_OK)
            or not output_parent.is_dir() or not password
            or any(ord(char) < 32 or ord(char) == 127 for char in password)):
        raise OpenBackupError('Не удалось подготовить открытие копии.')
    output = output_parent / ('InsFlow-восстановление-' + datetime.now().strftime('%Y%m%d-%H%M%S')
                              + '-' + uuid4().hex[:6])
    output.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix='.open-', dir=output) as private:
            cipher = Path(private) / 'payload.tar.age'
            plain = Path(private) / 'payload.tar.part'
            extract_ciphertext(archive_path, cipher)
            try:
                run_age_with_password([str(age_binary), '--decrypt', '--output', str(plain),
                                       str(cipher)], password, expected_prompts=1, timeout=600)
            except AgeProcessError:
                raise OpenBackupError('Пароль не подошёл либо копия повреждена. '
                                      'Проверьте пароль и скачанный файл.') from None
            report = validate_tar(plain)
            plain.chmod(0o600)
            plain.rename(output / 'payload.tar')
        text = ('Копия InsFlow открыта и проверена.\n'
                'Проверено файлов: {verified_files}. Документов: {media_files}.\n'
                'Релиз: {app_build_sha}.\n\n'
                'payload.tar содержит БД, документы, настройки и исходники.\n'
                'Распаковывать документы нужно на Linux или регистрозависимой файловой системе.\n'
                'На обычном диске Mac имена, различающиеся регистром, могут совпасть.\n'
                'В архиве есть секреты проекта: храните открытую копию в закрытом месте.\n').format(**report)
        (output / 'Проверка.txt').write_text(text, encoding='utf-8')
        (output / 'Проверка.txt').chmod(0o600)
        return output, report
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main():
    os.umask(0o077)
    try:
        archive = choose_archive()
        folder = choose_folder()
        password = ask_password()
        bundled = Path(__file__).resolve().parent / 'age'
        age = bundled if bundled.is_file() else Path.home() / '.config/insflow-backup/tools/age'
        output, report = open_backup(archive, folder, password, age)
        password = None
        message('Копия открыта. Проверено файлов: ' + str(report['verified_files'])
                + '.\n\nРезультат: ' + str(output)
                + '\n\npayload.tar предназначен для восстановления на Linux. '
                  'Документы автоматически не распаковывались.')
        subprocess.run(['open', str(output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    except Cancelled:
        return 0
    except OpenBackupError as error:
        try:
            message(str(error))
        except Cancelled:
            pass
        return 1
    except Exception:
        try:
            message('Не удалось открыть копию. Исходный ZIP не изменён.')
        except Cancelled:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

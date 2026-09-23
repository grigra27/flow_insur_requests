"""
Создаёт ежедневный бэкап БД и отправляет файл в VK через сообщество в личное
сообщение пользователю.

Конфигурация в .env:
    VK_BACKUP_TOKEN   — community access token (права messages, docs)
    VK_BACKUP_PEER_ID — peer_id получателя (user_id владельца)
    VK_API_VERSION    — версия API (default 5.199)

Использование:
    python manage.py send_backup_to_vk
    python manage.py send_backup_to_vk --keep 14
    python manage.py send_backup_to_vk --skip-create   # отправить последний из output-dir
    python manage.py send_backup_to_vk --upload-attempts 4 --total-timeout 900

Загрузка файла в VK оборачивается ретраями с экспоненциальным backoff: приёмные
ноды pu.vk.com периодически отвечают 405/502 или {'error': 'not saved'}. Каждая
повторная попытка заново запрашивает docs.getMessagesUploadServer — URL содержит
несущий rhash/_sig и привязан к конкретной ноде, поэтому повтор POST на тот же
url вернул бы ту же ошибку.
"""
import glob
import gzip
import logging
import os
import random
import re
import shutil
import time

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger('backup.send_backup_to_vk')

VK_API_BASE = 'https://api.vk.com/method'
# VK ограничивает документы 200 МБ. Берём 190 МБ как safety threshold.
VK_FILE_SIZE_LIMIT = 190 * 1024 * 1024
UPLOAD_TIMEOUT = 600

# Ответы приёмной ноды, которые имеет смысл повторить.
RETRYABLE_UPLOAD_HTTP = frozenset({405, 408, 425, 429, 500, 502, 503, 504, 507, 509})


class VKError(Exception):
    """Ошибка взаимодействия с VK API."""


class RetryableUploadError(Exception):
    """Транзитный сбой загрузки файла — повторять, заново взяв upload-ноду."""


def _env_number(name, default, cast=int):
    """Числовая настройка из env: пустая или мусорная строка не должна ронять прогон."""
    raw = os.getenv(name, '')
    try:
        return cast(raw) if raw.strip() else default
    except ValueError:
        logger.warning('Некорректное значение %s=%r, беру %r', name, raw, default)
        return default


APP_NAME = 'флоу / заявки'
MONTHS_GENITIVE = (
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
)


def _human_datetime(now=None, with_time=True):
    # Только localtime(): часы контейнера стоят в UTC, naive now() врёт на 3 часа.
    now = now or timezone.localtime()
    date = f'{now.day} {MONTHS_GENITIVE[now.month - 1]}'
    return f'{date}, {now:%H:%M}' if with_time else date


def _human_size(size_bytes):
    value = f'{size_bytes / 1024 / 1024:.1f}'.replace('.', ',')
    if value.endswith(',0'):
        value = value[:-2]
    return f'{value} МБ'


def _humanize_error(exc):
    """Одна понятная строка вместо трейсбека; подробности остаются в логе."""
    text = str(exc)
    attempts = re.search(r'попыток загрузки: (\d+)', text)
    suffix = f', попыток: {attempts.group(1)}' if attempts else ''

    if 'no_free_space' in text:
        return 'в VK закончилось место' + suffix
    if 'not saved' in text:
        return 'VK не сохранил файл' + suffix
    if 'no_file' in text:
        return 'файл не дошёл до VK' + suffix
    http = re.search(r'HTTP (\d{3})', text)
    if http:
        return f'VK отклонил загрузку (HTTP {http.group(1)})' + suffix
    if 'code=15' in text:
        return 'VK не даёт отправлять — проверьте права токена' + suffix
    return text[:200]


class Command(BaseCommand):
    help = (
        'Создать pg_dump бэкап БД и отправить его в VK '
        'через сообщество в личное сообщение пользователю.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default='/app/backups',
            help='Директория для бэкапов (default: /app/backups)',
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=14,
            help='Сколько локальных бэкапов хранить (default: 14)',
        )
        parser.add_argument(
            '--skip-create',
            action='store_true',
            help='Не создавать новый бэкап, отправить последний из output-dir',
        )
        parser.add_argument(
            '--upload-attempts',
            type=int,
            default=_env_number('VK_UPLOAD_ATTEMPTS', 4),
            help='Сколько попыток загрузки файла в VK сделать (default: 4, 1 = ретраев нет)',
        )
        parser.add_argument(
            '--retry-base-delay',
            type=float,
            default=_env_number('VK_RETRY_BASE_DELAY', 15, float),
            help='Базовая задержка backoff в секундах (default: 15)',
        )
        parser.add_argument(
            '--retry-max-delay',
            type=float,
            default=_env_number('VK_RETRY_MAX_DELAY', 600, float),
            help='Потолок одной задержки в секундах (default: 600)',
        )
        parser.add_argument(
            '--total-timeout',
            type=float,
            default=_env_number('VK_RETRY_TOTAL_TIMEOUT', 900, float),
            help='Общий бюджет отправки в секундах (default: 900)',
        )
        parser.add_argument(
            '--no-notify',
            action='store_true',
            help='Не слать в VK уведомление о провале (для ручных прогонов)',
        )

    def handle(self, *args, **options):
        token = getattr(settings, 'VK_BACKUP_TOKEN', '') or ''
        peer_id = str(getattr(settings, 'VK_BACKUP_PEER_ID', '') or '')

        if not token or not peer_id:
            raise CommandError(
                'VK_BACKUP_TOKEN и VK_BACKUP_PEER_ID должны быть заданы в .env'
            )

        output_dir = options['output_dir']
        keep = options['keep']
        os.makedirs(output_dir, exist_ok=True)

        self._deadline = time.monotonic() + options['total_timeout']
        copy_ready = False

        try:
            if not options['skip_create']:
                self._create_backup(output_dir, keep)

            dump_path = self._select_file_to_send(output_dir)
            if not dump_path:
                raise CommandError(f'Не найден ни один бэкап в {output_dir}')
            copy_ready = True

            size = os.path.getsize(dump_path)
            if size > VK_FILE_SIZE_LIMIT:
                raise VKError(
                    f'Файл бэкапа {os.path.basename(dump_path)} '
                    f'({size / 1024 / 1024:.1f} МБ) превышает лимит VK 190 МБ. '
                    f'Нужно переключиться на внешнее хранилище.'
                )

            self._send_to_vk(dump_path, token, peer_id, size, options)
            logger.info(
                'Бэкап %s (%d байт) успешно отправлен в VK',
                dump_path,
                size,
            )
            self.stdout.write(self.style.SUCCESS(
                f'✓ Бэкап отправлен в VK: {os.path.basename(dump_path)} '
                f'({size:,} байт)'
            ))
        except Exception as exc:
            logger.exception('Ошибка отправки бэкапа в VK')
            if not options['no_notify']:
                self._notify_failure(token, peer_id, exc, copy_ready)
            raise CommandError(f'Бэкап не отправлен: {exc}')

    # ----------------------------------------------------------- backup creation

    def _create_backup(self, output_dir, keep):
        """Создаёт pg_dump; если pg_dump недоступен — JSON."""
        try:
            call_command(
                'backup_db',
                '--format', 'pgdump',
                '--output-dir', output_dir,
                '--keep', str(keep),
            )
        except Exception as exc:
            logger.warning(
                'pg_dump не удался (%s), переключаемся на JSON-бэкап',
                exc,
            )
            call_command(
                'backup_db',
                '--format', 'json',
                '--output-dir', output_dir,
                '--keep', str(keep),
            )

    def _select_file_to_send(self, output_dir):
        """Возвращает путь к файлу для отправки.

        Приоритет: свежайший pg_dump → свежайший JSON (gzip-обёртка для экономии).
        """
        pgdumps = sorted(glob.glob(os.path.join(output_dir, 'pgdump_*.dump')))
        if pgdumps:
            return pgdumps[-1]

        jsons = sorted(glob.glob(os.path.join(output_dir, 'backup_*.json')))
        if not jsons:
            return None

        latest = jsons[-1]
        gz_path = latest + '.gz'
        if not os.path.exists(gz_path):
            with open(latest, 'rb') as src, gzip.open(gz_path, 'wb', compresslevel=9) as dst:
                shutil.copyfileobj(src, dst)
        return gz_path

    # ----------------------------------------------------------- VK API

    def _remaining_time(self):
        return self._deadline - time.monotonic()

    def _vk_call(self, method, token, params=None, timeout=60):
        """Вызов метода VK API. Возвращает поле response из ответа."""
        payload = dict(params or {})
        payload['access_token'] = token
        payload['v'] = getattr(settings, 'VK_API_VERSION', '5.199')

        response = requests.post(
            f'{VK_API_BASE}/{method}',
            data=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if 'error' in data:
            err = data['error']
            raise VKError(
                f'VK API error in {method}: '
                f'code={err.get("error_code")} msg={err.get("error_msg")}'
            )
        return data['response']

    def _upload_once(self, file_path, token, peer_id):
        """Один цикл «сервер загрузки → POST файла». Возвращает payload upload.php."""
        # URL несёт rhash/_sig и привязан к конкретной приёмной ноде,
        # поэтому на каждой попытке запрашиваем его заново.
        upload_info = self._vk_call(
            'docs.getMessagesUploadServer',
            token,
            params={'type': 'doc', 'peer_id': peer_id},
            timeout=max(1, min(60, self._remaining_time())),
        )
        upload_url = upload_info['upload_url']

        with open(file_path, 'rb') as f:
            upload_resp = requests.post(
                upload_url,
                files={
                    'file': (
                        os.path.basename(file_path),
                        f,
                        'application/octet-stream',
                    )
                },
                timeout=max(1, min(UPLOAD_TIMEOUT, self._remaining_time())),
            )

        if upload_resp.status_code in RETRYABLE_UPLOAD_HTTP:
            raise RetryableUploadError(
                f'HTTP {upload_resp.status_code} при загрузке на '
                f'{upload_url.split("/upload.php")[0]}'
            )
        # Прочие 4xx — проблема в запросе или токене, повтор не поможет.
        upload_resp.raise_for_status()

        upload_data = upload_resp.json()
        if 'error' in upload_data or 'file' not in upload_data:
            raise RetryableUploadError(f'VK upload error: {upload_data}')
        return upload_data

    def _upload_with_retry(self, file_path, token, peer_id, options):
        attempts = max(1, options['upload_attempts'])
        base = max(0.0, options['retry_base_delay'])
        cap = max(base, options['retry_max_delay'])

        for attempt in range(1, attempts + 1):
            try:
                return self._upload_once(file_path, token, peer_id)
            except RetryableUploadError as exc:
                if attempt == attempts:
                    logger.error(
                        'Загрузка в VK не удалась после %d попыток: %s', attempts, exc
                    )
                    detail = (
                        '' if attempts == 1 else f' (попыток загрузки: {attempts})'
                    )
                    raise RetryableUploadError(f'{exc}{detail}') from exc
                if self._remaining_time() <= 0:
                    logger.error(
                        'Бюджет времени (%s сек) исчерпан после %d попыток: %s',
                        options['total_timeout'], attempt, exc,
                    )
                    raise
                delay = min(cap, base * (2 ** (attempt - 1)))
                delay *= random.uniform(0.8, 1.2)
                delay = min(delay, max(0.0, self._remaining_time()))
                logger.warning(
                    'Попытка %d/%d неудачна (%s); повтор через %.1f сек',
                    attempt, attempts, exc, delay,
                )
                time.sleep(delay)

    def _send_to_vk(self, file_path, token, peer_id, size, options):
        # 1–2. Сервер загрузки + сам файл — с ретраями (см. _upload_with_retry)
        upload_data = self._upload_with_retry(file_path, token, peer_id, options)

        # 3. Сохраняем документ
        save_resp = self._vk_call(
            'docs.save',
            token,
            params={
                'file': upload_data['file'],
                'title': os.path.basename(file_path),
            },
        )

        # docs.save возвращает либо {"type": "doc", "doc": {...}} (5.81+),
        # либо просто список словарей в старых версиях. Поддерживаем оба.
        doc = None
        if isinstance(save_resp, dict) and 'doc' in save_resp:
            doc = save_resp['doc']
        elif isinstance(save_resp, list) and save_resp:
            doc = save_resp[0]
        if not doc or 'id' not in doc or 'owner_id' not in doc:
            raise VKError(f'Неожиданный ответ docs.save: {save_resp}')

        attachment = f"doc{doc['owner_id']}_{doc['id']}"

        # 4. Отправляем сообщение с прикреплённым документом
        message = (
            f'📦 Резервная копия базы «{APP_NAME}» — {_human_datetime()}\n'
            f'{_human_size(size)} · {os.path.basename(file_path)}'
        )
        self._vk_call(
            'messages.send',
            token,
            params={
                'peer_id': peer_id,
                'random_id': int(time.time() * 1000),
                'attachment': attachment,
                'message': message,
            },
        )

    def _notify_failure(self, token, peer_id, error_msg, copy_ready):
        """Best-effort уведомление о провале — ошибки здесь подавляем."""
        if not token or not peer_id:
            return
        try:
            reason = _humanize_error(error_msg)
            if copy_ready:
                body = (
                    f'⚠️ Копия базы «{APP_NAME}» за {_human_datetime(with_time=False)} '
                    f'не дошла в VK\n'
                    f'На сервере цела — под вопросом только внешняя копия.\n'
                    f'Причина: {reason}'
                )
            else:
                body = (
                    f'⚠️ Копия базы «{APP_NAME}» не создана — '
                    f'{_human_datetime(with_time=False)}\n'
                    f'Ни на сервере, ни в VK её нет — нужно разобрать вручную.\n'
                    f'Причина: {reason}'
                )
            self._vk_call(
                'messages.send',
                token,
                params={
                    'peer_id': peer_id,
                    'random_id': int(time.time() * 1000),
                    'message': body,
                },
            )
        except Exception as send_exc:
            logger.error(
                'Не удалось отправить уведомление о провале в VK: %s',
                send_exc,
            )

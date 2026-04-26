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
"""
import glob
import gzip
import logging
import os
import shutil
import time
from datetime import datetime

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('backup.send_backup_to_vk')

VK_API_BASE = 'https://api.vk.com/method'
# VK ограничивает документы 200 МБ. Берём 190 МБ как safety threshold.
VK_FILE_SIZE_LIMIT = 190 * 1024 * 1024


class VKError(Exception):
    """Ошибка взаимодействия с VK API."""


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

        try:
            if not options['skip_create']:
                self._create_backup(output_dir, keep)

            dump_path = self._select_file_to_send(output_dir)
            if not dump_path:
                raise CommandError(f'Не найден ни один бэкап в {output_dir}')

            size = os.path.getsize(dump_path)
            if size > VK_FILE_SIZE_LIMIT:
                raise VKError(
                    f'Файл бэкапа {os.path.basename(dump_path)} '
                    f'({size / 1024 / 1024:.1f} МБ) превышает лимит VK 190 МБ. '
                    f'Нужно переключиться на внешнее хранилище.'
                )

            self._send_to_vk(dump_path, token, peer_id, size)
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
            self._notify_failure(token, peer_id, str(exc))
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

    def _vk_call(self, method, token, params=None):
        """Вызов метода VK API. Возвращает поле response из ответа."""
        payload = dict(params or {})
        payload['access_token'] = token
        payload['v'] = getattr(settings, 'VK_API_VERSION', '5.199')

        response = requests.post(
            f'{VK_API_BASE}/{method}',
            data=payload,
            timeout=60,
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

    def _send_to_vk(self, file_path, token, peer_id, size):
        # 1. Сервер для загрузки документов в личные сообщения
        upload_info = self._vk_call(
            'docs.getMessagesUploadServer',
            token,
            params={'type': 'doc', 'peer_id': peer_id},
        )
        upload_url = upload_info['upload_url']

        # 2. Загружаем сам файл
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
                timeout=600,
            )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        if 'error' in upload_data or 'file' not in upload_data:
            raise VKError(f'VK upload error: {upload_data}')

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
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        message = (
            f'📦 Ежедневный бэкап InsFlow\n'
            f'Дата: {timestamp}\n'
            f'Размер: {size / 1024 / 1024:.2f} МБ\n'
            f'Файл: {os.path.basename(file_path)}'
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

    def _notify_failure(self, token, peer_id, error_msg):
        """Best-effort уведомление о провале — ошибки здесь подавляем."""
        if not token or not peer_id:
            return
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            self._vk_call(
                'messages.send',
                token,
                params={
                    'peer_id': peer_id,
                    'random_id': int(time.time() * 1000),
                    'message': (
                        f'❌ InsFlow: ошибка ежедневного бэкапа\n'
                        f'Дата: {timestamp}\n\n'
                        f'{error_msg[:1000]}'
                    ),
                },
            )
        except Exception as send_exc:
            logger.error(
                'Не удалось отправить уведомление о провале в VK: %s',
                send_exc,
            )

#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# backup-cron-setup.sh
#
# Идемпотентно прописывает в crontab текущего пользователя ежедневную задачу
# отправки бэкапа БД в VK через сообщество.
#
# Запуск из корня проекта:
#   bash scripts/backup-cron-setup.sh
#
# Время по умолчанию — 03:00 по Москве (CRON_TZ добавляется в crontab, если
# его нет). Переопределяется через BACKUP_CRON. Идентификация — через
# маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=cron-common.sh
source "${SCRIPT_DIR}/cron-common.sh"

WRAPPER="${PROJECT_DIR}/scripts/cron-send-backup-to-vk.sh"
MARKER="# insflow-backup-vk"
SCHEDULE="${BACKUP_CRON:-0 3 * * *}"

cron_install_line "$SCHEDULE" "$WRAPPER" "$MARKER"

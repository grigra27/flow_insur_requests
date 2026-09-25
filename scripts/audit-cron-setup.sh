#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# audit-cron-setup.sh
#
# Идемпотентно прописывает в crontab текущего пользователя ежедневную задачу
# чистки журналов django-easy-audit (LoginEvent/CRUDEvent старше 365 дней,
# RequestEvent старше 1 дня).
#
# Запуск из корня проекта:
#   bash scripts/audit-cron-setup.sh
#
# Время по умолчанию — 04:00 (после ежедневного бэкапа в 03:00).
# Часовой пояс — CRON_TZ=Europe/Moscow (добавляется в crontab, если его нет).
# Идентификация — через маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=cron-common.sh
source "${SCRIPT_DIR}/cron-common.sh"

WRAPPER="${PROJECT_DIR}/scripts/cron-purge-audit-log.sh"
MARKER="# insflow-audit-purge"
SCHEDULE="${AUDIT_CRON:-0 4 * * *}"

cron_install_line "$SCHEDULE" "$WRAPPER" "$MARKER"

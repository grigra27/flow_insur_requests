#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# log-rotate-cron-setup.sh
#
# Идемпотентно прописывает в crontab текущего пользователя ежедневную
# ротацию логов приложения (manage.py rotate_logs: файлы > 10 МБ сжимаются
# в .1.gz и обрезаются, хранится 5 архивов).
#
# Запуск из корня проекта:
#   bash scripts/log-rotate-cron-setup.sh
#
# Время по умолчанию — 04:30 по Москве (после чистки аудита в 04:00).
# Переопределяется через LOG_ROTATE_CRON.
# Идентификация — через маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=cron-common.sh
source "${SCRIPT_DIR}/cron-common.sh"

WRAPPER="${PROJECT_DIR}/scripts/cron-rotate-logs.sh"
MARKER="# insflow-log-rotate"
SCHEDULE="${LOG_ROTATE_CRON:-30 4 * * *}"

cron_install_line "$SCHEDULE" "$WRAPPER" "$MARKER"

#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# auto-close-cron-setup.sh
#
# Идемпотентно прописывает в crontab текущего пользователя ежедневную задачу
# автозакрытия зависших сводок (auto_close_stale_summaries).
#
# Запуск из корня проекта:
#   bash scripts/auto-close-cron-setup.sh
#
# Время по умолчанию — 00:10 по Москве. Переопределяется через AUTO_CLOSE_CRON.
# Идентификация — через маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=cron-common.sh
source "${SCRIPT_DIR}/cron-common.sh"

WRAPPER="${PROJECT_DIR}/scripts/cron-auto-close-summaries.sh"
MARKER="# insflow-auto-close"
SCHEDULE="${AUTO_CLOSE_CRON:-10 0 * * *}"

cron_install_line "$SCHEDULE" "$WRAPPER" "$MARKER"

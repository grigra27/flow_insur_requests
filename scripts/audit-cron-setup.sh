#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# audit-cron-setup.sh
#
# Идемпотентно прописывает в crontab текущего пользователя ежедневную задачу
# чистки журналов django-easy-audit (LoginEvent/CRUDEvent старше 90 дней,
# RequestEvent старше 1 дня).
#
# Запуск из корня проекта:
#   bash scripts/audit-cron-setup.sh
#
# Время по умолчанию — 04:00 (после ежедневного бэкапа в 03:00).
# Часовой пояс берётся из CRON_TZ в crontab.
# Идентификация — через маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WRAPPER="${PROJECT_DIR}/scripts/cron-purge-audit-log.sh"
MARKER="# insflow-audit-purge"
SCHEDULE="${AUDIT_CRON:-0 4 * * *}"

mkdir -p "${PROJECT_DIR}/logs"
chmod +x "$WRAPPER"

CRON_LINE="${SCHEDULE} PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin USE_DOCKER=1 ${WRAPPER} ${MARKER}"

existing="$(crontab -l 2>/dev/null || true)"
new_crontab="$(echo "$existing" | grep -v -F "$MARKER" || true)"

if [ -n "$new_crontab" ]; then
    new_crontab="${new_crontab}"$'\n'"${CRON_LINE}"
else
    new_crontab="${CRON_LINE}"
fi

echo "$new_crontab" | crontab -

echo "✅ Cron-задача чистки аудита установлена:"
echo "   Расписание: $SCHEDULE  (CRON_TZ читается из crontab)"
echo "   Скрипт:     $WRAPPER"
echo "   Маркер:     $MARKER"
crontab -l | grep -F "$MARKER" || true

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
# Время по умолчанию — 03:00. Часовой пояс берётся из CRON_TZ в crontab
# (на сервере уже стоит CRON_TZ=Europe/Moscow). Переопределяется через
# BACKUP_CRON. Идентификация — через маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WRAPPER="${PROJECT_DIR}/scripts/cron-send-backup-to-vk.sh"
MARKER="# insflow-backup-vk"
SCHEDULE="${BACKUP_CRON:-0 3 * * *}"

mkdir -p "${PROJECT_DIR}/logs"
chmod +x "$WRAPPER"

# В стиле существующей cron-auto-close-summaries.sh:
# explicit PATH (cron-демон стартует с пустым PATH и не видит docker),
# USE_DOCKER=1 (исполняем команду внутри web-контейнера).
CRON_LINE="${SCHEDULE} PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin USE_DOCKER=1 ${WRAPPER} ${MARKER}"

# Текущий crontab (если его нет — пустая строка, не падаем)
existing="$(crontab -l 2>/dev/null || true)"

# Удаляем все строки с нашим маркером, чтобы переустановка не плодила дубли.
# Прочие строки (CRON_TZ, другие задачи) сохраняются как есть.
new_crontab="$(echo "$existing" | grep -v -F "$MARKER" || true)"

if [ -n "$new_crontab" ]; then
    new_crontab="${new_crontab}"$'\n'"${CRON_LINE}"
else
    new_crontab="${CRON_LINE}"
fi

echo "$new_crontab" | crontab -

echo "✅ Cron-задача установлена:"
echo "   Расписание: $SCHEDULE  (CRON_TZ читается из crontab)"
echo "   Скрипт:     $WRAPPER"
echo "   Маркер:     $MARKER"
crontab -l | grep -F "$MARKER" || true

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
# Время по умолчанию — 03:00 каждый день. Переопределяется через BACKUP_CRON.
# Идентификация через маркер-комментарий в строке crontab.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${PROJECT_DIR}/logs/backup-cron.log"
MARKER="# insflow-backup-vk"
SCHEDULE="${BACKUP_CRON:-0 3 * * *}"

mkdir -p "${PROJECT_DIR}/logs"

# docker compose v2 vs docker-compose v1 — пробуем v2, фоллбек на v1
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

CRON_LINE="${SCHEDULE} cd ${PROJECT_DIR} && ${COMPOSE_CMD} -f docker-compose.yml exec -T web python manage.py send_backup_to_vk >> ${LOG_FILE} 2>&1 ${MARKER}"

# Получаем текущий crontab (если его нет — пустая строка)
existing="$(crontab -l 2>/dev/null || true)"

# Удаляем все строки с нашим маркером, чтобы переустановка не плодила дубли
new_crontab="$(echo "$existing" | grep -v -F "$MARKER" || true)"

# Добавляем актуальную строку
if [ -n "$new_crontab" ]; then
    new_crontab="${new_crontab}"$'\n'"${CRON_LINE}"
else
    new_crontab="${CRON_LINE}"
fi

echo "$new_crontab" | crontab -

echo "✅ Cron-задача установлена:"
echo "   Расписание: $SCHEDULE"
echo "   Лог:        $LOG_FILE"
echo "   Маркер:     $MARKER"
crontab -l | grep -F "$MARKER" || true

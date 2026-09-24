#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# cron-common.sh — общие функции для cron-обёрток и их установщиков.
#
# Подключение:
#   source "$(dirname "${BASH_SOURCE[0]}")/cron-common.sh"
#
# Все cron-задачи проекта живут в crontab пользователя, от которого идёт
# деплой (deploy). Раньше часть задач стояла в crontab root, а папка logs/
# принадлежала root — обёртки под deploy молча падали на первой записи в лог.
# ---------------------------------------------------------------------------

# Явный PATH: cron-демон стартует с урезанным PATH и не видит docker.
# USE_DOCKER=1 — команда исполняется внутри web-контейнера.
CRON_PATH="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CRON_TZ_LINE="CRON_TZ=Europe/Moscow"

# Проверяет, что лог-файл доступен на запись. Если нет — сообщает в syslog
# и stderr (cron-почты на сервере нет) и завершает скрипт с ошибкой, вместо
# того чтобы тихо умереть на первом `>> "$LOG_FILE"` под set -e.
cron_require_log() {
    local log_file="$1"
    local log_dir
    log_dir="$(dirname "$log_file")"

    mkdir -p "$log_dir" 2>/dev/null || true
    if touch "$log_file" 2>/dev/null; then
        return 0
    fi

    local msg="$(basename "$0"): нет прав на запись в $log_file (пользователь $(id -un)); задача не выполнена"
    logger -t insflow-cron -p user.err "$msg" 2>/dev/null || true
    echo "$msg" >&2
    exit 1
}

# Идемпотентно ставит строку в crontab текущего пользователя.
#   cron_install_line "<schedule>" "<wrapper path>" "<marker>"
# Строки с тем же маркером заменяются, прочие задачи сохраняются.
# Если в crontab нет CRON_TZ — добавляет его первой строкой.
cron_install_line() {
    local schedule="$1" wrapper="$2" marker="$3"
    local line="${schedule} ${CRON_PATH} USE_DOCKER=1 ${wrapper} ${marker}"
    local existing new_crontab

    chmod +x "$wrapper"

    existing="$(crontab -l 2>/dev/null || true)"
    new_crontab="$(echo "$existing" | grep -v -F "$marker" || true)"

    if ! echo "$new_crontab" | grep -q '^CRON_TZ='; then
        new_crontab="${CRON_TZ_LINE}"$'\n'"${new_crontab}"
    fi

    # Убираем пустые строки, которые копятся при повторных установках
    new_crontab="$(echo "$new_crontab" | sed '/^[[:space:]]*$/d')"
    printf '%s\n%s\n' "$new_crontab" "$line" | crontab -

    echo "✅ Cron-задача установлена для пользователя $(id -un):"
    echo "   Расписание: $schedule  ($CRON_TZ_LINE)"
    echo "   Скрипт:     $wrapper"
    echo "   Маркер:     $marker"
    crontab -l | grep -F "$marker" || true

    if [ ! -w "$(dirname "$wrapper")/../logs" ] && [ -d "$(dirname "$wrapper")/../logs" ]; then
        echo "⚠️  Папка logs/ недоступна на запись для $(id -un) — задача не сможет писать лог"
    fi
}

#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/cron_recovery_backup.log"
source "$SCRIPT_DIR/cron-common.sh"
cron_require_log "$LOG_FILE"
cd "$PROJECT_DIR"
echo "$(date '+%Y-%m-%d %H:%M:%S') - START encrypted recovery backup" >> "$LOG_FILE"
if python3 scripts/run_recovery_backup.py >> "$LOG_FILE" 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - END success" >> "$LOG_FILE"
else
    code=$?
    echo "$(date '+%Y-%m-%d %H:%M:%S') - END failed (exit_code=$code)" >> "$LOG_FILE"
    exit "$code"
fi

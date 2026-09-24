#!/bin/bash

# Cron wrapper for daily rotation of application log files (/app/logs in web).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/cron_rotate_logs.log"
PYTHON_BIN="${PYTHON_BIN:-python}"
USE_DOCKER="${USE_DOCKER:-0}"

# shellcheck source=cron-common.sh
source "$SCRIPT_DIR/cron-common.sh"
cron_require_log "$LOG_FILE"
cd "$PROJECT_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') - START rotate_logs (USE_DOCKER=$USE_DOCKER)" >> "$LOG_FILE"

if [ "$USE_DOCKER" = "1" ]; then
  CMD=(docker compose exec -T web python manage.py rotate_logs)
else
  CMD=("$PYTHON_BIN" manage.py rotate_logs)
fi

if "${CMD[@]}" >> "$LOG_FILE" 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') - END success" >> "$LOG_FILE"
else
  EXIT_CODE=$?
  echo "$(date '+%Y-%m-%d %H:%M:%S') - END failed (exit_code=$EXIT_CODE)" >> "$LOG_FILE"
  exit "$EXIT_CODE"
fi

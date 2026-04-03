#!/bin/bash

# Cron wrapper for auto-closing stale summaries.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/cron_auto_close_summaries.log"
PYTHON_BIN="${PYTHON_BIN:-python}"
USE_DOCKER="${USE_DOCKER:-0}"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') - START auto_close_stale_summaries (USE_DOCKER=$USE_DOCKER)" >> "$LOG_FILE"

if [ "$USE_DOCKER" = "1" ]; then
  CMD=(docker compose exec -T web python manage.py auto_close_stale_summaries)
else
  CMD=("$PYTHON_BIN" manage.py auto_close_stale_summaries)
fi

if "${CMD[@]}" >> "$LOG_FILE" 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') - END success" >> "$LOG_FILE"
else
  EXIT_CODE=$?
  echo "$(date '+%Y-%m-%d %H:%M:%S') - END failed (exit_code=$EXIT_CODE)" >> "$LOG_FILE"
  exit "$EXIT_CODE"
fi

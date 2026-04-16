#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# backup-before-deploy.sh
#
# Быстрый бекап базы данных перед деплоем обновлений.
# Запускать из корня проекта:
#
#   bash scripts/backup-before-deploy.sh
#
# Что делает:
#   1. Создаёт pg_dump (полный дамп PostgreSQL) в папке backups/
#   2. Оставляет последние 10 дампов, удаляя старые
#   3. Дополнительно создаёт JSON-бекап данных приложений
#
# Требования на сервере:
#   - postgresql-client (pg_dump)
#   - настроенный .env с DB_* переменными
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
KEEP=10

cd "$PROJECT_DIR"

echo "=== Бекап перед деплоем: $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "Директория: $BACKUP_DIR"
echo ""

# Активируем виртуальное окружение если есть
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# pg_dump — полный дамп базы
echo "1/2  pg_dump..."
python manage.py backup_db --format pgdump --output-dir "$BACKUP_DIR" --keep "$KEEP"

# JSON — данные приложений (для быстрого восстановления через loaddata)
echo "2/2  JSON дамп данных приложений..."
python manage.py backup_db --format json --output-dir "$BACKUP_DIR" --keep "$KEEP"

echo ""
echo "=== Готово. Можно деплоить. ==="

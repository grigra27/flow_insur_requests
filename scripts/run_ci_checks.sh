#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PYTHON_BIN="${PYTHON_BIN:-python}"

# CI always uses an isolated SQLite test database, including local runs with .env.
export DB_ENGINE=django.db.backends.sqlite3
export DB_NAME=:memory:
export DEBUG=False
export ENABLE_HTTPS=False

"$PYTHON_BIN" manage.py check
"$PYTHON_BIN" manage.py makemigrations --check --dry-run

test_labels=()
while IFS= read -r label || [[ -n "$label" ]]; do
    [[ -z "$label" || "$label" == \#* ]] && continue
    test_labels+=("$label")
done < scripts/ci_test_labels.txt

if [[ ${#test_labels[@]} -eq 0 ]]; then
    echo "CI regression suite must not be empty" >&2
    exit 1
fi

"$PYTHON_BIN" manage.py test "${test_labels[@]}" --noinput "$@"

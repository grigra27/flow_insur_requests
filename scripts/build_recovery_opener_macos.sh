#!/usr/bin/env bash
# Build a local Mac application; never bundle keys, passwords or configuration.
set -euo pipefail
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGE_BIN="${AGE_BIN:-${HOME}/.config/insflow-backup/tools/age}"
APP_PATH="${1:-${HOME}/Applications/Открыть бэкап InsFlow.app}"
if [[ "$(uname -s)" != Darwin || ! -x "$AGE_BIN" ]]; then
  echo 'A Mac and the installed age executable are required.' >&2
  exit 1
fi
if [[ -e "$APP_PATH" ]]; then
  echo 'The destination already exists; choose a new application path.' >&2
  exit 1
fi
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/insflow-opener.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
cat > "$BUILD_DIR/launcher.applescript" <<'APPLESCRIPT'
on run
    set helperPath to POSIX path of (path to resource "open_backup.py")
    do shell script "/usr/bin/python3 " & quoted form of helperPath
end run
APPLESCRIPT
/usr/bin/osacompile -o "$BUILD_DIR/InsFlow.app" "$BUILD_DIR/launcher.applescript"
RESOURCES="$BUILD_DIR/InsFlow.app/Contents/Resources"
install -m 600 "$SCRIPT_DIR/open_recovery_backup_macos.py" "$RESOURCES/open_backup.py"
install -m 600 "$SCRIPT_DIR/recovery_age.py" "$RESOURCES/recovery_age.py"
install -m 700 "$AGE_BIN" "$RESOURCES/age"
/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier ru.insflow.backup-opener' \
  "$BUILD_DIR/InsFlow.app/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string ru.insflow.backup-opener' \
    "$BUILD_DIR/InsFlow.app/Contents/Info.plist"
/usr/bin/codesign --force --deep --sign - "$BUILD_DIR/InsFlow.app" >/dev/null 2>&1
/usr/bin/codesign --verify --deep --strict "$BUILD_DIR/InsFlow.app" >/dev/null 2>&1
mkdir -p "$(dirname "$APP_PATH")"
mv "$BUILD_DIR/InsFlow.app" "$APP_PATH"
echo "Created: $APP_PATH"

#!/usr/bin/env bash
# Install the deployment user's encrypted recovery delivery job after setup.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "${SCRIPT_DIR}/cron-common.sh"
ALLOW_UNCONFIGURED=0
if [[ "${1:-}" == "--allow-unconfigured" ]]; then
  ALLOW_UNCONFIGURED=1
  shift
fi
if [[ $# -ne 0 ]]; then
  echo 'Recovery cron setup: unsupported arguments.' >&2
  exit 2
fi
CONFIG="${HOME}/.config/insflow-recovery/config.json"
if [[ ! -f "$CONFIG" && "$ALLOW_UNCONFIGURED" == 1 ]]; then
  echo 'Recovery cron not installed: owner configuration is absent.'
  exit 0
fi
if ! "${HOST_PYTHON_BIN:-python3}" - "$CONFIG" <<'PY'
import json,os,re,stat,sys
from pathlib import Path
try:
    path=Path(sys.argv[1]); info=path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and not(info.st_mode&0o077)
    config=json.loads(path.read_text())
    age=Path(config['age_binary']); recipient=Path(config['recipient_file']); state=Path(config['state_dir']).expanduser()
    assert age.is_absolute() and age.is_file() and os.access(age,os.X_OK)
    assert recipient.is_absolute() and recipient.is_file()
    assert state.is_absolute()
    if state.exists(): assert state.is_dir() and not(state.stat().st_mode&0o077)
    assert 1<=int(config.get('keep_local',14))<=60
    lines=[s.strip() for s in recipient.read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]
    assert lines and all(re.fullmatch(r'age1[0-9a-z]{58}',s) for s in lines)
except Exception:
    raise SystemExit(1)
PY
then
  echo 'Recovery cron not installed: private owner configuration, age or public recipient is invalid.' >&2
  exit 1
fi
WRAPPER="${PROJECT_DIR}/scripts/cron-send-recovery-to-vk.sh"
if [[ ! -f "$WRAPPER" ]]; then
  echo 'Recovery cron not installed: delivery wrapper is unavailable.' >&2
  exit 1
fi
cron_install_line "${RECOVERY_BACKUP_CRON:-15 3 * * *}" "$WRAPPER" '# insflow-recovery-vk'

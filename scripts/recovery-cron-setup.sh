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
    state=Path(config['state_dir']).expanduser()
    assert state.is_absolute()
    if state.exists(): assert state.is_dir() and not(state.stat().st_mode&0o077)
    assert 1<=int(config.get('keep_local',14))<=60
    archive_format=config.get('archive_format','age-zip')
    assert archive_format in ('age-zip','age-passphrase')
    if archive_format=='age-passphrase':
        age=Path(config['age_binary']); secret=Path(config['password_file'])
        secret_info=secret.lstat()
        assert age.is_absolute() and age.is_file() and os.access(age,os.X_OK)
        assert secret.is_absolute() and stat.S_ISREG(secret_info.st_mode)
        assert secret_info.st_uid==os.geteuid() and not(secret_info.st_mode&0o077)
        descriptor=os.open(secret,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'rb') as stream:
            opened=os.fstat(stream.fileno())
            assert (opened.st_dev,opened.st_ino)==(secret_info.st_dev,secret_info.st_ino)
            assert opened.st_uid==os.geteuid() and not(opened.st_mode&0o077)
            value=stream.read(4097)
        assert len(value)<=4096
        if value.endswith(b'\n'): value=value[:-1]
        text=value.decode('utf-8')
        assert len(text)>=8 and not any(ord(c)<32 or ord(c)==127 for c in text)
    else:
        age=Path(config['age_binary']); recipient=Path(config['recipient_file'])
        assert age.is_absolute() and age.is_file() and os.access(age,os.X_OK)
        assert recipient.is_absolute() and recipient.is_file()
        lines=[s.strip() for s in recipient.read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]
        assert lines and all(re.fullmatch(r'age1[0-9a-z]{58}',s) for s in lines)
except Exception:
    raise SystemExit(1)
PY
then
  echo 'Recovery cron not installed: private configuration or encryption credentials are invalid.' >&2
  exit 1
fi
WRAPPER="${PROJECT_DIR}/scripts/cron-send-recovery-to-vk.sh"
if [[ ! -f "$WRAPPER" ]]; then
  echo 'Recovery cron not installed: delivery wrapper is unavailable.' >&2
  exit 1
fi
cron_install_line "${RECOVERY_BACKUP_CRON:-15 3 * * *}" "$WRAPPER" '# insflow-recovery-vk'

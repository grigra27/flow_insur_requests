"""Deep dive into the franchise (rows 26..33) and anti-theft (rows 50..65)
blocks of leasing-company Excel applications.

This script was created during the stage 2.4 mini-audit to verify whether
the corpus carries actual values for:
  - franchise percent / absolute amount,
  - anti-theft systems (alarm/immobilizer/mechanical/satellite) brand+model.

Run from the project root:

    python scripts/inspect_franchise_antitheft.py

The output revealed that both blocks are present as an empty template in
the form but the values are not filled in by leasing companies — see the
audit conclusion in docs/improvement_plans/coverage_audit.md (stage 2.4
section) and the resulting decision to skip stage 2.4 entirely.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onlineservice.settings")
os.environ.setdefault("ENABLE_HTTPS", "false")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
os.environ.setdefault("SECRET_KEY", "audit")
os.environ.setdefault("ALLOWED_HOSTS", "localhost")

import django  # noqa: E402

django.setup()

import pandas as pd  # noqa: E402


def collect(limit=5):
    files = []
    for d in [ROOT / "avtozayavka" / "real_requests", ROOT / "avtozayavka" / "im_request"]:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.xls")):
            if p.name.startswith("."):
                continue
            files.append(p)
            if len(files) >= limit:
                return files
    return files


def show_block(df, start_row, end_row, start_col, end_col, label):
    print(f"\n  -- {label} (rows {start_row}..{end_row}, cols {start_col}..{end_col}) --")
    for r in range(start_row - 1, min(end_row, df.shape[0])):
        row_repr = []
        for c in range(start_col - 1, min(end_col, df.shape[1])):
            v = df.iat[r, c]
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s:
                row_repr.append(f"C{c+1}={s[:35]!r}")
        if row_repr:
            print(f"  R{r+1}: {' | '.join(row_repr)}")


def main():
    files = collect(5)
    for path in files:
        print(f"\n========== {path.name[:60]} ==========")
        try:
            df = pd.read_excel(path, sheet_name=0, header=None)
        except Exception as exc:
            print(f"  read err: {exc}")
            continue
        print(f"  shape={df.shape}")
        show_block(df, 26, 33, 2, 8, "FRANCHISE")
        show_block(df, 50, 65, 2, 6, "ANTI-THEFT")


if __name__ == "__main__":
    main()

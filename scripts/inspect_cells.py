"""Одноразовый скрипт: смотрит окрестности ячеек, отвечающих за asset_status и telematics_complex."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onlineservice.settings")
os.environ.setdefault("ENABLE_HTTPS", "false")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
os.environ.setdefault("SECRET_KEY", "audit-only")
os.environ.setdefault("ALLOWED_HOSTS", "localhost")

import django  # noqa: E402

django.setup()

import pandas as pd  # noqa: E402

CORPUS_DIRS = [
    ROOT / "avtozayavka" / "real_requests",
    ROOT / "avtozayavka" / "im_request",
]


def collect(limit=8):
    out = []
    for d in CORPUS_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.xls"))[: limit]:
            out.append(p)
            if len(out) >= limit:
                return out
    return out


def show_region(df, rows, cols, label):
    print(f"\n  [{label}] rows={rows} cols={cols}")
    for r in rows:
        line = []
        for c in cols:
            try:
                v = df.iat[r - 1, c - 1]
            except Exception:
                v = None
            if pd.isna(v):
                v = ""
            v = str(v).strip().replace("\n", " ")[:35]
            line.append(f"{r},{c}:{v!r:>35}")
        print("   " + " | ".join(line))


def main():
    files = collect(8)
    for path in files:
        print(f"\n=== {path.name} ===")
        try:
            df = pd.read_excel(path, sheet_name=0, header=None)
        except Exception as exc:
            print(f"  read error: {exc}")
            continue
        print(f"  shape: {df.shape}")
        # asset_status: K43/K45/K47/K49 + лейблы выше
        show_region(df, [38, 39, 40, 41, 42, 43, 45, 47, 49], [10, 11, 12, 13, 14], "objects table cols J,K,L,M,N rows 38..49")
        # telematics: D63 + соседи
        show_region(df, [60, 61, 62, 63, 64, 65, 66], [3, 4, 5, 6, 7], "telematics (CDEFG rows 60..66)")


if __name__ == "__main__":
    main()

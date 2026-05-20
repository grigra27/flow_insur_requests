"""Mini-audit for stage 2.3 fields: lease dates, insured_party, insurance
period, sum-type, indemnity basis, guard conditions, location right
holder, premium frequency.

Scans 30 corpus files, prints both the label hits and the value found
to the right of the label cell.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
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

CORPUS_DIRS = [
    ROOT / "avtozayavka" / "real_requests",
    ROOT / "avtozayavka" / "im_request",
]

# Each key may have several regex variants. We mark a hit when any variant
# is found inside the cell value (lowercased, ё→е).
LABELS = {
    "contract_lease_dates": [
        r"договор\s*лизинг",
        r"срок\s*лизинг",
        r"дата\s*дфа",
        r"начало\s*лизинг",
    ],
    "insured_party": [
        r"страхователь",
        r"выгодоприобретатель",
    ],
    "insurance_period": [
        r"период\s*страхов",
        r"срок\s*страхов",
        r"начало\s*страхов",
    ],
    "insured_sum_type": [
        r"страхов.{0,2}\s*сумм",
        r"агрегатн",
        r"неагрегатн",
    ],
    "indemnity_basis": [
        r"возмещен",
        r"\bс\s*износ",
        r"без\s*износ",
    ],
    "guard_conditions": [
        r"условия\s*хранен",
        r"условия\s*стоянк",
        r"гараж",
        r"\bохран",
    ],
    "property_location_right_holder": [
        r"правообладат",
        r"собственник\s*места",
        r"\bаренд\w*\s*земельн",
    ],
    "premium_frequency": [
        r"рассрочк",
        r"поквартальн",
        r"ежекварт",
        r"ежемесячн",
        r"полугоди",
        r"единовремен",
        r"график\s*платеж",
    ],
}


def collect(limit=30):
    files = []
    for d in CORPUS_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.xls")):
            if p.name.startswith("."):
                continue
            files.append(p)
            if len(files) >= limit:
                return files
    return files


def value_right(df, ridx, cidx):
    for nxt in range(cidx + 1, min(cidx + 10, df.shape[1])):
        v = df.iat[ridx, nxt]
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s and len(s) > 1:
            return s[:60]
    return ""


def main():
    files = collect(30)
    print(f"Inspecting {len(files)} files.\n")
    counter = Counter()
    files_with = {key: set() for key in LABELS}
    examples = {key: [] for key in LABELS}

    for path in files:
        try:
            df = pd.read_excel(path, sheet_name=0, header=None)
        except Exception as exc:
            print(f"  skip {path.name}: {exc}")
            continue
        for ridx, row in df.iterrows():
            for cidx, raw in row.items():
                if pd.isna(raw):
                    continue
                text = str(raw)
                normalized = text.lower().replace("ё", "е")
                for key, patterns in LABELS.items():
                    for pat in patterns:
                        if re.search(pat, normalized):
                            counter[key] += 1
                            files_with[key].add(path.name)
                            if len(examples[key]) < 4:
                                examples[key].append(
                                    (path.name[:48], f"R{ridx+1}C{cidx+1}", text[:42], value_right(df, ridx, cidx))
                                )
                            break

    print("--- Files containing each label (out of 30) ---")
    for key in LABELS:
        n = len(files_with[key])
        print(f"  {key:<32} {n}/30")
    print("\n--- Sample anchors (file / coord / label / value-right) ---")
    for key, items in examples.items():
        print(f"\n[{key}]")
        for it in items:
            print(f"  {it[0]:48} | {it[1]:8} | {it[2]:42} | {it[3]}")


if __name__ == "__main__":
    main()

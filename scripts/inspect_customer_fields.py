"""Quick check: do leasing-company Excel files contain ОГРН/КПП/addresses/etc.?

Scans the first 30 files of the corpus, looks for tokens, prints the cells
that contain them. Goal: validate whether customer fields planned for stage
2.2 are present in the source or live elsewhere (PTS, registry, …).
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

LABELS = {
    "ogrn": [r"\bогрн\b", r"огрнип"],
    "kpp": [r"\bкпп\b"],
    "legal_address": [r"юридическ.{0,2}\s*адрес", r"юр\.\s*адрес"],
    "postal_address": [r"почтов.{0,2}\s*адрес", r"фактическ.{0,2}\s*адрес"],
    "business_activity": [r"вид.{0,2}\s*деятельност", r"оквэд"],
    "birth_date": [r"дата\s*рождени"],
    "submission_date": [r"дата\s*подачи", r"дата\s*заявки", r"дата\s*составлен"],
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


def main():
    files = collect(30)
    print(f"Inspecting {len(files)} files.\n")
    counter = Counter()
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
                            if len(examples[key]) < 3:
                                # Capture cell at right (the actual value).
                                value_right = ""
                                for nxt in range(cidx + 1, min(cidx + 8, df.shape[1])):
                                    nv = df.iat[ridx, nxt]
                                    if pd.isna(nv):
                                        continue
                                    s = str(nv).strip()
                                    if s and len(s) > 1:
                                        value_right = s[:60]
                                        break
                                examples[key].append(
                                    (path.name[:55], f"R{ridx+1}C{cidx+1}", text[:40], value_right)
                                )
                            break  # one pattern per key per cell

    print("--- Label hits across 30 files ---")
    for key in LABELS:
        print(f"  {key:<22} hits={counter.get(key, 0)}")
    print("\n--- Sample anchors (file / coord / label / value-right) ---")
    for key, items in examples.items():
        print(f"\n[{key}]")
        for it in items:
            print(f"  {it[0]:55} | {it[1]:8} | {it[2]:40} | {it[3]}")


if __name__ == "__main__":
    main()

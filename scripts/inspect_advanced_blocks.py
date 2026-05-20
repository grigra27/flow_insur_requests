"""Mini-audit for stage 2.4: structured franchise options, anti-theft systems,
transportation origin/destination, СМР description.

Goal: figure out which blocks are present in the source enough to be worth
modelling.
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


def cell_str(df, ridx, cidx):
    try:
        v = df.iat[ridx, cidx]
    except Exception:
        return ""
    if pd.isna(v):
        return ""
    return str(v).strip()


def value_right(df, ridx, cidx, max_offset=8):
    for nxt in range(cidx + 1, min(cidx + max_offset, df.shape[1])):
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

    franchise_value_hits = Counter()  # rows 28..32: do we see %/abs values?
    franchise_sample = []
    anti_theft_hits = Counter()
    anti_theft_sample = []
    transportation_hits = Counter()
    transportation_sample = []
    cmw_hits = Counter()
    cmw_sample = []

    for path in files:
        try:
            df = pd.read_excel(path, sheet_name=0, header=None)
        except Exception as exc:
            print(f"  skip {path.name}: {exc}")
            continue

        # 1. Franchise: scan rows 26..32 (label «Франшиза», «без франшизы», «%»,
        # «абсолютная»), look for numeric values or X marks.
        for ridx in range(25, min(34, df.shape[0])):
            for cidx in range(df.shape[1]):
                v = cell_str(df, ridx, cidx).lower().replace("ё", "е")
                if not v:
                    continue
                if "франшиз" in v:
                    franchise_hits_local = []
                    # Sweep neighbors for numeric / X
                    for cn in range(max(0, cidx - 2), min(cidx + 8, df.shape[1])):
                        for rn in range(ridx, min(ridx + 3, df.shape[0])):
                            nb = cell_str(df, rn, cn)
                            if nb and (re.search(r"\d", nb) or nb.lower() in {"х", "x"}):
                                franchise_hits_local.append(f"R{rn+1}C{cn+1}={nb[:30]}")
                    if franchise_hits_local:
                        franchise_value_hits[path.name] += 1
                        if len(franchise_sample) < 5:
                            franchise_sample.append((path.name[:48], franchise_hits_local[:6]))
                    break

        # 2. Anti-theft systems: «сигнализация», «иммобилайзер», «спутник…»,
        # «механич…». For each, check whether the row/neighbors have filled values.
        anti_keys = {
            "alarm": ["сигнализаци"],
            "immobilizer": ["иммобилайзер", "иммобилизатор"],
            "satellite": ["спутник"],
            "mechanical": ["механич"],
        }
        for ridx in range(35, min(80, df.shape[0])):
            for cidx in range(df.shape[1]):
                v = cell_str(df, ridx, cidx).lower().replace("ё", "е")
                if not v or len(v) > 70:
                    continue
                for key, terms in anti_keys.items():
                    if any(t in v for t in terms):
                        # Look right and below for non-empty values.
                        found_val = ""
                        for offset_c in range(1, 8):
                            r = cell_str(df, ridx, cidx + offset_c)
                            if r and len(r) > 1 and r.lower() not in ("х", "x", "штатная", "установленная дополнительно"):
                                found_val = r[:50]
                                break
                        if not found_val:
                            for offset_r in range(1, 3):
                                for cn in range(cidx, cidx + 6):
                                    r = cell_str(df, ridx + offset_r, cn)
                                    if r and len(r) > 1 and r.lower() not in ("х", "x", "штатная", "установленная дополнительно"):
                                        found_val = f"(below) {r[:50]}"
                                        break
                                if found_val:
                                    break
                        if found_val:
                            anti_theft_hits[key] += 1
                            if len(anti_theft_sample) < 12:
                                anti_theft_sample.append((path.name[:40], key, f"R{ridx+1}C{cidx+1}", v[:30], found_val))

        # 3. Transportation origin/destination: «перевоз», look for city
        # «откуда / куда / маршрут» in neighborhood.
        for ridx in range(min(df.shape[0], 100)):
            for cidx in range(df.shape[1]):
                v = cell_str(df, ridx, cidx).lower().replace("ё", "е")
                if not v or len(v) > 80:
                    continue
                if "перевоз" in v:
                    # Look for «откуда/куда/маршрут/из/в» nearby.
                    transportation_hits["any"] += 1
                    for offset in range(1, 8):
                        nb = cell_str(df, ridx, cidx + offset).lower().replace("ё", "е")
                        if "откуда" in nb or "куда" in nb or "маршрут" in nb or " из " in nb:
                            transportation_hits["with_route"] += 1
                            if len(transportation_sample) < 5:
                                transportation_sample.append((path.name[:40], f"R{ridx+1}C{cidx+1}", v[:40], nb[:40]))
                            break
                    break

        # 4. СМР: «смр», «строительно-монтаж».
        for ridx in range(min(df.shape[0], 100)):
            for cidx in range(df.shape[1]):
                v = cell_str(df, ridx, cidx).lower().replace("ё", "е")
                if not v or len(v) > 80:
                    continue
                if re.search(r"\bсмр\b", v) or "строительно" in v and "монтаж" in v:
                    cmw_hits["label"] += 1
                    # Check neighbors for any value.
                    for offset in range(1, 6):
                        nb = cell_str(df, ridx, cidx + offset)
                        if nb and len(nb) > 1:
                            cmw_hits["with_value"] += 1
                            if len(cmw_sample) < 5:
                                cmw_sample.append((path.name[:40], f"R{ridx+1}C{cidx+1}", v[:40], nb[:60]))
                            break
                    break

    print("--- Franchise: files with numeric/X values in rows 26..33 ---")
    print(f"  hits: {len(franchise_value_hits)}/30 files")
    for s in franchise_sample:
        print(f"  {s[0]:48} | {s[1]}")

    print("\n--- Anti-theft: files where each block had non-template value ---")
    print(f"  alarm:       {anti_theft_hits.get('alarm', 0)}")
    print(f"  immobilizer: {anti_theft_hits.get('immobilizer', 0)}")
    print(f"  satellite:   {anti_theft_hits.get('satellite', 0)}")
    print(f"  mechanical:  {anti_theft_hits.get('mechanical', 0)}")
    print("  samples:")
    for s in anti_theft_sample:
        print(f"    {s[0]:40} | {s[1]:11} | {s[2]:8} | {s[3]:30} | {s[4]}")

    print("\n--- Transportation ---")
    print(f"  «перевоз» label: {transportation_hits.get('any', 0)}")
    print(f"  with route hint: {transportation_hits.get('with_route', 0)}")
    for s in transportation_sample:
        print(f"  {s[0]:40} | {s[1]:8} | {s[2]:40} | {s[3]}")

    print("\n--- СМР ---")
    print(f"  label hits:      {cmw_hits.get('label', 0)}")
    print(f"  with value next: {cmw_hits.get('with_value', 0)}")
    for s in cmw_sample:
        print(f"  {s[0]:40} | {s[1]:8} | {s[2]:40} | {s[3]}")


if __name__ == "__main__":
    main()

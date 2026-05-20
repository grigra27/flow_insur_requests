"""Coverage audit: прогоняет существующие парсеры по корпусу и считает заполненность полей.

Запуск из корня проекта:
    python scripts/coverage_audit.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Django bootstrap
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onlineservice.settings")
os.environ.setdefault("ENABLE_HTTPS", "false")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SECRET_KEY", "audit-only")
os.environ.setdefault("ALLOWED_HOSTS", "localhost")

import django  # noqa: E402

django.setup()

from core.excel_utils import ExcelReader  # noqa: E402
from insurance_requests.parsers.excel_v2.parser import ExcelRequestParserV2  # noqa: E402


CORPUS_DIRS = [
    ROOT / "avtozayavka" / "real_requests",
    ROOT / "avtozayavka" / "im_request",
]

# Поля, которые парсер v1 возвращает (плоский dict)
V1_FIELDS = [
    "client_name",
    "inn",
    "insurance_type",
    "insurance_period",
    "vehicle_info",
    "dfa_number",
    "branch",
    "manager_name",
    "franchise_type",
    "has_installment",
    "has_autostart",
    "has_casco_ce",
    "has_transportation",
    "has_construction_work",
    "manufacturing_year",
    "asset_status",
    "key_completeness",
    "pts_psm",
    "creditor_bank",
    "usage_purposes",
    "telematics_complex",
    "insurance_territory",
]

V2_FIELDS = V1_FIELDS + ["insured_objects_count"]

# Per-object fields filled by stage 3.1 inside each insured_objects[] entry.
V2_OBJECT_FIELDS = [
    "brand",
    "model",
    "condition",
    "equipment_type",
    "power_or_capacity",
    "acquisition_cost_value",
    "acquisition_cost_currency",
]


def is_meaningful(field_name: str, value) -> bool:
    """Заполнено ли поле осмысленным значением (не дефолтом и не пустотой)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value  # True = распознали условие; False = «нет признака», но не «не нашли»
    if isinstance(value, (int, float)):
        return value > 0
    s = str(value).strip()
    if not s:
        return False
    lowered = s.lower()
    # Маркеры дефолтных/fallback значений
    bad_markers = [
        "не указан",
        "не указано",
        "не указана",
        "не определ",
        "клиент не указан",
        "номер дфа не указан",
        "филиал не указан",
        "1234567890",  # фейковый ИНН в default_data
    ]
    if any(m in lowered for m in bad_markers):
        return False
    return True


def collect_corpus():
    files = []
    for d in CORPUS_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"}:
                files.append(p)
    return sorted(files)


def detect_hints(path: Path):
    """Грубо угадываем формат и тип по имени файла, чтобы дать parser v1 шанс."""
    name = path.name.lower()
    application_type = "individual_entrepreneur" if "ип " in name or "ип." in name or " ип" in name else "legal_entity"
    if any(token in name for token in ["об ", "имущест", "оборудован", "электростанц", "топливозаправ"]):
        application_format = "property"
    elif any(token in name for token in ["см ", "спецтехник", "погрузч", "экскават", "кран", "каток"]):
        application_format = "casco_equipment"
    else:
        application_format = "casco_equipment"
    return application_type, application_format


def run_v1(path: Path):
    application_type, application_format = detect_hints(path)
    try:
        reader = ExcelReader(
            file_path=str(path),
            application_type=application_type,
            application_format=application_format,
        )
        data = reader.read_insurance_request()
        failed = bool(data.get("error_info", {}).get("fallback_used"))
        return data, failed, application_type, application_format
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}, True, application_type, application_format


def run_v2(path: Path):
    try:
        result = ExcelRequestParserV2().parse(str(path), original_filename=path.name)
        data = dict(result.data)
        payload = data.get("parser_v2_payload", {}) or {}
        data["insured_objects_count"] = len(payload.get("insured_objects", []) or [])
        failed = bool(result.raw_debug.get("reader") == "failed")
        return data, failed, payload
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}, True, {}


def main():
    files = collect_corpus()
    print(f"Files in corpus: {len(files)}")

    v1_filled = defaultdict(int)
    v2_filled = defaultdict(int)
    v2_object_field_total = 0  # Считаем по всем найденным объектам, не по файлам.
    v2_object_field_filled = defaultdict(int)
    v2_files_with_first_object_filled = defaultdict(int)
    v1_total_failed = 0
    v2_total_failed = 0
    v1_objects_lost = 0
    v2_object_count_dist = defaultdict(int)
    sample_payload = None

    per_file_rows = []

    for i, path in enumerate(files):
        v1_data, v1_failed, app_type, app_format = run_v1(path)
        v2_data, v2_failed, v2_payload = run_v2(path)

        if v1_failed:
            v1_total_failed += 1
        if v2_failed:
            v2_total_failed += 1

        for f in V1_FIELDS:
            if is_meaningful(f, v1_data.get(f)):
                v1_filled[f] += 1
        for f in V2_FIELDS:
            if is_meaningful(f, v2_data.get(f)):
                v2_filled[f] += 1

        obj_count = v2_data.get("insured_objects_count", 0) or 0
        v2_object_count_dist[obj_count] += 1
        if obj_count > 1:
            v1_objects_lost += 1  # v1 кладёт всё в vehicle_info

        # Per-object fill stats (stage 3.1).
        objects = v2_payload.get("insured_objects") or []
        if objects:
            for obj in objects:
                v2_object_field_total += 1
                for of in V2_OBJECT_FIELDS:
                    if is_meaningful(of, obj.get(of)):
                        v2_object_field_filled[of] += 1
            first = objects[0]
            for of in V2_OBJECT_FIELDS:
                if is_meaningful(of, first.get(of)):
                    v2_files_with_first_object_filled[of] += 1

        if sample_payload is None and v2_payload.get("insured_objects"):
            sample_payload = {
                "file": path.name,
                "application_type": v2_payload.get("application_type"),
                "application_format": v2_payload.get("application_format"),
                "object_sample": v2_payload["insured_objects"][:2],
                "franchise_details": v2_payload.get("franchise_details"),
            }

        per_file_rows.append({
            "file": path.name,
            "app_type": app_type,
            "app_format": app_format,
            "v1_failed": v1_failed,
            "v2_failed": v2_failed,
            "v2_objects": obj_count,
        })

    total = len(files)

    def pct(n):
        return f"{n / total * 100:.1f}%" if total else "—"

    def pct_of(numerator, denominator):
        return f"{numerator / denominator * 100:.1f}%" if denominator else "—"

    report = {
        "total_files": total,
        "v1_total_failed": v1_total_failed,
        "v2_total_failed": v2_total_failed,
        "v1_filled": {f: {"count": c, "pct": pct(c)} for f, c in v1_filled.items()},
        "v2_filled": {f: {"count": c, "pct": pct(c)} for f, c in v2_filled.items()},
        "multi_object_files_lost_in_v1": v1_objects_lost,
        "v2_object_count_distribution": dict(v2_object_count_dist),
        "v2_object_field_total": v2_object_field_total,
        "v2_object_fields_filled_per_object": {
            f: {"count": v2_object_field_filled.get(f, 0), "pct": pct_of(v2_object_field_filled.get(f, 0), v2_object_field_total)}
            for f in V2_OBJECT_FIELDS
        },
        "v2_object_fields_filled_in_first_object_per_file": {
            f: {"count": v2_files_with_first_object_filled.get(f, 0), "pct": pct(v2_files_with_first_object_filled.get(f, 0))}
            for f in V2_OBJECT_FIELDS
        },
        "sample_v2_payload": sample_payload,
    }

    out_path = ROOT / "scripts" / "coverage_audit_result.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report saved to {out_path}")

    # Краткий итог в stdout
    print("\n--- V1 fill rate ---")
    for f in V1_FIELDS:
        c = v1_filled.get(f, 0)
        print(f"  {f:<26} {c:>4}/{total}  {pct(c)}")
    print(f"\n  v1_failed: {v1_total_failed}/{total}")

    print("\n--- V2 fill rate ---")
    for f in V2_FIELDS:
        c = v2_filled.get(f, 0)
        print(f"  {f:<26} {c:>4}/{total}  {pct(c)}")
    print(f"\n  v2_failed: {v2_total_failed}/{total}")

    print("\n--- V2 per-object fill rate (stage 3.1) ---")
    print(f"  total objects across all files: {v2_object_field_total}")
    for of in V2_OBJECT_FIELDS:
        c = v2_object_field_filled.get(of, 0)
        per_obj_pct = pct_of(c, v2_object_field_total)
        per_file_c = v2_files_with_first_object_filled.get(of, 0)
        per_file_pct = pct(per_file_c)
        print(f"  {of:<28} per-object {c:>4}/{v2_object_field_total}  {per_obj_pct:>6}   first-object-per-file {per_file_c:>4}/{total}  {per_file_pct}")
    print(f"  multi-object files (in v2, >1 obj): {sum(c for k, c in v2_object_count_dist.items() if k > 1)}")
    print(f"  v2 object-count distribution: {dict(sorted(v2_object_count_dist.items()))}")


if __name__ == "__main__":
    main()

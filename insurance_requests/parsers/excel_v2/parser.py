"""Best-effort Excel parser for insurance request uploads V2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from core.excel_utils import map_branch_name

logger = logging.getLogger(__name__)


PARSER_V2_VERSION = "2.0.0"
MISSING_CLIENT = "Клиент не указан"
MISSING_DFA = "Номер ДФА не указан"
MISSING_VEHICLE = "Предмет лизинга не указан"
CLIENT_COORDINATES = ("D7", "D8")
CLIENT_MAX_LABEL_ROW = 10
OBJECT_TEMPLATE_ROW_MARKERS = [
    "транспортные средства категории b",
    "транспортные средства категории c",
    "транспортные средства категории d",
    "специальная техника",
    "противоугонные системы и оборудование",
    "штатная",
    "установленная дополнительно",
    "название модель",
    "название модели",
    "модель сигнализации",
    "сигнализация",
    "иммобилайзер",
    "иммобилизатор",
    "мобилизатор",
    "механические противоугонные устройства",
    "спутниковая противоугонная система",
    "капот",
    "рычаг кпп",
    "прочее",
    "марка модель конфигурация",
]


@dataclass(frozen=True)
class GridCell:
    row: int
    col: int
    coordinate: str
    value: str

    @property
    def normalized(self) -> str:
        return normalize_text(self.value)


@dataclass
class ParserV2Result:
    data: Dict[str, Any]
    warnings: List[Dict[str, str]] = field(default_factory=list)
    source_map: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    raw_debug: Dict[str, Any] = field(default_factory=dict)
    original_filename: str = ""
    parser_version: str = PARSER_V2_VERSION

    def to_session_dict(self) -> Dict[str, Any]:
        return {
            "parser_version": self.parser_version,
            "original_filename": self.original_filename,
            "data": self.data,
            "warnings": self.warnings,
            "source_map": self.source_map,
            "confidence": self.confidence,
            "raw_debug": self.raw_debug,
        }


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_text(value: Any) -> str:
    text = clean_value(value).lower().replace("ё", "е")
    text = text.replace("№", " no ")
    text = re.sub(r"[\n\r\t:;,.()]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class ExcelRequestParserV2:
    """Label-based Parser V2 that never blocks request creation."""

    def parse(self, file_path: str, original_filename: str = "") -> ParserV2Result:
        warnings: List[Dict[str, str]] = []
        source_map: Dict[str, str] = {}

        try:
            cells, debug = self._read_cells(file_path)
        except Exception as exc:  # noqa: BLE001 - parser must return a useful draft
            logger.warning("Parser V2 could not read file %s: %s", file_path, exc, exc_info=True)
            data = self._default_data()
            data["notes"] = self._build_notes(
                [
                    {
                        "level": "error",
                        "field": "excel_file",
                        "message": "Файл не удалось прочитать. Создайте минимальную заявку и обработайте файл вручную.",
                        "source": original_filename or os.path.basename(file_path),
                    }
                ]
            )
            return ParserV2Result(
                data=data,
                warnings=[
                    {
                        "level": "error",
                        "field": "excel_file",
                        "message": f"Файл не удалось прочитать: {exc}",
                        "source": original_filename or os.path.basename(file_path),
                    }
                ],
                source_map={},
                confidence=0.0,
                raw_debug={
                    "reader": "failed",
                    "error": str(exc),
                    "file_name": original_filename or os.path.basename(file_path),
                },
                original_filename=original_filename,
            )

        data = self._default_data()
        rows = self._rows(cells)

        client_name, source = self._extract_client_name(cells, rows)
        if client_name:
            data["client_name"] = client_name
            source_map["client_name"] = source

        inn, source = self._extract_inn(cells, rows)
        if inn:
            data["inn"] = inn
            source_map["inn"] = source

        manager_name, source = self._extract_labeled_value(
            cells,
            rows,
            label_groups=[("менеджер",)],
            fallback_coordinate="C5",
        )
        if manager_name:
            data["manager_name"] = manager_name
            source_map["manager_name"] = source

        branch_raw, source = self._extract_branch(cells, rows)
        if branch_raw:
            data["branch"] = map_branch_name(branch_raw)
            source_map["branch"] = source

        dfa_number, source = self._extract_dfa_number(cells, original_filename)
        if dfa_number:
            data["dfa_number"] = dfa_number
            source_map["dfa_number"] = source

        data["insurance_type"], insurance_type_source = self._extract_insurance_type(cells)
        if insurance_type_source:
            source_map["insurance_type"] = insurance_type_source

        data["insurance_period"], period_source = self._extract_insurance_period(cells)
        if period_source:
            source_map["insurance_period"] = period_source

        insured_objects = self._extract_objects(cells, rows)
        if insured_objects:
            data["vehicle_info"] = self._vehicle_summary(insured_objects)
            source_map["vehicle_info"] = insured_objects[0].get("source", "")
            source_map["insured_objects"] = ", ".join(
                obj["source"] for obj in insured_objects[:10] if obj.get("source")
            )

        application_type = self._detect_application_type(cells)

        franchise_type, franchise_details = self._extract_franchise_type(cells, application_type)
        data["franchise_type"] = franchise_type
        if franchise_details.get("source"):
            source_map["franchise_type"] = franchise_details["source"]
        data["has_installment"] = self._contains_any(cells, ["рассроч", "ежекварт", "ежемесяч", "покварт"])
        data["has_autostart"] = self._extract_autostart(cells, rows)
        data["has_casco_ce"] = self._contains_any(cells, ["категори c", "категории c", "кат с", "кат. c", "c/e"])
        data["has_transportation"] = self._contains_any(cells, ["перевоз", "транспортиров"])
        data["has_construction_work"] = self._contains_any(cells, ["смр", "строительно монтаж"])

        manufacturing_year, source = self._extract_manufacturing_year(cells)
        if manufacturing_year:
            data["manufacturing_year"] = manufacturing_year
            source_map["manufacturing_year"] = source

        for field_name, label_groups in {
            "key_completeness": [("комплект", "ключ")],
            "pts_psm": [("птс",), ("псм",)],
            "creditor_bank": [("банк", "кредитор")],
            "usage_purposes": [("цель", "использ"), ("цели", "использ")],
            "insurance_territory": [("территор", "страх")],
        }.items():
            value, source = self._extract_labeled_value(cells, rows, label_groups=label_groups)
            if value:
                data[field_name] = value
                source_map[field_name] = source

        asset_value, asset_source = self._extract_asset_status(cells, rows, application_type)
        if asset_value:
            data["asset_status"] = asset_value
            source_map["asset_status"] = asset_source

        telematics_value, telematics_source = self._extract_telematics_complex(cells, rows)
        if telematics_value:
            data["telematics_complex"] = telematics_value
            source_map["telematics_complex"] = telematics_source

        parser_payload = {
            "insured_objects": insured_objects,
            "raw_branch": branch_raw,
            "application_format": self._detect_application_format(data),
            "application_type": application_type,
            "franchise_details": franchise_details,
        }
        data["parser_v2_payload"] = parser_payload

        warnings.extend(self._build_warnings(data, insured_objects))
        data["notes"] = self._build_notes(warnings)

        confidence = self._calculate_confidence(data, insured_objects)
        debug.update(
            {
                "file_name": original_filename or os.path.basename(file_path),
                "object_count": len(insured_objects),
                "warning_count": len(warnings),
            }
        )

        return ParserV2Result(
            data=data,
            warnings=warnings,
            source_map=source_map,
            confidence=confidence,
            raw_debug=debug,
            original_filename=original_filename,
        )

    def _read_cells(self, file_path: str) -> Tuple[List[GridCell], Dict[str, Any]]:
        try:
            workbook = load_workbook(file_path, data_only=True)
            sheet = workbook.active
            cells: List[GridCell] = []
            for row in sheet.iter_rows():
                for cell in row:
                    value = clean_value(cell.value)
                    if value:
                        cells.append(GridCell(cell.row, cell.column, cell.coordinate, value))
            return cells, {
                "reader": "openpyxl",
                "sheet_name": sheet.title,
                "row_count": sheet.max_row,
                "column_count": sheet.max_column,
                "cell_count": len(cells),
            }
        except Exception as openpyxl_error:
            logger.info("Parser V2 openpyxl read failed, trying pandas: %s", openpyxl_error)

        df = pd.read_excel(file_path, sheet_name=0, header=None)
        cells = []
        for row_index, row in df.iterrows():
            for col_index, value in row.items():
                clean = clean_value(value)
                if clean:
                    row_number = int(row_index) + 1
                    col_number = int(col_index) + 1
                    cells.append(
                        GridCell(
                            row=row_number,
                            col=col_number,
                            coordinate=f"{get_column_letter(col_number)}{row_number}",
                            value=clean,
                        )
                    )
        return cells, {
            "reader": "pandas",
            "sheet_name": "0",
            "row_count": int(df.shape[0]),
            "column_count": int(df.shape[1]),
            "cell_count": len(cells),
        }

    def _default_data(self) -> Dict[str, Any]:
        deadline = timezone.localtime(timezone.now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        return {
            "client_name": MISSING_CLIENT,
            "inn": "",
            "insurance_type": "другое",
            "insurance_period": "",
            "vehicle_info": MISSING_VEHICLE,
            "dfa_number": MISSING_DFA,
            "branch": "",
            "manager_name": "",
            "deal_status": "new",
            "franchise_type": "none",
            "has_installment": False,
            "has_autostart": False,
            "has_casco_ce": False,
            "has_transportation": False,
            "has_construction_work": False,
            "manufacturing_year": "",
            "asset_status": "",
            "key_completeness": "",
            "pts_psm": "",
            "creditor_bank": "",
            "usage_purposes": "",
            "telematics_complex": "",
            "insurance_territory": "",
            "response_deadline": deadline,
            "notes": "",
            "parser_v2_payload": {},
        }

    def _rows(self, cells: Iterable[GridCell]) -> Dict[int, List[GridCell]]:
        rows: Dict[int, List[GridCell]] = {}
        for cell in cells:
            rows.setdefault(cell.row, []).append(cell)
        for row_cells in rows.values():
            row_cells.sort(key=lambda item: item.col)
        return rows

    def _extract_labeled_value(
        self,
        cells: List[GridCell],
        rows: Dict[int, List[GridCell]],
        label_groups: List[Tuple[str, ...]],
        fallback_coordinate: str = "",
    ) -> Tuple[str, str]:
        fallback_cell = self._cell_by_coordinate(cells, fallback_coordinate) if fallback_coordinate else None

        for cell in cells:
            if not self._matches_any_group(cell.normalized, label_groups):
                continue

            inline = self._inline_value_after_label(cell.value)
            if inline:
                return inline, cell.coordinate

            right = self._first_value_right(rows, cell)
            if right:
                return right.value, right.coordinate

            below = self._first_value_below(rows, cell)
            if below:
                return below.value, below.coordinate

        if fallback_cell and fallback_cell.value:
            return fallback_cell.value, fallback_cell.coordinate

        return "", ""

    def _extract_client_name(self, cells: List[GridCell], rows: Dict[int, List[GridCell]]) -> Tuple[str, str]:
        for coordinate in CLIENT_COORDINATES:
            cell = self._cell_by_coordinate(cells, coordinate)
            if cell and self._looks_like_client_name(cell.value):
                return cell.value, cell.coordinate

        for cell in cells:
            if cell.row > CLIENT_MAX_LABEL_ROW:
                continue
            if not self._matches_any_group(
                cell.normalized,
                [("наименование", "лизингополучател"), ("страхователь",), ("клиент",)],
            ):
                continue

            inline = self._inline_value_after_label(cell.value)
            if self._looks_like_client_name(inline):
                return inline, cell.coordinate

            right = self._first_value_right(rows, cell)
            if right and self._looks_like_client_name(right.value):
                return right.value, right.coordinate

            below = self._first_value_below(rows, cell)
            if below and self._looks_like_client_name(below.value):
                return below.value, below.coordinate

        return "", ""

    def _extract_inn(self, cells: List[GridCell], rows: Dict[int, List[GridCell]]) -> Tuple[str, str]:
        value, source = self._extract_labeled_value(cells, rows, label_groups=[("инн",)])
        inn = self._normalize_inn(value)
        if inn:
            return inn, source

        for cell in cells:
            match = re.search(r"\b\d{10}(\d{2})?\b", cell.value)
            if match:
                return match.group(0), cell.coordinate
        return "", ""

    def _extract_branch(self, cells: List[GridCell], rows: Dict[int, List[GridCell]]) -> Tuple[str, str]:
        for cell in cells:
            if "филиал" not in cell.normalized and "обособленное подразделение" not in cell.normalized:
                continue
            if cell.normalized in {"филиал", "филиал оп"}:
                continue
            return cell.value, cell.coordinate

        value, source = self._extract_labeled_value(cells, rows, label_groups=[("филиал",)])
        if value:
            return value, source
        return "", ""

    def _extract_dfa_number(self, cells: List[GridCell], original_filename: str) -> Tuple[str, str]:
        pattern = re.compile(r"\b\d{4,6}(?:[-/][0-9A-Za-zА-Яа-яЁё]+){1,5}\b")
        for cell in cells:
            match = pattern.search(cell.value)
            if match:
                return match.group(0), cell.coordinate
        filename_match = pattern.search(original_filename or "")
        if filename_match:
            return filename_match.group(0), "filename"
        return "", ""

    def _extract_insurance_type(self, cells: List[GridCell]) -> Tuple[str, str]:
        full_text = " ".join(cell.normalized for cell in cells)
        source = self._first_source_containing(cells, ["имущество", "спецтехник", "каско"])
        if "страхование имущества" in full_text or "имущество" in full_text:
            return "страхование имущества", source
        if "спецтехник" in full_text:
            return "страхование спецтехники", source
        if "каско" in full_text:
            return "КАСКО", source
        return "другое", ""

    def _extract_insurance_period(self, cells: List[GridCell]) -> Tuple[str, str]:
        full_text = " ".join(cell.normalized for cell in cells)
        if "весь срок лизинга" in full_text or "на весь срок" in full_text:
            return "на весь срок лизинга", self._first_source_containing(cells, ["срок лизинга", "весь срок"])
        if "1 год" in full_text or "один год" in full_text or "12 мес" in full_text:
            return "1 год", self._first_source_containing(cells, ["1 год", "12 мес", "один год"])
        return "", ""

    def _extract_objects(self, cells: List[GridCell], rows: Dict[int, List[GridCell]]) -> List[Dict[str, str]]:
        start_rows = [
            row_number
            for row_number, row_cells in rows.items()
            if self._row_matches(row_cells, ["предмет лизинга", "объект страхования"])
            or (
                self._row_matches(row_cells, ["наименование"])
                and self._row_matches(row_cells, ["год", "стоимость", "vin", "заводской"])
            )
        ]
        objects: List[Dict[str, str]] = []
        seen = set()

        for start_row in start_rows[:3]:
            blank_rows = 0
            for row_number in range(start_row, start_row + 35):
                row_cells = rows.get(row_number, [])
                row_text = self._row_text(row_cells)
                row_norm = normalize_text(row_text)
                if not row_text:
                    blank_rows += 1
                    if blank_rows >= 3:
                        break
                    continue
                blank_rows = 0
                if row_number != start_row and self._is_object_stop_row(row_norm):
                    break
                if self._is_object_header_or_label(row_norm) or self._is_object_template_row(row_norm):
                    continue
                if len(row_text) < 8:
                    continue
                if row_text in seen:
                    continue
                seen.add(row_text)
                objects.append(
                    {
                        "description": row_text,
                        "year": self._year_from_text(row_text),
                        "source": self._row_source(row_cells),
                    }
                )

        if not objects:
            value, source = self._extract_labeled_value(cells, rows, label_groups=[("предмет", "лизинга"), ("объект", "страхования")])
            if value and not self._is_object_template_row(normalize_text(value)):
                objects.append({"description": value, "year": self._year_from_text(value), "source": source})

        return objects[:50]

    def _extract_franchise_type(self, cells: List[GridCell], application_type: str) -> Tuple[str, Dict[str, Any]]:
        cell_map = {(cell.row, cell.col): cell for cell in cells}
        value_rows = [30, 29] if application_type == "individual_entrepreneur" else [29, 30]

        for index, value_row in enumerate(value_rows):
            row_details = self._franchise_row_details(cell_map, value_row)
            if not row_details["selected_columns"]:
                continue
            if row_details["selection_row_looks_like_header"]:
                continue
            if index > 0 and not row_details["label_row_looks_like_franchise_options"]:
                continue
            return row_details["franchise_type"], row_details

        return "none", {
            "value_row": value_rows[0],
            "label_row": value_rows[0] - 1,
            "selected_columns": [],
            "source": "",
            "selection_row_looks_like_header": False,
            "label_row_looks_like_franchise_options": False,
        }

    def _franchise_row_details(self, cell_map: Dict[Tuple[int, int], GridCell], value_row: int) -> Dict[str, Any]:
        label_row = value_row - 1
        selected_columns = []
        for column_letter, col, variant in [
            ("D", 4, "without_franchise"),
            ("E", 5, "percent_franchise"),
            ("F", 6, "absolute_franchise"),
        ]:
            value_cell = cell_map.get((value_row, col))
            if not self._franchise_cell_has_selection(value_cell.value if value_cell else ""):
                continue

            label_cell = cell_map.get((label_row, col))
            selected_columns.append(
                {
                    "column": column_letter,
                    "variant": variant,
                    "value_coordinate": value_cell.coordinate,
                    "value": value_cell.value,
                    "label_coordinate": label_cell.coordinate if label_cell else f"{column_letter}{label_row}",
                    "label": label_cell.value if label_cell else "",
                }
            )

        selected_variants = {item["variant"] for item in selected_columns}
        has_without = "without_franchise" in selected_variants
        has_with = bool({"percent_franchise", "absolute_franchise"} & selected_variants)
        selection_row_looks_like_header = self._franchise_row_looks_like_option_labels(
            [item["value"] for item in selected_columns]
        )
        label_row_looks_like_franchise_options = self._franchise_row_looks_like_option_labels(
            [item["label"] for item in selected_columns]
        )

        if has_without and has_with:
            franchise_type = "both_variants"
        elif has_with:
            franchise_type = "with_franchise"
        else:
            franchise_type = "none"

        source_parts = [
            f"{item['value_coordinate']}={item['value']}"
            + (f" ({item['label_coordinate']}: {item['label']})" if item["label"] else "")
            for item in selected_columns
        ]

        return {
            "value_row": value_row,
            "label_row": label_row,
            "selected_columns": selected_columns,
            "franchise_type": franchise_type,
            "source": "; ".join(source_parts),
            "selection_row_looks_like_header": selection_row_looks_like_header,
            "label_row_looks_like_franchise_options": label_row_looks_like_franchise_options,
        }

    def _franchise_cell_has_selection(self, value: Any) -> bool:
        value = clean_value(value)
        return bool(value) and normalize_text(value) not in {"none", "nan", "null", "false"}

    def _franchise_row_looks_like_option_labels(self, values: Iterable[Any]) -> bool:
        label_like_count = sum(
            1 for value in values
            if self._franchise_text_looks_like_option_label(value)
        )
        return label_like_count >= 2

    def _franchise_text_looks_like_option_label(self, value: Any) -> bool:
        text = normalize_text(value)
        if not text:
            return False
        return any(
            marker in text
            for marker in [
                "без франшиз",
                "с франшиз",
                "франшиз",
                "страхов",
                "абсолют",
                "процент",
                "сумм",
                "руб",
                "%",
            ]
        )

    def _extract_autostart(self, cells: List[GridCell], rows: Dict[int, List[GridCell]]) -> bool:
        for cell in cells:
            if "автозапуск" not in cell.normalized:
                continue
            row_text = normalize_text(self._row_text(rows.get(cell.row, [])))
            if "нет" in row_text and "да" not in row_text:
                return False
            return True
        return False

    def _extract_manufacturing_year(self, cells: List[GridCell]) -> Tuple[str, str]:
        value, source = self._extract_labeled_value(cells, self._rows(cells), label_groups=[("год", "выпуск")])
        year = self._year_from_text(value)
        if year:
            return year, source
        for cell in cells:
            year = self._year_from_text(cell.value)
            if year:
                return year, cell.coordinate
        return "", ""

    def _ip_row_offset(self, application_type: str, base_row: int) -> int:
        if application_type == "individual_entrepreneur" and base_row > 8:
            return base_row + 1
        return base_row

    def _extract_asset_status(
        self,
        cells: List[GridCell],
        rows: Dict[int, List[GridCell]],
        application_type: str,
    ) -> Tuple[str, str]:
        # 1) Label-based: «статус имущества» / «состояние».
        value, source = self._extract_labeled_value(
            cells,
            rows,
            label_groups=[("статус", "имуществ"), ("состояние",)],
        )
        if value:
            return value, source
        # 2) Fallback by coordinates: column K (11) in object rows 43/45/47/49,
        # shifted by +1 for individual entrepreneur applications. Some templates
        # have an extra leading column, so we also try column L (12) as a backup.
        status_values = {"новое", "новый", "новая", "б/у", "бу", "б-у"}
        parts: List[str] = []
        coords: List[str] = []
        for base_row in (43, 45, 47, 49):
            target_row = self._ip_row_offset(application_type, base_row)
            row_cells = rows.get(target_row, [])
            for col in (11, 12):
                cell = next((c for c in row_cells if c.col == col), None)
                if not cell:
                    continue
                normalized = cell.normalized
                if not normalized:
                    continue
                if normalized in status_values:
                    parts.append(cell.value.strip())
                    coords.append(cell.coordinate)
                    break
                if col == 11 and cell.value.strip():
                    # Legacy V1 behaviour: trust column K even when value is non-canonical.
                    parts.append(cell.value.strip())
                    coords.append(cell.coordinate)
                    break
        if parts:
            return " ".join(parts), ", ".join(coords)
        return "", ""

    def _extract_telematics_complex(
        self,
        cells: List[GridCell],
        rows: Dict[int, List[GridCell]],
    ) -> Tuple[str, str]:
        # Real applications use two layouts for the telematics block:
        #   inline:    [label] | [«Наименование»] | [value]      (same row)
        #   stacked:   [label] | [«Наименование»]                (row N)
        #              ...     | [value]                          (row N+1 or +2)
        # We anchor on the «телемат» label and scan rightward columns first in
        # the same row, then in the following 1–3 rows, skipping sub-header labels.
        label_cell = next((cell for cell in cells if "телемат" in cell.normalized), None)
        if not label_cell:
            return "", ""
        sub_labels = {"наименование", "название", "модель", "марка", "конфигурация"}

        def is_value(cell: GridCell) -> bool:
            normalized = cell.normalized
            if not normalized or normalized in sub_labels:
                return False
            if self._looks_like_empty_or_label(cell.value):
                return False
            return True

        max_col_offset = 5
        # 1) Same row, to the right of the label.
        for cell in rows.get(label_cell.row, []):
            if cell.col <= label_cell.col or cell.col > label_cell.col + max_col_offset:
                continue
            if is_value(cell):
                return cell.value, cell.coordinate
        # 2) Rows below, columns to the right of the label.
        for row_offset in range(1, 4):
            for cell in rows.get(label_cell.row + row_offset, []):
                if cell.col <= label_cell.col or cell.col > label_cell.col + max_col_offset:
                    continue
                if is_value(cell):
                    return cell.value, cell.coordinate
        return "", ""

    def _build_warnings(self, data: Dict[str, Any], insured_objects: List[Dict[str, str]]) -> List[Dict[str, str]]:
        warnings: List[Dict[str, str]] = []
        required_checks = [
            ("client_name", MISSING_CLIENT, "Клиент не распознан."),
            ("inn", "", "ИНН не распознан."),
            ("dfa_number", MISSING_DFA, "Номер ДФА не распознан."),
            ("branch", "", "Филиал не распознан."),
            ("manager_name", "", "Менеджер не распознан."),
            ("vehicle_info", MISSING_VEHICLE, "Предмет лизинга не распознан."),
        ]
        for field_name, missing_value, message in required_checks:
            if data.get(field_name) == missing_value or not data.get(field_name):
                warnings.append({"level": "manual_required", "field": field_name, "message": message, "source": ""})

        if not data.get("insurance_period"):
            warnings.append(
                {
                    "level": "warning",
                    "field": "insurance_period",
                    "message": "Срок страхования не удалось привести к стандартному значению.",
                    "source": "",
                }
            )

        if insured_objects:
            warnings.append(
                {
                    "level": "info",
                    "field": "insured_objects",
                    "message": f"Найдено объектов: {len(insured_objects)}.",
                    "source": "",
                }
            )

        return warnings

    def _build_notes(self, warnings: List[Dict[str, str]]) -> str:
        if not warnings:
            return "Создано через Parser V2. Данные распознаны без критичных предупреждений."
        lines = ["Создано через Parser V2. Проверьте предупреждения разбора:"]
        lines.extend(f"- {warning['message']}" for warning in warnings if warning.get("level") != "info")
        return "\n".join(lines).strip()

    def _calculate_confidence(self, data: Dict[str, Any], insured_objects: List[Dict[str, str]]) -> float:
        checks = [
            bool(data.get("client_name") and data["client_name"] != MISSING_CLIENT),
            bool(data.get("inn")),
            bool(data.get("dfa_number") and data["dfa_number"] != MISSING_DFA),
            bool(data.get("branch")),
            bool(data.get("manager_name")),
            bool(insured_objects),
            data.get("insurance_type") != "другое",
            bool(data.get("insurance_period")),
        ]
        return round(sum(checks) / len(checks), 2)

    def _vehicle_summary(self, insured_objects: List[Dict[str, str]]) -> str:
        if not insured_objects:
            return MISSING_VEHICLE
        descriptions = [obj["description"] for obj in insured_objects if obj.get("description")]
        if len(descriptions) == 1:
            return descriptions[0][:1000]
        return "\n".join(descriptions[:8])[:1000]

    def _detect_application_format(self, data: Dict[str, Any]) -> str:
        if data.get("insurance_type") == "страхование имущества":
            return "property"
        return "casco_equipment"

    def _detect_application_type(self, cells: List[GridCell]) -> str:
        text = " ".join(cell.normalized for cell in cells[:120])
        if "индивидуальн" in text or re.search(r"\bип\b", text):
            return "individual_entrepreneur"
        return "legal_entity"

    def _matches_any_group(self, text: str, groups: List[Tuple[str, ...]]) -> bool:
        return any(all(normalize_text(word) in text for word in group) for group in groups)

    def _row_matches(self, row_cells: List[GridCell], labels: List[str]) -> bool:
        row_norm = normalize_text(self._row_text(row_cells))
        return any(label in row_norm for label in labels)

    def _inline_value_after_label(self, value: str) -> str:
        if ":" not in value:
            return ""
        before, after = value.split(":", 1)
        if len(normalize_text(before)) > 60:
            return ""
        after = clean_value(after)
        return after if len(after) > 1 else ""

    def _first_value_right(self, rows: Dict[int, List[GridCell]], cell: GridCell, max_offset: int = 8) -> Optional[GridCell]:
        same_row = rows.get(cell.row, [])
        for offset in range(1, max_offset + 1):
            candidate = next((item for item in same_row if item.col == cell.col + offset), None)
            if candidate and not self._looks_like_empty_or_label(candidate.value):
                return candidate
        return None

    def _first_value_below(self, rows: Dict[int, List[GridCell]], cell: GridCell, max_rows: int = 3) -> Optional[GridCell]:
        for row_number in range(cell.row + 1, cell.row + max_rows + 1):
            same_column = next((item for item in rows.get(row_number, []) if item.col == cell.col), None)
            if same_column and not self._looks_like_empty_or_label(same_column.value):
                return same_column
        return None

    def _looks_like_empty_or_label(self, value: str) -> bool:
        normalized = normalize_text(value)
        if not normalized:
            return True
        label_words = [
            "страхователь",
            "лизингополучатель",
            "менеджер",
            "инн",
            "филиал",
            "объект",
            "предмет",
            "наименование",
        ]
        return normalized in label_words

    def _looks_like_client_name(self, value: str) -> bool:
        normalized = normalize_text(value)
        if len(normalized) < 3:
            return False
        blocked_values = {
            "лизингодатель",
            "лизингополучатель",
            "страхователь",
            "клиент",
            "наименование лизингополучателя",
        }
        if normalized in blocked_values:
            return False
        return "адрес" not in normalized

    def _cell_by_coordinate(self, cells: List[GridCell], coordinate: str) -> Optional[GridCell]:
        if not coordinate:
            return None
        return next((cell for cell in cells if cell.coordinate.upper() == coordinate.upper()), None)

    def _normalize_inn(self, value: str) -> str:
        match = re.search(r"\b\d{10}(\d{2})?\b", clean_value(value))
        return match.group(0) if match else ""

    def _row_text(self, row_cells: List[GridCell]) -> str:
        return " ".join(cell.value for cell in row_cells if cell.value).strip()

    def _row_source(self, row_cells: List[GridCell]) -> str:
        if not row_cells:
            return ""
        return f"{row_cells[0].coordinate}:{row_cells[-1].coordinate}"

    def _is_object_header_or_label(self, row_norm: str) -> bool:
        if any(label in row_norm for label in ["предмет лизинга", "объект страхования"]):
            return True
        header_hits = ["наименование", "год", "стоимость", "vin", "заводской", "серийный"]
        return sum(1 for item in header_hits if item in row_norm) >= 2

    def _is_object_template_row(self, row_norm: str) -> bool:
        return any(marker in row_norm for marker in OBJECT_TEMPLATE_ROW_MARKERS)

    def _is_object_stop_row(self, row_norm: str) -> bool:
        return any(
            marker in row_norm
            for marker in [
                "условия страхования",
                "страховая сумма",
                "франшиз",
                "порядок оплаты",
                "график платеж",
                "дополнительные условия",
                "противоугонные системы и оборудование",
            ]
        )

    def _year_from_text(self, text: str) -> str:
        match = re.search(r"\b(19\d{2}|20\d{2})\b", clean_value(text))
        return match.group(1) if match else ""

    def _contains_any(self, cells: List[GridCell], markers: List[str]) -> bool:
        full_text = " ".join(cell.normalized for cell in cells)
        return any(normalize_text(marker) in full_text for marker in markers)

    def _first_source_containing(self, cells: List[GridCell], markers: List[str]) -> str:
        normalized_markers = [normalize_text(marker) for marker in markers]
        for cell in cells:
            if any(marker in cell.normalized for marker in normalized_markers):
                return cell.coordinate
        return ""

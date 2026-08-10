"""Repeatable forensic checks for the company-method source workbook.

The script reads XLSX as ZIP/XML and never executes workbook formulas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL_NS = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}
EXPECTED_SHEETS = ["Lista zagrożeń", "form_ Risk_Score", "form czynniki mierzalne", "form_chemia", "OWAS", "EJMS"]


def audit(path: Path, specs_root: Path) -> dict[str, object]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = json.loads((specs_root / "manifest.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"].lstrip("/") for item in relationships.findall("p:Relationship", REL_NS)}
        sheets = []
        sheet_paths = {}
        for item in workbook.findall("m:sheets/m:sheet", NS):
            name = item.attrib["name"]
            target = targets[item.attrib[f"{{{NS['r']}}}id"]]
            sheet_paths[name] = target if target.startswith("xl/") else f"xl/{target}"
            sheets.append(name)
        shared = _shared_strings(archive)
        comments = sorted(ref for name in archive.namelist() if name.startswith("xl/comments") and name.endswith(".xml") for ref in _comment_refs(archive.read(name)))
        media_count = sum(name.startswith("xl/media/") and name.lower().endswith(".png") for name in archive.namelist())
        owas_cells = _cells(archive.read(sheet_paths["OWAS"]), shared)
        codes = [str(owas_cells.get(f"AB{row}", "")) for row in range(79, 331)]
        code_counts = Counter(codes)
        risk_formulas = _formulas(archive.read(sheet_paths["form_ Risk_Score"]))
        ejms_formulas = _formulas(archive.read(sheet_paths["EJMS"]))
    checks = {
        "hash_matches_manifest": digest == manifest["source_workbook_sha256"],
        "sheets_match": sheets == EXPECTED_SHEETS,
        "png_media_count_is_159": media_count == 159,
        "comment_count_is_4": len(comments) == 4,
        "owas_3133_is_duplicated": code_counts["3133"] == 2,
        "owas_expected_codes_are_missing": all(code_counts[code] == 0 for code in ("2133", "4173", "4373")),
        "owas_invalid_codes_are_present": all(code_counts[code] == 1 for code in ("7173", "7373")),
        "risk_value_formulas_are_missing": all(f"AI{row}" not in risk_formulas for row in range(6, 18)),
        "risk_category_refs_are_broken": sum("#REF!" in risk_formulas.get(f"AJ{row}", "") for row in range(6, 18)) == 11,
        "ejms_broken_reference_is_present": "Y1416" in ejms_formulas.get("S11", ""),
    }
    return {"workbook_sha256": digest, "sheets": sheets, "png_media_count": media_count, "comment_refs": comments, "checks": checks, "passed": all(checks.values())}


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(text.text or "" for text in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]


def _cells(xml: bytes, shared: list[str]) -> dict[str, object]:
    root = ET.fromstring(xml)
    result = {}
    for cell in root.findall(".//m:c", NS):
        ref = cell.attrib.get("r")
        value = cell.find("m:v", NS)
        if not ref or value is None or value.text is None:
            continue
        raw: object = value.text
        if cell.attrib.get("t") == "s":
            raw = shared[int(value.text)]
        elif cell.attrib.get("t") != "str":
            try:
                number = float(value.text)
                raw = int(number) if number.is_integer() else number
            except ValueError:
                pass
        result[ref] = raw
    return result


def _formulas(xml: bytes) -> dict[str, str]:
    root = ET.fromstring(xml)
    return {cell.attrib["r"]: formula.text or "" for cell in root.findall(".//m:c", NS) if (formula := cell.find("m:f", NS)) is not None}


def _comment_refs(xml: bytes) -> list[str]:
    root = ET.fromstring(xml)
    return [comment.attrib["ref"] for comment in root.findall(".//m:comment", NS)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit testy.xlsx against canonical company-method specs")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--specs", type=Path, default=Path(__file__).resolve().parents[2] / "method-specs")
    args = parser.parse_args()
    result = audit(args.workbook.resolve(), args.specs.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

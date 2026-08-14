"""Export the immutable Python RULA/REBA tables for the TypeScript scene adapter.

The Python assessment package remains the source of truth. Run with --check in
CI/tests to detect a stale generated artifact.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worker.src.assessment.rula import tables as rula  # noqa: E402
from worker.src.assessment.reba import tables as reba  # noqa: E402

TARGET = ROOT / "src/lib/scene-ergonomics/assessment-tables.generated.json"


def payload() -> dict[str, object]:
    return {
        "generated_from": "worker/src/assessment/{rula,reba}/tables.py",
        "rula": {"version": rula.TABLE_VERSION, "source_doi": rula.SOURCE_DOI, "table_a": rula.TABLE_A, "table_b": rula.TABLE_B, "table_c": rula.TABLE_C},
        "reba": {"version": reba.TABLE_VERSION, "source_doi": reba.SOURCE_DOI, "table_a": reba.TABLE_A, "table_b": reba.TABLE_B, "table_c": reba.TABLE_C},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(payload(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        return 0 if TARGET.exists() and TARGET.read_text(encoding="utf-8") == rendered else 1
    TARGET.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

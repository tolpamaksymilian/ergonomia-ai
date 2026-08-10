"""Compare two Pose diagnostics documents without claiming model accuracy."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


COMPARISON_FIELDS: tuple[tuple[str, ...], ...] = (
    ("tracking", "track_loss_count"),
    ("tracking", "reacquisition_count"),
    ("tracking", "invalid_bone_count"),
    ("body", "mean_valid_joint_ratio"),
    ("body", "invalid_bone_count"),
    ("hands", "left", "valid_ratio"),
    ("hands", "right", "valid_ratio"),
    ("hands", "assignment_switches"),
    ("hands", "finger_rejections"),
    ("holding", "left", "likely_holding_seconds"),
    ("holding", "right", "likely_holding_seconds"),
    ("holding", "bimanual", "likely_holding_seconds"),
    ("scene_cut_count",),
    ("refinement", "frames_reprocessed"),
    ("refinement", "frames_improved"),
    ("refinement", "mean_quality_gain"),
    ("refinement", "refinement_ratio"),
    ("runtime_seconds",),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Porównuje dwa pliki pose-diagnostics.json. Wynik opisuje różnice "
            "techniczne, a nie accuracy ani jakość względem ground truth."
        )
    )
    parser.add_argument("baseline", help="Diagnostyka bazowa.")
    parser.add_argument("candidate", help="Diagnostyka porównywana.")
    parser.add_argument("--json-output", help="Opcjonalny plik wyniku JSON.")
    return parser.parse_args()


def compare_diagnostics(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for path in COMPARISON_FIELDS:
        first = _finite_at(baseline, path)
        second = _finite_at(candidate, path)
        rows.append(
            {
                "field": ".".join(path),
                "baseline": first,
                "candidate": second,
                "delta": (
                    round(second - first, 6)
                    if first is not None and second is not None
                    else None
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "comparison_kind": "technical-diagnostics-delta",
        "accuracy_claimed": False,
        "baseline_worker_version": baseline.get("worker_version"),
        "candidate_worker_version": candidate.get("worker_version"),
        "metrics": rows,
        "baseline_warnings": _warnings(baseline),
        "candidate_warnings": _warnings(candidate),
    }


def main() -> int:
    arguments = parse_arguments()
    try:
        baseline_path = _input_path(arguments.baseline)
        candidate_path = _input_path(arguments.candidate)
        baseline = _read_document(baseline_path)
        candidate = _read_document(candidate_path)
        comparison = compare_diagnostics(baseline, candidate)
        if arguments.json_output:
            target = Path(arguments.json_output).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(comparison, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print("TECHNICAL DIAGNOSTICS COMPARISON")
        print("accuracy_claimed=false")
        for row in comparison["metrics"]:
            if isinstance(row, dict):
                print(
                    f"{row['field']}: baseline={row['baseline']} "
                    f"candidate={row['candidate']} delta={row['delta']}"
                )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        return 2


def _input_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"Plik nie istnieje albo jest pusty: {path}")
    return path


def _read_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Dokument musi być obiektem JSON: {path}")
    return value


def _finite_at(document: dict[str, Any], path: tuple[str, ...]) -> float | None:
    value: object = document
    for name in path:
        if not isinstance(value, dict):
            return None
        value = value.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _warnings(document: dict[str, Any]) -> list[str]:
    quality = document.get("quality")
    values = quality.get("warning_codes") if isinstance(quality, dict) else None
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


if __name__ == "__main__":
    raise SystemExit(main())

"""Small offline KPI report for before/after Pose JSON comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


KPI_NAMES = (
    "main_skeleton_render_coverage_ratio",
    "single_frame_bone_flicker_count",
    "joint_jump_event_count",
    "bone_length_stability_error",
    "angle_outlier_count",
    "angle_usable_coverage_ratio",
    "grip_valid_coverage_ratio",
    "left_hand_grip_coverage_ratio",
    "right_hand_grip_coverage_ratio",
    "overlay_label_overlap_count",
    "overlay_label_readability_score",
    "overlay_main_metric_visibility_ratio",
)


def collect_quality_kpis(document: Mapping[str, Any]) -> dict[str, int | float | None]:
    """Find the public quality KPIs without assuming one summary nesting level."""
    output: dict[str, int | float | None] = {name: None for name in KPI_NAMES}

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in output and output[key] is None and isinstance(item, (int, float)) and not isinstance(item, bool):
                    output[key] = item
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(document.get("summary", document))
    return output


def compare_quality_documents(
    candidate: Mapping[str, Any], baseline: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    candidate_kpis = collect_quality_kpis(candidate)
    baseline_kpis = collect_quality_kpis(baseline) if baseline is not None else None
    deltas = None
    if baseline_kpis is not None:
        deltas = {
            name: round(float(candidate_kpis[name]) - float(baseline_kpis[name]), 6)
            if candidate_kpis[name] is not None and baseline_kpis[name] is not None else None
            for name in KPI_NAMES
        }
    return {"candidate": candidate_kpis, "baseline": baseline_kpis, "delta": deltas}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Pose V6 quality KPIs")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("baseline", type=Path, nargs="?")
    args = parser.parse_args(argv)
    try:
        candidate = _read_document(args.candidate)
        baseline = _read_document(args.baseline) if args.baseline else None
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.exit(2, f"quality benchmark error: {error}\n")
    print(json.dumps(compare_quality_documents(candidate, baseline), ensure_ascii=False, indent=2))
    return 0


def _read_document(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

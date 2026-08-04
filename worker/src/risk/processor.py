"""Public orchestration API for Risk Engine V1."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .evaluator import (
    aggregate_overall,
    aggregate_zones,
    calculate_data_coverage,
    classify_frames,
    select_key_frames,
    summarize_metrics,
)
from .exposure import resolve_frame_timing
from .profile import load_risk_profile
from .schemas import MetricsValidationError, RiskProfile


SUPPORTED_METRICS_SCHEMAS = frozenset({"1.0"})
SUPPORTED_METRICS_VERSIONS = frozenset({"ergonomics-metrics-v1.0"})
RISK_ENGINE_VERSION = "risk-engine-v1.0"


def process_risk_document(
    metrics_document: dict[str, Any],
    profile_document: dict[str, Any],
) -> dict[str, Any]:
    """Validate both documents and build a deterministic risk assessment."""

    frames, analysis_id, metrics_version = _validate_metrics_document(
        metrics_document
    )
    profile = load_risk_profile(profile_document)
    _validate_profile_compatibility(frames, profile)

    fps = _extract_fps(metrics_document)
    timing = resolve_frame_timing(frames, fps)
    classified_frames = classify_frames(frames, profile)
    metric_summaries = summarize_metrics(classified_frames, profile, timing)
    zones = aggregate_zones(metric_summaries, profile)
    coverage = calculate_data_coverage(classified_frames, profile)
    overall = aggregate_overall(metric_summaries, zones, profile, coverage)
    key_frames = select_key_frames(classified_frames, profile, timing)
    enabled_metric_count = sum(
        metric.enabled for metric in profile.metrics.values()
    )

    return {
        "schema_version": "1.0",
        "generated_by": "Ergonomia AI Risk Engine",
        "risk_engine_version": RISK_ENGINE_VERSION,
        "analysis_id": analysis_id,
        "source_metrics_version": metrics_version,
        "profile": {
            "profile_id": profile.profile_id,
            "profile_name": profile.profile_name,
            "profile_version": profile.profile_version,
            "status": profile.status,
            "normative_method": profile.normative_method,
        },
        "configuration": {
            "normative_scoring_enabled": False,
            "rula_enabled": False,
            "reba_enabled": False,
        },
        "data_quality": {
            "frame_count": len(frames),
            "enabled_metric_count": enabled_metric_count,
            "valid_metric_coverage": round(coverage, 6),
            "timing_method": timing.method,
            "timing_fallback_used": timing.fallback_used,
            "timing_fallback_reason": timing.fallback_reason,
        },
        "overall": overall,
        "zones": zones,
        "metrics": metric_summaries,
        "frames": classified_frames,
        "key_frames": key_frames,
        "limitations": _limitations(profile, timing.method),
    }


def process_risk_file(
    metrics_path: str | Path,
    profile_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Read input files, process them and write UTF-8 JSON without NaN values."""

    metrics_file = Path(metrics_path)
    profile_file = Path(profile_path)
    output_file = Path(output_path)
    metrics_document = _read_json_object(metrics_file, "metrics")
    profile_document = _read_json_object(profile_file, "profile")
    result = process_risk_document(metrics_document, profile_document)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return result


def _validate_metrics_document(
    document: object,
) -> tuple[list[dict[str, Any]], str, str]:
    if not isinstance(document, dict):
        raise MetricsValidationError("Dokument metryk musi być obiektem JSON.")
    schema_version = document.get("schema_version")
    if schema_version not in SUPPORTED_METRICS_SCHEMAS:
        raise MetricsValidationError(
            f"Nieobsługiwana schema_version metryk: {schema_version!r}."
        )
    metrics_version = document.get("metrics_version")
    if metrics_version not in SUPPORTED_METRICS_VERSIONS:
        raise MetricsValidationError(
            f"Nieobsługiwana metrics_version: {metrics_version!r}."
        )
    analysis_id = document.get("analysis_id")
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise MetricsValidationError("Brak poprawnego analysis_id w dokumencie metryk.")
    if not isinstance(document.get("summary"), dict):
        raise MetricsValidationError("Dokument metryk musi zawierać summary jako obiekt.")
    raw_frames = document.get("frames")
    if not isinstance(raw_frames, list):
        raise MetricsValidationError("Dokument metryk musi zawierać tablicę frames.")
    if not raw_frames:
        raise MetricsValidationError("Dokument metryk zawiera pustą listę frames.")
    frames: list[dict[str, Any]] = []
    for index, frame in enumerate(raw_frames):
        if not isinstance(frame, dict):
            raise MetricsValidationError(f"frames[{index}] musi być obiektem JSON.")
        frames.append(frame)
    return frames, analysis_id.strip(), str(metrics_version)


def _validate_profile_compatibility(
    frames: list[dict[str, Any]],
    profile: RiskProfile,
) -> None:
    available: set[str] = set()
    for frame in frames:
        raw_metrics = frame.get("metrics")
        if isinstance(raw_metrics, dict):
            available.update(
                name for name in raw_metrics if isinstance(name, str)
            )
    missing = sorted(
        name
        for name, metric in profile.metrics.items()
        if metric.enabled and name not in available
    )
    if missing:
        raise MetricsValidationError(
            "Profil odwołuje się do metryk nieobecnych w całym dokumencie: "
            + ", ".join(missing)
        )


def _extract_fps(document: dict[str, Any]) -> float | None:
    candidates = [document.get("fps")]
    source = document.get("source")
    if isinstance(source, dict):
        candidates.append(source.get("fps"))
    configuration = document.get("configuration")
    if isinstance(configuration, dict):
        candidates.append(configuration.get("source_fps"))
    for value in candidates:
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0
        ):
            return float(value)
    return None


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise MetricsValidationError(f"Plik {label} nie istnieje: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except json.JSONDecodeError as error:
        raise MetricsValidationError(
            f"Niepoprawny JSON w pliku {label}: {error.msg}."
        ) from error
    if not isinstance(document, dict):
        raise MetricsValidationError(f"Plik {label} musi zawierać obiekt JSON.")
    return document


def _limitations(profile: RiskProfile, timing_method: str) -> list[str]:
    limitations = [
        "analysis_based_on_2d_video",
        "occluded_body_parts_may_be_missing",
        "result_is_technical_screening",
        "specialist_review_required",
    ]
    if profile.status in {"development", "draft"}:
        limitations.append("development_profile_used")
    if timing_method == "fps_fallback":
        limitations.append("frame_timestamps_replaced_with_fps_fallback")
    elif timing_method == "unavailable":
        limitations.append("exposure_timing_unavailable")
    return limitations

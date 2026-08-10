"""Transparent frame, metric, zone and overall evaluation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .exposure import (
    TimingInfo,
    calculate_exposure,
    cumulative_exposure_ratio,
    longest_sequence_seconds,
)
from .profile import level_for_normalized_score, select_band
from .schemas import (
    BandLevel,
    MetricProfile,
    RISK_LEVELS,
    RISK_SEVERITY,
    RiskProfile,
)


def classify_frames(
    frames: Sequence[dict[str, Any]],
    profile: RiskProfile,
) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    active_metrics = {
        name: metric for name, metric in profile.metrics.items() if metric.enabled
    }
    for frame in frames:
        raw_metrics = frame.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
        frame_result = {
            "source_frame_index": _integer_or_none(frame.get("source_frame_index")),
            "output_frame_index": _integer_or_none(frame.get("output_frame_index")),
            "timestamp": _finite_or_none(frame.get("timestamp")),
            "source_timestamp_seconds": _finite_or_none(
                frame.get("source_timestamp_seconds")
            ),
            "output_timestamp_seconds": _finite_or_none(
                frame.get("output_timestamp_seconds")
            ),
            "timestamp_seconds": _first_frame_timestamp(frame),
            "person_detected": (
                frame.get("person_detected")
                if isinstance(frame.get("person_detected"), bool)
                else None
            ),
            "metrics": {},
        }
        output_metrics: dict[str, Any] = frame_result["metrics"]
        for name, metric_profile in active_metrics.items():
            output_metrics[name] = evaluate_frame_metric(
                name,
                metrics.get(name),
                metric_profile,
            )
        classified.append(frame_result)
    return classified


def evaluate_frame_metric(
    metric_name: str,
    raw_metric: object,
    profile: MetricProfile,
) -> dict[str, Any]:
    invalid = _validate_frame_metric(raw_metric)
    if invalid is not None:
        quality, reason = invalid
        return {
            "metric_name": metric_name,
            "value": None,
            "valid": False,
            "quality": quality,
            "level": "insufficient_data",
            "score": None,
            "weight": profile.weight,
            "weighted_score": None,
            "band": None,
            "rejection_reason": reason,
        }

    raw = raw_metric
    assert isinstance(raw, Mapping)
    value = float(raw["value"])
    quality = float(raw["quality"])
    band = select_band(profile, value)
    return {
        "metric_name": metric_name,
        "value": value,
        "valid": True,
        "quality": quality,
        "level": band.level,
        "score": band.score,
        "weight": profile.weight,
        "weighted_score": round(band.score * profile.weight, 6),
        "band": {"minimum": band.minimum, "maximum": band.maximum},
        "rejection_reason": None,
    }


def summarize_metrics(
    classified_frames: Sequence[dict[str, Any]],
    profile: RiskProfile,
    timing: TimingInfo,
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for name, metric_profile in profile.metrics.items():
        if not metric_profile.enabled:
            summaries[name] = _disabled_metric_summary(name)
            continue

        results = [frame["metrics"][name] for frame in classified_frames]
        valid_flags = [bool(result["valid"]) for result in results]
        levels = [str(result["level"]) for result in results]
        values = [float(result["value"]) for result in results if result["valid"]]
        valid_frames = len(values)
        invalid_frames = len(results) - valid_frames
        valid_ratio = valid_frames / len(results) if results else 0.0
        exposure = calculate_exposure(levels, valid_flags, timing)
        statistics = _value_statistics(
            values,
            profile.summary_rule.percentile_for_summary,
        )
        data_quality = _data_quality(valid_ratio, metric_profile.minimum_valid_ratio)
        final_level, final_score, reasons = _metric_final_decision(
            metric_profile,
            valid_ratio,
            levels,
            valid_flags,
            values,
            timing,
            profile,
        )
        summaries[name] = {
            "metric_name": name,
            "enabled": True,
            "valid_frames": valid_frames,
            "invalid_frames": invalid_frames,
            "valid_ratio": round(valid_ratio, 6),
            "data_quality": data_quality,
            "value_statistics": statistics,
            "exposure": exposure,
            "final_level": final_level,
            "final_score": final_score,
            "weighted_score": (
                round(final_score * metric_profile.weight, 6)
                if final_score is not None
                else None
            ),
            "decision_reasons": reasons,
        }
    return summaries


def aggregate_zones(
    metric_summaries: Mapping[str, dict[str, Any]],
    profile: RiskProfile,
) -> dict[str, dict[str, Any]]:
    zones: dict[str, dict[str, Any]] = {}
    for zone_name, names in profile.zones.items():
        active_names = [name for name in names if profile.metrics[name].enabled]
        sufficient_names = [
            name
            for name in active_names
            if metric_summaries[name]["final_level"] not in {
                "insufficient_data",
                "disabled",
            }
        ]
        active_count = len(active_names)
        sufficient_count = len(sufficient_names)
        coverage = sufficient_count / active_count if active_count else 0.0
        insufficient_count = active_count - sufficient_count
        reasons: list[str] = []

        if active_count == 0:
            level = "insufficient_data"
            reasons.append("zone_has_no_active_metrics")
        elif insufficient_count > active_count / 2:
            level = "insufficient_data"
            reasons.append("majority_of_zone_metrics_insufficient")
        else:
            level = max(
                (metric_summaries[name]["final_level"] for name in sufficient_names),
                key=lambda item: RISK_SEVERITY[item],
                default="insufficient_data",
            )
            reasons.append(f"highest_metric_level_{level}")

        weighted_sum = sum(
            float(metric_summaries[name]["weighted_score"])
            for name in sufficient_names
            if metric_summaries[name]["weighted_score"] is not None
        )
        maximum_weighted = sum(
            profile.metrics[name].maximum_score * profile.metrics[name].weight
            for name in sufficient_names
        )
        normalized = (
            min(1.0, max(0.0, weighted_sum / maximum_weighted))
            if maximum_weighted > 0
            else 0.0
        )
        zones[zone_name] = {
            "active_metrics": active_count,
            "metrics_with_sufficient_data": sufficient_count,
            "coverage": round(coverage, 6),
            "highest_level": level,
            "weighted_score_sum": round(weighted_sum, 6),
            "normalized_score": round(normalized, 6),
            "decision_reasons": reasons,
        }
    return zones


def aggregate_overall(
    metric_summaries: Mapping[str, dict[str, Any]],
    zones: Mapping[str, dict[str, Any]],
    profile: RiskProfile,
    data_coverage: float,
) -> dict[str, Any]:
    evaluated_zones = [
        name
        for name, zone in zones.items()
        if zone["highest_level"] != "insufficient_data"
    ]
    insufficient_zones = [
        name
        for name, zone in zones.items()
        if zone["highest_level"] == "insufficient_data"
    ]
    reasons: list[str] = []
    if data_coverage < profile.overall.minimum_data_coverage:
        reasons.append("overall_data_coverage_below_minimum")
    if not evaluated_zones:
        reasons.append("no_zones_with_sufficient_data")
    if reasons:
        return {
            "overall_level": "insufficient_data",
            "overall_score": None,
            "data_coverage": round(data_coverage, 6),
            "evaluated_zones": evaluated_zones,
            "insufficient_zones": insufficient_zones,
            "highest_risk_zones": [],
            "decision_reasons": reasons,
        }

    sufficient_metrics = [
        name
        for name, summary in metric_summaries.items()
        if summary["enabled"] and summary["final_level"] != "insufficient_data"
    ]
    weighted_sum = sum(
        float(metric_summaries[name]["weighted_score"])
        for name in sufficient_metrics
        if metric_summaries[name]["weighted_score"] is not None
    )
    maximum_weighted = sum(
        profile.metrics[name].maximum_score * profile.metrics[name].weight
        for name in sufficient_metrics
    )
    normalized = (
        min(1.0, max(0.0, weighted_sum / maximum_weighted))
        if maximum_weighted > 0
        else 0.0
    )
    overall_level = level_for_normalized_score(profile.overall, normalized)
    reasons.append("weighted_average_applied")

    peak = profile.overall.peak_guard
    if peak.enabled:
        triggering_metrics = [
            name
            for name in sufficient_metrics
            if RISK_SEVERITY[metric_summaries[name]["final_level"]]
            >= RISK_SEVERITY[peak.minimum_level]
            and _summary_cumulative_ratio(metric_summaries[name], peak.minimum_level)
            >= peak.minimum_exposure_ratio
        ]
        if triggering_metrics and RISK_SEVERITY[overall_level] < RISK_SEVERITY[
            peak.minimum_level
        ]:
            overall_level = peak.minimum_level
            reasons.append(f"peak_guard_promoted_to_{peak.minimum_level}")

    highest_severity = max(
        RISK_SEVERITY[zones[name]["highest_level"]] for name in evaluated_zones
    )
    highest_zones = [
        name
        for name in evaluated_zones
        if RISK_SEVERITY[zones[name]["highest_level"]] == highest_severity
    ]
    return {
        "overall_level": overall_level,
        "overall_score": round(normalized, 6),
        "data_coverage": round(data_coverage, 6),
        "evaluated_zones": evaluated_zones,
        "insufficient_zones": insufficient_zones,
        "highest_risk_zones": highest_zones,
        "decision_reasons": reasons,
    }


def select_key_frames(
    frames: Sequence[dict[str, Any]],
    profile: RiskProfile,
    timing: TimingInfo,
) -> list[dict[str, Any]]:
    zone_by_metric = {
        metric_name: zone
        for zone, names in profile.zones.items()
        for metric_name in names
    }
    candidates: list[tuple[int, float, float, int, str, dict[str, Any]]] = []
    for frame_index, frame in enumerate(frames):
        for metric_name, result in frame["metrics"].items():
            if result["level"] not in {"high", "critical"}:
                continue
            candidates.append(
                (
                    RISK_SEVERITY[result["level"]],
                    float(result["weighted_score"]),
                    float(result["quality"]),
                    frame_index,
                    metric_name,
                    result,
                )
            )
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

    selected: list[dict[str, Any]] = []
    per_metric: dict[str, int] = {}
    used_frames: set[tuple[int | None, int | None]] = set()
    selected_times: list[float] = []
    minimum_gap = profile.key_frames.minimum_time_separation_seconds
    for _, _, _, frame_index, metric_name, result in candidates:
        if per_metric.get(metric_name, 0) >= 3:
            continue
        frame = frames[frame_index]
        frame_key = (frame["source_frame_index"], frame["output_frame_index"])
        if frame_key in used_frames:
            continue
        timestamp = timing.timeline_seconds[frame_index]
        if timestamp is not None and any(
            abs(timestamp - existing) < minimum_gap for existing in selected_times
        ):
            continue
        selected.append(
            {
                "source_frame_index": frame["source_frame_index"],
                "output_frame_index": frame["output_frame_index"],
                "timestamp_seconds": (
                    round(timestamp, 6) if timestamp is not None else None
                ),
                "metric_name": metric_name,
                "zone": zone_by_metric[metric_name],
                "value": result["value"],
                "level": result["level"],
                "weighted_score": result["weighted_score"],
                "quality": result["quality"],
            }
        )
        per_metric[metric_name] = per_metric.get(metric_name, 0) + 1
        used_frames.add(frame_key)
        if timestamp is not None:
            selected_times.append(timestamp)
        if len(selected) == 10:
            break
    return selected


def calculate_data_coverage(
    frames: Sequence[dict[str, Any]],
    profile: RiskProfile,
) -> float:
    enabled_count = sum(metric.enabled for metric in profile.metrics.values())
    possible = len(frames) * enabled_count
    if possible == 0:
        return 0.0
    valid = sum(
        1
        for frame in frames
        for result in frame["metrics"].values()
        if result["valid"]
    )
    return min(1.0, max(0.0, valid / possible))


def _metric_final_decision(
    metric: MetricProfile,
    valid_ratio: float,
    levels: Sequence[str],
    valid_flags: Sequence[bool],
    values: Sequence[float],
    timing: TimingInfo,
    profile: RiskProfile,
) -> tuple[str, float | None, list[str]]:
    if valid_ratio < metric.minimum_valid_ratio:
        return "insufficient_data", None, ["valid_ratio_below_minimum"]
    if timing.method == "unavailable":
        return "insufficient_data", None, ["timing_data_unavailable"]
    if not values:
        return "insufficient_data", None, ["no_valid_metric_values"]

    percentile_value = _percentile(values, profile.summary_rule.percentile_for_summary)
    percentile_level = select_band(metric, percentile_value).level
    reasons = [f"percentile_band_{percentile_level}"]
    final_level: BandLevel = "low"
    for candidate in ("critical", "high", "moderate"):
        cumulative_ratio = cumulative_exposure_ratio(
            levels,
            valid_flags,
            timing,
            candidate,
        )
        longest = longest_sequence_seconds(
            levels,
            valid_flags,
            timing,
            candidate,
            exact=False,
        )
        ratio_met = (
            cumulative_ratio > 0
            and cumulative_ratio >= profile.summary_rule.minimum_exposure_ratio
        )
        sequence_met = (
            longest > 0
            and longest >= profile.summary_rule.minimum_sequence_seconds
        )
        if ratio_met or sequence_met:
            final_level = candidate
            if ratio_met:
                reasons.append(f"{candidate}_exposure_ratio_exceeded")
            if sequence_met:
                reasons.append("minimum_sequence_duration_exceeded")
            break
    if final_level == "low":
        reasons.append("no_persistent_elevated_exposure")
    return final_level, _score_for_level(metric, final_level), reasons


def _summary_cumulative_ratio(summary: Mapping[str, Any], minimum_level: str) -> float:
    exposure = summary["exposure"]
    severity = RISK_SEVERITY[minimum_level]
    return min(
        1.0,
        sum(
            float(exposure.get(f"{level}_exposure_ratio", 0.0))
            for level in ("moderate", "high", "critical")
            if RISK_SEVERITY[level] >= severity
        ),
    )


def _validate_frame_metric(raw_metric: object) -> tuple[float, str] | None:
    if not isinstance(raw_metric, Mapping):
        return 0.0, "missing_metric"
    valid = raw_metric.get("valid")
    if not isinstance(valid, bool):
        return 0.0, "invalid_metric_contract"
    quality = _finite_or_none(raw_metric.get("quality"))
    if quality is None or not 0.0 <= quality <= 1.0:
        return 0.0, "invalid_quality"
    if not valid:
        reason = raw_metric.get("rejection_reason")
        return quality, reason if isinstance(reason, str) and reason else "invalid_metric"
    value = _finite_or_none(raw_metric.get("value"))
    if value is None:
        return quality, "invalid_metric_value"
    return None


def _value_statistics(values: Sequence[float], percentile: float) -> dict[str, Any]:
    if not values:
        return {
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
            "percentile": None,
            "percentile_used": percentile,
        }
    ordered = sorted(values)
    return {
        "mean": round(sum(ordered) / len(ordered), 6),
        "median": round(_percentile(ordered, 50.0), 6),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "percentile": round(_percentile(ordered, percentile), 6),
        "percentile_used": percentile,
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _score_for_level(metric: MetricProfile, level: BandLevel) -> float:
    return next(band.score for band in metric.bands if band.level == level)


def _data_quality(valid_ratio: float, minimum_valid_ratio: float) -> str:
    if valid_ratio >= minimum_valid_ratio:
        return "sufficient"
    if valid_ratio > 0:
        return "limited"
    return "insufficient"


def _disabled_metric_summary(name: str) -> dict[str, Any]:
    return {
        "metric_name": name,
        "enabled": False,
        "valid_frames": 0,
        "invalid_frames": 0,
        "valid_ratio": 0.0,
        "data_quality": "insufficient",
        "value_statistics": None,
        "exposure": None,
        "final_level": "disabled",
        "final_score": None,
        "weighted_score": None,
        "decision_reasons": ["metric_disabled_in_profile"],
    }


def _finite_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _integer_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _first_frame_timestamp(frame: Mapping[str, Any]) -> float | None:
    for name in (
        "source_timestamp_seconds",
        "timestamp",
        "output_timestamp_seconds",
    ):
        value = _finite_or_none(frame.get(name))
        if value is not None:
            return value
    return None

"""Deterministic assembly of an Analysis Report V1 document."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .schemas import (
    REPORT_SCHEMA_VERSION,
    REPORT_VERSION,
    RISK_LEVELS,
    finite_number,
    optional_text,
    ratio,
    required_mapping,
    required_text,
    validate_report_inputs,
)


DISCLAIMER = (
    "System wspiera analizę ergonomii i nie zastępuje oceny specjalisty."
)
METRIC_LIMIT = 8
SEVERITY = {
    "critical": 4,
    "high": 3,
    "moderate": 2,
    "low": 1,
    "insufficient_data": 0,
    "disabled": -1,
}
LEVEL_LABELS = {
    "critical": "krytyczny",
    "high": "wysoki",
    "moderate": "umiarkowany",
    "low": "niski",
    "insufficient_data": "niewystarczające dane",
}
ZONE_LABELS = {
    "neck": "Szyja",
    "trunk": "Tułów",
    "left_upper_limb": "Lewa kończyna górna",
    "right_upper_limb": "Prawa kończyna górna",
    "left_hand": "Lewa dłoń",
    "right_hand": "Prawa dłoń",
}
METRIC_LABELS = {
    "trunk_inclination_deg": "Pochylenie tułowia",
    "neck_flexion_deg": "Zgięcie szyi",
    "left_upper_arm_elevation_deg": "Elewacja lewego ramienia",
    "right_upper_arm_elevation_deg": "Elewacja prawego ramienia",
    "left_elbow_flexion_deg": "Zgięcie lewego łokcia",
    "right_elbow_flexion_deg": "Zgięcie prawego łokcia",
    "left_forearm_inclination_deg": "Pochylenie lewego przedramienia",
    "right_forearm_inclination_deg": "Pochylenie prawego przedramienia",
    "left_wrist_flexion_deg": "Zgięcie lewego nadgarstka",
    "right_wrist_flexion_deg": "Zgięcie prawego nadgarstka",
    "left_hand_closure_ratio": "Zamknięcie lewej dłoni",
    "right_hand_closure_ratio": "Zamknięcie prawej dłoni",
    "left_pinch_distance_ratio": "Chwyt lewej dłoni",
    "right_pinch_distance_ratio": "Chwyt prawej dłoni",
}


def build_analysis_report(
    analysis: Mapping[str, Any],
    ergonomics: Mapping[str, Any],
    risk: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a report without rerunning metrics or risk classification."""

    analysis_id = validate_report_inputs(analysis, ergonomics, risk)
    generated_at_value = generated_at or datetime.now(timezone.utc).isoformat()
    profile = required_mapping(risk.get("profile"), "risk.profile")
    overall = required_mapping(risk.get("overall"), "risk.overall")
    risk_quality = required_mapping(risk.get("data_quality"), "risk.data_quality")
    overall_level = required_text(overall.get("overall_level"), "overall_level")
    valid_metric_ratio = ratio(
        risk_quality.get("valid_metric_coverage"), "valid_metric_coverage"
    )
    insufficient_data = overall_level == "insufficient_data"
    dominant_metrics = _dominant_metrics(risk)
    dominant_zones = _text_list(overall.get("highest_risk_zones"))
    key_moments = _key_moments(risk)

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_by": "Ergonomia AI Report Engine",
        "report_version": REPORT_VERSION,
        "generated_at": generated_at_value,
        "analysis": _analysis_section(analysis, analysis_id, risk_quality),
        "processing": _processing_section(analysis, ergonomics, risk),
        "data_quality": _quality_section(
            analysis,
            ergonomics,
            risk_quality,
            valid_metric_ratio,
            insufficient_data,
        ),
        "risk_summary": {
            "overall_level": overall_level,
            "overall_status": "insufficient_data" if insufficient_data else "classified",
            "insufficient_data": insufficient_data,
            "profile": {
                "profile_id": required_text(profile.get("profile_id"), "profile_id"),
                "profile_name": required_text(profile.get("profile_name"), "profile_name"),
                "profile_version": required_text(
                    profile.get("profile_version"), "profile_version"
                ),
                "profile_status": required_text(profile.get("status"), "profile_status"),
                "normative_method": optional_text(profile.get("normative_method")),
            },
            "dominant_zones": dominant_zones,
            "dominant_metrics": [item["metric_name"] for item in dominant_metrics[:5]],
            "key_frames_count": len(key_moments),
            "valid_metric_ratio": valid_metric_ratio,
        },
        "body_areas": _body_areas(risk),
        "metric_summary": _metric_summary(ergonomics, risk),
        "key_moments": key_moments,
        "observations": _observations(
            overall_level,
            dominant_zones,
            _text_list(overall.get("insufficient_zones")),
        ),
        "limitations": _limitations(risk, str(profile.get("status"))),
        "disclaimer": DISCLAIMER,
    }
    hand_activity = _hand_activity(ergonomics)
    if hand_activity is not None:
        report["hand_activity"] = hand_activity
        report["holding_activity"] = hand_activity
    movement = _movement_features(ergonomics)
    if movement is not None:
        report["movement_features"] = movement
    source_quality = _source_quality(ergonomics)
    if source_quality is not None:
        report["pose_quality"] = source_quality
    posture_duration = ergonomics.get("posture_duration")
    if isinstance(posture_duration, Mapping):
        report["posture_duration"] = dict(posture_duration)
    report["limitations"] = list(
        dict.fromkeys(
            [
                *report["limitations"],
                *_pose_quality_limitations(ergonomics),
                *_text_list(ergonomics.get("quality_limitations")),
            ]
        )
    )
    return report


def _movement_features(ergonomics: Mapping[str, Any]) -> dict[str, Any] | None:
    source = ergonomics.get("movement_features")
    if not isinstance(source, Mapping):
        return None
    fields = (
        "valid_frames",
        "invalid_frames",
        "movement_range",
        "median_absolute_velocity",
        "percentile_95_absolute_velocity",
        "repetition_count",
        "repetition_frequency_per_minute",
        "cycle_count",
        "reversal_count",
        "cycles_per_minute",
        "range_of_motion",
        "peak_absolute_velocity",
        "longest_stable_posture_seconds",
        "valid_exposure_seconds",
    )
    output: dict[str, Any] = {}
    for metric_name, raw in source.items():
        if not isinstance(metric_name, str) or not isinstance(raw, Mapping):
            continue
        item: dict[str, Any] = {}
        for field in fields:
            value = raw.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                item[field] = value
                continue
            number = finite_number(value)
            if number is not None and number >= 0.0:
                item[field] = round(number, 6)
        if item:
            output[metric_name] = item
    return output or None


def _source_quality(ergonomics: Mapping[str, Any]) -> dict[str, Any] | None:
    source = ergonomics.get("source_quality_summary")
    if not isinstance(source, Mapping):
        return None
    allowed = {"tracking", "body", "hands", "quality", "warning_codes"}
    return {
        key: value
        for key, value in source.items()
        if key in allowed and isinstance(value, (Mapping, list, str, int, float))
    } or None


def _hand_activity(ergonomics: Mapping[str, Any]) -> dict[str, Any] | None:
    source = ergonomics.get("hand_activity")
    if not isinstance(source, Mapping):
        return None
    output: dict[str, Any] = {"external_load_known": False}
    for side in ("left", "right"):
        raw = source.get(side)
        if not isinstance(raw, Mapping):
            continue
        item: dict[str, Any] = {}
        valid_observation = finite_number(raw.get("valid_observation_seconds"))
        if valid_observation is not None and valid_observation >= 0.0:
            item["valid_observation_seconds"] = round(valid_observation, 6)
        observation_known = valid_observation is not None and valid_observation > 0.0
        for field in (
            "likely_holding_seconds",
            "static_holding_seconds",
            "longest_holding_seconds",
            "holding_ratio",
        ):
            value = finite_number(raw.get(field))
            if observation_known and value is not None and value >= 0.0:
                item[field] = round(value, 6)
        count = raw.get("holding_episode_count")
        if observation_known and isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            item["holding_episode_count"] = count
        episodes = raw.get("episodes")
        known_object_seconds: Counter[str] = Counter()
        known_object_confidences: dict[str, list[float]] = {}
        if isinstance(episodes, list):
            for episode in episodes:
                if not isinstance(episode, Mapping):
                    continue
                object_class = optional_text(episode.get("known_object_class"))
                if object_class is not None:
                    duration = finite_number(episode.get("duration_seconds"))
                    if duration is not None and duration >= 0.0:
                        known_object_seconds[object_class] += duration
                    confidence = finite_number(episode.get("known_object_confidence"))
                    if confidence is not None and 0.0 <= confidence <= 1.0:
                        known_object_confidences.setdefault(object_class, []).append(confidence)
        item["object_interactions"] = [
            {
                "object_class": name,
                "holding_seconds": round(seconds, 6),
                "confidence": (
                    round(sum(known_object_confidences.get(name, ())) / len(known_object_confidences[name]), 6)
                    if known_object_confidences.get(name)
                    else None
                ),
            }
            for name, seconds in known_object_seconds.most_common(5)
        ]
        likely_seconds = finite_number(raw.get("likely_holding_seconds"))
        item["holding_detected"] = (
            "likely"
            if observation_known and likely_seconds is not None and likely_seconds > 0.0
            else "not_detected"
            if observation_known
            else "unknown"
        )
        if item["holding_detected"] == "likely" and not item["object_interactions"]:
            item["unclassified_object_possible"] = True
        output[side] = item
    bimanual = source.get("bimanual")
    if isinstance(bimanual, Mapping):
        output["bimanual"] = {
            key: value
            for key in ("likely_holding_seconds", "episode_count")
            if (value := bimanual.get(key)) is not None
        }
    return output if len(output) > 1 else None


def _pose_quality_limitations(ergonomics: Mapping[str, Any]) -> list[str]:
    summary = ergonomics.get("source_quality_summary")
    limitations: list[str] = []
    if isinstance(summary, Mapping):
        for side, label in (("left_hand", "left"), ("right_hand", "right")):
            hand = summary.get(side)
            valid_ratio = finite_number(hand.get("valid_ratio")) if isinstance(hand, Mapping) else None
            if valid_ratio is not None and valid_ratio < 0.50:
                limitations.append(f"limited_{label}_hand_visibility")
        tracking = summary.get("tracking")
        out_ratio = finite_number(tracking.get("out_of_frame_ratio")) if isinstance(tracking, Mapping) else None
        if out_ratio is not None and out_ratio > 0.25:
            limitations.append("person_partially_out_of_frame")
    activity = ergonomics.get("hand_activity")
    if isinstance(activity, Mapping):
        for side, label in (("left", "left"), ("right", "right")):
            hand_activity = activity.get(side)
            if not isinstance(hand_activity, Mapping):
                continue
            holding_seconds = finite_number(hand_activity.get("likely_holding_seconds"))
            episodes = hand_activity.get("episodes")
            known_object = any(
                isinstance(episode, Mapping)
                and optional_text(episode.get("known_object_class")) is not None
                for episode in episodes
            ) if isinstance(episodes, list) else False
            if holding_seconds is not None and holding_seconds > 0.0 and not known_object:
                limitations.append(f"{label}_holding_object_unclassified")
    return limitations


def _analysis_section(
    analysis: Mapping[str, Any],
    analysis_id: str,
    risk_quality: Mapping[str, Any],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "analysis_id": analysis_id,
        "title": required_text(analysis.get("title"), "analysis.title"),
        "analyzed_frames": risk_quality.get("frame_count"),
    }
    optional_text_fields = ("created_at", "source_file_name")
    for field in optional_text_fields:
        value = optional_text(analysis.get(field))
        if value is not None:
            output[field] = value
    for field in ("source_duration_seconds", "source_width", "source_height"):
        value = finite_number(analysis.get(field))
        if value is not None and value >= 0:
            output[field] = int(value) if field in {"source_width", "source_height"} else value
    return output


def _processing_section(
    analysis: Mapping[str, Any],
    ergonomics: Mapping[str, Any],
    risk: Mapping[str, Any],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "ergonomics_metrics_version": ergonomics.get("metrics_version"),
        "risk_engine_version": risk.get("risk_engine_version"),
        "report_engine_version": REPORT_VERSION,
    }
    pose_version = optional_text(analysis.get("pose_quality_version"))
    if pose_version is not None:
        output["pose_pipeline_version"] = pose_version
    return output


def _quality_section(
    analysis: Mapping[str, Any],
    ergonomics: Mapping[str, Any],
    risk_quality: Mapping[str, Any],
    valid_metric_ratio: float,
    insufficient_data: bool,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "frame_count": risk_quality.get("frame_count"),
        "valid_metric_ratio": valid_metric_ratio,
        "insufficient_data": insufficient_data,
        "rejection_reasons": _rejection_reasons(ergonomics),
    }
    for field in ("pose_presence_ratio",):
        value = finite_number(analysis.get(field))
        if value is not None and 0 <= value <= 1:
            output[field] = round(value, 6)
    for field in ("pose_processed_frames", "pose_detected_frames"):
        value = analysis.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            output[field] = value

    invalid_metric_values = 0
    found_counter = False
    summary = ergonomics.get("summary")
    if isinstance(summary, Mapping):
        for metric in summary.values():
            if not isinstance(metric, Mapping):
                continue
            invalid_frames = metric.get("invalid_frames")
            if isinstance(invalid_frames, int) and not isinstance(invalid_frames, bool) and invalid_frames >= 0:
                invalid_metric_values += invalid_frames
                found_counter = True
    if found_counter:
        output["invalid_metric_values"] = invalid_metric_values
    return output


def _rejection_reasons(ergonomics: Mapping[str, Any]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    frames = ergonomics.get("frames")
    if not isinstance(frames, list):
        return []
    for frame in frames:
        metrics = frame.get("metrics") if isinstance(frame, Mapping) else None
        if not isinstance(metrics, Mapping):
            continue
        for metric in metrics.values():
            if not isinstance(metric, Mapping) or metric.get("valid") is True:
                continue
            reason = optional_text(metric.get("rejection_reason"))
            if reason is not None:
                counter[reason] += 1
    return [
        {"reason": reason, "count": count}
        for reason, count in counter.most_common(5)
    ]


def _body_areas(risk: Mapping[str, Any]) -> list[dict[str, Any]]:
    zones = required_mapping(risk.get("zones"), "risk.zones")
    output: list[dict[str, Any]] = []
    for zone_name, raw_zone in zones.items():
        if not isinstance(zone_name, str) or not isinstance(raw_zone, Mapping):
            continue
        level = raw_zone.get("highest_level")
        if level not in RISK_LEVELS:
            continue
        coverage = finite_number(raw_zone.get("coverage"))
        item: dict[str, Any] = {
            "area_id": zone_name,
            "label": ZONE_LABELS.get(zone_name, zone_name),
            "level": level,
            "insufficient_data": level == "insufficient_data",
        }
        if coverage is not None and 0 <= coverage <= 1:
            item["coverage"] = round(coverage, 6)
        for source, target in (
            ("active_metrics", "active_metrics"),
            ("metrics_with_sufficient_data", "metrics_with_sufficient_data"),
        ):
            value = raw_zone.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                item[target] = value
        output.append(item)
    return output


def _dominant_metrics(risk: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = required_mapping(risk.get("metrics"), "risk.metrics")
    candidates: list[dict[str, Any]] = []
    for metric_name, raw_metric in metrics.items():
        if not isinstance(metric_name, str) or not isinstance(raw_metric, Mapping):
            continue
        level = raw_metric.get("final_level")
        if level not in SEVERITY or level == "disabled":
            continue
        weighted_score = finite_number(raw_metric.get("weighted_score"))
        exposure = raw_metric.get("exposure")
        peak_exposure = 0.0
        if isinstance(exposure, Mapping):
            peak_exposure = max(
                finite_number(exposure.get("high_exposure_ratio")) or 0.0,
                finite_number(exposure.get("critical_exposure_ratio")) or 0.0,
            )
        candidates.append(
            {
                "metric_name": metric_name,
                "level": level,
                "weighted_score": weighted_score,
                "peak_exposure": peak_exposure,
                "source": raw_metric,
            }
        )
    candidates.sort(
        key=lambda item: (
            SEVERITY[str(item["level"])],
            float(item["peak_exposure"]),
            float(item["weighted_score"] or 0.0),
            str(item["metric_name"]),
        ),
        reverse=True,
    )
    return candidates


def _metric_summary(
    ergonomics: Mapping[str, Any],
    risk: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ergonomics_summary = ergonomics.get("summary")
    ergonomic_metrics = ergonomics_summary if isinstance(ergonomics_summary, Mapping) else {}
    output: list[dict[str, Any]] = []
    for candidate in _dominant_metrics(risk)[:METRIC_LIMIT]:
        name = str(candidate["metric_name"])
        risk_metric = candidate["source"]
        if not isinstance(risk_metric, Mapping):
            continue
        item: dict[str, Any] = {
            "metric_name": name,
            "label": METRIC_LABELS.get(name, name),
            "unit": "deg" if name.endswith("_deg") else "ratio",
            "level": candidate["level"],
        }
        valid_ratio_value = finite_number(risk_metric.get("valid_ratio"))
        if valid_ratio_value is not None and 0 <= valid_ratio_value <= 1:
            item["valid_ratio"] = round(valid_ratio_value, 6)
        data_quality = optional_text(risk_metric.get("data_quality"))
        if data_quality is not None:
            item["data_quality"] = data_quality

        statistics: dict[str, Any] = {}
        ergonomic_metric = ergonomic_metrics.get(name)
        if isinstance(ergonomic_metric, Mapping):
            for field in ("median", "maximum", "percentile_95"):
                value = finite_number(ergonomic_metric.get(field))
                if value is not None:
                    statistics[field] = value
        risk_statistics = risk_metric.get("value_statistics")
        if isinstance(risk_statistics, Mapping):
            if "percentile_95" not in statistics:
                percentile = finite_number(risk_statistics.get("percentile"))
                if percentile is not None:
                    statistics["percentile"] = percentile
            percentile_used = finite_number(risk_statistics.get("percentile_used"))
            if percentile_used is not None:
                statistics["percentile_used"] = percentile_used
        if statistics:
            item["statistics"] = statistics

        exposure = risk_metric.get("exposure")
        limited_exposure: dict[str, Any] = {}
        if isinstance(exposure, Mapping):
            for field in (
                "total_valid_duration_seconds",
                "moderate_duration_seconds",
                "high_duration_seconds",
                "critical_duration_seconds",
                "moderate_exposure_ratio",
                "high_exposure_ratio",
                "critical_exposure_ratio",
            ):
                value = finite_number(exposure.get(field))
                if value is not None and value >= 0:
                    limited_exposure[field] = value
        if limited_exposure:
            item["exposure"] = limited_exposure
        output.append(item)
    return output


def _key_moments(risk: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_frames = risk.get("key_frames")
    if not isinstance(raw_frames, list):
        return []
    output: list[dict[str, Any]] = []
    for raw_frame in raw_frames[:10]:
        if not isinstance(raw_frame, Mapping):
            continue
        metric_name = optional_text(raw_frame.get("metric_name"))
        level = raw_frame.get("level")
        if metric_name is None or level not in RISK_LEVELS:
            continue
        item: dict[str, Any] = {
            "metric_name": metric_name,
            "metric_label": METRIC_LABELS.get(metric_name, metric_name),
            "level": level,
            "reason": f"Kluczowy moment wskazany przez Risk Engine dla metryki {METRIC_LABELS.get(metric_name, metric_name)}.",
        }
        zone = optional_text(raw_frame.get("zone"))
        if zone is not None:
            item["area_id"] = zone
            item["area_label"] = ZONE_LABELS.get(zone, zone)
        for field in ("source_frame_index", "output_frame_index"):
            value = raw_frame.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                item[field] = value
        for field in ("timestamp_seconds", "value", "quality"):
            value = finite_number(raw_frame.get(field))
            if value is not None:
                item[field] = value
        output.append(item)
    return output


def _observations(
    overall_level: str,
    dominant_zones: list[str],
    insufficient_zones: list[str],
) -> list[str]:
    if overall_level == "insufficient_data":
        observations = ["Za mało poprawnych danych do wiarygodnej oceny."]
    else:
        observations = [
            "Ogólny poziom technicznej klasyfikacji: "
            f"{LEVEL_LABELS.get(overall_level, overall_level)}."
        ]
    if dominant_zones:
        labels = ", ".join(ZONE_LABELS.get(zone, zone) for zone in dominant_zones)
        observations.append(
            f"Najwyższy poziom odnotowano dla obszarów: {labels}."
        )
    if insufficient_zones:
        labels = ", ".join(ZONE_LABELS.get(zone, zone) for zone in insufficient_zones)
        observations.append(f"Niewystarczające dane dla obszarów: {labels}.")
    return observations


def _limitations(risk: Mapping[str, Any], profile_status: str) -> list[str]:
    source = _text_list(risk.get("limitations"))
    additions = [
        "result_depends_on_recording_quality",
        "occluded_body_parts_may_be_missing",
        "external_load_not_measured",
        "rula_not_calculated",
        "reba_not_calculated",
        "specialist_review_required",
    ]
    if profile_status in {"development", "draft"}:
        additions.append("production_profile_not_used")
    return list(dict.fromkeys([*source, *additions]))


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]

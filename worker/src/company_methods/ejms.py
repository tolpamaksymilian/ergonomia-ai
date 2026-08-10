"""Evidence-aware EJMS Section I and partial Section II evaluator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schemas import finite_number, list_of_mappings, mapping
from .specs import load_spec

EJMS_VERSION = "ejms-company-v1.1-beta.1"
LEVELS = ("LOW", "MOD", "HIGH")


def evaluate_ejms(
    ergonomics_document: Mapping[str, Any],
    manual_inputs: Mapping[str, Any] | None = None,
    owas_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    spec = load_spec("ejms")
    frames = list_of_mappings(ergonomics_document.get("frames"))
    manual = manual_inputs or {}
    owas_frames = list_of_mappings(mapping(owas_document).get("frames"))
    areas = {}
    for area, rules in spec["rules"]["section_i"]["areas"].items():
        areas[area] = _evaluate_area(area, rules, frames, mapping(manual.get("section_i")).get(area), spec, owas_frames)
    known_score = sum(result["score"] for result in areas.values() if isinstance(result.get("score"), (int, float)))
    possible_score_min = sum(int(result.get("possible_score_min", 0)) for result in areas.values())
    possible_score_max = sum(int(result.get("possible_score_max", 0)) for result in areas.values())
    section_ii = evaluate_section_ii(mapping(manual.get("section_ii")), spec)
    missing = [item for result in areas.values() for item in result["missing_inputs"]]
    missing.extend(section_ii["missing_inputs"])
    status = "PARTIAL" if frames else "UNAVAILABLE"
    if frames and not missing:
        status = "AUTOMATIC"
    return {
        "method_id": "ejms-company", "version": EJMS_VERSION, "status": status,
        "section_i": {
            "score": known_score if not missing else None,
            "known_score": known_score,
            "possible_score_min": possible_score_min,
            "possible_score_max": possible_score_max,
            "areas": areas,
            "global_ranking": None,
            "global_ranking_status": "SOURCE_THRESHOLD_CONFLICT",
        },
        "section_ii": section_ii, "missing_inputs": sorted(set(missing)),
        "limitations": ["global_ranking_disabled_due_to_source_conflict", "absolute_distance_not_estimated_without_calibration", "force_not_estimated_from_video"],
    }


def matrix_score(posture: str, frequency: str) -> int | None:
    if posture not in LEVELS or frequency not in LEVELS:
        return None
    return int(load_spec("ejms")["rules"]["matrix"][posture][frequency])


def evaluate_section_ii(inputs: Mapping[str, Any], spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source_spec = spec or load_spec("ejms")
    thresholds = source_spec["thresholds"]["section_ii"]
    results: dict[str, Any] = {}
    definitions = {
        "weight_kg": "weight_kg", "horizontal_distance_cm": "horizontal_distance_cm",
        "start_hand_height_from_waist_cm": "start_hand_height_from_waist_cm",
        "vertical_travel_cm": "vertical_travel_cm", "frequency_per_minute": "frequency_per_minute",
        "twist_deg": "twist_deg", "distance_m": "distance_m",
    }
    for field, threshold_name in definitions.items():
        value = finite_number(inputs.get(field))
        results[field] = {"value": value, "score": _band_score(value, thresholds[threshold_name]), "source": "USER_PROVIDED" if value is not None else "UNKNOWN"}
    grip = inputs.get("grip")
    grip_score = thresholds["grip"].get(grip) if isinstance(grip, str) else None
    results["grip"] = {"value": grip, "score": grip_score, "source": "USER_PROVIDED" if grip_score is not None else "UNKNOWN"}
    missing = [f"ejms.section_ii.{name}" for name, item in results.items() if item["score"] is None]
    known_score = sum(int(item["score"]) for item in results.values() if item["score"] is not None)
    possible_min = known_score
    possible_max = known_score
    for name, item in results.items():
        if item["score"] is not None:
            continue
        options = (
            [int(value) for value in thresholds["grip"].values()]
            if name == "grip"
            else [int(band[2]) for band in thresholds[name] if isinstance(band, list) and len(band) == 3]
        )
        possible_min += min(options, default=0)
        possible_max += max(options, default=0)
    return {
        "status": "MANUAL" if not missing else "PARTIAL",
        "score": known_score if not missing else None,
        "known_score": known_score,
        "possible_score_min": possible_min,
        "possible_score_max": possible_max,
        "components": results,
        "missing_inputs": missing,
    }


def _evaluate_area(area: str, rules: Mapping[str, Any], frames: list[Mapping[str, Any]], manual: object, spec: Mapping[str, Any], owas_frames: list[Mapping[str, Any]]) -> dict[str, Any]:
    samples = [_area_value(area, frame, owas_frames[index] if index < len(owas_frames) else {}) for index, frame in enumerate(frames)]
    known = [(value, quality) for value, quality in samples if value is not None]
    posture = _posture_level(area, [value for value, _ in known], rules)
    duration_ratio = sum(1 for value, _ in known if _value_is_uncomfortable(area, value, rules)) / len(frames) if frames else None
    frequency = finite_number(mapping(manual).get("frequency_per_minute"))
    if frequency is None:
        frequency = _transition_frequency(area, samples, frames)
    frequency_level = _frequency_level(frequency, duration_ratio, rules)
    manual_force = mapping(manual).get("force_level")
    force_level = manual_force if manual_force in LEVELS else None
    posture_force = _merge_posture_force(posture, force_level)
    score = matrix_score(posture_force, frequency_level)
    posture_options = [posture_force] if posture_force in LEVELS else list(LEVELS)
    frequency_options = [frequency_level] if frequency_level in LEVELS else list(LEVELS)
    possible_scores = [
        candidate
        for posture_option in posture_options
        for frequency_option in frequency_options
        if (candidate := matrix_score(posture_option, frequency_option)) is not None
    ]
    missing = []
    if force_level is None and posture != "HIGH":
        missing.append(f"ejms.section_i.{area}.force_level")
    if frequency_level is None:
        missing.append(f"ejms.section_i.{area}.frequency_or_duration")
    final_level = posture_force if score is not None else "UNKNOWN"
    quality = min((quality for _, quality in known), default=0.0)
    peak = max((value for value, _ in known), default=None)
    return {
        "posture_level": posture, "force_level": force_level or "UNKNOWN", "posture_force_level": posture_force or "UNKNOWN",
        "frequency_duration_level": frequency_level or "UNKNOWN", "score": score, "data_status": "COMPLETE" if not missing else "PARTIAL",
        "possible_score_min": min(possible_scores) if possible_scores else 0,
        "possible_score_max": max(possible_scores) if possible_scores else 0,
        "final_level": final_level, "valid_frames": len(known), "total_frames": len(frames),
        "duration_ratio": round(duration_ratio, 6) if duration_ratio is not None else None,
        "frequency_per_minute": round(frequency, 6) if frequency is not None else None, "quality": round(quality, 6),
        "missing_inputs": missing, "trace": [f"EJMS!A{rules['row']}:M{rules['row']}", "EJMS!C25:I29"],
        "decision_evidence": {"observed_peak": peak, "posture_rule": dict(rules), "metric_source": "VIDEO_DERIVED" if peak is not None else "UNKNOWN"},
    }


def _area_value(area: str, frame: Mapping[str, Any], owas_frame: Mapping[str, Any]) -> tuple[float | None, float]:
    if area == "legs":
        legs = mapping(mapping(owas_frame.get("components")).get("legs"))
        value = finite_number(legs.get("value")) if legs.get("source") == "VIDEO_DERIVED" else None
        return value, finite_number(legs.get("quality")) or 0.0
    metrics = mapping(frame.get("metrics"))
    names = {
        "neck": ["neck_flexion_deg"], "arm": ["left_upper_arm_elevation_deg", "right_upper_arm_elevation_deg"],
        "trunk": ["trunk_inclination_deg"], "forearm_elbow": ["left_elbow_flexion_deg", "right_elbow_flexion_deg"],
        "wrist": ["left_wrist_flexion_deg", "right_wrist_flexion_deg"],
        "fingers_hands": ["left_hand_closure_ratio", "right_hand_closure_ratio"],
    }.get(area, [])
    values = []
    qualities = []
    for name in names:
        item = mapping(metrics.get(name))
        value = finite_number(item.get("value")) if item.get("valid") is True else None
        if value is not None:
            values.append(abs(value))
            qualities.append(finite_number(item.get("quality")) or 0.0)
    return (max(values), min(qualities)) if values else (None, 0.0)


def _posture_level(area: str, values: list[float], rules: Mapping[str, Any]) -> str | None:
    if not values:
        return None
    peak = max(values)
    low = mapping(rules.get("posture_low"))
    high = mapping(rules.get("posture_high"))
    if area == "neck":
        high_min = finite_number(high.get("min_exclusive_deg"))
        low_max = finite_number(low.get("max_exclusive_deg"))
        return "HIGH" if high_min is not None and peak > high_min else "LOW" if low_max is not None and peak < low_max else "MOD"
    if area == "arm":
        high_min = finite_number(high.get("elbow_above_shoulder_deg"))
        low_max = finite_number(low.get("elbow_from_trunk_max_exclusive_deg"))
        return "HIGH" if high_min is not None and peak > high_min else "LOW" if low_max is not None and peak < low_max else "MOD"
    if area == "trunk":
        high_min = finite_number(high.get("flexion_or_twist_min_exclusive_deg"))
        low_max = finite_number(low.get("flexion_max_exclusive_deg"))
        return "HIGH" if high_min is not None and peak > high_min else "LOW" if low_max is not None and peak < low_max else "MOD"
    if area == "forearm_elbow":
        low_min = finite_number(low.get("elbow_flexion_min_deg"))
        low_max = finite_number(low.get("elbow_flexion_max_deg"))
        return "LOW" if low_min is not None and low_max is not None and all(low_min <= value <= low_max for value in values) else "MOD"
    if area == "wrist":
        high_min = finite_number(high.get("flexion_min_exclusive_deg"))
        low_max = finite_number(low.get("flexion_extension_abs_max_exclusive_deg"))
        return "HIGH" if high_min is not None and peak > high_min else "LOW" if low_max is not None and peak < low_max else "MOD"
    if area == "legs":
        codes = {int(value) for value in values}
        return "HIGH" if 6 in codes else "MOD" if codes & {3, 4, 5} else "LOW"
    return None


def _value_is_uncomfortable(area: str, value: float, rules: Mapping[str, Any]) -> bool:
    level = _posture_level(area, [value], rules)
    return level in {"MOD", "HIGH"}


def _frequency_level(frequency: float | None, duration_ratio: float | None, rules: Mapping[str, Any]) -> str | None:
    low_frequency = finite_number(rules.get("frequency_low_per_minute"))
    high_frequency = finite_number(rules.get("frequency_high_per_minute"))
    low_duration = finite_number(rules.get("duration_low_ratio"))
    high_duration = finite_number(rules.get("duration_high_ratio"))
    if frequency is None and duration_ratio is None:
        return None
    if (high_frequency is not None and frequency is not None and frequency > high_frequency) or (high_duration is not None and duration_ratio is not None and duration_ratio > high_duration):
        return "HIGH"
    if (low_frequency is None or frequency is None or frequency < low_frequency) and (low_duration is None or duration_ratio is None or duration_ratio < low_duration):
        return "LOW"
    return "MOD"


def _merge_posture_force(posture: str | None, force: str | None) -> str | None:
    if posture == "HIGH" or force == "HIGH":
        return "HIGH"
    if posture is None:
        return force
    if force is None:
        return None if posture == "LOW" else posture
    return LEVELS[max(LEVELS.index(posture), LEVELS.index(force))]


def _transition_frequency(area: str, samples: list[tuple[float | None, float]], frames: list[Mapping[str, Any]]) -> float | None:
    if len(samples) < 2:
        return None
    values = [value for value, _ in samples]
    known = [value for value in values if value is not None]
    if len(known) < 2:
        return None
    threshold = 8.0 if area in {"wrist", "forearm_elbow", "arm", "neck", "trunk"} else 0.15
    events = sum(1 for previous, current in zip(values, values[1:]) if previous is not None and current is not None and abs(current - previous) >= threshold)
    timestamps = [_timestamp(frame) for frame in frames]
    duration = (timestamps[-1] - timestamps[0]) if timestamps[0] is not None and timestamps[-1] is not None else None
    return events * 60 / duration if duration is not None and duration > 0 else None


def _timestamp(frame: Mapping[str, Any]) -> float | None:
    for name in ("source_timestamp_seconds", "timestamp_seconds", "timestamp", "output_timestamp_seconds"):
        value = finite_number(frame.get(name))
        if value is not None:
            return value
    return None


def _band_score(value: float | None, bands: object) -> int | None:
    if value is None or not isinstance(bands, list):
        return None
    for band in bands:
        if not isinstance(band, list) or len(band) != 3:
            continue
        minimum, maximum, score = finite_number(band[0]), finite_number(band[1]), band[2]
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue
        return int(score)
    return None

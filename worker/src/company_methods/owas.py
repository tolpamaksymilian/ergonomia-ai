"""Evidence-aware company OWAS evaluator backed by exact workbook lookup JSON."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .schemas import evidence, finite_number, list_of_mappings, mapping
from .specs import load_spec

OWAS_VERSION = "owas-company-v1.1-beta.1"


def evaluate_owas(
    pose_document: Mapping[str, Any] | None,
    ergonomics_document: Mapping[str, Any],
    manual_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    spec = load_spec("owas")
    metrics_frames = list_of_mappings(ergonomics_document.get("frames"))
    pose_frames = list_of_mappings(mapping(pose_document).get("frames"))
    manual = manual_inputs or {}
    load_code = _load_code(manual.get("load_kg"))
    durations = _durations(metrics_frames, ergonomics_document)
    walking_flags = _walking_flags(pose_frames)
    frames: list[dict[str, Any]] = []
    category_durations: Counter[int] = Counter()
    posture_durations: Counter[str] = Counter()
    category_episodes: Counter[int] = Counter()
    previous_category: int | None = None
    for index, frame in enumerate(metrics_frames):
        pose_frame = pose_frames[index] if index < len(pose_frames) else {}
        back = _back_code(frame)
        arms = _arms_code(frame)
        legs = _legs_code(pose_frame, walking=walking_flags[index] if index < len(walking_flags) else False)
        codes = [back["value"], arms["value"], legs["value"]]
        possible = []
        if all(isinstance(value, int) for value in codes):
            load_codes = [load_code] if load_code is not None else [1, 2, 3]
            for candidate_load in load_codes:
                code = "".join(str(value) for value in [*codes, candidate_load])
                item = spec["lookup"].get(code)
                possible.append({"code": code, "status": item["status"] if item else "SOURCE_MISSING", "categories": item["categories"] if item else []})
        resolved = possible[0]["categories"][0] if len(possible) == 1 and possible[0]["status"] == "VERIFIED" and len(possible[0]["categories"]) == 1 else None
        duration = durations[index]
        posture_code = "".join(str(value) for value in codes) if all(isinstance(value, int) for value in codes) else None
        if posture_code is not None:
            posture_durations[posture_code] += duration
        if resolved is not None:
            category_durations[resolved] += duration
            if resolved != previous_category:
                category_episodes[resolved] += 1
        previous_category = resolved
        frames.append({
            "source_frame_index": frame.get("source_frame_index"), "output_frame_index": frame.get("output_frame_index"),
            "timestamp_seconds": _timestamp(frame), "duration_seconds": round(duration, 6),
            "components": {"back": back, "arms": arms, "legs": legs, "load": evidence(load_code, "USER_PROVIDED" if load_code else "UNKNOWN", reason=None if load_code else "load_kg_required")},
            "posture_code": posture_code,
            "code": possible[0]["code"] if len(possible) == 1 else None, "category": resolved,
            "possible_categories": possible, "status": _frame_status(possible, load_code),
        })
    valid_duration = sum(category_durations.values())
    posture_valid_duration = sum(posture_durations.values())
    total_duration = sum(durations)
    longest = _longest_episodes(frames)
    category_ratios = {str(key): round(category_durations[key] / total_duration, 6) if total_duration else 0.0 for key in range(1, 5)}
    forced_posture = manual.get("forced_posture") if manual.get("forced_posture") in {"forced", "unforced"} else None
    time_assessment = _time_distribution_assessment(category_ratios, forced_posture, spec)
    missing_inputs = []
    if load_code is None:
        missing_inputs.append("owas.load_kg")
    if forced_posture is None:
        missing_inputs.append("owas.forced_posture")
    return {
        "method_id": "owas-company", "version": OWAS_VERSION,
        "status": "AUTOMATIC" if frames and not missing_inputs and all(frame["status"] == "AUTOMATIC" for frame in frames) else ("PARTIAL" if frames else "UNAVAILABLE"),
        "load_evidence": evidence(load_code, "USER_PROVIDED" if load_code else "UNKNOWN", reason=None if load_code else "load_kg_required"),
        "forced_posture_evidence": evidence(forced_posture, "USER_PROVIDED" if forced_posture else "UNKNOWN", reason=None if forced_posture else "forced_posture_required"),
        "frames": frames,
        "summary": {
            "frame_count": len(frames),
            "posture_classified_duration_seconds": round(posture_valid_duration, 6),
            "classified_duration_seconds": round(valid_duration, 6),
            "active_duration_seconds": round(total_duration, 6),
            "posture_coverage_ratio": round(posture_valid_duration / total_duration, 6) if total_duration else 0.0,
            "posture_duration_seconds": {key: round(value, 6) for key, value in posture_durations.items()},
            "category_duration_seconds": {str(key): round(category_durations[key], 6) for key in range(1, 5)},
            "category_ratios": category_ratios,
            "episode_counts": {str(key): category_episodes[key] for key in range(1, 5)},
            "longest_episode_seconds": {str(key): round(longest[key], 6) for key in range(1, 5)},
            "dominant_category": category_durations.most_common(1)[0][0] if category_durations else None,
            "time_distribution_assessment": time_assessment,
        },
        "missing_inputs": missing_inputs,
        "limitations": ["2d_video_cannot_reliably_determine_trunk_twist", "load_not_estimated_from_video"],
    }


def _time_distribution_assessment(ratios: Mapping[str, float], posture: str | None, spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = []
    rules = spec.get("thresholds", {}).get("time_distribution", [])
    for category in range(1, 5):
        ratio = ratios.get(str(category), 0.0)
        matches = []
        if posture is not None and isinstance(rules, list):
            for raw in rules:
                if not isinstance(raw, Mapping) or category not in raw.get("categories", []):
                    continue
                expected = mapping(raw.get("posture_by_category")).get(str(category), raw.get("posture"))
                if expected != posture or not _ratio_matches(ratio, raw):
                    continue
                matches.append({"level": raw.get("level"), "source_ref": f"OWAS!{raw.get('source_ref')}"})
        levels = {item["level"] for item in matches}
        results.append({
            "category": category, "ratio": ratio, "posture": posture or "UNKNOWN",
            "level": next(iter(levels)) if len(levels) == 1 else None,
            "status": "VERIFIED" if len(levels) == 1 else "SOURCE_AMBIGUOUS" if len(levels) > 1 else "REQUIRES_DATA",
            "matching_rules": matches,
        })
    return results


def _ratio_matches(value: float, rule: Mapping[str, Any]) -> bool:
    minimum = finite_number(rule.get("minimum_ratio"))
    minimum_exclusive = finite_number(rule.get("minimum_ratio_exclusive"))
    maximum = finite_number(rule.get("maximum_ratio"))
    return (minimum is None or value >= minimum) and (minimum_exclusive is None or value > minimum_exclusive) and (maximum is None or value <= maximum)


def _metric(frame: Mapping[str, Any], name: str) -> tuple[float | None, float]:
    item = mapping(mapping(frame.get("metrics")).get(name))
    value = finite_number(item.get("value")) if item.get("valid") is True else None
    quality = finite_number(item.get("quality")) or 0.0
    return value, quality


def _back_code(frame: Mapping[str, Any]) -> dict[str, Any]:
    value, quality = _metric(frame, "trunk_inclination_deg")
    if value is None:
        return evidence(None, "UNKNOWN", quality=quality, reason="trunk_metric_missing")
    return evidence(1 if abs(value) <= 20 else 2, "VIDEO_DERIVED", quality=quality, reason="twist_not_inferred_from_2d")


def _arms_code(frame: Mapping[str, Any]) -> dict[str, Any]:
    left, lq = _metric(frame, "left_upper_arm_elevation_deg")
    right, rq = _metric(frame, "right_upper_arm_elevation_deg")
    if left is None or right is None:
        return evidence(None, "UNKNOWN", quality=min(lq, rq), reason="both_arm_chains_required")
    above = int(left > 90) + int(right > 90)
    return evidence(1 if above == 0 else 2 if above == 1 else 3, "VIDEO_DERIVED", quality=min(lq, rq))


def _legs_code(frame: Mapping[str, Any], *, walking: bool = False) -> dict[str, Any]:
    joints = _joints(frame)
    required = [joints.get(name) for name in ("left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle")]
    if any(point is None for point in required):
        return evidence(None, "UNKNOWN", reason="leg_keypoints_missing")
    lh, rh, lk, rk, la, ra = required
    left_angle = _angle(lh, lk, la)
    right_angle = _angle(rh, rk, ra)
    if left_angle is None or right_angle is None:
        return evidence(None, "UNKNOWN", reason="leg_geometry_invalid")
    if walking:
        return evidence(7, "VIDEO_DERIVED", quality=0.55, reason="temporal_gait_pattern_detected")
    hip_y = (lh[1] + rh[1]) / 2
    knee_y = (lk[1] + rk[1]) / 2
    ankle_y = (la[1] + ra[1]) / 2
    if ankle_y <= knee_y or knee_y <= hip_y:
        return evidence(None, "UNKNOWN", reason="unsupported_camera_orientation")
    if 65 <= left_angle <= 125 and 65 <= right_angle <= 125 and (knee_y - hip_y) < 0.75 * (ankle_y - knee_y):
        return evidence(1, "VIDEO_DERIVED", quality=0.65)
    bent_left, bent_right = left_angle < 150, right_angle < 150
    if left_angle < 80 or right_angle < 80:
        code = 6
    elif bent_left and bent_right:
        code = 4
    elif bent_left or bent_right:
        code = 5
    elif abs(la[1] - ra[1]) > 0.25 * _distance(lh, rh):
        code = 3
    else:
        code = 2
    return evidence(code, "VIDEO_DERIVED", quality=0.65)


def _walking_flags(frames: list[Mapping[str, Any]]) -> list[bool]:
    """Detect a conservative gait sequence from relative, scale-free leg motion.

    A single moving ankle is deliberately insufficient. Two adjacent transitions
    must show meaningful ankle motion relative to the pelvis and a changing
    stance. This avoids treating camera translation or one noisy frame as walk.
    """
    flags = [False] * len(frames)
    transitions: list[bool] = [False] * len(frames)
    joint_frames = [_joints(frame) for frame in frames]
    for index in range(1, len(joint_frames)):
        previous, current = joint_frames[index - 1], joint_frames[index]
        names = ("left_hip", "right_hip", "left_ankle", "right_ankle")
        if any(name not in previous or name not in current for name in names):
            continue
        hip_width = _distance(current["left_hip"], current["right_hip"])
        if hip_width <= 1e-9:
            continue
        previous_relative = _relative_ankles(previous)
        current_relative = _relative_ankles(current)
        ankle_motion = (
            _distance(previous_relative[0], current_relative[0])
            + _distance(previous_relative[1], current_relative[1])
        ) / hip_width
        stance_change = abs(
            _distance(*current_relative) - _distance(*previous_relative)
        ) / hip_width
        vertical_change = abs(
            abs(current_relative[0][1] - current_relative[1][1])
            - abs(previous_relative[0][1] - previous_relative[1][1])
        ) / hip_width
        transitions[index] = ankle_motion >= 0.20 and (stance_change >= 0.08 or vertical_change >= 0.08)
    for index in range(1, len(transitions)):
        if transitions[index] and (transitions[index - 1] or (index + 1 < len(transitions) and transitions[index + 1])):
            flags[index] = True
            flags[index - 1] = True
    return flags


def _relative_ankles(joints: Mapping[str, tuple[float, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    pelvis = (
        (joints["left_hip"][0] + joints["right_hip"][0]) / 2,
        (joints["left_hip"][1] + joints["right_hip"][1]) / 2,
    )
    return (
        (joints["left_ankle"][0] - pelvis[0], joints["left_ankle"][1] - pelvis[1]),
        (joints["right_ankle"][0] - pelvis[0], joints["right_ankle"][1] - pelvis[1]),
    )


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _joints(frame: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    candidates = mapping(frame.get("joint_evidence_v5")) or mapping(mapping(frame.get("body_quality")).get("joints"))
    if isinstance(mapping(frame.get("body_quality")).get("joints"), list):
        candidates = {str(item.get("name")): item for item in list_of_mappings(mapping(frame.get("body_quality")).get("joints"))}
    result = {}
    for name, raw in candidates.items():
        if not isinstance(name, str) or not isinstance(raw, Mapping):
            continue
        coordinates = raw.get("coordinates") or raw.get("point")
        if isinstance(coordinates, Sequence) and len(coordinates) >= 2:
            x, y = finite_number(coordinates[0]), finite_number(coordinates[1])
            if x is not None and y is not None:
                result[name] = (x, y)
    return result


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float | None:
    import math
    u, v = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu <= 1e-9 or nv <= 1e-9:
        return None
    cosine = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(cosine))


def _load_code(value: object) -> int | None:
    kg = finite_number(value)
    if kg is None or kg < 0:
        return None
    return 1 if kg < 10 else 2 if kg <= 20 else 3


def _timestamp(frame: Mapping[str, Any]) -> float | None:
    for name in ("source_timestamp_seconds", "timestamp_seconds", "timestamp", "output_timestamp_seconds"):
        value = finite_number(frame.get(name))
        if value is not None and value >= 0:
            return value
    return None


def _durations(frames: list[Mapping[str, Any]], document: Mapping[str, Any]) -> list[float]:
    if not frames:
        return []
    timestamps = [_timestamp(frame) for frame in frames]
    fps = finite_number(mapping(document.get("source")).get("fps")) or finite_number(document.get("fps")) or 30.0
    fallback = 1.0 / fps if fps > 0 else 1.0 / 30.0
    values = []
    for index, current in enumerate(timestamps):
        following = timestamps[index + 1] if index + 1 < len(timestamps) else None
        delta = following - current if current is not None and following is not None else fallback
        values.append(delta if delta > 0 else fallback)
    return values


def _frame_status(possible: list[dict[str, Any]], load_code: int | None) -> str:
    if any(item["status"] == "SOURCE_AMBIGUOUS" for item in possible):
        return "SOURCE_ERROR"
    if not possible:
        return "REQUIRES_DATA"
    return "AUTOMATIC" if load_code is not None and possible[0]["status"] == "VERIFIED" else "PARTIAL"


def _longest_episodes(frames: list[dict[str, Any]]) -> Counter[int]:
    result: Counter[int] = Counter()
    current_category, current_duration = None, 0.0
    for frame in frames:
        category = frame.get("category")
        if category != current_category:
            if isinstance(current_category, int):
                result[current_category] = max(result[current_category], current_duration)
            current_category, current_duration = category, 0.0
        if isinstance(category, int):
            current_duration += float(frame["duration_seconds"])
    if isinstance(current_category, int):
        result[current_category] = max(result[current_category], current_duration)
    return result

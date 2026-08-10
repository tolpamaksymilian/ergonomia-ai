"""Pure REBA posture categories and assessment-only leg geometry."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from ..evidence import metric_evidence, unknown, user_evidence
from ..schemas import EvidenceSource, EvidenceValue, finite_number
from ..rula.components import lower_arm_category, upper_arm_category, wrist_category


def neck_category(angle: float) -> tuple[str, int]:
    return ("0_to_20", 1) if angle <= 20.0 else ("over_20", 2)


def trunk_category(angle: float) -> tuple[str, int]:
    if angle <= 1e-6: return "erect", 1
    if angle <= 20.0: return "0_to_20", 2
    if angle <= 60.0: return "20_to_60", 3
    return "over_60", 4


def reba_lower_arm_category(flexion: float) -> tuple[str, int]:
    return ("60_to_100", 1) if 60.0 <= flexion <= 100.0 else ("outside_60_to_100", 2)


def build_components(
    frame: Mapping[str, Any],
    pose_frame: Mapping[str, Any] | None,
    side: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, EvidenceValue]:
    context = context or {}; prefix = f"{side}_"
    leg = leg_evidence(pose_frame, side)
    return {
        "neck": metric_evidence(frame, "neck_flexion_deg", "neck", neck_category),
        "trunk": metric_evidence(frame, "trunk_inclination_deg", "trunk", trunk_category),
        "legs": leg,
        "upper_arm": metric_evidence(frame, prefix + "upper_arm_elevation_deg", "upper_arm", upper_arm_category),
        "lower_arm": metric_evidence(frame, prefix + "elbow_flexion_deg", "lower_arm", reba_lower_arm_category),
        "wrist": metric_evidence(frame, prefix + "wrist_flexion_deg", "wrist", wrist_category),
        "neck_adjustment": unknown("neck_adjustment", ("neck_twist", "neck_side_bend"), "axial_and_frontal_neck_posture_missing", possible_scores=(0, 1)),
        "trunk_adjustment": unknown("trunk_adjustment", ("trunk_twist", "trunk_side_bend"), "axial_and_frontal_trunk_posture_missing", possible_scores=(0, 1)),
        "upper_arm_adjustment": unknown("upper_arm_adjustment", ("shoulder_elevation", "arm_abduction", "arm_support"), "frontal_depth_or_support_context_missing", possible_scores=(-1, 0, 1, 2)),
        "wrist_adjustment": unknown("wrist_adjustment", (prefix + "wrist_deviation_or_twist",), "wrist_deviation_and_twist_not_reliably_observable", possible_scores=(0, 1)),
        "load_force": user_evidence("load_force", _optional_int(context.get("reba_load_force")), range(0, 4), "reba_load_force"),
        "coupling": user_evidence("coupling", _optional_int(context.get("reba_coupling")), range(0, 4), "reba_coupling"),
        "activity": user_evidence("activity", _optional_int(context.get("reba_activity")), range(0, 4), "reba_activity"),
    }


def leg_evidence(pose_frame: Mapping[str, Any] | None, side: str) -> EvidenceValue:
    if pose_frame is None:
        return unknown("legs", (f"{side}_hip", f"{side}_knee", f"{side}_ankle"), "pose_frame_unavailable", possible_scores=(1, 2, 3, 4))
    points = pose_frame.get("smoothed_keypoints"); scores = pose_frame.get("scores")
    indices = (11, 13, 15) if side == "left" else (12, 14, 16)
    parsed = [_point(points, scores, index) for index in indices]
    if any(item is None for item in parsed):
        return unknown("legs", (f"{side}_hip", f"{side}_knee", f"{side}_ankle"), "missing_or_low_quality_leg_keypoint", possible_scores=(1, 2, 3, 4))
    hip, knee, ankle = parsed  # type: ignore[misc]
    joint_angle = _angle(hip[0], knee[0], ankle[0])
    if joint_angle is None:
        return unknown(
            "legs",
            (f"{side}_hip", f"{side}_knee", f"{side}_ankle"),
            "zero_length_leg_vector",
            possible_scores=(1, 2, 3, 4),
        )
    flexion = 180.0 - joint_angle
    adjustment = 2 if flexion > 60.0 else 1 if flexion >= 30.0 else 0
    possible_scores = tuple(sorted({min(4, base + adjustment) for base in (1, 2)}))
    return EvidenceValue(
        name="legs", raw_input=round(flexion, 6), category="knee_flexion", score=None,
        quality=min(hip[1], knee[1], ankle[1]), source=EvidenceSource.DERIVED,
        evidence=(f"{side}_hip", f"{side}_knee", f"{side}_ankle"),
        missing_evidence=("weight_distribution_and_leg_support",),
        notes=("knee_flexion_derived; bilateral_or_unilateral_support_unknown",),
        possible_scores=possible_scores,
    )


def _point(points: object, scores: object, index: int) -> tuple[tuple[float, float], float] | None:
    if not isinstance(points, list) or index >= len(points): return None
    raw = points[index]
    if not isinstance(raw, list) or len(raw) < 2: return None
    x, y = finite_number(raw[0]), finite_number(raw[1])
    quality = finite_number(scores[index]) if isinstance(scores, list) and index < len(scores) else None
    if x is None or y is None or quality is None or quality < 0.55 or (x == 0.0 and y == 0.0): return None
    return (x, y), quality


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float | None:
    first=(a[0]-b[0],a[1]-b[1]); second=(c[0]-b[0],c[1]-b[1])
    n1=math.hypot(*first); n2=math.hypot(*second)
    if n1 <= 1e-9 or n2 <= 1e-9: return None
    cosine=max(-1.0,min(1.0,(first[0]*second[0]+first[1]*second[1])/(n1*n2)))
    return math.degrees(math.acos(cosine))


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

"""Pure RULA posture categorization and evidence mapping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..evidence import metric_evidence, unknown, user_evidence
from ..schemas import EvidenceValue


def upper_arm_category(angle: float) -> tuple[str, int]:
    if angle <= 20.0: return "minus_20_to_20", 1
    if angle <= 45.0: return "20_to_45", 2
    if angle <= 90.0: return "45_to_90", 3
    return "over_90", 4


def lower_arm_category(flexion: float) -> tuple[str, int]:
    return ("60_to_100", 1) if 60.0 <= flexion <= 100.0 else ("outside_60_to_100", 2)


def wrist_category(angle: float) -> tuple[str, int]:
    absolute = abs(angle)
    if absolute <= 1e-6: return "neutral", 1
    if absolute <= 15.0: return "0_to_15", 2
    return "over_15", 3


def neck_category(angle: float) -> tuple[str, int]:
    if angle <= 10.0: return "0_to_10", 1
    if angle <= 20.0: return "10_to_20", 2
    return "over_20", 3


def trunk_category(angle: float) -> tuple[str, int]:
    if angle <= 1e-6: return "erect", 1
    if angle <= 20.0: return "0_to_20", 2
    if angle <= 60.0: return "20_to_60", 3
    return "over_60", 4


def build_components(
    frame: Mapping[str, Any],
    side: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, EvidenceValue]:
    context = context or {}
    prefix = f"{side}_"
    return {
        "upper_arm": metric_evidence(frame, prefix + "upper_arm_elevation_deg", "upper_arm", upper_arm_category),
        "lower_arm": metric_evidence(frame, prefix + "elbow_flexion_deg", "lower_arm", lower_arm_category),
        "wrist": metric_evidence(frame, prefix + "wrist_flexion_deg", "wrist", wrist_category),
        "wrist_twist": unknown("wrist_twist", (prefix + "wrist_pronation_supination",), "axial_rotation_not_observable_in_2d", possible_scores=(1, 2)),
        "neck": metric_evidence(frame, "neck_flexion_deg", "neck", neck_category),
        "trunk": metric_evidence(frame, "trunk_inclination_deg", "trunk", trunk_category),
        "legs": unknown("legs", ("balanced_weight_distribution", "foot_support"), "support_and_balance_not_observable", possible_scores=(1, 2)),
        "muscle_use": user_evidence("muscle_use", _optional_int(context.get("rula_muscle_use")), range(0, 2), "rula_muscle_use"),
        "force_load": user_evidence("force_load", _optional_int(context.get("rula_force_load")), range(0, 4), "rula_force_load"),
        "upper_arm_adjustment": unknown("upper_arm_adjustment", ("shoulder_elevation", "arm_abduction", "arm_support"), "frontal_depth_or_support_context_missing", possible_scores=(-1, 0, 1, 2)),
        "lower_arm_adjustment": unknown("lower_arm_adjustment", ("arm_across_midline",), "depth_relation_not_observable_in_2d", possible_scores=(0, 1)),
        "wrist_adjustment": unknown("wrist_adjustment", (prefix + "radial_ulnar_deviation",), "wrist_deviation_not_reliably_observable", possible_scores=(0, 1)),
        "neck_adjustment": unknown("neck_adjustment", ("neck_twist", "neck_side_bend"), "axial_and_frontal_neck_posture_missing", possible_scores=(0, 1, 2)),
        "trunk_adjustment": unknown("trunk_adjustment", ("trunk_twist", "trunk_side_bend"), "axial_and_frontal_trunk_posture_missing", possible_scores=(0, 1, 2)),
    }


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

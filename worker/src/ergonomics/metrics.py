"""Frame-local ergonomic measurements built on validated Pose V3 data."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from . import geometry
from .schemas import FramePose, MetricResult, PointSample, RejectionReason, ValidatedHand


BODY_SOURCES: dict[str, tuple[str, ...]] = {
    "trunk_inclination_deg": ("left_shoulder", "right_shoulder", "left_hip", "right_hip"),
    "neck_flexion_deg": ("nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip"),
    "left_upper_arm_elevation_deg": ("left_shoulder", "left_elbow", "right_shoulder", "left_hip", "right_hip"),
    "right_upper_arm_elevation_deg": ("right_shoulder", "right_elbow", "left_shoulder", "left_hip", "right_hip"),
    "left_elbow_flexion_deg": ("left_shoulder", "left_elbow", "left_wrist"),
    "right_elbow_flexion_deg": ("right_shoulder", "right_elbow", "right_wrist"),
    "left_forearm_inclination_deg": ("left_elbow", "left_wrist"),
    "right_forearm_inclination_deg": ("right_elbow", "right_wrist"),
}

HAND_LANDMARK_NAMES: dict[int, str] = {
    0: "wrist",
    1: "thumb_cmc", 2: "thumb_mcp", 3: "thumb_ip", 4: "thumb_tip",
    5: "index_mcp", 6: "index_pip", 7: "index_dip", 8: "index_tip",
    9: "middle_mcp", 10: "middle_pip", 11: "middle_dip", 12: "middle_tip",
    13: "ring_mcp", 14: "ring_pip", 15: "ring_dip", 16: "ring_tip",
    17: "pinky_mcp", 18: "pinky_pip", 19: "pinky_dip", 20: "pinky_tip",
}


def _point_rejection(points: list[PointSample]) -> RejectionReason | None:
    priorities: tuple[RejectionReason, ...] = (
        "invalid_coordinate",
        "missing_keypoint",
        "low_keypoint_quality",
    )
    reasons = {point.rejection_reason for point in points if not point.valid}
    for reason in priorities:
        if reason in reasons:
            return reason
    return next(iter(reasons), None)


def _body_points(
    frame: FramePose,
    source_names: tuple[str, ...],
) -> tuple[list[PointSample] | None, MetricResult | None]:
    points = [frame.body[name] for name in source_names]
    reason = _point_rejection(points)
    if reason is not None:
        return None, MetricResult.rejected(source_names, reason)
    return points, None


def _quality(points: list[PointSample], hand: ValidatedHand | None = None) -> float:
    qualities = [point.quality for point in points]
    if hand is not None:
        qualities.append(hand.quality)
    return min(qualities) if qualities else 0.0


def _geometry_result(
    value: float | None,
    points: list[PointSample],
    source_names: tuple[str, ...],
    *,
    hand: ValidatedHand | None = None,
) -> MetricResult:
    if value is None:
        return MetricResult.rejected(source_names, "zero_length_vector")
    if not math.isfinite(value):
        return MetricResult.rejected(source_names, "geometry_validation_failed")
    return MetricResult.accepted(value, _quality(points, hand), source_names)


def _trunk(frame: FramePose) -> MetricResult:
    sources = BODY_SOURCES["trunk_inclination_deg"]
    points, rejected = _body_points(frame, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    left_shoulder, right_shoulder, left_hip, right_hip = (p.coordinates for p in points)
    shoulder_mid = geometry.midpoint(left_shoulder, right_shoulder)  # type: ignore[arg-type]
    hip_mid = geometry.midpoint(left_hip, right_hip)  # type: ignore[arg-type]
    value = None if shoulder_mid is None or hip_mid is None else geometry.angle_from_vertical(shoulder_mid - hip_mid)
    return _geometry_result(value, points, sources)


def _neck(frame: FramePose) -> MetricResult:
    sources = BODY_SOURCES["neck_flexion_deg"]
    points, rejected = _body_points(frame, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    nose, left_shoulder, right_shoulder, left_hip, right_hip = (p.coordinates for p in points)
    shoulder_mid = geometry.midpoint(left_shoulder, right_shoulder)  # type: ignore[arg-type]
    hip_mid = geometry.midpoint(left_hip, right_hip)  # type: ignore[arg-type]
    value = (
        None
        if shoulder_mid is None or hip_mid is None or nose is None
        else geometry.angle_between_vectors(shoulder_mid - hip_mid, nose - shoulder_mid)
    )
    return _geometry_result(value, points, sources)


def _upper_arm(frame: FramePose, side: str) -> MetricResult:
    metric_name = f"{side}_upper_arm_elevation_deg"
    sources = BODY_SOURCES[metric_name]
    points, rejected = _body_points(frame, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    shoulder, elbow, other_shoulder, left_hip, right_hip = (p.coordinates for p in points)
    shoulder_mid = geometry.midpoint(shoulder, other_shoulder)  # type: ignore[arg-type]
    hip_mid = geometry.midpoint(left_hip, right_hip)  # type: ignore[arg-type]
    value = (
        None
        if shoulder_mid is None or hip_mid is None or shoulder is None or elbow is None
        else geometry.angle_between_vectors(hip_mid - shoulder_mid, elbow - shoulder)
    )
    return _geometry_result(value, points, sources)


def _elbow(frame: FramePose, side: str) -> MetricResult:
    metric_name = f"{side}_elbow_flexion_deg"
    sources = BODY_SOURCES[metric_name]
    points, rejected = _body_points(frame, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    shoulder, elbow, wrist = (p.coordinates for p in points)
    included_angle = geometry.angle_three_points(shoulder, elbow, wrist)  # type: ignore[arg-type]
    value = None if included_angle is None else min(180.0, max(0.0, 180.0 - included_angle))
    return _geometry_result(value, points, sources)


def _forearm(frame: FramePose, side: str) -> MetricResult:
    metric_name = f"{side}_forearm_inclination_deg"
    sources = BODY_SOURCES[metric_name]
    points, rejected = _body_points(frame, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    elbow, wrist = (p.coordinates for p in points)
    value = None if elbow is None or wrist is None else geometry.angle_from_vertical(wrist - elbow)
    return _geometry_result(value, points, sources)


def _hand_sources(side: str, indices: tuple[int, ...]) -> tuple[str, ...]:
    return tuple(f"{side}_hand_{HAND_LANDMARK_NAMES[index]}" for index in indices)


def _validated_hand_points(
    hand: ValidatedHand,
    indices: tuple[int, ...],
    sources: tuple[str, ...],
) -> tuple[list[PointSample] | None, MetricResult | None]:
    if not hand.valid:
        return None, MetricResult.rejected(sources, hand.rejection_reason or "hand_not_valid")
    points = [hand.landmarks[index] for index in indices]
    reason = _point_rejection(points)
    if reason is not None:
        return None, MetricResult.rejected(sources, reason)
    return points, None


def _wrist(frame: FramePose, side: str) -> MetricResult:
    hand = frame.left_hand if side == "left" else frame.right_hand
    body_names = (f"{side}_elbow", f"{side}_wrist")
    hand_indices = (0, 9)
    sources = body_names + _hand_sources(side, hand_indices)
    if not hand.valid:
        return MetricResult.rejected(sources, hand.rejection_reason or "hand_not_valid")
    body_points, rejected = _body_points(frame, body_names)
    if rejected is not None or body_points is None:
        return MetricResult.rejected(sources, rejected.rejection_reason)  # type: ignore[arg-type,union-attr]
    hand_points, rejected = _validated_hand_points(hand, hand_indices, sources)
    if rejected is not None or hand_points is None:
        return rejected  # type: ignore[return-value]
    elbow, wrist = (point.coordinates for point in body_points)
    hand_wrist, middle_mcp = (point.coordinates for point in hand_points)
    value = geometry.angle_between_vectors(wrist - elbow, middle_mcp - hand_wrist)  # type: ignore[operator]
    return _geometry_result(value, body_points + hand_points, sources, hand=hand)


def _hand_closure(frame: FramePose, side: str) -> MetricResult:
    hand = frame.left_hand if side == "left" else frame.right_hand
    indices = tuple(range(5, 21))
    sources = _hand_sources(side, indices)
    points, rejected = _validated_hand_points(hand, indices, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    by_index = {index: point for index, point in zip(indices, points, strict=True)}
    extension_ratios: list[float] = []
    for chain in ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20)):
        direct = geometry.distance(by_index[chain[0]].coordinates, by_index[chain[-1]].coordinates)  # type: ignore[arg-type]
        segments = [
            geometry.distance(by_index[first].coordinates, by_index[second].coordinates)  # type: ignore[arg-type]
            for first, second in zip(chain, chain[1:])
        ]
        if direct is None or any(segment is None for segment in segments):
            return MetricResult.rejected(sources, "geometry_validation_failed")
        chain_length = sum(segment for segment in segments if segment is not None)
        if chain_length <= geometry.EPSILON:
            return MetricResult.rejected(sources, "zero_length_vector")
        extension_ratios.append(min(1.0, max(0.0, direct / chain_length)))
    value = min(1.0, max(0.0, 1.0 - float(np.mean(extension_ratios))))
    return _geometry_result(value, points, sources, hand=hand)


def _pinch(frame: FramePose, side: str) -> MetricResult:
    hand = frame.left_hand if side == "left" else frame.right_hand
    indices = (4, 8, 0, 9, 5, 17)
    sources = _hand_sources(side, indices)
    points, rejected = _validated_hand_points(hand, indices, sources)
    if rejected is not None or points is None:
        return rejected  # type: ignore[return-value]
    by_index = {index: point for index, point in zip(indices, points, strict=True)}
    pinch_distance = geometry.distance(by_index[4].coordinates, by_index[8].coordinates)  # type: ignore[arg-type]
    palm_distances = [
        geometry.distance(by_index[first].coordinates, by_index[second].coordinates)  # type: ignore[arg-type]
        for first, second in ((0, 9), (5, 17), (0, 5), (0, 17))
    ]
    if pinch_distance is None or any(value is None for value in palm_distances):
        return MetricResult.rejected(sources, "geometry_validation_failed")
    palm_scale = float(np.median([value for value in palm_distances if value is not None]))
    if palm_scale <= geometry.EPSILON:
        return MetricResult.rejected(sources, "zero_length_vector")
    return _geometry_result(pinch_distance / palm_scale, points, sources, hand=hand)


def metric_source_points() -> dict[str, tuple[str, ...]]:
    result = dict(BODY_SOURCES)
    for side in ("left", "right"):
        result[f"{side}_wrist_flexion_deg"] = (
            f"{side}_elbow",
            f"{side}_wrist",
            *_hand_sources(side, (0, 9)),
        )
        result[f"{side}_hand_closure_ratio"] = _hand_sources(side, tuple(range(5, 21)))
        result[f"{side}_pinch_distance_ratio"] = _hand_sources(side, (4, 8, 0, 9, 5, 17))
    return result


def compute_frame_metrics(frame: FramePose) -> dict[str, MetricResult]:
    sources = metric_source_points()
    if not frame.person_detected:
        return {
            name: MetricResult.rejected(source_points, "person_not_detected")
            for name, source_points in sources.items()
        }

    calculators: dict[str, Callable[[], MetricResult]] = {
        "trunk_inclination_deg": lambda: _trunk(frame),
        "neck_flexion_deg": lambda: _neck(frame),
        "left_upper_arm_elevation_deg": lambda: _upper_arm(frame, "left"),
        "right_upper_arm_elevation_deg": lambda: _upper_arm(frame, "right"),
        "left_elbow_flexion_deg": lambda: _elbow(frame, "left"),
        "right_elbow_flexion_deg": lambda: _elbow(frame, "right"),
        "left_forearm_inclination_deg": lambda: _forearm(frame, "left"),
        "right_forearm_inclination_deg": lambda: _forearm(frame, "right"),
        "left_wrist_flexion_deg": lambda: _wrist(frame, "left"),
        "right_wrist_flexion_deg": lambda: _wrist(frame, "right"),
        "left_hand_closure_ratio": lambda: _hand_closure(frame, "left"),
        "right_hand_closure_ratio": lambda: _hand_closure(frame, "right"),
        "left_pinch_distance_ratio": lambda: _pinch(frame, "left"),
        "right_pinch_distance_ratio": lambda: _pinch(frame, "right"),
    }
    return {name: calculator() for name, calculator in calculators.items()}

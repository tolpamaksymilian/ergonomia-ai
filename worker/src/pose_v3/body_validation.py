"""Per-joint and per-bone conservative validation for Pose Worker V0.3."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from .tracking import TrackingDecision, TrackingState


BODY_POINT_COUNT = 23
BODY_BONES: dict[str, tuple[int, int]] = {
    "shoulders": (5, 6),
    "left_upper_arm": (5, 7),
    "left_forearm": (7, 9),
    "right_upper_arm": (6, 8),
    "right_forearm": (8, 10),
    "left_torso": (5, 11),
    "right_torso": (6, 12),
    "hips": (11, 12),
    "left_thigh": (11, 13),
    "left_lower_leg": (13, 15),
    "right_thigh": (12, 14),
    "right_lower_leg": (14, 16),
    "left_ankle_big_toe": (15, 17),
    "left_ankle_small_toe": (15, 18),
    "left_ankle_heel": (15, 19),
    "left_toe_width": (17, 18),
    "left_foot_side": (18, 19),
    "right_ankle_big_toe": (16, 20),
    "right_ankle_small_toe": (16, 21),
    "right_ankle_heel": (16, 22),
    "right_toe_width": (20, 21),
    "right_foot_side": (21, 22),
}
_CHILD_JOINTS = {7, 8, 9, 10, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}


class RejectionReason(StrEnum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INVALID_COORDINATE = "INVALID_COORDINATE"
    OUT_OF_FRAME = "OUT_OF_FRAME"
    EDGE_UNCERTAIN = "EDGE_UNCERTAIN"
    BONE_LENGTH_OUTLIER = "BONE_LENGTH_OUTLIER"
    BONE_DIRECTION_OUTLIER = "BONE_DIRECTION_OUTLIER"
    JOINT_VELOCITY_OUTLIER = "JOINT_VELOCITY_OUTLIER"
    JOINT_ACCELERATION_OUTLIER = "JOINT_ACCELERATION_OUTLIER"
    TRACK_LOST = "TRACK_LOST"
    TRACK_REACQUIRING = "TRACK_REACQUIRING"
    TEMPORAL_OUTLIER = "TEMPORAL_OUTLIER"
    OCCLUDED = "OCCLUDED"
    DEPENDENCY_INVALID = "DEPENDENCY_INVALID"


@dataclass(frozen=True)
class BodyValidationConfig:
    keypoint_threshold: float = 0.78
    edge_margin_ratio: float = 0.025
    edge_high_confidence_threshold: float = 0.92
    maximum_joint_velocity_bbox_ratio: float = 0.38
    maximum_joint_acceleration_bbox_ratio: float = 0.55
    bone_log_tolerance: float = 0.42
    maximum_bone_direction_change_degrees: float = 120.0
    locked_keypoint_threshold_ratio: float = 0.90
    profile_minimum_samples: int = 4
    profile_maximum_samples: int = 90


@dataclass(frozen=True)
class JointDiagnostic:
    raw_confidence: float
    quality: float
    valid: bool
    reason: str | None


@dataclass(frozen=True)
class BoneDiagnostic:
    valid: bool
    quality: float
    normalized_length: float | None
    reason: str | None


@dataclass(frozen=True)
class BodyValidationResult:
    points: np.ndarray
    scores: np.ndarray
    joints: tuple[JointDiagnostic, ...]
    bones: dict[str, BoneDiagnostic]
    quality: float
    valid_joint_ratio: float
    out_of_frame_joint_count: int


class BodyProportionProfile:
    """Robust person-specific median bone lengths normalized to bbox height."""

    def __init__(self, maximum_samples: int = 90) -> None:
        self._samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=maximum_samples)
        )

    def expected(self, bone_name: str, minimum_samples: int = 4) -> float | None:
        values = list(self._samples.get(bone_name, ()))
        if len(values) < minimum_samples:
            return None
        return float(np.median(np.asarray(values, dtype=float)))

    def add(self, bone_name: str, normalized_length: float) -> bool:
        if not math.isfinite(normalized_length) or not 0.01 <= normalized_length <= 1.25:
            return False
        values = list(self._samples.get(bone_name, ()))
        if len(values) >= 4:
            array = np.asarray(values, dtype=float)
            median = float(np.median(array))
            mad = float(np.median(np.abs(array - median)))
            tolerance = max(0.08 * median, 3.5 * mad)
            if abs(normalized_length - median) > tolerance:
                return False
        self._samples[bone_name].append(float(normalized_length))
        return True

    def to_dict(self) -> dict[str, dict[str, float | int | None]]:
        return {
            name: {
                "samples": len(self._samples.get(name, ())),
                "median": round(value, 6) if value is not None else None,
            }
            for name in BODY_BONES
            if (value := self.expected(name, 1)) is not None
        }


class BodyValidator:
    def __init__(self, config: BodyValidationConfig) -> None:
        self.config = config
        self.profile = BodyProportionProfile(config.profile_maximum_samples)
        self._previous_points = np.zeros((BODY_POINT_COUNT, 2), dtype=np.float32)
        self._previous_valid = np.zeros((BODY_POINT_COUNT,), dtype=bool)
        self._previous_velocity = np.zeros((BODY_POINT_COUNT, 2), dtype=np.float32)
        self._previous_bone_vectors: dict[str, np.ndarray] = {}

    def validate(
        self,
        points: np.ndarray,
        scores: np.ndarray,
        bbox: np.ndarray | None,
        tracking: TrackingDecision,
        frame_width: int,
        frame_height: int,
        *,
        motion_gate_multiplier: float = 1.0,
    ) -> BodyValidationResult:
        output_points = np.zeros((points.shape[0], 2), dtype=np.float32)
        output_scores = np.zeros((scores.shape[0],), dtype=np.float32)
        joints: list[JointDiagnostic] = []
        usable = min(BODY_POINT_COUNT, points.shape[0], scores.shape[0])
        bbox_height = _bbox_height(bbox, frame_height)
        margin_x = max(2.0, frame_width * self.config.edge_margin_ratio)
        margin_y = max(2.0, frame_height * self.config.edge_margin_ratio)
        out_of_frame_count = 0

        track_reason: RejectionReason | None = None
        if not tracking.accept_pose:
            track_reason = (
                RejectionReason.TRACK_REACQUIRING
                if tracking.state == TrackingState.REACQUIRING
                else RejectionReason.OCCLUDED
                if tracking.state == TrackingState.OCCLUDED
                else RejectionReason.TRACK_LOST
            )

        gate_multiplier = max(1.0, float(motion_gate_multiplier))
        locked_observation = tracking.accept_pose and tracking.state in {
            TrackingState.TRACKED,
            TrackingState.PARTIAL,
            TrackingState.OCCLUDED,
        }
        confidence_threshold = self.config.keypoint_threshold * (
            self.config.locked_keypoint_threshold_ratio if locked_observation else 1.0
        )

        for index in range(BODY_POINT_COUNT):
            raw_confidence = (
                float(np.clip(scores[index], 0.0, 1.0))
                if index < scores.shape[0] and math.isfinite(float(scores[index]))
                else 0.0
            )
            reason = track_reason
            tracking_quality = (
                1.0
                if tracking.state == TrackingState.TRACKED
                else 0.78
                if tracking.state == TrackingState.PARTIAL
                else 0.60
                if tracking.state == TrackingState.OCCLUDED
                else 0.0
            )
            quality_components = [raw_confidence, tracking_quality]
            coordinate: np.ndarray | None = None
            if reason is None:
                if index >= usable or not np.isfinite(points[index]).all():
                    reason = RejectionReason.INVALID_COORDINATE
                elif raw_confidence < confidence_threshold:
                    reason = RejectionReason.LOW_CONFIDENCE
                else:
                    coordinate = np.asarray(points[index], dtype=np.float32)
                    x, y = float(coordinate[0]), float(coordinate[1])
                    if x < 0.0 or y < 0.0 or x >= frame_width or y >= frame_height:
                        reason = RejectionReason.OUT_OF_FRAME
                        out_of_frame_count += 1
                    else:
                        edge_distance = min(x, frame_width - 1 - x, y, frame_height - 1 - y)
                        edge_margin = min(margin_x, margin_y)
                        edge_quality = float(np.clip(edge_distance / max(edge_margin, 1.0), 0.0, 1.0))
                        quality_components.append(edge_quality)
                        if edge_quality < 1.0 and raw_confidence < self.config.edge_high_confidence_threshold:
                            reason = RejectionReason.EDGE_UNCERTAIN

            velocity = np.zeros((2,), dtype=np.float32)
            if reason is None and coordinate is not None and self._previous_valid[index]:
                velocity = (coordinate - self._previous_points[index]) / bbox_height
                velocity_norm = float(np.linalg.norm(velocity))
                velocity_quality = max(
                    0.0,
                    1.0 - velocity_norm / self.config.maximum_joint_velocity_bbox_ratio,
                )
                quality_components.append(velocity_quality)
                if velocity_norm > self.config.maximum_joint_velocity_bbox_ratio * gate_multiplier:
                    reason = RejectionReason.JOINT_VELOCITY_OUTLIER
                else:
                    acceleration = float(np.linalg.norm(velocity - self._previous_velocity[index]))
                    acceleration_quality = max(
                        0.0,
                        1.0 - acceleration / self.config.maximum_joint_acceleration_bbox_ratio,
                    )
                    quality_components.append(acceleration_quality)
                    if acceleration > self.config.maximum_joint_acceleration_bbox_ratio * gate_multiplier * gate_multiplier:
                        reason = RejectionReason.JOINT_ACCELERATION_OUTLIER

            valid = reason is None and coordinate is not None
            quality = float(np.clip(np.mean(quality_components), 0.0, 1.0)) if valid else 0.0
            if valid and coordinate is not None:
                output_points[index] = np.clip(
                    coordinate,
                    [0.0, 0.0],
                    [max(0, frame_width - 1), max(0, frame_height - 1)],
                )
                output_scores[index] = quality
                self._previous_points[index] = coordinate
                self._previous_velocity[index] = velocity
            self._previous_valid[index] = valid
            joints.append(JointDiagnostic(raw_confidence, quality, valid, reason.value if reason else None))

        while len(joints) < BODY_POINT_COUNT:
            joints.append(JointDiagnostic(0.0, 0.0, False, RejectionReason.INVALID_COORDINATE.value))

        bones: dict[str, BoneDiagnostic] = {}
        for name, (first, second) in BODY_BONES.items():
            if not joints[first].valid or not joints[second].valid:
                bones[name] = BoneDiagnostic(
                    False,
                    0.0,
                    None,
                    RejectionReason.DEPENDENCY_INVALID.value,
                )
                continue
            length = float(np.linalg.norm(output_points[second] - output_points[first]))
            vector = output_points[second] - output_points[first]
            normalized = length / bbox_height
            expected = self.profile.expected(name, self.config.profile_minimum_samples)
            error = abs(math.log(max(normalized, 1e-6) / max(expected, 1e-6))) if expected else 0.0
            valid = math.isfinite(normalized) and 0.01 <= normalized <= 1.25 and error <= self.config.bone_log_tolerance
            direction_quality = 1.0
            previous_vector = self._previous_bone_vectors.get(name)
            if valid and previous_vector is not None:
                denominator = float(np.linalg.norm(vector) * np.linalg.norm(previous_vector))
                if denominator > 1e-8:
                    direction_change = math.degrees(
                        math.acos(
                            float(
                                np.clip(
                                    np.dot(vector, previous_vector) / denominator,
                                    -1.0,
                                    1.0,
                                )
                            )
                        )
                    )
                    direction_quality = max(
                        0.0,
                        1.0
                        - direction_change
                        / (self.config.maximum_bone_direction_change_degrees * gate_multiplier),
                    )
                    if direction_change > self.config.maximum_bone_direction_change_degrees * gate_multiplier:
                        valid = False
            quality = (
                float(
                    np.clip(
                        min(
                            1.0
                            - error
                            / max(self.config.bone_log_tolerance, 1e-6),
                            direction_quality,
                        ),
                        0.0,
                        1.0,
                    )
                )
                if valid
                else 0.0
            )
            reason = (
                None
                if valid
                else RejectionReason.BONE_DIRECTION_OUTLIER.value
                if direction_quality <= 0.0
                else RejectionReason.BONE_LENGTH_OUTLIER.value
            )
            bones[name] = BoneDiagnostic(valid, quality, normalized if math.isfinite(normalized) else None, reason)
            if valid:
                self._previous_bone_vectors[name] = vector.copy()
            if not valid and second in _CHILD_JOINTS:
                output_points[second] = 0.0
                output_scores[second] = 0.0
                original = joints[second]
                joints[second] = JointDiagnostic(
                    original.raw_confidence,
                    0.0,
                    False,
                    RejectionReason.BONE_LENGTH_OUTLIER.value,
                )
                # Do not use a joint rejected by bone validation as the
                # temporal anchor of the next frame.
                self._previous_valid[second] = False
            elif valid and second in _CHILD_JOINTS:
                original = joints[second]
                combined_quality = min(original.quality, quality)
                joints[second] = JointDiagnostic(
                    original.raw_confidence,
                    combined_quality,
                    True,
                    None,
                )
                output_scores[second] = combined_quality

        if tracking.accept_pose and tracking.state == TrackingState.TRACKED:
            for name, diagnostic in bones.items():
                if diagnostic.valid and diagnostic.normalized_length is not None:
                    self.profile.add(name, diagnostic.normalized_length)

        valid_count = sum(1 for joint in joints if joint.valid)
        valid_ratio = valid_count / BODY_POINT_COUNT
        valid_qualities = [joint.quality for joint in joints if joint.valid]
        body_quality = float(np.mean(valid_qualities)) * valid_ratio if valid_qualities else 0.0
        return BodyValidationResult(
            points=output_points,
            scores=output_scores,
            joints=tuple(joints),
            bones=bones,
            quality=float(np.clip(body_quality, 0.0, 1.0)),
            valid_joint_ratio=valid_ratio,
            out_of_frame_joint_count=out_of_frame_count,
        )


def serialize_body_validation(result: BodyValidationResult) -> dict[str, object]:
    return {
        "quality": round(result.quality, 6),
        "valid_joint_ratio": round(result.valid_joint_ratio, 6),
        "out_of_frame_joint_count": result.out_of_frame_joint_count,
        "joints": [
            {
                "raw_confidence": round(joint.raw_confidence, 6),
                "quality": round(joint.quality, 6),
                "valid": joint.valid,
                "reason": joint.reason,
            }
            for joint in result.joints
        ],
        "bones": {
            name: {
                "valid": bone.valid,
                "quality": round(bone.quality, 6),
                "normalized_length": (
                    round(bone.normalized_length, 6)
                    if bone.normalized_length is not None
                    else None
                ),
                "reason": bone.reason,
            }
            for name, bone in result.bones.items()
        },
    }


def _bbox_height(bbox: np.ndarray | None, frame_height: int) -> float:
    if bbox is None:
        return max(1.0, frame_height * 0.5)
    values = np.asarray(bbox, dtype=float).reshape(-1)
    if values.size != 4 or not np.isfinite(values).all():
        return max(1.0, frame_height * 0.5)
    return max(1.0, float(values[3] - values[1]))

"""Central biomechanical pose graph for Worker V0.4.

The graph deliberately separates raw model output, validated analytical
geometry and render-only state. Predicted coordinates are diagnostics and
candidate gates; they never become valid measurements.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterable

import numpy as np

try:  # package import in tests / module import in the standalone worker
    from ..pose_v3.body_validation import (
        BODY_BONES,
        BODY_POINT_COUNT,
        BodyValidationConfig,
        BodyValidationResult,
        BodyValidator,
    )
    from ..pose_v3.tracking import TrackingDecision, TrackingState
except ImportError:  # pragma: no cover - exercised by script-mode worker
    from pose_v3.body_validation import (
        BODY_BONES,
        BODY_POINT_COUNT,
        BodyValidationConfig,
        BodyValidationResult,
        BodyValidator,
    )
    from pose_v3.tracking import TrackingDecision, TrackingState


JOINT_NAMES: tuple[str, ...] = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_big_toe",
    "left_small_toe",
    "left_heel",
    "right_big_toe",
    "right_small_toe",
    "right_heel",
)

LIMB_CHAINS: dict[str, tuple[int, ...]] = {
    "left_arm": (5, 7, 9),
    "right_arm": (6, 8, 10),
    "left_leg": (11, 13, 15, 17),
    "right_leg": (12, 14, 16, 20),
}

SYMMETRIC_BONE_PAIRS: tuple[tuple[str, str], ...] = (
    ("left_upper_arm", "right_upper_arm"),
    ("left_forearm", "right_forearm"),
    ("left_thigh", "right_thigh"),
    ("left_lower_leg", "right_lower_leg"),
    ("left_ankle_big_toe", "right_ankle_big_toe"),
)

JOINT_TO_LIMB: dict[int, str] = {
    joint: limb for limb, chain in LIMB_CHAINS.items() for joint in chain
}


class MeasurementSource(StrEnum):
    RAW = "raw"
    INTERPOLATED = "interpolated"
    PREDICTED = "predicted"
    MISSING = "missing"


class TemporalState(StrEnum):
    STABLE = "STABLE"
    SUSPECT = "SUSPECT"
    INTERPOLATED = "INTERPOLATED"
    PREDICTED_SHORT = "PREDICTED_SHORT"
    MISSING = "MISSING"


class OcclusionState(StrEnum):
    VISIBLE = "VISIBLE"
    OCCLUDED_BY_BODY = "OCCLUDED_BY_BODY"
    OCCLUDED = "OCCLUDED"
    OUT_OF_FRAME = "OUT_OF_FRAME"
    UNKNOWN = "UNKNOWN"


class LimbState(StrEnum):
    VISIBLE = "VISIBLE"
    PARTIAL = "PARTIAL"
    OCCLUDED = "OCCLUDED"
    OUT_OF_FRAME = "OUT_OF_FRAME"
    PREDICTED_SHORT = "PREDICTED_SHORT"
    LOST = "LOST"
    REACQUIRING = "REACQUIRING"


@dataclass(frozen=True)
class PoseGraphConfig:
    body_validation: BodyValidationConfig = field(default_factory=BodyValidationConfig)
    maximum_prediction_frames: int = 2
    prediction_damping: float = 0.72
    candidate_distance_gate_scale: float = 0.32
    reacquiring_gate_multiplier: float = 1.45
    maximum_scale_change_ratio: float = 0.18
    profile_minimum_quality: float = 0.78
    limb_reacquire_confirm_frames: int = 2
    torso_occlusion_margin_ratio: float = 0.08

    def validate(self) -> None:
        if self.maximum_prediction_frames < 0 or self.maximum_prediction_frames > 5:
            raise ValueError("maximum_prediction_frames must be in range 0..5")
        if not 0.0 < self.prediction_damping <= 1.0:
            raise ValueError("prediction_damping must be in range (0, 1]")
        if self.candidate_distance_gate_scale <= 0.0:
            raise ValueError("candidate_distance_gate_scale must be positive")
        if self.reacquiring_gate_multiplier < 1.0:
            raise ValueError("reacquiring_gate_multiplier must be at least 1")
        if not 0.0 < self.maximum_scale_change_ratio < 1.0:
            raise ValueError("maximum_scale_change_ratio must be in range (0, 1)")
        if not 0.0 <= self.profile_minimum_quality <= 1.0:
            raise ValueError("profile_minimum_quality must be in range 0..1")
        if self.limb_reacquire_confirm_frames < 1:
            raise ValueError("limb_reacquire_confirm_frames must be positive")


@dataclass(frozen=True)
class BodyAnchors:
    shoulder_center: tuple[float, float] | None
    hip_center: tuple[float, float] | None
    torso_center: tuple[float, float] | None
    torso_axis: tuple[float, float] | None
    quality: float


@dataclass(frozen=True)
class JointState:
    name: str
    coordinates: tuple[float, float] | None
    raw_coordinates: tuple[float, float] | None
    confidence: float
    quality: float
    visibility: float
    valid: bool
    temporal_state: TemporalState
    occlusion_state: OcclusionState
    source: MeasurementSource
    rejection_reasons: tuple[str, ...]
    velocity: tuple[float, float]
    acceleration: tuple[float, float]
    predicted_position: tuple[float, float] | None
    edge_distance: float | None
    interpolation_age: int


@dataclass(frozen=True)
class BoneState:
    name: str
    joint_a: str
    joint_b: str
    valid: bool
    quality: float
    normalized_length: float | None
    reference_length: float | None
    length_error: float | None
    angular_velocity: float | None
    occlusion_state: OcclusionState
    render_state: str
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class LimbDiagnostic:
    name: str
    state: LimbState
    quality: float
    valid_joint_count: int
    expected_joint_count: int
    occluded_joint_count: int
    out_of_frame_joint_count: int
    prediction_age: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PoseGraphFrame:
    raw_points: np.ndarray
    raw_scores: np.ndarray
    analysis_points: np.ndarray
    analysis_scores: np.ndarray
    joints: tuple[JointState, ...]
    bones: dict[str, BoneState]
    limbs: dict[str, LimbDiagnostic]
    anchors: BodyAnchors
    body_scale: float
    body_scale_quality: float
    body_coverage_ratio: float
    quality: float
    tracking_state: str
    relative_depth_available: bool
    frame_width: int
    frame_height: int

    def interpolation_allowed(self) -> np.ndarray:
        prohibited_occlusion = {
            OcclusionState.OCCLUDED,
            OcclusionState.OCCLUDED_BY_BODY,
            OcclusionState.OUT_OF_FRAME,
        }
        prohibited_limb = {
            LimbState.OCCLUDED,
            LimbState.OUT_OF_FRAME,
            LimbState.LOST,
        }
        allowed: list[bool] = []
        for index, joint in enumerate(self.joints):
            limb_name = JOINT_TO_LIMB.get(index)
            limb = self.limbs.get(limb_name) if limb_name is not None else None
            allowed.append(
                joint.occlusion_state not in prohibited_occlusion
                and (limb is None or limb.state not in prohibited_limb)
            )
        body = np.asarray(allowed, dtype=bool)
        output = np.zeros((self.analysis_scores.shape[0],), dtype=bool)
        output[: min(body.size, output.size)] = body[: min(body.size, output.size)]
        return output

    def to_dict(self) -> dict[str, object]:
        return {
            "body_scale": round(self.body_scale, 6),
            "body_scale_quality": round(self.body_scale_quality, 6),
            "body_coverage_ratio": round(self.body_coverage_ratio, 6),
            "quality": round(self.quality, 6),
            "tracking_state": self.tracking_state,
            "relative_depth_available": self.relative_depth_available,
            "frame_size": {"width": self.frame_width, "height": self.frame_height},
            "anchors": {
                "shoulder_center": _rounded_point(self.anchors.shoulder_center),
                "hip_center": _rounded_point(self.anchors.hip_center),
                "torso_center": _rounded_point(self.anchors.torso_center),
                "torso_axis": _rounded_point(self.anchors.torso_axis),
                "quality": round(self.anchors.quality, 6),
            },
            "joints": [serialize_joint(joint) for joint in self.joints],
            "bones": {name: serialize_bone(bone) for name, bone in self.bones.items()},
            "limbs": {name: serialize_limb(limb) for name, limb in self.limbs.items()},
        }


class AdaptiveBodyScale:
    """Robust screen-space scale estimated from person-specific anchor ratios."""

    def __init__(self, maximum_samples: int = 90) -> None:
        self._ratios: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=maximum_samples)
        )
        self._last_scale: float | None = None

    def estimate(
        self,
        measurements: dict[str, float],
        bbox_height: float,
        *,
        update_profile: bool,
        maximum_change_ratio: float,
    ) -> tuple[float, float]:
        safe_bbox = max(1.0, float(bbox_height))
        candidates = [safe_bbox]
        for name, value in measurements.items():
            if not math.isfinite(value) or value <= 1e-6:
                continue
            references = self._ratios.get(name)
            if references:
                reference = float(np.median(np.asarray(references, dtype=float)))
                if reference > 1e-6:
                    candidates.append(value / reference)
            if update_profile:
                ratio = value / safe_bbox
                if 0.01 <= ratio <= 1.25 and self._accept_ratio(name, ratio):
                    self._ratios[name].append(ratio)
        raw_scale = float(np.median(np.asarray(candidates, dtype=float)))
        if self._last_scale is not None:
            minimum = self._last_scale * (1.0 - maximum_change_ratio)
            maximum = self._last_scale * (1.0 + maximum_change_ratio)
            scale = float(np.clip(raw_scale, minimum, maximum))
        else:
            scale = raw_scale
        dispersion = float(np.median(np.abs(np.asarray(candidates) - raw_scale)))
        quality = float(np.clip(1.0 - dispersion / max(raw_scale * 0.20, 1e-6), 0.0, 1.0))
        if update_profile or self._last_scale is None:
            self._last_scale = scale
        return max(1.0, scale), quality

    def _accept_ratio(self, name: str, value: float) -> bool:
        samples = list(self._ratios.get(name, ()))
        if len(samples) < 4:
            return True
        array = np.asarray(samples, dtype=float)
        median = float(np.median(array))
        mad = float(np.median(np.abs(array - median)))
        return abs(value - median) <= max(3.5 * mad, median * 0.08)


class DynamicBoneProfile:
    """Stable references with median, MAD, confidence and bounded memory."""

    def __init__(self, maximum_samples: int = 120) -> None:
        self._samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=maximum_samples)
        )

    def add(self, name: str, value: float) -> bool:
        if not math.isfinite(value) or not 0.005 <= value <= 1.5:
            return False
        reference = self.reference(name)
        if reference is not None:
            median, mad, _, _ = reference
            if abs(value - median) > max(3.5 * mad, median * 0.10):
                return False
        self._samples[name].append(float(value))
        return True

    def reference(self, name: str) -> tuple[float, float, float, int] | None:
        values = list(self._samples.get(name, ()))
        if not values:
            return None
        array = np.asarray(values, dtype=float)
        median = float(np.median(array))
        mad = float(np.median(np.abs(array - median)))
        confidence = float(np.clip(len(values) / 12.0, 0.0, 1.0))
        return median, mad, confidence, len(values)

    def to_dict(self) -> dict[str, dict[str, float | int]]:
        result: dict[str, dict[str, float | int]] = {}
        for name in BODY_BONES:
            reference = self.reference(name)
            if reference is None:
                continue
            median, mad, confidence, count = reference
            result[name] = {
                "median": round(median, 6),
                "mad": round(mad, 6),
                "rolling_confidence": round(confidence, 6),
                "sample_count": count,
                "stable_reference": round(median, 6),
            }
        return result


@dataclass
class _JointMemory:
    position: np.ndarray | None = None
    velocity: np.ndarray = field(default_factory=lambda: np.zeros((2,), dtype=np.float32))
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros((2,), dtype=np.float32))
    missing_frames: int = 0


@dataclass
class _LimbMemory:
    state: LimbState = LimbState.LOST
    reacquire_frames: int = 0
    missing_frames: int = 0


class BiomechanicalPoseGraph:
    """Stateful local + chain + global validation for the main person."""

    def __init__(self, config: PoseGraphConfig) -> None:
        config.validate()
        self.config = config
        self.local_validator = BodyValidator(config.body_validation)
        self.scale_profile = AdaptiveBodyScale()
        self.bone_profile = DynamicBoneProfile()
        self._joints = [_JointMemory() for _ in range(BODY_POINT_COUNT)]
        self._limbs = {name: _LimbMemory() for name in LIMB_CHAINS}
        self._previous_bone_vectors: dict[str, np.ndarray] = {}
        self._last_timestamp: float | None = None

    def update(
        self,
        *,
        raw_points: np.ndarray,
        raw_scores: np.ndarray,
        bbox: np.ndarray | None,
        tracking: TrackingDecision,
        frame_width: int,
        frame_height: int,
        timestamp_seconds: float,
        relative_depth: np.ndarray | None = None,
    ) -> PoseGraphFrame:
        local = self.local_validator.validate(
            raw_points,
            raw_scores,
            bbox,
            tracking,
            frame_width,
            frame_height,
        )
        delta = self._frame_delta(timestamp_seconds)
        anchors = _body_anchors(local)
        bbox_height = _bbox_height(bbox, frame_height)
        measurements = _anchor_measurements(local.points, local.scores)
        update_profile = (
            tracking.state == TrackingState.TRACKED
            and tracking.accept_pose
            and local.quality >= self.config.profile_minimum_quality
            and anchors.quality >= self.config.profile_minimum_quality
        )
        body_scale, scale_quality = self.scale_profile.estimate(
            measurements,
            bbox_height,
            update_profile=update_profile,
            maximum_change_ratio=self.config.maximum_scale_change_ratio,
        )
        joints = self._joint_states(
            raw_points,
            raw_scores,
            local,
            tracking,
            bbox,
            body_scale,
            frame_width,
            frame_height,
            delta,
        )
        limbs = self._limb_states(joints, bbox, frame_width, frame_height)
        joints = self._apply_chain_hierarchy(joints, limbs)
        analysis_points, analysis_scores = _joint_arrays(joints, raw_points.shape[0])
        bones = self._bone_states(
            joints,
            analysis_points,
            body_scale,
            delta,
            update_profile,
        )
        joints, analysis_points, analysis_scores = self._invalidate_bad_bone_children(
            joints,
            bones,
            analysis_points,
            analysis_scores,
        )
        valid_joint_count = sum(joint.valid for joint in joints)
        coverage = valid_joint_count / BODY_POINT_COUNT
        valid_quality = [joint.quality for joint in joints if joint.valid]
        quality = (
            float(np.median(np.asarray(valid_quality))) * coverage * scale_quality
            if valid_quality
            else 0.0
        )
        return PoseGraphFrame(
            raw_points=np.asarray(raw_points, dtype=np.float32).copy(),
            raw_scores=np.asarray(raw_scores, dtype=np.float32).copy(),
            analysis_points=analysis_points,
            analysis_scores=analysis_scores,
            joints=tuple(joints),
            bones=bones,
            limbs=limbs,
            anchors=anchors,
            body_scale=body_scale,
            body_scale_quality=scale_quality,
            body_coverage_ratio=coverage,
            quality=float(np.clip(quality, 0.0, 1.0)),
            tracking_state=tracking.state.value,
            relative_depth_available=_relative_depth_available(relative_depth),
            frame_width=frame_width,
            frame_height=frame_height,
        )

    def _frame_delta(self, timestamp: float) -> float:
        delta = (
            timestamp - self._last_timestamp
            if self._last_timestamp is not None and math.isfinite(timestamp)
            else 0.0
        )
        self._last_timestamp = timestamp if math.isfinite(timestamp) else self._last_timestamp
        return delta if math.isfinite(delta) and delta > 1e-6 else 1.0 / 30.0

    def _joint_states(
        self,
        raw_points: np.ndarray,
        raw_scores: np.ndarray,
        local: BodyValidationResult,
        tracking: TrackingDecision,
        bbox: np.ndarray | None,
        body_scale: float,
        width: int,
        height: int,
        delta: float,
    ) -> list[JointState]:
        output: list[JointState] = []
        torso_bounds = _torso_bounds(local.points, local.scores, body_scale)
        gate_multiplier = (
            self.config.reacquiring_gate_multiplier
            if tracking.state == TrackingState.REACQUIRING
            else 1.0
        )
        for index in range(BODY_POINT_COUNT):
            memory = self._joints[index]
            raw = _finite_point(raw_points, index)
            confidence = _finite_score(raw_scores, index)
            local_joint = local.joints[index]
            candidate = local.points[index].copy() if local_joint.valid else None
            predicted = _predict(memory, delta, self.config.prediction_damping)
            reasons = [local_joint.reason] if local_joint.reason else []
            velocity = np.zeros((2,), dtype=np.float32)
            acceleration = np.zeros((2,), dtype=np.float32)
            valid = candidate is not None
            quality = local_joint.quality if valid else 0.0
            temporal_state = TemporalState.STABLE if valid else TemporalState.MISSING
            source = MeasurementSource.RAW if valid else MeasurementSource.MISSING
            if valid and candidate is not None and predicted is not None and memory.position is not None:
                distance = float(np.linalg.norm(candidate - predicted))
                gate = self.config.candidate_distance_gate_scale * body_scale * gate_multiplier
                if distance > gate:
                    valid = False
                    quality = 0.0
                    temporal_state = TemporalState.SUSPECT
                    source = MeasurementSource.MISSING
                    reasons.append("EXPECTED_POSITION_GATE")
                else:
                    velocity = (candidate - memory.position) / max(delta, 1e-6)
                    acceleration = (velocity - memory.velocity) / max(delta, 1e-6)
                    temporal_quality = float(np.clip(1.0 - distance / max(gate, 1e-6), 0.0, 1.0))
                    quality = min(quality, 0.45 + 0.55 * temporal_quality)
            occlusion = OcclusionState.VISIBLE
            if not valid:
                memory.missing_frames += 1
                occlusion = _infer_occlusion(
                    predicted,
                    bbox,
                    torso_bounds,
                    width,
                    height,
                )
                if predicted is not None and memory.missing_frames <= self.config.maximum_prediction_frames:
                    temporal_state = TemporalState.PREDICTED_SHORT
                    source = MeasurementSource.PREDICTED
                else:
                    predicted = None
            else:
                memory.missing_frames = 0
                if candidate is not None:
                    memory.position = candidate.copy()
                    memory.acceleration = acceleration.copy()
                    memory.velocity = velocity.copy()
            edge_distance = _edge_distance(candidate if valid else raw, width, height)
            output.append(
                JointState(
                    name=JOINT_NAMES[index],
                    coordinates=_point_tuple(candidate) if valid else None,
                    raw_coordinates=_point_tuple(raw),
                    confidence=confidence,
                    quality=float(np.clip(quality, 0.0, 1.0)),
                    visibility=float(np.clip(confidence, 0.0, 1.0)) if valid else 0.0,
                    valid=valid,
                    temporal_state=temporal_state,
                    occlusion_state=occlusion,
                    source=source,
                    rejection_reasons=tuple(dict.fromkeys(reason for reason in reasons if reason)),
                    velocity=_point_tuple(velocity) or (0.0, 0.0),
                    acceleration=_point_tuple(acceleration) or (0.0, 0.0),
                    predicted_position=_point_tuple(predicted),
                    edge_distance=edge_distance,
                    interpolation_age=0,
                )
            )
        return output

    def _limb_states(
        self,
        joints: list[JointState],
        bbox: np.ndarray | None,
        width: int,
        height: int,
    ) -> dict[str, LimbDiagnostic]:
        output: dict[str, LimbDiagnostic] = {}
        for name, chain in LIMB_CHAINS.items():
            memory = self._limbs[name]
            selected = [joints[index] for index in chain]
            valid_count = sum(joint.valid for joint in selected)
            out_count = sum(joint.occlusion_state == OcclusionState.OUT_OF_FRAME for joint in selected)
            occluded_count = sum(
                joint.occlusion_state in {OcclusionState.OCCLUDED, OcclusionState.OCCLUDED_BY_BODY}
                for joint in selected
            )
            reasons: list[str] = []
            if valid_count == len(chain):
                proposed = LimbState.VISIBLE
            elif valid_count > 0 and out_count > 0:
                proposed = LimbState.OUT_OF_FRAME
                reasons.append("LIMB_OUT_OF_FRAME")
            elif valid_count > 0 and occluded_count > 0:
                proposed = LimbState.OCCLUDED
                reasons.append("LIMB_OCCLUDED")
            elif valid_count > 0:
                proposed = LimbState.PARTIAL
                reasons.append("LIMB_PARTIAL")
            elif out_count > 0:
                proposed = LimbState.OUT_OF_FRAME
                reasons.append("LIMB_OUT_OF_FRAME")
            elif occluded_count > 0:
                proposed = LimbState.OCCLUDED
                reasons.append("LIMB_OCCLUDED")
            elif any(joint.predicted_position is not None for joint in selected):
                proposed = LimbState.PREDICTED_SHORT
                reasons.append("SHORT_TERM_PREDICTION")
            else:
                proposed = LimbState.LOST
                reasons.append("LIMB_LOST")

            if proposed == LimbState.VISIBLE and memory.state in {
                LimbState.LOST,
                LimbState.OCCLUDED,
                LimbState.OUT_OF_FRAME,
            }:
                memory.reacquire_frames += 1
                if memory.reacquire_frames < self.config.limb_reacquire_confirm_frames:
                    proposed = LimbState.REACQUIRING
                    reasons.append("LIMB_REACQUIRING")
                else:
                    memory.reacquire_frames = 0
            elif proposed != LimbState.VISIBLE:
                memory.reacquire_frames = 0
            memory.state = proposed
            memory.missing_frames = 0 if valid_count else memory.missing_frames + 1
            qualities = [joint.quality for joint in selected if joint.valid]
            quality = float(np.median(np.asarray(qualities))) * valid_count / len(chain) if qualities else 0.0
            output[name] = LimbDiagnostic(
                name=name,
                state=proposed,
                quality=float(np.clip(quality, 0.0, 1.0)),
                valid_joint_count=valid_count,
                expected_joint_count=len(chain),
                occluded_joint_count=occluded_count,
                out_of_frame_joint_count=out_count,
                prediction_age=memory.missing_frames,
                reasons=tuple(dict.fromkeys(reasons)),
            )
        return output

    def _apply_chain_hierarchy(
        self,
        joints: list[JointState],
        limbs: dict[str, LimbDiagnostic],
    ) -> list[JointState]:
        output = list(joints)
        for limb_name, chain in LIMB_CHAINS.items():
            parent_valid = True
            for position, index in enumerate(chain):
                joint = output[index]
                if position > 0 and not parent_valid and joint.valid:
                    output[index] = _replace_joint(
                        joint,
                        quality=joint.quality * 0.55,
                        reasons=(*joint.rejection_reasons, "PARENT_ANCHOR_INVALID"),
                    )
                parent_valid = output[index].valid
            if limbs[limb_name].state == LimbState.REACQUIRING:
                for index in chain[1:]:
                    joint = output[index]
                    if joint.valid:
                        output[index] = _replace_joint(
                            joint,
                            quality=joint.quality * 0.72,
                            reasons=(*joint.rejection_reasons, "LIMB_REACQUIRING"),
                        )
        return output

    def _bone_states(
        self,
        joints: list[JointState],
        points: np.ndarray,
        body_scale: float,
        delta: float,
        update_profile: bool,
    ) -> dict[str, BoneState]:
        output: dict[str, BoneState] = {}
        for name, (first, second) in BODY_BONES.items():
            first_joint, second_joint = joints[first], joints[second]
            reasons: list[str] = []
            if not first_joint.valid or not second_joint.valid:
                reasons.append("DEPENDENCY_INVALID")
                occlusion = _stronger_occlusion(first_joint.occlusion_state, second_joint.occlusion_state)
                output[name] = BoneState(
                    name,
                    JOINT_NAMES[first],
                    JOINT_NAMES[second],
                    False,
                    0.0,
                    None,
                    None,
                    None,
                    None,
                    occlusion,
                    "HIDDEN",
                    tuple(reasons),
                )
                continue
            vector = points[second] - points[first]
            length = float(np.linalg.norm(vector))
            normalized = length / max(body_scale, 1e-6)
            reference_data = self.bone_profile.reference(name)
            reference = reference_data[0] if reference_data else None
            mad = reference_data[1] if reference_data else 0.0
            length_error = abs(normalized - reference) if reference is not None else 0.0
            tolerance = max(4.0 * mad, (reference or normalized) * 0.16, 0.015)
            valid = math.isfinite(normalized) and 0.005 <= normalized <= 0.85
            if reference is not None and length_error > tolerance:
                valid = False
                reasons.append("GLOBAL_BONE_LENGTH_OUTLIER")
            previous_vector = self._previous_bone_vectors.get(name)
            angular_velocity = _angular_velocity(previous_vector, vector, delta)
            if angular_velocity is not None and angular_velocity > 900.0:
                valid = False
                reasons.append("BONE_ANGULAR_VELOCITY_OUTLIER")
            length_quality = (
                float(np.clip(1.0 - length_error / max(tolerance, 1e-6), 0.0, 1.0))
                if reference is not None
                else 0.80
            )
            quality = min(first_joint.quality, second_joint.quality, length_quality) if valid else 0.0
            if valid:
                self._previous_bone_vectors[name] = vector.copy()
                if update_profile and quality >= self.config.profile_minimum_quality:
                    self.bone_profile.add(name, normalized)
            output[name] = BoneState(
                name=name,
                joint_a=JOINT_NAMES[first],
                joint_b=JOINT_NAMES[second],
                valid=valid,
                quality=float(np.clip(quality, 0.0, 1.0)),
                normalized_length=normalized if math.isfinite(normalized) else None,
                reference_length=reference,
                length_error=length_error if reference is not None else None,
                angular_velocity=angular_velocity,
                occlusion_state=OcclusionState.VISIBLE,
                render_state="VISIBLE" if valid else "HIDDEN",
                rejection_reasons=tuple(dict.fromkeys(reasons)),
            )
        for left_name, right_name in SYMMETRIC_BONE_PAIRS:
            left = output.get(left_name)
            right = output.get(right_name)
            if (
                left is None
                or right is None
                or not left.valid
                or not right.valid
                or left.normalized_length is None
                or right.normalized_length is None
            ):
                continue
            reference = max(
                (left.normalized_length + right.normalized_length) / 2.0,
                1e-6,
            )
            asymmetry = abs(left.normalized_length - right.normalized_length) / reference
            if asymmetry <= 0.28:
                continue
            # Symmetry is a soft quality signal and never invalidates a side.
            output[left_name] = replace(
                left,
                quality=left.quality * 0.75,
                rejection_reasons=(*left.rejection_reasons, "SYMMETRY_SOFT_WARNING"),
            )
            output[right_name] = replace(
                right,
                quality=right.quality * 0.75,
                rejection_reasons=(*right.rejection_reasons, "SYMMETRY_SOFT_WARNING"),
            )
        return output

    def _invalidate_bad_bone_children(
        self,
        joints: list[JointState],
        bones: dict[str, BoneState],
        points: np.ndarray,
        scores: np.ndarray,
    ) -> tuple[list[JointState], np.ndarray, np.ndarray]:
        output = list(joints)
        points = points.copy()
        scores = scores.copy()
        child_joints = {7, 8, 9, 10, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}
        for name, (_, child) in BODY_BONES.items():
            bone = bones[name]
            if bone.valid or child not in child_joints or not output[child].valid:
                continue
            points[child] = 0.0
            scores[child] = 0.0
            output[child] = _replace_joint(
                output[child],
                valid=False,
                quality=0.0,
                coordinates=None,
                temporal_state=TemporalState.SUSPECT,
                source=MeasurementSource.MISSING,
                reasons=(*output[child].rejection_reasons, *bone.rejection_reasons),
            )
            self._joints[child].position = None
        return output, points, scores


def apply_interpolation_metadata(
    frame: PoseGraphFrame,
    points: np.ndarray,
    scores: np.ndarray,
    interpolation_mask: np.ndarray,
) -> PoseGraphFrame:
    joints = list(frame.joints)
    for index in range(min(BODY_POINT_COUNT, interpolation_mask.size)):
        if not bool(interpolation_mask[index]):
            continue
        joints[index] = _replace_joint(
            joints[index],
            valid=True,
            quality=float(np.clip(scores[index], 0.0, 1.0)),
            coordinates=_point_tuple(points[index]),
            temporal_state=TemporalState.INTERPOLATED,
            source=MeasurementSource.INTERPOLATED,
            reasons=(*joints[index].rejection_reasons, "BIDIRECTIONAL_RECONSTRUCTION"),
            interpolation_age=1,
        )
    return PoseGraphFrame(
        raw_points=frame.raw_points,
        raw_scores=frame.raw_scores,
        analysis_points=points.copy(),
        analysis_scores=scores.copy(),
        joints=tuple(joints),
        bones=frame.bones,
        limbs=frame.limbs,
        anchors=frame.anchors,
        body_scale=frame.body_scale,
        body_scale_quality=frame.body_scale_quality,
        body_coverage_ratio=frame.body_coverage_ratio,
        quality=frame.quality,
        tracking_state=frame.tracking_state,
        relative_depth_available=frame.relative_depth_available,
        frame_width=frame.frame_width,
        frame_height=frame.frame_height,
    )


def summarize_pose_graph(frames: Iterable[PoseGraphFrame]) -> dict[str, object]:
    values = list(frames)
    if not values:
        return {
            "frame_count": 0,
            "mean_body_coverage_ratio": 0.0,
            "mean_valid_joint_ratio": 0.0,
            "invalid_bone_count": 0,
            "max_bone_length_outlier": None,
            "interpolation_count": 0,
            "limb_state_counts": {},
            "body_proportion_profile": {},
        }
    limb_counts: dict[str, dict[str, int]] = {
        name: defaultdict(int) for name in LIMB_CHAINS
    }
    invalid_bones = 0
    interpolated = 0
    length_errors: list[float] = []
    for frame in values:
        invalid_bones += sum(not bone.valid for bone in frame.bones.values())
        length_errors.extend(
            abs(bone.length_error)
            for bone in frame.bones.values()
            if bone.length_error is not None and math.isfinite(bone.length_error)
        )
        interpolated += sum(joint.source == MeasurementSource.INTERPOLATED for joint in frame.joints)
        for name, limb in frame.limbs.items():
            limb_counts[name][limb.state.value] += 1
    return {
        "frame_count": len(values),
        "mean_body_coverage_ratio": round(float(np.mean([item.body_coverage_ratio for item in values])), 6),
        "mean_valid_joint_ratio": round(float(np.mean([sum(j.valid for j in item.joints) / BODY_POINT_COUNT for item in values])), 6),
        "invalid_bone_count": invalid_bones,
        "max_bone_length_outlier": (
            round(max(length_errors), 6) if length_errors else None
        ),
        "interpolation_count": interpolated,
        "limb_state_counts": {name: dict(counts) for name, counts in limb_counts.items()},
    }


def serialize_joint(joint: JointState) -> dict[str, object]:
    return {
        "name": joint.name,
        "coordinates": _rounded_point(joint.coordinates),
        "raw_coordinates": _rounded_point(joint.raw_coordinates),
        "confidence": round(joint.confidence, 6),
        "quality": round(joint.quality, 6),
        "visibility": round(joint.visibility, 6),
        "valid": joint.valid,
        "temporal_state": joint.temporal_state.value,
        "occlusion_state": joint.occlusion_state.value,
        "source": joint.source.value,
        "rejection_reasons": list(joint.rejection_reasons),
        "velocity": [round(value, 6) for value in joint.velocity],
        "acceleration": [round(value, 6) for value in joint.acceleration],
        "predicted_position": _rounded_point(joint.predicted_position),
        "edge_distance": round(joint.edge_distance, 6) if joint.edge_distance is not None else None,
        "interpolation_age": joint.interpolation_age,
    }


def serialize_bone(bone: BoneState) -> dict[str, object]:
    return {
        "joint_a": bone.joint_a,
        "joint_b": bone.joint_b,
        "valid": bone.valid,
        "quality": round(bone.quality, 6),
        "normalized_length": _rounded(bone.normalized_length),
        "reference_length": _rounded(bone.reference_length),
        "length_error": _rounded(bone.length_error),
        "angular_velocity": _rounded(bone.angular_velocity),
        "occlusion_state": bone.occlusion_state.value,
        "render_state": bone.render_state,
        "rejection_reasons": list(bone.rejection_reasons),
    }


def serialize_limb(limb: LimbDiagnostic) -> dict[str, object]:
    return {
        "state": limb.state.value,
        "quality": round(limb.quality, 6),
        "valid_joint_count": limb.valid_joint_count,
        "expected_joint_count": limb.expected_joint_count,
        "occluded_joint_count": limb.occluded_joint_count,
        "out_of_frame_joint_count": limb.out_of_frame_joint_count,
        "prediction_age": limb.prediction_age,
        "reasons": list(limb.reasons),
    }


def _body_anchors(local: BodyValidationResult) -> BodyAnchors:
    shoulder = _midpoint_if_valid(local, 5, 6)
    hip = _midpoint_if_valid(local, 11, 12)
    torso_center = (
        _point_tuple((np.asarray(shoulder) + np.asarray(hip)) / 2.0)
        if shoulder is not None and hip is not None
        else None
    )
    torso_axis = (
        _point_tuple(np.asarray(shoulder) - np.asarray(hip))
        if shoulder is not None and hip is not None
        else None
    )
    qualities = [local.joints[index].quality for index in (5, 6, 11, 12) if local.joints[index].valid]
    quality = float(np.min(qualities)) if len(qualities) == 4 else 0.0
    return BodyAnchors(shoulder, hip, torso_center, torso_axis, quality)


def _anchor_measurements(points: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    output: dict[str, float] = {}
    if _array_points_valid(points, scores, (5, 6)):
        output["shoulder_width"] = float(np.linalg.norm(points[5] - points[6]))
    if _array_points_valid(points, scores, (11, 12)):
        output["hip_width"] = float(np.linalg.norm(points[11] - points[12]))
    if _array_points_valid(points, scores, (5, 6, 11, 12)):
        shoulder = (points[5] + points[6]) / 2.0
        hip = (points[11] + points[12]) / 2.0
        output["torso_length"] = float(np.linalg.norm(shoulder - hip))
    return output


def _torso_bounds(points: np.ndarray, scores: np.ndarray, body_scale: float) -> tuple[float, float, float, float] | None:
    indices = (5, 6, 11, 12)
    if not _array_points_valid(points, scores, indices):
        return None
    selected = points[list(indices)]
    margin = max(2.0, body_scale * 0.05)
    return (
        float(np.min(selected[:, 0]) - margin),
        float(np.min(selected[:, 1]) - margin),
        float(np.max(selected[:, 0]) + margin),
        float(np.max(selected[:, 1]) + margin),
    )


def _infer_occlusion(
    predicted: np.ndarray | None,
    bbox: np.ndarray | None,
    torso_bounds: tuple[float, float, float, float] | None,
    width: int,
    height: int,
) -> OcclusionState:
    if predicted is None or not np.isfinite(predicted).all():
        return OcclusionState.UNKNOWN
    x, y = float(predicted[0]), float(predicted[1])
    if x < 0.0 or y < 0.0 or x >= width or y >= height:
        return OcclusionState.OUT_OF_FRAME
    if torso_bounds is not None and _inside_bounds(x, y, torso_bounds):
        return OcclusionState.OCCLUDED_BY_BODY
    if bbox is not None and _inside_bounds(x, y, tuple(float(value) for value in bbox)):
        return OcclusionState.OCCLUDED
    return OcclusionState.UNKNOWN


def _joint_arrays(joints: list[JointState], original_count: int) -> tuple[np.ndarray, np.ndarray]:
    count = max(BODY_POINT_COUNT, original_count)
    points = np.zeros((count, 2), dtype=np.float32)
    scores = np.zeros((count,), dtype=np.float32)
    for index, joint in enumerate(joints):
        if joint.valid and joint.coordinates is not None:
            points[index] = joint.coordinates
            scores[index] = joint.quality
    return points, scores


def _replace_joint(
    joint: JointState,
    *,
    valid: bool | None = None,
    quality: float | None = None,
    coordinates: tuple[float, float] | None | object = ...,
    temporal_state: TemporalState | None = None,
    source: MeasurementSource | None = None,
    reasons: tuple[str, ...] | None = None,
    interpolation_age: int | None = None,
) -> JointState:
    return JointState(
        name=joint.name,
        coordinates=joint.coordinates if coordinates is ... else coordinates,  # type: ignore[arg-type]
        raw_coordinates=joint.raw_coordinates,
        confidence=joint.confidence,
        quality=joint.quality if quality is None else quality,
        visibility=joint.visibility if valid is None or valid else 0.0,
        valid=joint.valid if valid is None else valid,
        temporal_state=joint.temporal_state if temporal_state is None else temporal_state,
        occlusion_state=joint.occlusion_state,
        source=joint.source if source is None else source,
        rejection_reasons=tuple(dict.fromkeys(reasons or joint.rejection_reasons)),
        velocity=joint.velocity,
        acceleration=joint.acceleration,
        predicted_position=joint.predicted_position,
        edge_distance=joint.edge_distance,
        interpolation_age=joint.interpolation_age if interpolation_age is None else interpolation_age,
    )


def _predict(memory: _JointMemory, delta: float, damping: float) -> np.ndarray | None:
    if memory.position is None:
        return None
    prediction = memory.position + memory.velocity * delta * damping + 0.5 * memory.acceleration * delta * delta * damping
    return prediction.astype(np.float32) if np.isfinite(prediction).all() else None


def _angular_velocity(previous: np.ndarray | None, current: np.ndarray, delta: float) -> float | None:
    if previous is None:
        return None
    denominator = float(np.linalg.norm(previous) * np.linalg.norm(current))
    if denominator <= 1e-8:
        return None
    cosine = float(np.clip(np.dot(previous, current) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine)) / max(delta, 1e-6)


def _stronger_occlusion(first: OcclusionState, second: OcclusionState) -> OcclusionState:
    order = {
        OcclusionState.VISIBLE: 0,
        OcclusionState.UNKNOWN: 1,
        OcclusionState.OCCLUDED: 2,
        OcclusionState.OCCLUDED_BY_BODY: 3,
        OcclusionState.OUT_OF_FRAME: 4,
    }
    return first if order[first] >= order[second] else second


def _midpoint_if_valid(local: BodyValidationResult, first: int, second: int) -> tuple[float, float] | None:
    if not local.joints[first].valid or not local.joints[second].valid:
        return None
    return _point_tuple((local.points[first] + local.points[second]) / 2.0)


def _array_points_valid(points: np.ndarray, scores: np.ndarray, indices: tuple[int, ...]) -> bool:
    return all(
        index < points.shape[0]
        and index < scores.shape[0]
        and float(scores[index]) > 0.0
        and np.isfinite(points[index]).all()
        for index in indices
    )


def _bbox_height(bbox: np.ndarray | None, frame_height: int) -> float:
    if bbox is None or np.asarray(bbox).size != 4 or not np.isfinite(bbox).all():
        return max(1.0, float(frame_height))
    return max(1.0, float(bbox[3] - bbox[1]))


def _finite_point(points: np.ndarray, index: int) -> np.ndarray | None:
    if index >= points.shape[0] or points.shape[1:] != (2,) or not np.isfinite(points[index]).all():
        return None
    return np.asarray(points[index], dtype=np.float32)


def _finite_score(scores: np.ndarray, index: int) -> float:
    if index >= scores.shape[0] or not math.isfinite(float(scores[index])):
        return 0.0
    return float(np.clip(scores[index], 0.0, 1.0))


def _point_tuple(point: np.ndarray | tuple[float, float] | None) -> tuple[float, float] | None:
    if point is None:
        return None
    values = np.asarray(point, dtype=float).reshape(-1)
    if values.size != 2 or not np.isfinite(values).all():
        return None
    return float(values[0]), float(values[1])


def _rounded_point(point: tuple[float, float] | None) -> list[float] | None:
    return [round(value, 3) for value in point] if point is not None else None


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None


def _edge_distance(point: np.ndarray | None, width: int, height: int) -> float | None:
    if point is None or not np.isfinite(point).all():
        return None
    x, y = float(point[0]), float(point[1])
    return min(x, y, width - 1 - x, height - 1 - y)


def _inside_bounds(x: float, y: float, bounds: tuple[float, float, float, float]) -> bool:
    return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]


def _relative_depth_available(relative_depth: np.ndarray | None) -> bool:
    if relative_depth is None:
        return False
    values = np.asarray(relative_depth, dtype=float)
    return values.size >= BODY_POINT_COUNT and np.isfinite(values[:BODY_POINT_COUNT]).any()

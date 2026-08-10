"""FPS-aware evidence fusion and kinematic graph consensus for body joints."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math

import numpy as np

from .config import EvidenceFusionConfig


class JointConsensus(StrEnum):
    ACCEPTED = "ACCEPTED"
    WEAK = "WEAK"
    REJECTED = "REJECTED"
    OCCLUDED = "OCCLUDED"
    PREDICTED = "PREDICTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class JointTopology:
    name: str
    parent: str | None
    children: tuple[str, ...]
    chain: str
    side: str
    body_region: str


@dataclass(frozen=True)
class JointEvidence:
    model: float
    temporal: float
    kinematic: float
    tracking: float
    visibility: float
    image_quality: float
    final_quality: float
    consensus: JointConsensus
    velocity_scale_per_second: float | None
    acceleration_scale_per_second2: float | None
    jerk_scale_per_second3: float | None
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "model": round(self.model, 6), "temporal": round(self.temporal, 6),
            "kinematic": round(self.kinematic, 6), "tracking": round(self.tracking, 6),
            "visibility": round(self.visibility, 6), "image_quality": round(self.image_quality, 6),
            "final_quality": round(self.final_quality, 6), "consensus": self.consensus.value,
            "velocity_scale_per_second": _rounded(self.velocity_scale_per_second),
            "acceleration_scale_per_second2": _rounded(self.acceleration_scale_per_second2),
            "jerk_scale_per_second3": _rounded(self.jerk_scale_per_second3),
            "rejection_reasons": list(self.rejection_reasons),
            "quality_is_probability": False,
        }


@dataclass
class _MotionMemory:
    position: np.ndarray | None = None
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    timestamp: float | None = None
    last_quality: float = 0.0


class JointEvidenceFusion:
    """Rejects outliers without allowing them to update temporal anchors."""

    def __init__(self, config: EvidenceFusionConfig | None = None) -> None:
        self.config = config or EvidenceFusionConfig()
        self._memory: dict[str, _MotionMemory] = {}

    def reset(self) -> None:
        self._memory.clear()

    def evaluate(
        self,
        name: str,
        point: tuple[float, float] | None,
        *,
        timestamp_seconds: float,
        body_scale: float,
        model_quality: float,
        kinematic_quality: float,
        tracking_quality: float,
        visibility_quality: float,
        image_quality: float,
        global_translation: tuple[float, float] = (0.0, 0.0),
        occluded: bool = False,
        out_of_frame: bool = False,
    ) -> JointEvidence:
        memory = self._memory.setdefault(name, _MotionMemory())
        reasons: list[str] = []
        scale = max(float(body_scale), 1e-6)
        components = [model_quality, kinematic_quality, tracking_quality, visibility_quality, image_quality]
        components = [float(np.clip(value, 0.0, 1.0)) for value in components]
        model, kinematic, tracking, visibility, image = components
        candidate = _point(point)
        dt = timestamp_seconds - memory.timestamp if memory.timestamp is not None else None
        temporal = 1.0 if memory.position is None else 0.0
        velocity_value = acceleration_value = jerk_value = None
        motion_valid = True
        if candidate is not None and memory.position is not None and dt is not None and dt > 1e-6:
            compensated = candidate - np.asarray(global_translation, dtype=np.float64)
            velocity = (compensated - memory.position) / dt
            acceleration = (velocity - memory.velocity) / dt
            jerk = (acceleration - memory.acceleration) / dt
            velocity_value = float(np.linalg.norm(velocity) / scale)
            acceleration_value = float(np.linalg.norm(acceleration) / scale)
            jerk_value = float(np.linalg.norm(jerk) / scale)
            if velocity_value > self.config.maximum_velocity_scale_per_second:
                reasons.append("VELOCITY_OUTLIER")
            if acceleration_value > self.config.maximum_acceleration_scale_per_second2:
                reasons.append("ACCELERATION_OUTLIER")
            if jerk_value > self.config.maximum_jerk_scale_per_second3:
                reasons.append("JERK_OUTLIER")
            motion_valid = not reasons
            ratios = (
                velocity_value / self.config.maximum_velocity_scale_per_second,
                acceleration_value / self.config.maximum_acceleration_scale_per_second2,
                jerk_value / self.config.maximum_jerk_scale_per_second3,
            )
            temporal = float(np.clip(1.0 - max(ratios), 0.0, 1.0))
        if out_of_frame:
            reasons.append("OUT_OF_FRAME")
        if candidate is None:
            reasons.append("MISSING_COORDINATE")
        if model < self.config.minimum_model_quality:
            reasons.append("MODEL_QUALITY_LOW")
        # Conservative fusion: a strong model score cannot hide a failed chain or temporal signal.
        final = min(model, kinematic, tracking, visibility, image, max(temporal, 0.05))
        valid = candidate is not None and motion_valid and not out_of_frame and model >= self.config.minimum_model_quality
        if valid and final >= self.config.accepted_score:
            consensus = JointConsensus.ACCEPTED
        elif valid and final >= self.config.weak_score:
            consensus = JointConsensus.WEAK
        elif occluded:
            consensus = JointConsensus.OCCLUDED
        elif candidate is None and memory.position is not None and dt is not None and 0.0 < dt <= self.config.maximum_prediction_seconds:
            consensus = JointConsensus.PREDICTED
        elif candidate is None:
            consensus = JointConsensus.UNKNOWN
        else:
            consensus = JointConsensus.REJECTED
        if consensus in {JointConsensus.ACCEPTED, JointConsensus.WEAK} and candidate is not None:
            if memory.position is not None and dt is not None and dt > 1e-6:
                compensated = candidate - np.asarray(global_translation, dtype=np.float64)
                velocity = (compensated - memory.position) / dt
                acceleration = (velocity - memory.velocity) / dt
                memory.velocity = velocity
                memory.acceleration = acceleration
                memory.position = compensated
            else:
                memory.position = candidate.copy()
            memory.timestamp = timestamp_seconds
            memory.last_quality = final
        return JointEvidence(model, temporal, kinematic, tracking, visibility, image, final if valid else 0.0, consensus, velocity_value, acceleration_value, jerk_value, tuple(dict.fromkeys(reasons)))


JOINT_GRAPH: dict[str, JointTopology] = {
    "left_shoulder": JointTopology("left_shoulder", "neck", ("left_elbow",), "left_arm", "left", "left_upper_limb"),
    "left_elbow": JointTopology("left_elbow", "left_shoulder", ("left_wrist",), "left_arm", "left", "left_upper_limb"),
    "left_wrist": JointTopology("left_wrist", "left_elbow", ("left_hand_root",), "left_arm", "left", "left_hand"),
    "right_shoulder": JointTopology("right_shoulder", "neck", ("right_elbow",), "right_arm", "right", "right_upper_limb"),
    "right_elbow": JointTopology("right_elbow", "right_shoulder", ("right_wrist",), "right_arm", "right", "right_upper_limb"),
    "right_wrist": JointTopology("right_wrist", "right_elbow", ("right_hand_root",), "right_arm", "right", "right_hand"),
    "left_hip": JointTopology("left_hip", "pelvis", ("left_knee",), "left_leg", "left", "legs"),
    "left_knee": JointTopology("left_knee", "left_hip", ("left_ankle",), "left_leg", "left", "legs"),
    "right_hip": JointTopology("right_hip", "pelvis", ("right_knee",), "right_leg", "right", "legs"),
    "right_knee": JointTopology("right_knee", "right_hip", ("right_ankle",), "right_leg", "right", "legs"),
}


def _point(value: tuple[float, float] | None) -> np.ndarray | None:
    if value is None:
        return None
    result = np.asarray(value, dtype=np.float64)
    return result if result.shape == (2,) and np.isfinite(result).all() and not np.allclose(result, 0.0) else None


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None

"""Small dependency-free data contracts used by the metrics engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np


RejectionReason = Literal[
    "missing_keypoint",
    "low_keypoint_quality",
    "invalid_coordinate",
    "zero_length_vector",
    "person_not_detected",
    "hand_not_valid",
    "unsupported_input_schema",
    "geometry_validation_failed",
]

METRIC_NAMES: tuple[str, ...] = (
    "trunk_inclination_deg",
    "neck_flexion_deg",
    "left_upper_arm_elevation_deg",
    "right_upper_arm_elevation_deg",
    "left_elbow_flexion_deg",
    "right_elbow_flexion_deg",
    "left_forearm_inclination_deg",
    "right_forearm_inclination_deg",
    "left_wrist_flexion_deg",
    "right_wrist_flexion_deg",
    "left_hand_closure_ratio",
    "right_hand_closure_ratio",
    "left_pinch_distance_ratio",
    "right_pinch_distance_ratio",
)


@dataclass(frozen=True)
class PointSample:
    name: str
    coordinates: np.ndarray | None
    quality: float
    rejection_reason: RejectionReason | None = None

    @property
    def valid(self) -> bool:
        return self.coordinates is not None and self.rejection_reason is None


@dataclass(frozen=True)
class ValidatedHand:
    side: Literal["left", "right"]
    valid: bool
    quality: float
    landmarks: dict[int, PointSample]
    rejection_reason: RejectionReason | None


@dataclass(frozen=True)
class FramePose:
    person_detected: bool
    body: dict[str, PointSample]
    left_hand: ValidatedHand
    right_hand: ValidatedHand


@dataclass(frozen=True)
class MetricResult:
    value: float | None
    valid: bool
    quality: float
    source_points: tuple[str, ...]
    rejection_reason: RejectionReason | None

    @classmethod
    def accepted(
        cls,
        value: float,
        quality: float,
        source_points: tuple[str, ...],
    ) -> "MetricResult":
        safe_quality = min(1.0, max(0.0, float(quality)))
        if not math.isfinite(value):
            return cls.rejected(source_points, "geometry_validation_failed")
        return cls(
            value=round(float(value), 6),
            valid=True,
            quality=round(safe_quality, 6),
            source_points=source_points,
            rejection_reason=None,
        )

    @classmethod
    def rejected(
        cls,
        source_points: tuple[str, ...],
        reason: RejectionReason,
    ) -> "MetricResult":
        return cls(
            value=None,
            valid=False,
            quality=0.0,
            source_points=source_points,
            rejection_reason=reason,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "valid": self.valid,
            "quality": self.quality,
            "source_points": list(self.source_points),
            "rejection_reason": self.rejection_reason,
        }

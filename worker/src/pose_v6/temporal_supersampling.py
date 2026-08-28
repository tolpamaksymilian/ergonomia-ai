"""Support-only temporal super-resolution for high-motion Pose V6.6 spans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

import numpy as np


class TemporalSampleProvenance(StrEnum):
    MEASURED_NATIVE_FRAME = "MEASURED_NATIVE_FRAME"
    TEMPORAL_SUPERSAMPLE_SUPPORT = "TEMPORAL_SUPERSAMPLE_SUPPORT"


@dataclass(frozen=True)
class TemporalSupportSample:
    timestamp_seconds: float
    points: np.ndarray
    scores: np.ndarray
    left_native_index: int
    right_native_index: int
    interpolation_ratio: float
    provenance: TemporalSampleProvenance = TemporalSampleProvenance.TEMPORAL_SUPERSAMPLE_SUPPORT
    measurement_eligible: bool = False


@dataclass(frozen=True)
class TemporalSupersamplingResult:
    factor: int
    support_samples: tuple[TemporalSupportSample, ...]
    native_frame_count: int
    native_measurement_count: int

    @property
    def support_sample_count(self) -> int:
        return len(self.support_samples)

    @property
    def measurement_coverage_denominator(self) -> int:
        """Synthetic support never changes analytical coverage."""

        return self.native_frame_count

    def to_dict(self) -> dict[str, object]:
        return {
            "factor": self.factor,
            "backend": "pose-trajectory-hermite-with-native-image-validation",
            "support_sample_count": self.support_sample_count,
            "native_frame_count": self.native_frame_count,
            "native_measurement_count": self.native_measurement_count,
            "measurement_coverage_denominator": self.measurement_coverage_denominator,
            "support_is_measurement": False,
            "provenance": TemporalSampleProvenance.TEMPORAL_SUPERSAMPLE_SUPPORT.value,
        }

    def motion_vector_at_native(
        self,
        native_index: int,
        joint_indexes: Sequence[int],
    ) -> np.ndarray | None:
        """Estimate local direction from support on both sides of a native frame."""

        before = [
            item for item in self.support_samples
            if item.right_native_index == native_index
        ]
        after = [
            item for item in self.support_samples
            if item.left_native_index == native_index
        ]
        if not before or not after:
            return None
        left = max(before, key=lambda item: item.timestamp_seconds)
        right = min(after, key=lambda item: item.timestamp_seconds)
        indexes = [
            index for index in joint_indexes
            if index < len(left.scores)
            and index < len(right.scores)
            and left.scores[index] > 0.0
            and right.scores[index] > 0.0
        ]
        if not indexes:
            return None
        vectors = right.points[indexes] - left.points[indexes]
        finite = np.isfinite(vectors).all(axis=1)
        if not np.any(finite):
            return None
        return np.median(vectors[finite], axis=0).astype(np.float32)


class HighMotionTemporalSupersampling:
    """Create 2-5x trajectory support without duplicating native frames."""

    def __init__(self, factor: int) -> None:
        if factor not in {1, 2, 3, 4, 5}:
            raise ValueError("temporal supersampling factor must be in range 1..5")
        self.factor = factor

    def generate(
        self,
        points: Sequence[np.ndarray],
        scores: Sequence[np.ndarray],
        timestamps: Sequence[float],
        *,
        eligible_intervals: set[int] | None = None,
    ) -> TemporalSupersamplingResult:
        count = len(points)
        if not (count == len(scores) == len(timestamps)):
            raise ValueError("temporal supersampling inputs must have equal lengths")
        if count == 0:
            return TemporalSupersamplingResult(self.factor, (), 0, 0)
        point_array = np.stack(points).astype(np.float32)
        score_array = np.stack(scores).astype(np.float32)
        if point_array.ndim != 3 or point_array.shape[2] != 2:
            raise ValueError("temporal points must have shape (frame, joint, 2)")
        if score_array.shape != point_array.shape[:2]:
            raise ValueError("temporal scores must have shape (frame, joint)")
        time_array = np.asarray(timestamps, dtype=np.float64)
        if not np.isfinite(time_array).all() or np.any(np.diff(time_array) <= 0.0):
            raise ValueError("native timestamps must be finite and strictly increasing")
        native_measurements = int(np.count_nonzero(score_array > 0.0))
        support: list[TemporalSupportSample] = []
        if self.factor == 1:
            return TemporalSupersamplingResult(
                self.factor, (), count, native_measurements,
            )
        intervals = eligible_intervals if eligible_intervals is not None else set(range(count - 1))
        for left in range(count - 1):
            if left not in intervals:
                continue
            right = left + 1
            duration = float(time_array[right] - time_array[left])
            for step in range(1, self.factor):
                ratio = step / self.factor
                values = _hermite_frame(
                    point_array,
                    score_array,
                    time_array,
                    left,
                    right,
                    ratio,
                )
                valid = (score_array[left] > 0.0) & (score_array[right] > 0.0)
                sample_scores = np.zeros_like(score_array[left])
                sample_scores[valid] = (
                    np.minimum(score_array[left, valid], score_array[right, valid]) * 0.65
                )
                support.append(TemporalSupportSample(
                    timestamp_seconds=float(time_array[left] + duration * ratio),
                    points=values,
                    scores=sample_scores,
                    left_native_index=left,
                    right_native_index=right,
                    interpolation_ratio=ratio,
                ))
        return TemporalSupersamplingResult(
            self.factor,
            tuple(support),
            count,
            native_measurements,
        )


def bidirectional_native_prediction(
    points: Sequence[np.ndarray],
    scores: Sequence[np.ndarray],
    timestamps: Sequence[float],
    frame_index: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Predict one native pose from sharp neighbours; still support-only."""

    if frame_index <= 0 or frame_index + 1 >= len(points):
        return None
    before = np.asarray(points[frame_index - 1], dtype=np.float32)
    after = np.asarray(points[frame_index + 1], dtype=np.float32)
    before_scores = np.asarray(scores[frame_index - 1], dtype=np.float32)
    after_scores = np.asarray(scores[frame_index + 1], dtype=np.float32)
    before_time = float(timestamps[frame_index - 1])
    current_time = float(timestamps[frame_index])
    after_time = float(timestamps[frame_index + 1])
    duration = after_time - before_time
    if not np.isfinite((before_time, current_time, after_time)).all() or duration <= 1e-9:
        return None
    ratio = float(np.clip((current_time - before_time) / duration, 0.0, 1.0))
    valid = (before_scores > 0.0) & (after_scores > 0.0)
    predicted = before + (after - before) * ratio
    predicted_scores = np.zeros_like(before_scores)
    predicted_scores[valid] = np.minimum(before_scores[valid], after_scores[valid]) * 0.60
    return predicted, predicted_scores


def _hermite_frame(
    points: np.ndarray,
    scores: np.ndarray,
    timestamps: np.ndarray,
    left: int,
    right: int,
    ratio: float,
) -> np.ndarray:
    first = points[left]
    second = points[right]
    duration = float(timestamps[right] - timestamps[left])
    before = max(0, left - 1)
    after = min(len(points) - 1, right + 1)
    first_dt = float(timestamps[right] - timestamps[before])
    second_dt = float(timestamps[after] - timestamps[left])
    first_velocity = (
        (points[right] - points[before]) / first_dt
        if first_dt > 1e-9 else np.zeros_like(first)
    )
    second_velocity = (
        (points[after] - points[left]) / second_dt
        if second_dt > 1e-9 else np.zeros_like(second)
    )
    t = float(np.clip(ratio, 0.0, 1.0))
    t2 = t * t
    t3 = t2 * t
    value = (
        (2 * t3 - 3 * t2 + 1) * first
        + (t3 - 2 * t2 + t) * first_velocity * duration
        + (-2 * t3 + 3 * t2) * second
        + (t3 - t2) * second_velocity * duration
    )
    valid = (scores[left] > 0.0) & (scores[right] > 0.0)
    linear = first + (second - first) * t
    # Bound cubic overshoot without suppressing genuine endpoint displacement.
    extent = np.linalg.norm(second - first, axis=1, keepdims=True) * 0.18 + 1.0
    lower = np.minimum(first, second) - extent
    upper = np.maximum(first, second) + extent
    value = np.clip(value, lower, upper)
    value[~valid] = linear[~valid]
    return value.astype(np.float32)


__all__ = [
    "HighMotionTemporalSupersampling",
    "TemporalSampleProvenance",
    "TemporalSupersamplingResult",
    "TemporalSupportSample",
    "bidirectional_native_prediction",
]

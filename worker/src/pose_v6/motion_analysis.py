"""Scale- and FPS-aware dynamic motion classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from .config import MotionConfig


class MotionState(StrEnum):
    NORMAL_MOTION = "NORMAL_MOTION"
    FAST_MOTION = "FAST_MOTION"
    EXTREME_MOTION = "EXTREME_MOTION"


@dataclass(frozen=True)
class MotionObservation:
    state: MotionState
    median_joint_speed_scale_per_second: float
    endpoint_speed_scale_per_second: float
    bbox_speed_scale_per_second: float
    gate_multiplier: float

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "median_joint_speed_scale_per_second": round(self.median_joint_speed_scale_per_second, 6),
            "endpoint_speed_scale_per_second": round(self.endpoint_speed_scale_per_second, 6),
            "bbox_speed_scale_per_second": round(self.bbox_speed_scale_per_second, 6),
            "gate_multiplier": round(self.gate_multiplier, 6),
        }


class MotionAnalyzer:
    def __init__(self, config: MotionConfig) -> None:
        config.validate()
        self.config = config
        self._points: np.ndarray | None = None
        self._scores: np.ndarray | None = None
        self._bbox: np.ndarray | None = None
        self._timestamp: float | None = None

    def reset(self) -> None:
        self._points = None
        self._scores = None
        self._bbox = None
        self._timestamp = None

    def update(
        self,
        points: np.ndarray,
        scores: np.ndarray,
        bbox: np.ndarray | None,
        timestamp_seconds: float,
        *,
        camera_translation: tuple[float, float] = (0.0, 0.0),
    ) -> MotionObservation:
        body_scale = _bbox_height(bbox)
        median_speed = endpoint_speed = bbox_speed = 0.0
        if self._timestamp is not None and timestamp_seconds > self._timestamp:
            delta = timestamp_seconds - self._timestamp
            if self._points is not None and self._scores is not None:
                count = min(23, len(points), len(scores), len(self._points), len(self._scores))
                # Very weak RTMW outputs are too noisy to describe physical
                # motion and can otherwise turn detector noise into an
                # ``EXTREME_MOTION`` episode.  This threshold only controls
                # dynamic gate selection; it never promotes a point to an
                # analytical measurement.
                valid = (np.asarray(scores[:count]) >= 0.25) & (np.asarray(self._scores[:count]) >= 0.25)
                if np.any(valid):
                    displacement = np.asarray(points[:count], dtype=np.float32) - self._points[:count]
                    displacement -= np.asarray(camera_translation, dtype=np.float32)
                    speeds = np.linalg.norm(displacement[valid], axis=1) / max(body_scale * delta, 1e-6)
                    median_speed = float(np.median(speeds))
                    endpoint_indexes = np.asarray([7, 8, 9, 10, 13, 14, 15, 16])
                    endpoint_indexes = endpoint_indexes[endpoint_indexes < count]
                    endpoint_valid = valid[endpoint_indexes]
                    if np.any(endpoint_valid):
                        endpoint_speed = float(np.max(np.linalg.norm(displacement[endpoint_indexes][endpoint_valid], axis=1) / max(body_scale * delta, 1e-6)))
            if bbox is not None and self._bbox is not None:
                current_center = (np.asarray(bbox)[:2] + np.asarray(bbox)[2:]) * 0.5
                previous_center = (self._bbox[:2] + self._bbox[2:]) * 0.5
                bbox_speed = float(np.linalg.norm(current_center - previous_center - np.asarray(camera_translation)) / max(body_scale * delta, 1e-6))
        signal = max(median_speed, endpoint_speed * 0.75, bbox_speed)
        if signal >= self.config.extreme_threshold_scale_per_second:
            state, multiplier = MotionState.EXTREME_MOTION, self.config.extreme_gate_multiplier
        elif signal >= self.config.fast_threshold_scale_per_second:
            state, multiplier = MotionState.FAST_MOTION, self.config.fast_gate_multiplier
        else:
            state, multiplier = MotionState.NORMAL_MOTION, 1.0
        self._points = np.asarray(points, dtype=np.float32).copy()
        self._scores = np.asarray(scores, dtype=np.float32).copy()
        self._bbox = np.asarray(bbox, dtype=np.float32).copy() if bbox is not None else self._bbox
        self._timestamp = timestamp_seconds
        return MotionObservation(state, median_speed, endpoint_speed, bbox_speed, multiplier)


def _bbox_height(bbox: np.ndarray | None) -> float:
    if bbox is None:
        return 1.0
    values = np.asarray(bbox, dtype=float).reshape(-1)
    return max(1.0, float(values[3] - values[1])) if values.size == 4 and np.isfinite(values).all() else 1.0

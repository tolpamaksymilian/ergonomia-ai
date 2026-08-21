"""FPS-aware person-box prediction and safe track-conditioned recovery."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np


class BBoxSource(StrEnum):
    YOLOX_MEASURED = "YOLOX_MEASURED"
    TRACK_PREDICTED = "TRACK_PREDICTED"
    TEMPORAL_REFINED = "TEMPORAL_REFINED"
    RECOVERY_SEARCH = "RECOVERY_SEARCH"
    MISSING = "MISSING"


@dataclass(frozen=True)
class PredictedBoundingBox:
    bbox_xyxy: np.ndarray
    source: BBoxSource
    prediction_age_seconds: float
    uncertainty: float
    velocity_xy: tuple[float, float]
    scale_velocity: tuple[float, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "bbox_xyxy": [round(float(value), 3) for value in self.bbox_xyxy],
            "source": self.source.value,
            "prediction_age_seconds": round(self.prediction_age_seconds, 6),
            "uncertainty": round(self.uncertainty, 6),
            "velocity_xy": [round(value, 3) for value in self.velocity_xy],
            "scale_velocity": [round(value, 3) for value in self.scale_velocity],
        }


@dataclass
class _BoxState:
    center: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    size: np.ndarray = field(default_factory=lambda: np.ones(2, dtype=np.float32))
    center_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    size_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    timestamp: float = 0.0
    measured_timestamp: float = 0.0
    samples: int = 0


class BBoxMotionEstimator:
    """Constant-velocity alpha-beta estimator with bounded uncertainty."""

    def __init__(self, *, alpha: float = 0.72, beta: float = 0.24) -> None:
        if not 0.0 < alpha <= 1.0 or not 0.0 <= beta <= 1.0:
            raise ValueError("invalid alpha-beta filter coefficients")
        self.alpha = alpha
        self.beta = beta
        self._state: _BoxState | None = None

    @property
    def has_track(self) -> bool:
        return self._state is not None and self._state.samples >= 1

    def reset(self) -> None:
        self._state = None

    def observe(
        self,
        bbox: np.ndarray,
        timestamp_seconds: float,
        *,
        camera_translation: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        values = _valid_bbox(bbox)
        if not math.isfinite(timestamp_seconds):
            raise ValueError("timestamp must be finite")
        center = (values[:2] + values[2:]) * 0.5
        size = values[2:] - values[:2]
        if self._state is None:
            self._state = _BoxState(center.copy(), size.copy(), timestamp=timestamp_seconds, measured_timestamp=timestamp_seconds, samples=1)
            return
        state = self._state
        delta = max(1e-4, timestamp_seconds - state.timestamp)
        camera = np.asarray(camera_translation, dtype=np.float32)
        predicted_center = state.center + (state.center_velocity + camera / delta) * delta
        predicted_size = np.maximum(2.0, state.size + state.size_velocity * delta)
        center_residual = center - predicted_center
        size_residual = size - predicted_size
        state.center = predicted_center + self.alpha * center_residual
        state.size = np.maximum(2.0, predicted_size + self.alpha * size_residual)
        state.center_velocity = state.center_velocity + self.beta * center_residual / delta
        state.size_velocity = state.size_velocity + self.beta * size_residual / delta
        state.timestamp = timestamp_seconds
        state.measured_timestamp = timestamp_seconds
        state.samples += 1

    def predict(
        self,
        timestamp_seconds: float,
        *,
        frame_width: int,
        frame_height: int,
        roi_scale: float = 1.0,
        camera_translation: tuple[float, float] = (0.0, 0.0),
    ) -> PredictedBoundingBox | None:
        if self._state is None or frame_width <= 1 or frame_height <= 1:
            return None
        state = self._state
        delta = max(0.0, timestamp_seconds - state.timestamp)
        age = max(0.0, timestamp_seconds - state.measured_timestamp)
        center = state.center + state.center_velocity * delta + np.asarray(camera_translation, dtype=np.float32)
        size = np.maximum(2.0, state.size + state.size_velocity * delta) * max(1.0, roi_scale)
        bbox = np.concatenate((center - size * 0.5, center + size * 0.5)).astype(np.float32)
        bbox[[0, 2]] = np.clip(bbox[[0, 2]], 0.0, frame_width - 1.0)
        bbox[[1, 3]] = np.clip(bbox[[1, 3]], 0.0, frame_height - 1.0)
        if bbox[2] - bbox[0] < 4.0 or bbox[3] - bbox[1] < 4.0:
            return None
        speed = float(np.linalg.norm(state.center_velocity)) / max(1.0, float(np.linalg.norm(state.size)))
        uncertainty = float(np.clip(age * (0.65 + speed), 0.0, 1.0))
        return PredictedBoundingBox(
            bbox_xyxy=bbox,
            source=BBoxSource.TRACK_PREDICTED,
            prediction_age_seconds=age,
            uncertainty=uncertainty,
            velocity_xy=(float(state.center_velocity[0]), float(state.center_velocity[1])),
            scale_velocity=(float(state.size_velocity[0]), float(state.size_velocity[1])),
        )


def recovery_allowed(
    prediction: PredictedBoundingBox | None,
    *,
    tracking_state: str,
    scene_cut: bool,
    maximum_age_seconds: float,
    maximum_uncertainty: float = 0.80,
) -> bool:
    if prediction is None or scene_cut or tracking_state.upper() in {"LOST", "REACQUIRING"}:
        return False
    return (
        prediction.prediction_age_seconds <= maximum_age_seconds
        and prediction.uncertainty <= maximum_uncertainty
    )


def _valid_bbox(bbox: np.ndarray) -> np.ndarray:
    values = np.asarray(bbox, dtype=np.float32).reshape(-1)
    if values.size != 4 or not np.isfinite(values).all() or values[2] <= values[0] or values[3] <= values[1]:
        raise ValueError("bbox must be finite xyxy with positive size")
    return values

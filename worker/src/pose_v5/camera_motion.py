"""Lightweight sparse-flow global camera motion diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from .config import CameraMotionConfig


@dataclass(frozen=True)
class CameraMotion:
    translation_x: float
    translation_y: float
    magnitude_pixels: float
    track_count: int
    quality: float
    camera_shake: bool
    scene_cut: bool
    available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "translation": [round(self.translation_x, 4), round(self.translation_y, 4)],
            "magnitude_pixels": round(self.magnitude_pixels, 4),
            "track_count": self.track_count, "quality": round(self.quality, 6),
            "camera_shake": self.camera_shake, "scene_cut": self.scene_cut,
            "available": self.available,
        }


class CameraMotionEstimator:
    def __init__(self, config: CameraMotionConfig | None = None) -> None:
        self.config = config or CameraMotionConfig()
        self._previous_gray: np.ndarray | None = None
        self._previous_translation = np.zeros(2, dtype=np.float64)

    def reset(self) -> None:
        self._previous_gray = None
        self._previous_translation[:] = 0.0

    def update(self, frame: np.ndarray, excluded_bbox: tuple[int, int, int, int] | None = None) -> CameraMotion:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame.astype(np.uint8)
        if self._previous_gray is None or self._previous_gray.shape != gray.shape:
            self._previous_gray = gray.copy()
            return CameraMotion(0.0, 0.0, 0.0, 0, 0.0, False, False, False)
        histogram_distance = _histogram_distance(self._previous_gray, gray)
        scene_cut = histogram_distance >= self.config.scene_cut_histogram_distance
        if scene_cut:
            self._previous_gray = gray.copy(); self._previous_translation[:] = 0.0
            return CameraMotion(0.0, 0.0, 0.0, 0, 0.0, False, True, True)
        mask = np.full(gray.shape, 255, dtype=np.uint8)
        if excluded_bbox is not None:
            x1, y1, x2, y2 = excluded_bbox
            cv2.rectangle(mask, (max(0, x1), max(0, y1)), (min(gray.shape[1] - 1, x2), min(gray.shape[0] - 1, y2)), 0, -1)
        previous_points = cv2.goodFeaturesToTrack(self._previous_gray, maxCorners=self.config.maximum_corners, qualityLevel=0.02, minDistance=8, mask=mask)
        if previous_points is None:
            self._previous_gray = gray.copy()
            return CameraMotion(0.0, 0.0, 0.0, 0, 0.0, False, False, False)
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(self._previous_gray, gray, previous_points, None)
        valid = status.reshape(-1).astype(bool) if status is not None else np.zeros(len(previous_points), dtype=bool)
        if next_points is None or int(np.count_nonzero(valid)) < self.config.minimum_tracks:
            self._previous_gray = gray.copy()
            return CameraMotion(0.0, 0.0, 0.0, int(np.count_nonzero(valid)), 0.0, False, False, False)
        deltas = next_points.reshape(-1, 2)[valid] - previous_points.reshape(-1, 2)[valid]
        translation = np.median(deltas, axis=0)
        residuals = np.linalg.norm(deltas - translation, axis=1)
        residual_median = float(np.median(residuals))
        quality = float(np.clip(1.0 - residual_median / 8.0, 0.0, 1.0))
        acceleration = float(np.linalg.norm(translation - self._previous_translation))
        shake = acceleration > self.config.shake_acceleration_ratio * max(float(np.linalg.norm(translation)), 1.0)
        self._previous_translation = translation.astype(np.float64)
        self._previous_gray = gray.copy()
        return CameraMotion(float(translation[0]), float(translation[1]), float(np.linalg.norm(translation)), len(deltas), quality, shake, False, True)


def robust_translation(previous: np.ndarray, current: np.ndarray) -> tuple[float, float] | None:
    """Testable point-track primitive independent of OpenCV feature detection."""
    first = np.asarray(previous, dtype=float); second = np.asarray(current, dtype=float)
    if first.shape != second.shape or first.ndim != 2 or first.shape[1] != 2 or first.shape[0] < 3:
        return None
    valid = np.isfinite(first).all(axis=1) & np.isfinite(second).all(axis=1)
    if int(np.count_nonzero(valid)) < 3:
        return None
    value = np.median(second[valid] - first[valid], axis=0)
    return float(value[0]), float(value[1])


def _histogram_distance(first: np.ndarray, second: np.ndarray) -> float:
    first_hist = cv2.calcHist([first], [0], None, [32], [0, 256]); second_hist = cv2.calcHist([second], [0], None, [32], [0, 256])
    cv2.normalize(first_hist, first_hist); cv2.normalize(second_hist, second_hist)
    value = cv2.compareHist(first_hist, second_hist, cv2.HISTCMP_BHATTACHARYYA)
    return float(value) if math.isfinite(value) else 1.0

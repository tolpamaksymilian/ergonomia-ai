"""Explicit coordinate-space boundaries for Pose V6.6 candidates.

RTMLib returns top-down pose observations in source-image pixels even when it
receives an explicit crop.  The helpers in this module make that boundary
testable and prevent a crop offset or scale from being applied twice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np


class CoordinateSpace(StrEnum):
    ORIGINAL_PIXELS = "ORIGINAL_PIXELS"
    PERSON_CROP_PIXELS = "PERSON_CROP_PIXELS"
    MODEL_INPUT = "MODEL_INPUT"
    NORMALIZED_CROP = "NORMALIZED_CROP"


class CoordinateSpaceError(ValueError):
    """A candidate crossed an unsupported or repeated coordinate boundary."""


@dataclass(frozen=True)
class CropTransform:
    """Invertible original/crop/model transform for one bounded ROI."""

    bbox_xyxy: tuple[float, float, float, float]
    model_input_size: tuple[int, int]

    def __post_init__(self) -> None:
        values = np.asarray(self.bbox_xyxy, dtype=np.float64)
        if values.shape != (4,) or not np.isfinite(values).all():
            raise CoordinateSpaceError("crop bbox must contain four finite values")
        if values[2] <= values[0] or values[3] <= values[1]:
            raise CoordinateSpaceError("crop bbox must have positive width and height")
        width, height = self.model_input_size
        if width <= 0 or height <= 0:
            raise CoordinateSpaceError("model input size must be positive")

    @property
    def crop_size(self) -> np.ndarray:
        x1, y1, x2, y2 = self.bbox_xyxy
        return np.asarray((x2 - x1, y2 - y1), dtype=np.float64)

    def original_to_crop(self, points: np.ndarray) -> np.ndarray:
        values = _points(points)
        return values - np.asarray(self.bbox_xyxy[:2], dtype=np.float64)

    def crop_to_original(self, points: np.ndarray) -> np.ndarray:
        values = _points(points)
        return values + np.asarray(self.bbox_xyxy[:2], dtype=np.float64)

    def crop_to_model(self, points: np.ndarray) -> np.ndarray:
        values = _points(points)
        return values * np.asarray(self.model_input_size, dtype=np.float64) / self.crop_size

    def model_to_crop(self, points: np.ndarray) -> np.ndarray:
        values = _points(points)
        return values * self.crop_size / np.asarray(self.model_input_size, dtype=np.float64)

    def original_to_normalized(self, points: np.ndarray) -> np.ndarray:
        return self.original_to_crop(points) / self.crop_size

    def normalized_to_original(self, points: np.ndarray) -> np.ndarray:
        return self.crop_to_original(_points(points) * self.crop_size)

    def round_trip_error(self, points: np.ndarray) -> float:
        original = _points(points)
        restored = self.crop_to_original(
            self.model_to_crop(self.crop_to_model(self.original_to_crop(original)))
        )
        return float(np.max(np.linalg.norm(restored - original, axis=-1)))


@dataclass(frozen=True)
class CoordinatePoseCandidate:
    """Pose candidate carrying its space and conversion provenance."""

    points: np.ndarray
    scores: np.ndarray
    space: CoordinateSpace
    source: str
    conversion_count: int = 0
    transform: CropTransform | None = None

    def validate(self, *, frame_width: int, frame_height: int) -> None:
        points = np.asarray(self.points)
        scores = np.asarray(self.scores)
        if points.ndim != 2 or points.shape[1] != 2:
            raise CoordinateSpaceError("candidate points must have shape (joint, 2)")
        if scores.shape != (points.shape[0],):
            raise CoordinateSpaceError("candidate scores must have shape (joint,)")
        if not np.isfinite(scores).all():
            raise CoordinateSpaceError("candidate scores must be finite")
        visible = scores > 0.0
        if np.any(visible) and not np.isfinite(points[visible]).all():
            raise CoordinateSpaceError("visible candidate coordinates must be finite")
        if self.conversion_count not in {0, 1}:
            raise CoordinateSpaceError("candidate violated the one-conversion rule")
        if self.space == CoordinateSpace.ORIGINAL_PIXELS and np.any(visible):
            visible_points = points[visible]
            if np.any(visible_points[:, 0] < 0.0) or np.any(visible_points[:, 0] >= frame_width):
                raise CoordinateSpaceError("original-pixel x coordinate is outside the frame")
            if np.any(visible_points[:, 1] < 0.0) or np.any(visible_points[:, 1] >= frame_height):
                raise CoordinateSpaceError("original-pixel y coordinate is outside the frame")

    def to_original_pixels(self) -> "CoordinatePoseCandidate":
        if self.space == CoordinateSpace.ORIGINAL_PIXELS:
            if self.conversion_count > 1:
                raise CoordinateSpaceError("candidate was converted to original pixels twice")
            return self
        if self.conversion_count != 0:
            raise CoordinateSpaceError("candidate was converted more than once")
        if self.transform is None:
            raise CoordinateSpaceError("crop/model candidate requires a CropTransform")
        if self.space == CoordinateSpace.PERSON_CROP_PIXELS:
            converted = self.transform.crop_to_original(self.points)
        elif self.space == CoordinateSpace.MODEL_INPUT:
            converted = self.transform.crop_to_original(
                self.transform.model_to_crop(self.points)
            )
        elif self.space == CoordinateSpace.NORMALIZED_CROP:
            converted = self.transform.normalized_to_original(self.points)
        else:  # pragma: no cover - exhaustive StrEnum guard
            raise CoordinateSpaceError(f"unsupported coordinate space: {self.space}")
        return replace(
            self,
            points=converted.astype(np.float32),
            space=CoordinateSpace.ORIGINAL_PIXELS,
            conversion_count=1,
        )


def original_pixel_candidate(
    points: np.ndarray,
    scores: np.ndarray,
    *,
    source: str,
    frame_width: int,
    frame_height: int,
) -> CoordinatePoseCandidate:
    """Wrap RTMLib output, whose public contract is source-image pixels."""

    candidate = CoordinatePoseCandidate(
        np.asarray(points, dtype=np.float32),
        np.asarray(scores, dtype=np.float32),
        CoordinateSpace.ORIGINAL_PIXELS,
        source,
        conversion_count=1,
    )
    candidate.validate(frame_width=frame_width, frame_height=frame_height)
    return candidate


def _points(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != 2 or not np.isfinite(array).all():
        raise CoordinateSpaceError("coordinates must have shape (n, 2) and be finite")
    return array


__all__ = [
    "CoordinatePoseCandidate",
    "CoordinateSpace",
    "CoordinateSpaceError",
    "CropTransform",
    "original_pixel_candidate",
]

"""Lightweight object association using cached YOLOX detections."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

try:
    from ..pose_v3.hand_object.holding import ObjectDetection
except ImportError:  # pragma: no cover - standalone worker import mode
    from pose_v3.hand_object.holding import ObjectDetection


@dataclass(frozen=True)
class TrackedObject:
    track_id: int
    class_id: int
    class_name: str | None
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float | None
    center: tuple[float, float]
    velocity: tuple[float, float]
    age_frames: int
    missing_frames: int


@dataclass
class _TrackMemory:
    track_id: int
    detection: ObjectDetection
    center: np.ndarray
    velocity: np.ndarray
    age_frames: int
    missing_frames: int


class ObjectTrackManager:
    """Small IoU/center/class tracker; it does not run another detector."""

    def __init__(
        self,
        *,
        maximum_missing_frames: int = 2,
        maximum_center_distance_ratio: float = 0.18,
        minimum_iou: float = 0.02,
    ) -> None:
        if maximum_missing_frames < 0:
            raise ValueError("maximum_missing_frames cannot be negative")
        if not 0.0 < maximum_center_distance_ratio <= 1.0:
            raise ValueError("maximum_center_distance_ratio must be in range (0, 1]")
        if not 0.0 <= minimum_iou <= 1.0:
            raise ValueError("minimum_iou must be in range 0..1")
        self.maximum_missing_frames = maximum_missing_frames
        self.maximum_center_distance_ratio = maximum_center_distance_ratio
        self.minimum_iou = minimum_iou
        self._tracks: dict[int, _TrackMemory] = {}
        self._next_track_id = 1
        self._last_timestamp: float | None = None

    def update(
        self,
        detections: list[ObjectDetection],
        *,
        frame_width: int,
        frame_height: int,
        timestamp_seconds: float,
    ) -> list[TrackedObject]:
        delta = (
            timestamp_seconds - self._last_timestamp
            if self._last_timestamp is not None
            else 0.0
        )
        if not math.isfinite(delta) or delta <= 1e-6:
            delta = 1.0 / 30.0
        self._last_timestamp = timestamp_seconds
        diagonal = max(1.0, math.hypot(frame_width, frame_height))
        candidates: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            predicted = track.center + track.velocity * delta
            for index, detection in enumerate(detections):
                if detection.class_id != track.detection.class_id:
                    continue
                center = _center(detection.bbox_xyxy)
                distance = float(np.linalg.norm(center - predicted)) / diagonal
                overlap = bbox_iou(track.detection.bbox_xyxy, detection.bbox_xyxy)
                if distance > self.maximum_center_distance_ratio and overlap < self.minimum_iou:
                    continue
                cost = 0.62 * distance / self.maximum_center_distance_ratio + 0.38 * (1.0 - overlap)
                candidates.append((cost, track_id, index))

        assigned_tracks: set[int] = set()
        assigned_detections: set[int] = set()
        for _, track_id, detection_index in sorted(candidates):
            if track_id in assigned_tracks or detection_index in assigned_detections:
                continue
            detection = detections[detection_index]
            track = self._tracks[track_id]
            center = _center(detection.bbox_xyxy)
            track.velocity = (center - track.center) / delta
            track.center = center
            track.detection = detection
            track.age_frames += 1
            track.missing_frames = 0
            assigned_tracks.add(track_id)
            assigned_detections.add(detection_index)

        for track_id, track in list(self._tracks.items()):
            if track_id not in assigned_tracks:
                track.missing_frames += 1
                if track.missing_frames > self.maximum_missing_frames:
                    del self._tracks[track_id]

        for index, detection in enumerate(detections):
            if index in assigned_detections or not _valid_detection(detection):
                continue
            center = _center(detection.bbox_xyxy)
            track_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[track_id] = _TrackMemory(
                track_id,
                detection,
                center,
                np.zeros((2,), dtype=np.float32),
                1,
                0,
            )
            assigned_tracks.add(track_id)

        return [
            _serialize_track(track)
            for track_id, track in sorted(self._tracks.items())
            if track_id in assigned_tracks and track.missing_frames == 0
        ]


def track_object_sequence(
    frames: list[list[ObjectDetection]],
    timestamps: list[float],
    *,
    frame_width: int,
    frame_height: int,
) -> list[list[TrackedObject]]:
    if len(frames) != len(timestamps):
        raise ValueError("object frames and timestamps must have equal length")
    manager = ObjectTrackManager()
    return [
        manager.update(
            detections,
            frame_width=frame_width,
            frame_height=frame_height,
            timestamp_seconds=timestamp,
        )
        for detections, timestamp in zip(frames, timestamps)
    ]


def bbox_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 1e-8 else 0.0


def _serialize_track(track: _TrackMemory) -> TrackedObject:
    return TrackedObject(
        track_id=track.track_id,
        class_id=track.detection.class_id,
        class_name=track.detection.class_name,
        bbox_xyxy=track.detection.bbox_xyxy,
        confidence=track.detection.confidence,
        center=(float(track.center[0]), float(track.center[1])),
        velocity=(float(track.velocity[0]), float(track.velocity[1])),
        age_frames=track.age_frames,
        missing_frames=track.missing_frames,
    )


def _center(bbox: tuple[float, float, float, float]) -> np.ndarray:
    return np.asarray(((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0), dtype=np.float32)


def _valid_detection(detection: ObjectDetection) -> bool:
    values = np.asarray(detection.bbox_xyxy, dtype=float)
    return bool(
        values.size == 4
        and np.isfinite(values).all()
        and values[2] > values[0]
        and values[3] > values[1]
    )

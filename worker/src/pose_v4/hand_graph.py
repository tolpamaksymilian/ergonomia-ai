"""Hand graph V0.4: assignment hysteresis, palm frame and finger chains."""

from __future__ import annotations

import itertools
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

try:
    from ..pose_v3.hand_pipeline import (
        HAND_POINT_COUNT,
        HandObservation,
        HandPipelineConfig,
        RawHandFrame,
        ValidatedHandFrame,
        _Candidate,
    )
except ImportError:  # pragma: no cover - standalone worker import mode
    from pose_v3.hand_pipeline import (
        HAND_POINT_COUNT,
        HandObservation,
        HandPipelineConfig,
        RawHandFrame,
        ValidatedHandFrame,
        _Candidate,
    )

from .graph import PoseGraphFrame
from .object_tracking import TrackedObject


PALM_INDICES = (0, 5, 9, 13, 17)
FINGER_CHAINS: dict[str, tuple[int, ...]] = {
    "thumb": (1, 2, 3, 4),
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}


class FingerVisibility(StrEnum):
    VISIBLE = "VISIBLE"
    PARTIAL = "PARTIAL"
    OCCLUDED = "OCCLUDED"
    LOST = "LOST"


class HandOcclusion(StrEnum):
    VISIBLE = "VISIBLE"
    PARTIAL = "PARTIAL"
    OCCLUDED_BY_OBJECT = "HAND_OCCLUDED_BY_OBJECT"
    OCCLUDED_BY_BODY = "HAND_OCCLUDED_BY_BODY"
    OUT_OF_FRAME = "HAND_OUT_OF_FRAME"
    LOST = "HAND_LOST"
    REACQUIRING = "HAND_REACQUIRING"


class GripStateV2(StrEnum):
    OPEN = "OPEN"
    RELAXED = "RELAXED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    POWER_GRIP_CANDIDATE = "POWER_GRIP_CANDIDATE"
    PRECISION_PINCH_CANDIDATE = "PRECISION_PINCH_CANDIDATE"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HandGraphConfig:
    minimum_palm_points: int = 4
    minimum_palm_quality: float = 0.48
    assignment_switch_margin: float = 0.18
    assignment_maximum_cost: float = 1.35
    roi_minimum_size: float = 72.0
    roi_forearm_scale: float = 1.05
    roi_velocity_expansion: float = 0.18
    profile_maximum_samples: int = 90

    def validate(self) -> None:
        if not 3 <= self.minimum_palm_points <= 5:
            raise ValueError("minimum_palm_points must be in range 3..5")
        if not 0.0 <= self.minimum_palm_quality <= 1.0:
            raise ValueError("minimum_palm_quality must be in range 0..1")
        if self.assignment_switch_margin < 0.0:
            raise ValueError("assignment_switch_margin cannot be negative")
        if self.assignment_maximum_cost <= 0.0:
            raise ValueError("assignment_maximum_cost must be positive")
        if self.roi_minimum_size <= 0.0 or self.roi_forearm_scale <= 0.0:
            raise ValueError("ROI sizes must be positive")


@dataclass(frozen=True)
class PalmFrame:
    center: tuple[float, float] | None
    width: float | None
    height: float | None
    scale: float | None
    orientation_degrees: float | None
    normal_signal: tuple[float, float, float] | None
    base_directions: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class FingerDiagnostic:
    name: str
    state: FingerVisibility
    quality: float
    valid_points: int
    flexion_mcp: float | None
    flexion_pip: float | None
    flexion_dip: float | None
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class GripFeaturesV2:
    state: GripStateV2
    confidence: float
    closure_ratio: float | None
    aperture_ratio: float | None
    thumb_index_distance_ratio: float | None
    thumb_middle_distance_ratio: float | None
    thumb_opposition_proxy: float | None
    thumb_flexion: float | None
    finger_flexion: dict[str, float | None]
    palm_orientation_degrees: float | None
    wrist_orientation_degrees: float | None
    stability: float


@dataclass(frozen=True)
class HandGraphFrame:
    side: str
    visible: bool
    quality: float
    palm_quality: float
    occlusion_state: HandOcclusion
    palm: PalmFrame
    fingers: dict[str, FingerDiagnostic]
    grip: GripFeaturesV2
    nearest_object_track_id: int | None
    nearest_object_class: str | None
    nearest_object_confidence: float | None
    nearest_object_distance_ratio: float | None
    nearest_object_velocity: tuple[float, float] | None
    assignment_quality: float
    roi_xyxy: tuple[int, int, int, int] | None
    source_frame: ValidatedHandFrame

    def to_dict(self) -> dict[str, object]:
        return {
            "side": self.side,
            "visible": self.visible,
            "quality": round(self.quality, 6),
            "palm_quality": round(self.palm_quality, 6),
            "occlusion_state": self.occlusion_state.value,
            "assignment_quality": round(self.assignment_quality, 6),
            "roi_xyxy": list(self.roi_xyxy) if self.roi_xyxy is not None else None,
            "palm": serialize_palm(self.palm),
            "fingers": {name: serialize_finger(value) for name, value in self.fingers.items()},
            "grip_v2": serialize_grip(self.grip),
            "object_association": {
                "track_id": self.nearest_object_track_id,
                "class_name": self.nearest_object_class,
                "confidence": _rounded(self.nearest_object_confidence),
                "distance_ratio": _rounded(self.nearest_object_distance_ratio),
                "velocity": list(self.nearest_object_velocity) if self.nearest_object_velocity else None,
            },
        }


@dataclass
class HandAssignmentMemory:
    centers: dict[str, np.ndarray] = field(default_factory=dict)
    velocities: dict[str, np.ndarray] = field(default_factory=dict)
    orientations: dict[str, float] = field(default_factory=dict)
    scales: dict[str, float] = field(default_factory=dict)
    missed_frames: dict[str, int] = field(default_factory=lambda: {"left": 0, "right": 0})
    assignment_switches: int = 0
    _last_timestamp: float | None = None

    def predicted_center(self, side: str, timestamp: float) -> np.ndarray | None:
        center = self.centers.get(side)
        if center is None:
            return None
        delta = timestamp - self._last_timestamp if self._last_timestamp is not None else 0.0
        if not math.isfinite(delta) or delta < 0.0:
            delta = 0.0
        return center + self.velocities.get(side, np.zeros((2,), dtype=np.float32)) * delta

    def update(self, assignments: dict[str, RawHandFrame], timestamp: float) -> None:
        delta = timestamp - self._last_timestamp if self._last_timestamp is not None else 0.0
        if not math.isfinite(delta) or delta <= 1e-6:
            delta = 1.0 / 30.0
        current_centers: dict[str, np.ndarray] = {}
        for side in ("left", "right"):
            observation = assignments[side].observation
            if observation is not None:
                current_centers[side] = np.mean(
                    observation.points_px[list(PALM_INDICES)], axis=0
                ).astype(np.float32)
        if (
            set(current_centers) == {"left", "right"}
            and set(self.centers) >= {"left", "right"}
        ):
            keep_cost = float(
                np.linalg.norm(current_centers["left"] - self.centers["left"])
                + np.linalg.norm(current_centers["right"] - self.centers["right"])
            )
            swap_cost = float(
                np.linalg.norm(current_centers["left"] - self.centers["right"])
                + np.linalg.norm(current_centers["right"] - self.centers["left"])
            )
            scale = max(1.0, float(np.mean(list(self.scales.values()))))
            if swap_cost + 0.18 * scale < keep_cost:
                self.assignment_switches += 1
        for side in ("left", "right"):
            observation = assignments[side].observation
            if observation is None:
                self.missed_frames[side] = self.missed_frames.get(side, 0) + 1
                continue
            center = current_centers[side]
            previous = self.centers.get(side)
            if previous is not None:
                self.velocities[side] = (center - previous) / delta
            self.centers[side] = center
            self.orientations[side] = observation.orientation_degrees
            self.scales[side] = observation.palm_scale
            self.missed_frames[side] = 0
        self._last_timestamp = timestamp


class PalmScaleProfile:
    def __init__(self, maximum_samples: int = 90) -> None:
        self._samples: dict[str, dict[str, deque[float]]] = {
            side: defaultdict(lambda: deque(maxlen=maximum_samples))
            for side in ("left", "right")
        }

    def add(self, side: str, palm: PalmFrame, quality: float) -> bool:
        if quality < 0.72 or palm.scale is None or palm.width is None or palm.height is None:
            return False
        values = {
            "palm_width": palm.width,
            "palm_height": palm.height,
            "palm_scale": palm.scale,
        }
        accepted = True
        for name, value in values.items():
            samples = self._samples[side][name]
            if len(samples) >= 4:
                array = np.asarray(samples, dtype=float)
                median = float(np.median(array))
                mad = float(np.median(np.abs(array - median)))
                if abs(value - median) > max(3.5 * mad, median * 0.12):
                    accepted = False
                    continue
            samples.append(float(value))
        return accepted

    def quality(self, side: str, palm: PalmFrame) -> float:
        if palm.scale is None:
            return 0.0
        samples = self._samples[side]["palm_scale"]
        if len(samples) < 3:
            return 0.80
        array = np.asarray(samples, dtype=float)
        median = float(np.median(array))
        mad = float(np.median(np.abs(array - median)))
        tolerance = max(4.0 * mad, median * 0.20)
        return float(np.clip(1.0 - abs(palm.scale - median) / max(tolerance, 1e-6), 0.0, 1.0))


def assign_hands_to_body_v2(
    candidates: list[_Candidate],
    body_points: np.ndarray,
    body_scores: np.ndarray,
    body_threshold: float,
    config: HandPipelineConfig,
    graph_config: HandGraphConfig,
    timestamp_seconds: float,
    memory: HandAssignmentMemory,
) -> dict[str, RawHandFrame]:
    graph_config.validate()
    anchors = {
        side: _body_anchor(side, body_points, body_scores, body_threshold)
        for side in ("left", "right")
    }
    costs: dict[tuple[str, int], tuple[float, HandObservation]] = {}
    for side in ("left", "right"):
        anchor = anchors[side]
        if anchor is None:
            continue
        wrist, elbow, forearm = anchor
        predicted = memory.predicted_center(side, timestamp_seconds)
        other = memory.predicted_center("right" if side == "left" else "left", timestamp_seconds)
        for index, candidate in enumerate(candidates):
            palm_center = np.mean(candidate.points_px[list(PALM_INDICES)], axis=0)
            palm_scale = _palm_scale(candidate.points_px)
            if palm_scale < config.min_palm_size_pixels or forearm < config.min_forearm_pixels:
                continue
            root_ratio = float(np.linalg.norm(candidate.points_px[0] - wrist) / max(forearm, 1.0))
            if root_ratio > config.assignment_max_wrist_distance_ratio:
                continue
            predicted_cost = (
                float(np.linalg.norm(palm_center - predicted) / max(forearm, 1.0))
                if predicted is not None
                else root_ratio
            )
            orientation = _orientation(candidate.points_px)
            orientation_cost = (
                _angle_difference(orientation, memory.orientations[side]) / 180.0
                if side in memory.orientations
                else 0.25
            )
            scale_cost = (
                abs(math.log(max(palm_scale, 1e-6) / max(memory.scales[side], 1e-6)))
                if side in memory.scales
                else 0.0
            )
            label = candidate.handedness_label.lower()
            handedness_cost = (
                config.handedness_soft_penalty * candidate.handedness_score
                if label in {"left", "right"} and label != side
                else 0.0
            )
            switch_penalty = 0.0
            if predicted is not None and other is not None:
                own_distance = float(np.linalg.norm(palm_center - predicted))
                other_distance = float(np.linalg.norm(palm_center - other))
                if other_distance + graph_config.assignment_switch_margin * forearm < own_distance:
                    switch_penalty = graph_config.assignment_switch_margin
            cost = (
                0.32 * root_ratio
                + 0.30 * predicted_cost
                + 0.12 * orientation_cost
                + 0.10 * scale_cost
                + handedness_cost
                + switch_penalty
            )
            observation = HandObservation(
                points_px=candidate.points_px.copy(),
                world_points=candidate.world_points.copy(),
                handedness_label=candidate.handedness_label,
                handedness_score=candidate.handedness_score,
                body_wrist=wrist.copy(),
                forearm_length=forearm,
                root_wrist_distance_ratio=root_ratio,
                palm_scale=palm_scale,
                orientation_degrees=orientation,
                assignment_score=cost,
            )
            costs[(side, index)] = (cost, observation)

    missing_cost = graph_config.assignment_maximum_cost
    choices = [-1, *range(len(candidates))]
    best: tuple[float, tuple[int, int]] | None = None
    for left_index, right_index in itertools.product(choices, choices):
        if left_index >= 0 and left_index == right_index:
            continue
        total = 0.0
        feasible = True
        for side, index in (("left", left_index), ("right", right_index)):
            if index < 0:
                total += missing_cost
            elif (side, index) not in costs:
                feasible = False
                break
            else:
                total += costs[(side, index)][0]
        if feasible and (best is None or total < best[0]):
            best = total, (left_index, right_index)

    result: dict[str, RawHandFrame] = {
        "left": RawHandFrame(None, timestamp_seconds, bool(candidates)),
        "right": RawHandFrame(None, timestamp_seconds, bool(candidates)),
    }
    if best is not None:
        for side, index in zip(("left", "right"), best[1]):
            if index >= 0 and costs[(side, index)][0] <= graph_config.assignment_maximum_cost:
                result[side] = RawHandFrame(costs[(side, index)][1], timestamp_seconds, True)
    for side in ("left", "right"):
        if result[side].observation is None:
            reason = (
                "no_hand_detection"
                if not candidates
                else "body_wrist_or_elbow_missing"
                if anchors[side] is None
                else "global_assignment_gate"
            )
            result[side].assignment_reasons.append(reason)
    memory.update(result, timestamp_seconds)
    return result


def predict_hand_rois(
    body_points: np.ndarray,
    body_scores: np.ndarray,
    *,
    body_threshold: float,
    frame_width: int,
    frame_height: int,
    timestamp_seconds: float,
    memory: HandAssignmentMemory,
    config: HandGraphConfig,
) -> dict[str, tuple[int, int, int, int]]:
    output: dict[str, tuple[int, int, int, int]] = {}
    for side in ("left", "right"):
        anchor = _body_anchor(side, body_points, body_scores, body_threshold)
        predicted = memory.predicted_center(side, timestamp_seconds)
        if anchor is None and predicted is None:
            continue
        if anchor is not None:
            wrist, elbow, forearm = anchor
            direction = wrist - elbow
            norm = float(np.linalg.norm(direction))
            direction = direction / norm if norm > 1e-6 else np.zeros((2,), dtype=np.float32)
            anchor_center = wrist + direction * forearm * 0.28
        else:
            forearm = max(config.roi_minimum_size, memory.scales.get(side, 24.0) * 3.0)
            anchor_center = predicted.copy()  # type: ignore[union-attr]
        center = (
            0.58 * anchor_center + 0.42 * predicted
            if predicted is not None
            else anchor_center
        )
        speed = float(np.linalg.norm(memory.velocities.get(side, np.zeros((2,), dtype=np.float32))))
        palm_scale = memory.scales.get(side, forearm * 0.30)
        half_size = max(
            config.roi_minimum_size / 2.0,
            forearm * config.roi_forearm_scale,
            palm_scale * 2.8,
        ) + speed * config.roi_velocity_expansion
        output[side] = _clip_roi(center, half_size, frame_width, frame_height)
    return output


def union_hand_roi(
    rois: dict[str, tuple[int, int, int, int] | None],
    *,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int] | None:
    """Return a clipped union of all valid hand ROIs.

    A frame can have an ROI for only one hand.  Hand Rescue therefore may
    legitimately pass ``None`` for the other side.  Treat missing or
    degenerate ROIs as unavailable instead of letting them crash the whole
    Pose pipeline.
    """
    if frame_width <= 0 or frame_height <= 0:
        return None

    values: list[tuple[int, int, int, int]] = []
    for value in rois.values():
        if value is None or len(value) != 4:
            continue

        x1, y1, x2, y2 = (int(coordinate) for coordinate in value)
        x1 = max(0, min(frame_width, x1))
        y1 = max(0, min(frame_height, y1))
        x2 = max(0, min(frame_width, x2))
        y2 = max(0, min(frame_height, y2))

        if x2 <= x1 or y2 <= y1:
            continue

        values.append((x1, y1, x2, y2))

    if not values:
        return None

    return (
        min(value[0] for value in values),
        min(value[1] for value in values),
        max(value[2] for value in values),
        max(value[3] for value in values),
    )


def analyze_hand_graph_sequence(
    side: str,
    frames: list[ValidatedHandFrame],
    body_frames: list[PoseGraphFrame],
    object_frames: list[list[TrackedObject]],
    rois: list[tuple[int, int, int, int] | None],
    *,
    config: HandGraphConfig,
) -> list[HandGraphFrame]:
    if not (len(frames) == len(body_frames) == len(object_frames) == len(rois)):
        raise ValueError("hand, body, object and ROI sequences must have equal length")
    config.validate()
    profile = PalmScaleProfile(config.profile_maximum_samples)
    output: list[HandGraphFrame] = []
    previous: HandGraphFrame | None = None
    for frame, body, objects, roi in zip(frames, body_frames, object_frames, rois):
        graph = analyze_hand_graph_frame(
            side,
            frame,
            body,
            objects,
            roi,
            profile,
            previous,
            config,
        )
        output.append(graph)
        if graph.visible:
            previous = graph
    return output


def analyze_hand_graph_frame(
    side: str,
    frame: ValidatedHandFrame,
    body: PoseGraphFrame,
    objects: list[TrackedObject],
    roi: tuple[int, int, int, int] | None,
    profile: PalmScaleProfile,
    previous: HandGraphFrame | None,
    config: HandGraphConfig,
) -> HandGraphFrame:
    palm = compute_palm_frame(frame)
    valid_palm_points = (
        sum(bool(frame.point_validity[index]) for index in PALM_INDICES)
        if frame.point_validity.size == HAND_POINT_COUNT
        else 0
    )
    geometry_quality = profile.quality(side, palm)
    palm_quality = (
        min(frame.quality, valid_palm_points / len(PALM_INDICES), geometry_quality)
        if frame.visible and palm.scale is not None
        else 0.0
    )
    nearest = _nearest_object(palm, objects)
    hand_occlusion = _hand_occlusion(frame, body, palm, nearest, valid_palm_points)
    visible = (
        frame.visible
        and valid_palm_points >= config.minimum_palm_points
        and palm_quality >= config.minimum_palm_quality
        and hand_occlusion not in {HandOcclusion.OUT_OF_FRAME, HandOcclusion.LOST}
    )
    fingers = {
        name: _finger_diagnostic(name, chain, frame, nearest, hand_occlusion)
        for name, chain in FINGER_CHAINS.items()
    }
    grip = compute_grip_features_v2(frame, palm, fingers, previous.grip if previous else None)
    if visible:
        profile.add(side, palm, palm_quality)
    assignment_quality = (
        float(np.clip(1.0 - min(frame.reject_reasons.count("assignment"), 1), 0.0, 1.0))
        if frame.visible
        else 0.0
    )
    return HandGraphFrame(
        side=side,
        visible=visible,
        quality=float(np.clip(min(frame.quality, palm_quality) if visible else 0.0, 0.0, 1.0)),
        palm_quality=float(np.clip(palm_quality, 0.0, 1.0)),
        occlusion_state=hand_occlusion,
        palm=palm,
        fingers=fingers,
        grip=grip,
        nearest_object_track_id=nearest[0].track_id if nearest else None,
        nearest_object_class=nearest[0].class_name if nearest else None,
        nearest_object_confidence=nearest[0].confidence if nearest else None,
        nearest_object_distance_ratio=nearest[1] if nearest else None,
        nearest_object_velocity=nearest[0].velocity if nearest else None,
        assignment_quality=assignment_quality,
        roi_xyxy=roi,
        source_frame=frame,
    )


def compute_palm_frame(frame: ValidatedHandFrame) -> PalmFrame:
    if not frame.visible or frame.points_px.shape != (HAND_POINT_COUNT, 2):
        return PalmFrame(None, None, None, None, None, None, {})
    points = frame.points_px.astype(np.float32)
    if not np.isfinite(points).all():
        return PalmFrame(None, None, None, None, None, None, {})
    center = np.mean(points[list(PALM_INDICES)], axis=0)
    width = float(np.linalg.norm(points[5] - points[17]))
    height = float(np.linalg.norm(points[0] - points[9]))
    scale = float(np.median([width, height]))
    orientation = _orientation(points)
    normal = None
    if frame.world_points.shape == (HAND_POINT_COUNT, 3) and np.isfinite(frame.world_points).all():
        first = frame.world_points[5] - frame.world_points[0]
        second = frame.world_points[17] - frame.world_points[0]
        cross = np.cross(first, second)
        norm = float(np.linalg.norm(cross))
        if norm > 1e-8:
            cross /= norm
            normal = tuple(float(value) for value in cross)
    bases: dict[str, tuple[float, float]] = {}
    for name, chain in FINGER_CHAINS.items():
        vector = points[chain[0]] - center
        norm = float(np.linalg.norm(vector))
        if norm > 1e-8:
            bases[name] = (float(vector[0] / norm), float(vector[1] / norm))
    return PalmFrame(
        center=(float(center[0]), float(center[1])),
        width=width if width > 1e-6 else None,
        height=height if height > 1e-6 else None,
        scale=scale if scale > 1e-6 else None,
        orientation_degrees=orientation,
        normal_signal=normal,
        base_directions=bases,
    )


def compute_grip_features_v2(
    frame: ValidatedHandFrame,
    palm: PalmFrame,
    fingers: dict[str, FingerDiagnostic],
    previous: GripFeaturesV2 | None,
) -> GripFeaturesV2:
    if not frame.visible or palm.center is None or palm.scale is None or palm.scale <= 1e-6:
        return _unknown_grip()
    points = frame.points_px
    valid = frame.point_validity if frame.point_validity.size == HAND_POINT_COUNT else np.zeros((HAND_POINT_COUNT,), dtype=bool)
    required = (4, 8, 12)
    thumb_index = _distance_ratio(points, valid, 4, 8, palm.scale)
    thumb_middle = _distance_ratio(points, valid, 4, 12, palm.scale)
    aperture_values = [value for value in (thumb_index, thumb_middle) if value is not None]
    aperture = float(np.mean(aperture_values)) if aperture_values else None
    center = np.asarray(palm.center, dtype=np.float32)
    tip_distances = [
        float(np.linalg.norm(points[index] - center) / palm.scale)
        for index in (8, 12, 16, 20)
        if bool(valid[index])
    ]
    closure = float(np.clip(1.0 - np.mean(tip_distances) / 1.65, 0.0, 1.0)) if len(tip_distances) >= 3 else None
    finger_flexion = {
        name: _mean_flexion(diagnostic)
        for name, diagnostic in fingers.items()
        if name != "thumb"
    }
    thumb_flexion = _mean_flexion(fingers["thumb"])
    opposition = (
        float(np.clip(1.0 - thumb_index / 0.65, 0.0, 1.0))
        if thumb_index is not None
        else None
    )
    stability = 1.0
    if previous is not None and previous.closure_ratio is not None and closure is not None:
        stability = float(np.clip(1.0 - abs(closure - previous.closure_ratio) * 1.8, 0.0, 1.0))
    quality = float(np.clip(frame.quality, 0.0, 1.0))
    if quality < 0.45 or closure is None:
        state = GripStateV2.UNKNOWN
    elif thumb_index is not None and thumb_index <= 0.16 and opposition is not None and opposition >= 0.65:
        state = GripStateV2.PRECISION_PINCH_CANDIDATE
    elif closure >= 0.74:
        state = GripStateV2.CLOSED
    elif closure >= 0.56 and aperture is not None and aperture < 0.55:
        state = GripStateV2.POWER_GRIP_CANDIDATE
    elif closure >= 0.34:
        state = GripStateV2.PARTIALLY_CLOSED
    elif closure >= 0.16:
        state = GripStateV2.RELAXED
    else:
        state = GripStateV2.OPEN
    separation = {
        GripStateV2.OPEN: 0.90,
        GripStateV2.RELAXED: 0.72,
        GripStateV2.PARTIALLY_CLOSED: 0.72,
        GripStateV2.POWER_GRIP_CANDIDATE: 0.80,
        GripStateV2.PRECISION_PINCH_CANDIDATE: 0.84,
        GripStateV2.CLOSED: 0.88,
        GripStateV2.UNKNOWN: 0.0,
    }[state]
    confidence = float(np.clip(0.62 * quality + 0.23 * stability + 0.15 * separation, 0.0, 1.0))
    wrist_orientation = None
    if bool(valid[0]) and palm.center is not None:
        vector = center - points[0]
        wrist_orientation = math.degrees(math.atan2(float(vector[1]), float(vector[0])))
    return GripFeaturesV2(
        state=state,
        confidence=confidence,
        closure_ratio=closure,
        aperture_ratio=aperture,
        thumb_index_distance_ratio=thumb_index,
        thumb_middle_distance_ratio=thumb_middle,
        thumb_opposition_proxy=opposition,
        thumb_flexion=thumb_flexion,
        finger_flexion=finger_flexion,
        palm_orientation_degrees=palm.orientation_degrees,
        wrist_orientation_degrees=wrist_orientation,
        stability=stability,
    )


def serialize_palm(palm: PalmFrame) -> dict[str, object]:
    return {
        "center": list(palm.center) if palm.center else None,
        "width": _rounded(palm.width),
        "height": _rounded(palm.height),
        "scale": _rounded(palm.scale),
        "orientation_degrees": _rounded(palm.orientation_degrees),
        "relative_normal_signal": list(palm.normal_signal) if palm.normal_signal else None,
        "base_directions": {name: list(value) for name, value in palm.base_directions.items()},
    }


def serialize_finger(finger: FingerDiagnostic) -> dict[str, object]:
    return {
        "state": finger.state.value,
        "quality": round(finger.quality, 6),
        "valid_points": finger.valid_points,
        "mcp_flexion": _rounded(finger.flexion_mcp),
        "pip_flexion": _rounded(finger.flexion_pip),
        "dip_flexion": _rounded(finger.flexion_dip),
        "rejection_reasons": list(finger.rejection_reasons),
    }


def serialize_grip(grip: GripFeaturesV2) -> dict[str, object]:
    return {
        "state": grip.state.value,
        "confidence": round(grip.confidence, 6),
        "closure_ratio": _rounded(grip.closure_ratio),
        "aperture_ratio": _rounded(grip.aperture_ratio),
        "thumb_index_distance_ratio": _rounded(grip.thumb_index_distance_ratio),
        "thumb_middle_distance_ratio": _rounded(grip.thumb_middle_distance_ratio),
        "thumb_opposition_proxy": _rounded(grip.thumb_opposition_proxy),
        "thumb_flexion": _rounded(grip.thumb_flexion),
        "finger_flexion": {name: _rounded(value) for name, value in grip.finger_flexion.items()},
        "palm_orientation_degrees": _rounded(grip.palm_orientation_degrees),
        "wrist_orientation_degrees": _rounded(grip.wrist_orientation_degrees),
        "stability": round(grip.stability, 6),
    }


def _finger_diagnostic(
    name: str,
    chain: tuple[int, ...],
    frame: ValidatedHandFrame,
    nearest: tuple[TrackedObject, float] | None,
    hand_occlusion: HandOcclusion,
) -> FingerDiagnostic:
    valid = frame.point_validity if frame.point_validity.size == HAND_POINT_COUNT else np.zeros((HAND_POINT_COUNT,), dtype=bool)
    valid_count = sum(bool(valid[index]) for index in chain)
    reasons = [frame.point_reasons[index] for index in chain if index < len(frame.point_reasons) and frame.point_reasons[index]]
    if valid_count == len(chain):
        state = FingerVisibility.VISIBLE
    elif valid_count >= 2:
        state = FingerVisibility.OCCLUDED if nearest is not None or hand_occlusion in {HandOcclusion.OCCLUDED_BY_BODY, HandOcclusion.OCCLUDED_BY_OBJECT} else FingerVisibility.PARTIAL
    elif nearest is not None or hand_occlusion in {HandOcclusion.OCCLUDED_BY_BODY, HandOcclusion.OCCLUDED_BY_OBJECT}:
        state = FingerVisibility.OCCLUDED
    else:
        state = FingerVisibility.LOST
    quality = frame.quality * valid_count / len(chain)
    points = frame.points_px
    angles = (
        _safe_flexion(points[0], points[chain[0]], points[chain[1]]) if name == "thumb" else _safe_flexion(points[0], points[chain[0]], points[chain[1]]),
        _safe_flexion(points[chain[0]], points[chain[1]], points[chain[2]]),
        _safe_flexion(points[chain[1]], points[chain[2]], points[chain[3]]),
    ) if frame.visible and points.shape == (HAND_POINT_COUNT, 2) else (None, None, None)
    if state != FingerVisibility.VISIBLE:
        angles = tuple(
            value if all(bool(valid[index]) for index in required) else None
            for value, required in zip(
                angles,
                ((chain[0], chain[1]), (chain[0], chain[1], chain[2]), (chain[1], chain[2], chain[3])),
            )
        )
    return FingerDiagnostic(
        name,
        state,
        float(np.clip(quality, 0.0, 1.0)),
        valid_count,
        angles[0],
        angles[1],
        angles[2],
        tuple(dict.fromkeys(str(reason) for reason in reasons)),
    )


def _hand_occlusion(
    frame: ValidatedHandFrame,
    body: PoseGraphFrame,
    palm: PalmFrame,
    nearest: tuple[TrackedObject, float] | None,
    valid_palm_points: int,
) -> HandOcclusion:
    if frame.tracking_state == "HAND_REACQUIRING":
        return HandOcclusion.REACQUIRING
    if palm.center is not None:
        x, y = palm.center
        if x < 0.0 or y < 0.0 or x >= body.frame_width or y >= body.frame_height:
            return HandOcclusion.OUT_OF_FRAME
    if nearest is not None and valid_palm_points >= 3 and valid_palm_points < len(PALM_INDICES):
        return HandOcclusion.OCCLUDED_BY_OBJECT
    missing_tips = 0
    if frame.point_validity.size == HAND_POINT_COUNT:
        missing_tips = sum(not bool(frame.point_validity[index]) for index in (4, 8, 12, 16, 20))
    if nearest is not None and valid_palm_points >= 4 and missing_tips >= 2:
        return HandOcclusion.OCCLUDED_BY_OBJECT
    if palm.center is not None and body.anchors.torso_center is not None and body.body_scale > 0.0:
        distance = float(np.linalg.norm(np.asarray(palm.center) - np.asarray(body.anchors.torso_center)))
        if missing_tips >= 2 and distance / body.body_scale < 0.24:
            return HandOcclusion.OCCLUDED_BY_BODY
    if frame.visible and valid_palm_points < len(PALM_INDICES):
        return HandOcclusion.PARTIAL
    if frame.visible:
        return HandOcclusion.VISIBLE
    return HandOcclusion.LOST


def _nearest_object(palm: PalmFrame, objects: list[TrackedObject]) -> tuple[TrackedObject, float] | None:
    if palm.center is None or palm.scale is None:
        return None
    center = np.asarray(palm.center, dtype=float)
    best: tuple[TrackedObject, float] | None = None
    for item in objects:
        x1, y1, x2, y2 = item.bbox_xyxy
        nearest = np.asarray((np.clip(center[0], x1, x2), np.clip(center[1], y1, y2)))
        ratio = float(np.linalg.norm(nearest - center) / max(palm.scale, 1e-6))
        if ratio <= 2.25 and (best is None or ratio < best[1]):
            best = item, ratio
    return best


def _body_anchor(side: str, points: np.ndarray, scores: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray, float] | None:
    wrist_index, elbow_index = ((9, 7) if side == "left" else (10, 8))
    if any(index >= points.shape[0] or index >= scores.shape[0] or scores[index] < threshold or not np.isfinite(points[index]).all() for index in (wrist_index, elbow_index)):
        return None
    wrist = points[wrist_index].astype(np.float32)
    elbow = points[elbow_index].astype(np.float32)
    forearm = float(np.linalg.norm(wrist - elbow))
    return (wrist, elbow, forearm) if forearm > 1.0 else None


def _palm_scale(points: np.ndarray) -> float:
    values = [np.linalg.norm(points[0] - points[9]), np.linalg.norm(points[5] - points[17])]
    return float(np.median(values)) if np.isfinite(values).all() else 0.0


def _orientation(points: np.ndarray) -> float:
    vector = points[9] - points[0]
    return math.degrees(math.atan2(float(vector[1]), float(vector[0])))


def _angle_difference(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _clip_roi(center: np.ndarray, half_size: float, width: int, height: int) -> tuple[int, int, int, int]:
    x1 = max(0, int(math.floor(float(center[0]) - half_size)))
    y1 = max(0, int(math.floor(float(center[1]) - half_size)))
    x2 = min(width, int(math.ceil(float(center[0]) + half_size)))
    y2 = min(height, int(math.ceil(float(center[1]) + half_size)))
    if x2 <= x1:
        x2 = min(width, x1 + 1)
    if y2 <= y1:
        y2 = min(height, y1 + 1)
    return x1, y1, x2, y2


def _distance_ratio(points: np.ndarray, valid: np.ndarray, first: int, second: int, scale: float) -> float | None:
    if not bool(valid[first]) or not bool(valid[second]):
        return None
    value = float(np.linalg.norm(points[first] - points[second]) / max(scale, 1e-6))
    return value if math.isfinite(value) else None


def _safe_flexion(first: np.ndarray, middle: np.ndarray, last: np.ndarray) -> float | None:
    first_vector = first - middle
    second_vector = last - middle
    denominator = float(np.linalg.norm(first_vector) * np.linalg.norm(second_vector))
    if denominator <= 1e-8 or not math.isfinite(denominator):
        return None
    cosine = float(np.clip(np.dot(first_vector, second_vector) / denominator, -1.0, 1.0))
    return float(np.clip(180.0 - math.degrees(math.acos(cosine)), 0.0, 180.0))


def _mean_flexion(diagnostic: FingerDiagnostic) -> float | None:
    values = [value for value in (diagnostic.flexion_mcp, diagnostic.flexion_pip, diagnostic.flexion_dip) if value is not None]
    return float(np.mean(values)) / 180.0 if values else None


def _unknown_grip() -> GripFeaturesV2:
    return GripFeaturesV2(
        GripStateV2.UNKNOWN,
        0.0,
        None,
        None,
        None,
        None,
        None,
        None,
        {},
        None,
        None,
        0.0,
    )


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None

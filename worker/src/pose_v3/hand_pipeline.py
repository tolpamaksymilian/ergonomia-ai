from __future__ import annotations

import math
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

try:
    import mediapipe as mp
except ImportError as error:  # pragma: no cover - jasny błąd przy uruchomieniu
    mp = None  # type: ignore[assignment]
    _MEDIAPIPE_IMPORT_ERROR: Exception | None = error
else:
    _MEDIAPIPE_IMPORT_ERROR = None


HandSide = Literal["left", "right"]

HAND_LANDMARKER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)

HAND_POINT_COUNT = 21
HAND_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
)
PALM_EDGES: tuple[tuple[int, int], ...] = (
    (0, 5), (5, 9), (9, 13), (13, 17), (17, 0), (5, 17),
)
FINGER_CHAINS: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4),
    (0, 5, 6, 7, 8),
    (0, 9, 10, 11, 12),
    (0, 13, 14, 15, 16),
    (0, 17, 18, 19, 20),
)


@dataclass(frozen=True)
class HandPipelineConfig:
    model_path: Path
    num_hands: int = 2
    detection_confidence: float = 0.65
    presence_confidence: float = 0.65
    tracking_confidence: float = 0.65

    assignment_max_wrist_distance_ratio: float = 1.05
    handedness_soft_penalty: float = 0.18

    min_palm_size_pixels: float = 8.0
    min_forearm_pixels: float = 12.0
    min_lock_frames: int = 2
    max_interpolation_gap_frames: int = 1

    max_root_wrist_distance_ratio: float = 0.75
    min_scale_ratio: float = 0.50
    max_scale_ratio: float = 1.90
    max_scale_change_ratio: float = 0.48
    max_orientation_change_degrees: float = 105.0
    max_joint_velocity_palm_ratio: float = 1.35
    max_median_joint_velocity_palm_ratio: float = 0.70
    max_world_depth_jump_meters: float = 0.11

    bone_log_tolerance: float = 0.52
    max_bone_outliers: int = 3
    max_hand_radius_forearm_ratio: float = 1.55
    max_bone_forearm_ratio: float = 0.68

    median_window: int = 3
    smoothing_alpha: float = 0.62
    bone_projection_strength: float = 0.42


@dataclass
class HandObservation:
    points_px: np.ndarray
    world_points: np.ndarray
    handedness_label: str
    handedness_score: float
    body_wrist: np.ndarray
    forearm_length: float
    root_wrist_distance_ratio: float
    palm_scale: float
    orientation_degrees: float
    assignment_score: float


@dataclass
class RawHandFrame:
    observation: HandObservation | None
    timestamp_seconds: float
    detector_found: bool
    assignment_reasons: list[str] = field(default_factory=list)


@dataclass
class ValidatedHandFrame:
    visible: bool
    interpolated: bool
    points_px: np.ndarray
    world_points: np.ndarray
    quality: float
    reject_reasons: list[str]
    handedness_label: str | None
    handedness_score: float


@dataclass(frozen=True)
class HandTrackSummary:
    side: HandSide
    total_frames: int
    detected_frames: int
    valid_frames: int
    interpolated_frames: int
    rejected_frames: int
    detected_ratio: float
    valid_ratio: float
    mean_quality: float
    reject_reason_counts: dict[str, int]


@dataclass(frozen=True)
class HandPipelineResult:
    frames: list[ValidatedHandFrame]
    summary: HandTrackSummary


@dataclass(frozen=True)
class _Candidate:
    points_px: np.ndarray
    world_points: np.ndarray
    handedness_label: str
    handedness_score: float


class MediaPipeHandEngine:
    """MediaPipe Hand Landmarker w trybie VIDEO z automatycznym modelem."""

    def __init__(self, config: HandPipelineConfig) -> None:
        if mp is None:
            raise RuntimeError(
                "Brakuje pakietu mediapipe. Zainstaluj go komendą: "
                "python -m pip install mediapipe==1.0.0"
            ) from _MEDIAPIPE_IMPORT_ERROR

        self.config = config
        self._ensure_model(config.model_path)

        BaseOptions = mp.tasks.BaseOptions
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        RunningMode = mp.tasks.vision.RunningMode

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(config.model_path)),
            running_mode=RunningMode.VIDEO,
            num_hands=config.num_hands,
            min_hand_detection_confidence=config.detection_confidence,
            min_hand_presence_confidence=config.presence_confidence,
            min_tracking_confidence=config.tracking_confidence,
        )
        self._landmarker = HandLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1

    @staticmethod
    def _ensure_model(model_path: Path) -> None:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        if model_path.exists() and model_path.stat().st_size > 1_000_000:
            return

        temporary_path = model_path.with_suffix(model_path.suffix + ".download")
        temporary_path.unlink(missing_ok=True)
        try:
            urllib.request.urlretrieve(HAND_LANDMARKER_MODEL_URL, temporary_path)
            if not temporary_path.exists() or temporary_path.stat().st_size <= 1_000_000:
                raise RuntimeError("Pobrany model MediaPipe Hand Landmarker jest pusty.")
            temporary_path.replace(model_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def close(self) -> None:
        close_method = getattr(self._landmarker, "close", None)
        if callable(close_method):
            close_method()

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> list[_Candidate]:
        safe_timestamp = max(self._last_timestamp_ms + 1, int(timestamp_ms))
        self._last_timestamp_ms = safe_timestamp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, safe_timestamp)

        hand_landmarks = list(getattr(result, "hand_landmarks", []) or [])
        world_landmarks = list(getattr(result, "hand_world_landmarks", []) or [])
        handedness = list(getattr(result, "handedness", []) or [])

        height, width = frame_bgr.shape[:2]
        candidates: list[_Candidate] = []
        for index, landmarks in enumerate(hand_landmarks):
            if len(landmarks) != HAND_POINT_COUNT:
                continue

            points_px = np.asarray(
                [[float(item.x) * width, float(item.y) * height] for item in landmarks],
                dtype=np.float32,
            )
            if not np.isfinite(points_px).all():
                continue

            if index < len(world_landmarks) and len(world_landmarks[index]) == HAND_POINT_COUNT:
                world = np.asarray(
                    [[float(item.x), float(item.y), float(item.z)] for item in world_landmarks[index]],
                    dtype=np.float32,
                )
            else:
                world = np.zeros((HAND_POINT_COUNT, 3), dtype=np.float32)

            label = "Unknown"
            score = 0.0
            if index < len(handedness) and handedness[index]:
                category = handedness[index][0]
                label = str(
                    getattr(category, "category_name", None)
                    or getattr(category, "display_name", None)
                    or "Unknown"
                )
                score = float(getattr(category, "score", 0.0) or 0.0)

            candidates.append(
                _Candidate(
                    points_px=points_px,
                    world_points=world,
                    handedness_label=label,
                    handedness_score=float(np.clip(score, 0.0, 1.0)),
                )
            )

        return candidates


def _point_valid(points: np.ndarray, scores: np.ndarray, index: int, threshold: float) -> bool:
    return (
        index < points.shape[0]
        and index < scores.shape[0]
        and float(scores[index]) >= threshold
        and np.isfinite(points[index]).all()
    )


def _body_anchor(
    side: HandSide,
    body_points: np.ndarray,
    body_scores: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, float] | None:
    wrist_index, elbow_index = ((9, 7) if side == "left" else (10, 8))
    if not _point_valid(body_points, body_scores, wrist_index, threshold):
        return None
    if not _point_valid(body_points, body_scores, elbow_index, threshold):
        return None

    wrist = body_points[wrist_index].astype(np.float32)
    elbow = body_points[elbow_index].astype(np.float32)
    forearm = float(np.linalg.norm(wrist - elbow))
    if not math.isfinite(forearm) or forearm <= 1.0:
        return None
    return wrist, forearm


def _palm_scale(points: np.ndarray) -> float:
    distances = (
        np.linalg.norm(points[0] - points[9]),
        np.linalg.norm(points[5] - points[17]),
        np.linalg.norm(points[0] - points[5]),
        np.linalg.norm(points[0] - points[17]),
    )
    valid = [float(value) for value in distances if math.isfinite(float(value)) and value > 0]
    return float(np.median(valid)) if valid else 0.0


def _orientation_degrees(points: np.ndarray) -> float:
    vector = points[9] - points[0]
    return math.degrees(math.atan2(float(vector[1]), float(vector[0])))


def _angle_difference_degrees(first: float, second: float) -> float:
    difference = (first - second + 180.0) % 360.0 - 180.0
    return abs(difference)


def assign_hands_to_body(
    candidates: list[_Candidate],
    body_points: np.ndarray,
    body_scores: np.ndarray,
    body_threshold: float,
    config: HandPipelineConfig,
    timestamp_seconds: float,
) -> dict[HandSide, RawHandFrame]:
    result: dict[HandSide, RawHandFrame] = {
        "left": RawHandFrame(None, timestamp_seconds, bool(candidates)),
        "right": RawHandFrame(None, timestamp_seconds, bool(candidates)),
    }

    anchors = {
        side: _body_anchor(side, body_points, body_scores, body_threshold)
        for side in ("left", "right")
    }

    possible: list[tuple[float, int, HandSide, HandObservation]] = []
    for candidate_index, candidate in enumerate(candidates):
        palm_scale = _palm_scale(candidate.points_px)
        if palm_scale < config.min_palm_size_pixels:
            continue

        for side in ("left", "right"):
            anchor = anchors[side]
            if anchor is None:
                continue
            wrist, forearm = anchor
            if forearm < config.min_forearm_pixels:
                continue

            root_distance_ratio = float(
                np.linalg.norm(candidate.points_px[0] - wrist) / max(forearm, 1.0)
            )
            if root_distance_ratio > config.assignment_max_wrist_distance_ratio:
                continue

            # MediaPipe handedness bywa odwrócone dla nie-lustrzanego filmu,
            # dlatego jest tylko miękką karą, a nie warunkiem bezwzględnym.
            label = candidate.handedness_label.lower()
            expected = side.lower()
            handedness_penalty = 0.0
            if label in {"left", "right"} and label != expected:
                handedness_penalty = config.handedness_soft_penalty * candidate.handedness_score

            assignment_score = root_distance_ratio + handedness_penalty
            observation = HandObservation(
                points_px=candidate.points_px.copy(),
                world_points=candidate.world_points.copy(),
                handedness_label=candidate.handedness_label,
                handedness_score=candidate.handedness_score,
                body_wrist=wrist.copy(),
                forearm_length=forearm,
                root_wrist_distance_ratio=root_distance_ratio,
                palm_scale=palm_scale,
                orientation_degrees=_orientation_degrees(candidate.points_px),
                assignment_score=assignment_score,
            )
            possible.append((assignment_score, candidate_index, side, observation))

    used_candidates: set[int] = set()
    used_sides: set[HandSide] = set()
    for _, candidate_index, side, observation in sorted(possible, key=lambda item: item[0]):
        if candidate_index in used_candidates or side in used_sides:
            continue
        used_candidates.add(candidate_index)
        used_sides.add(side)
        result[side] = RawHandFrame(
            observation=observation,
            timestamp_seconds=timestamp_seconds,
            detector_found=True,
        )

    for side in ("left", "right"):
        if result[side].observation is None:
            reasons: list[str] = []
            if not candidates:
                reasons.append("no_hand_detection")
            elif anchors[side] is None:
                reasons.append("body_wrist_or_elbow_missing")
            else:
                reasons.append("no_hand_matched_to_body_wrist")
            result[side].assignment_reasons.extend(reasons)

    return result


def _bone_lengths(points: np.ndarray) -> np.ndarray:
    return np.asarray(
        [float(np.linalg.norm(points[second] - points[first])) for first, second in HAND_EDGES],
        dtype=np.float32,
    )


def _hand_radius(points: np.ndarray) -> float:
    return float(np.max(np.linalg.norm(points - points[0], axis=1)))


def _reference_statistics(raw_frames: list[RawHandFrame], config: HandPipelineConfig) -> tuple[float, np.ndarray]:
    scales: list[float] = []
    normalized_bones: list[np.ndarray] = []
    for frame in raw_frames:
        observation = frame.observation
        if observation is None:
            continue
        if observation.root_wrist_distance_ratio > config.max_root_wrist_distance_ratio * 1.35:
            continue
        if observation.palm_scale < config.min_palm_size_pixels:
            continue
        bones = _bone_lengths(observation.points_px)
        if not np.isfinite(bones).all():
            continue
        scales.append(observation.palm_scale)
        normalized_bones.append(bones / max(observation.palm_scale, 1.0))

    reference_scale = float(np.median(scales)) if scales else 0.0
    if normalized_bones:
        reference_bones = np.median(np.stack(normalized_bones, axis=0), axis=0).astype(np.float32)
    else:
        reference_bones = np.zeros((len(HAND_EDGES),), dtype=np.float32)
    return reference_scale, reference_bones


def _validate_raw_frames(
    raw_frames: list[RawHandFrame],
    config: HandPipelineConfig,
) -> tuple[list[bool], list[list[str]], list[float], float, np.ndarray]:
    reference_scale, reference_bones = _reference_statistics(raw_frames, config)
    valid_flags: list[bool] = []
    reasons_per_frame: list[list[str]] = []
    qualities: list[float] = []

    previous_observation: HandObservation | None = None
    previous_valid_index: int | None = None

    for frame_index, frame in enumerate(raw_frames):
        observation = frame.observation
        reasons = list(frame.assignment_reasons)
        quality_components: list[float] = []

        if observation is None:
            if not reasons:
                reasons.append("missing_hand")
            valid_flags.append(False)
            reasons_per_frame.append(reasons)
            qualities.append(0.0)
            continue

        points = observation.points_px
        if points.shape != (HAND_POINT_COUNT, 2) or not np.isfinite(points).all():
            reasons.append("invalid_landmark_array")

        if observation.root_wrist_distance_ratio > config.max_root_wrist_distance_ratio:
            reasons.append("root_too_far_from_body_wrist")
        else:
            quality_components.append(
                max(0.0, 1.0 - observation.root_wrist_distance_ratio / config.max_root_wrist_distance_ratio)
            )

        if reference_scale <= 0.0 or observation.palm_scale <= 0.0:
            reasons.append("invalid_palm_scale")
            scale_ratio = 0.0
        else:
            scale_ratio = observation.palm_scale / reference_scale
            if scale_ratio < config.min_scale_ratio or scale_ratio > config.max_scale_ratio:
                reasons.append("palm_scale_outlier")
            else:
                quality_components.append(max(0.0, 1.0 - abs(math.log(scale_ratio))))

        bones = _bone_lengths(points)
        if not np.isfinite(bones).all():
            reasons.append("invalid_bone_lengths")
        elif reference_bones.size and np.count_nonzero(reference_bones > 1e-5):
            normalized = bones / max(observation.palm_scale, 1.0)
            safe_reference = np.where(reference_bones > 1e-5, reference_bones, normalized)
            log_error = np.abs(np.log(np.clip(normalized / np.maximum(safe_reference, 1e-5), 1e-4, 1e4)))
            outlier_count = int(np.count_nonzero(log_error > config.bone_log_tolerance))
            if outlier_count > config.max_bone_outliers:
                reasons.append("bone_length_outlier")
            quality_components.append(max(0.0, 1.0 - float(np.median(log_error))))

        if observation.forearm_length <= 0.0:
            reasons.append("invalid_forearm_length")
        else:
            if _hand_radius(points) / observation.forearm_length > config.max_hand_radius_forearm_ratio:
                reasons.append("hand_radius_too_large")
            if float(np.max(bones)) / observation.forearm_length > config.max_bone_forearm_ratio:
                reasons.append("finger_segment_too_long")

        if previous_observation is not None and previous_valid_index is not None:
            gap = max(1, frame_index - previous_valid_index)
            previous_points = previous_observation.points_px
            previous_scale = max(previous_observation.palm_scale, 1.0)
            current_scale = max(observation.palm_scale, 1.0)
            normalization_scale = max(1.0, (previous_scale + current_scale) / 2.0)
            displacements = np.linalg.norm(points - previous_points, axis=1) / normalization_scale / gap
            max_velocity = float(np.max(displacements))
            median_velocity = float(np.median(displacements))
            if max_velocity > config.max_joint_velocity_palm_ratio:
                reasons.append("excessive_joint_velocity")
            if median_velocity > config.max_median_joint_velocity_palm_ratio:
                reasons.append("excessive_hand_translation")

            scale_change = abs(current_scale - previous_scale) / max(previous_scale, 1.0) / gap
            if scale_change > config.max_scale_change_ratio:
                reasons.append("sudden_scale_change")

            orientation_change = _angle_difference_degrees(
                observation.orientation_degrees,
                previous_observation.orientation_degrees,
            ) / gap
            if orientation_change > config.max_orientation_change_degrees:
                reasons.append("sudden_orientation_change")

            if (
                observation.world_points.shape == (HAND_POINT_COUNT, 3)
                and previous_observation.world_points.shape == (HAND_POINT_COUNT, 3)
            ):
                current_depth = float(np.median(observation.world_points[:, 2]))
                previous_depth = float(np.median(previous_observation.world_points[:, 2]))
                if abs(current_depth - previous_depth) / gap > config.max_world_depth_jump_meters:
                    reasons.append("world_depth_jump")

        # Powody techniczne nie dyskwalifikują podwójnie; każdy nienaturalny skok ukrywa dłoń.
        valid = not reasons
        valid_flags.append(valid)
        reasons_per_frame.append(reasons)

        base_quality = float(np.mean(quality_components)) if quality_components else 0.0
        handedness_quality = observation.handedness_score
        qualities.append(float(np.clip(0.82 * base_quality + 0.18 * handedness_quality, 0.0, 1.0)))

        if valid:
            previous_observation = observation
            previous_valid_index = frame_index

    return valid_flags, reasons_per_frame, qualities, reference_scale, reference_bones


def _valid_runs(flags: list[bool]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(flags):
        if value and start is None:
            start = index
        is_last = index == len(flags) - 1
        if start is not None and ((not value) or is_last):
            end = index if value and is_last else index - 1
            runs.append((start, end))
            start = None
    return runs


def _temporal_median(points: np.ndarray, visible: np.ndarray, window: int) -> np.ndarray:
    output = points.copy()
    radius = max(0, window // 2)
    for frame_index in range(points.shape[0]):
        if not visible[frame_index]:
            continue
        start = max(0, frame_index - radius)
        end = min(points.shape[0], frame_index + radius + 1)
        indices = [index for index in range(start, end) if visible[index]]
        if indices:
            output[frame_index] = np.median(points[indices], axis=0)
    return output


def _bidirectional_ema(points: np.ndarray, visible: np.ndarray, alpha: float) -> np.ndarray:
    alpha = float(np.clip(alpha, 0.05, 0.95))
    forward = points.copy()
    last: np.ndarray | None = None
    for index in range(points.shape[0]):
        if not visible[index]:
            last = None
            continue
        last = points[index].copy() if last is None else alpha * points[index] + (1.0 - alpha) * last
        forward[index] = last

    backward = points.copy()
    last = None
    for index in range(points.shape[0] - 1, -1, -1):
        if not visible[index]:
            last = None
            continue
        last = points[index].copy() if last is None else alpha * points[index] + (1.0 - alpha) * last
        backward[index] = last

    output = points.copy()
    output[visible] = (forward[visible] + backward[visible]) / 2.0
    return output


def _project_bones(
    points: np.ndarray,
    palm_scale: float,
    reference_bones: np.ndarray,
    strength: float,
) -> np.ndarray:
    output = points.copy()
    strength = float(np.clip(strength, 0.0, 1.0))
    if palm_scale <= 0.0 or reference_bones.size != len(HAND_EDGES):
        return output

    for edge_index, (parent, child) in enumerate(HAND_EDGES):
        target_length = float(reference_bones[edge_index]) * palm_scale
        if target_length <= 0.0:
            continue
        vector = output[child] - output[parent]
        current_length = float(np.linalg.norm(vector))
        if current_length <= 1e-5 or not math.isfinite(current_length):
            continue
        projected = output[parent] + vector / current_length * target_length
        output[child] = (1.0 - strength) * output[child] + strength * projected
    return output


def stabilize_hand_track(
    side: HandSide,
    raw_frames: list[RawHandFrame],
    config: HandPipelineConfig,
) -> HandPipelineResult:
    frame_count = len(raw_frames)
    if frame_count == 0:
        return HandPipelineResult(
            frames=[],
            summary=HandTrackSummary(side, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, {}),
        )

    valid_flags, reasons, qualities, reference_scale, reference_bones = _validate_raw_frames(
        raw_frames,
        config,
    )

    visible = np.zeros((frame_count,), dtype=bool)
    for start, end in _valid_runs(valid_flags):
        if end - start + 1 >= config.min_lock_frames:
            visible[start : end + 1] = True
        else:
            for index in range(start, end + 1):
                reasons[index].append("unstable_short_run")

    interpolated = np.zeros((frame_count,), dtype=bool)
    index = 0
    while index < frame_count:
        if visible[index]:
            index += 1
            continue
        gap_start = index
        while index < frame_count and not visible[index]:
            index += 1
        gap_end = index - 1
        gap_length = gap_end - gap_start + 1
        before = gap_start - 1
        after = index
        if (
            gap_length <= config.max_interpolation_gap_frames
            and before >= 0
            and after < frame_count
            and visible[before]
            and visible[after]
            and raw_frames[before].observation is not None
            and raw_frames[after].observation is not None
        ):
            first = raw_frames[before].observation
            second = raw_frames[after].observation
            scale = max(1.0, (first.palm_scale + second.palm_scale) / 2.0)
            median_displacement = float(np.median(np.linalg.norm(second.points_px - first.points_px, axis=1))) / scale
            if median_displacement <= config.max_median_joint_velocity_palm_ratio * (gap_length + 1):
                visible[gap_start : gap_end + 1] = True
                interpolated[gap_start : gap_end + 1] = True
                for gap_index in range(gap_start, gap_end + 1):
                    reasons[gap_index] = ["interpolated_short_gap"]

    points = np.zeros((frame_count, HAND_POINT_COUNT, 2), dtype=np.float32)
    world = np.zeros((frame_count, HAND_POINT_COUNT, 3), dtype=np.float32)
    handedness_labels: list[str | None] = [None] * frame_count
    handedness_scores = np.zeros((frame_count,), dtype=np.float32)

    for frame_index, frame in enumerate(raw_frames):
        if not visible[frame_index]:
            continue
        if interpolated[frame_index]:
            before = frame_index - 1
            while before >= 0 and raw_frames[before].observation is None:
                before -= 1
            after = frame_index + 1
            while after < frame_count and raw_frames[after].observation is None:
                after += 1
            if before >= 0 and after < frame_count:
                ratio = (frame_index - before) / (after - before)
                first = raw_frames[before].observation
                second = raw_frames[after].observation
                if first is not None and second is not None:
                    points[frame_index] = (1.0 - ratio) * first.points_px + ratio * second.points_px
                    world[frame_index] = (1.0 - ratio) * first.world_points + ratio * second.world_points
                    handedness_labels[frame_index] = first.handedness_label
                    handedness_scores[frame_index] = min(first.handedness_score, second.handedness_score)
                    qualities[frame_index] = min(qualities[before], qualities[after]) * 0.85
        else:
            observation = frame.observation
            if observation is not None:
                points[frame_index] = observation.points_px
                world[frame_index] = observation.world_points
                handedness_labels[frame_index] = observation.handedness_label
                handedness_scores[frame_index] = observation.handedness_score

    points = _temporal_median(points, visible, config.median_window)
    points = _bidirectional_ema(points, visible, config.smoothing_alpha)

    for frame_index in range(frame_count):
        if not visible[frame_index]:
            continue
        current_scale = _palm_scale(points[frame_index])
        points[frame_index] = _project_bones(
            points[frame_index],
            current_scale if current_scale > 0 else reference_scale,
            reference_bones,
            config.bone_projection_strength,
        )

        observation = raw_frames[frame_index].observation
        forearm = observation.forearm_length if observation is not None else 0.0
        if forearm > 0.0:
            if _hand_radius(points[frame_index]) / forearm > config.max_hand_radius_forearm_ratio:
                visible[frame_index] = False
                reasons[frame_index].append("postfilter_hand_radius_outlier")
                continue
            if float(np.max(_bone_lengths(points[frame_index]))) / forearm > config.max_bone_forearm_ratio:
                visible[frame_index] = False
                reasons[frame_index].append("postfilter_bone_length_outlier")

    reject_counts: dict[str, int] = {}
    output_frames: list[ValidatedHandFrame] = []
    for frame_index in range(frame_count):
        if not visible[frame_index]:
            for reason in reasons[frame_index] or ["not_visible"]:
                reject_counts[reason] = reject_counts.get(reason, 0) + 1
        output_frames.append(
            ValidatedHandFrame(
                visible=bool(visible[frame_index]),
                interpolated=bool(interpolated[frame_index] and visible[frame_index]),
                points_px=points[frame_index].copy() if visible[frame_index] else np.zeros((HAND_POINT_COUNT, 2), dtype=np.float32),
                world_points=world[frame_index].copy() if visible[frame_index] else np.zeros((HAND_POINT_COUNT, 3), dtype=np.float32),
                quality=float(np.clip(qualities[frame_index], 0.0, 1.0)) if visible[frame_index] else 0.0,
                reject_reasons=[] if visible[frame_index] else list(dict.fromkeys(reasons[frame_index] or ["not_visible"])),
                handedness_label=handedness_labels[frame_index],
                handedness_score=float(np.clip(handedness_scores[frame_index], 0.0, 1.0)),
            )
        )

    detected_frames = sum(1 for frame in raw_frames if frame.observation is not None)
    valid_frames = int(np.count_nonzero(visible))
    interpolated_frames = int(np.count_nonzero(interpolated & visible))
    mean_quality = (
        float(np.mean([frame.quality for frame in output_frames if frame.visible]))
        if valid_frames
        else 0.0
    )
    summary = HandTrackSummary(
        side=side,
        total_frames=frame_count,
        detected_frames=detected_frames,
        valid_frames=valid_frames,
        interpolated_frames=interpolated_frames,
        rejected_frames=frame_count - valid_frames,
        detected_ratio=detected_frames / frame_count,
        valid_ratio=valid_frames / frame_count,
        mean_quality=mean_quality,
        reject_reason_counts=reject_counts,
    )
    return HandPipelineResult(frames=output_frames, summary=summary)


def draw_validated_hand(
    image: np.ndarray,
    frame: ValidatedHandFrame,
    color: tuple[int, int, int],
    thickness: int,
    radius: int,
) -> None:
    if not frame.visible:
        return
    points = frame.points_px
    for first, second in HAND_EDGES:
        first_point = tuple(np.round(points[first]).astype(int))
        second_point = tuple(np.round(points[second]).astype(int))
        cv2.line(image, first_point, second_point, color, thickness, cv2.LINE_AA)
    for point in points:
        cv2.circle(image, tuple(np.round(point).astype(int)), radius, color, -1, cv2.LINE_AA)


def serialize_hand_frame(frame: ValidatedHandFrame) -> dict[str, Any]:
    if not frame.visible:
        return {
            "visible": False,
            "interpolated": False,
            "quality": 0.0,
            "handedness": None,
            "handedness_score": 0.0,
            "landmarks_2d": None,
            "world_landmarks_3d": None,
            "reject_reasons": frame.reject_reasons,
        }
    return {
        "visible": True,
        "interpolated": frame.interpolated,
        "quality": round(frame.quality, 6),
        "handedness": frame.handedness_label,
        "handedness_score": round(frame.handedness_score, 6),
        "landmarks_2d": np.round(frame.points_px, 2).tolist(),
        "world_landmarks_3d": np.round(frame.world_points, 6).tolist(),
        "reject_reasons": [],
    }


def serialize_hand_summary(summary: HandTrackSummary) -> dict[str, Any]:
    return {
        "side": summary.side,
        "total_frames": summary.total_frames,
        "detected_frames": summary.detected_frames,
        "valid_frames": summary.valid_frames,
        "interpolated_frames": summary.interpolated_frames,
        "rejected_frames": summary.rejected_frames,
        "detected_ratio": round(summary.detected_ratio, 6),
        "valid_ratio": round(summary.valid_ratio, 6),
        "mean_quality": round(summary.mean_quality, 6),
        "reject_reason_counts": summary.reject_reason_counts,
    }


def resolve_hand_model_path(worker_directory: Path, configured_value: str | None) -> Path:
    value = (configured_value or "models/hand_landmarker.task").strip()
    candidate = Path(os.path.expandvars(value)).expanduser()
    if not candidate.is_absolute():
        candidate = worker_directory / candidate
    return candidate.resolve()

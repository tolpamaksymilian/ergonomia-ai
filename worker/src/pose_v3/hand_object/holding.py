"""Deterministic grip features and conservative holding episode detection."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np

from ..hand_pipeline import ValidatedHandFrame


class GripState(StrEnum):
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    PINCH = "PINCH"
    UNKNOWN = "UNKNOWN"


class HoldingState(StrEnum):
    NOT_HOLDING = "NOT_HOLDING"
    POSSIBLE_HOLDING = "POSSIBLE_HOLDING"
    LIKELY_HOLDING = "LIKELY_HOLDING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HoldingConfig:
    enabled: bool = True
    minimum_hand_quality: float = 0.45
    minimum_confirmation_seconds: float = 0.40
    release_confirmation_seconds: float = 0.25
    maximum_unknown_gap_seconds: float = 0.20
    likely_evidence_threshold: float = 0.62
    possible_evidence_threshold: float = 0.42
    object_maximum_distance_palm_ratio: float = 2.0


@dataclass(frozen=True)
class ObjectDetection:
    bbox_xyxy: tuple[float, float, float, float]
    class_id: int
    class_name: str | None
    confidence: float | None = None
    detection_index: int | None = None


@dataclass(frozen=True)
class GripFeatures:
    valid: bool
    quality: float
    closure_ratio: float | None
    thumb_index_distance_ratio: float | None
    thumb_middle_distance_ratio: float | None
    finger_flexion: float | None
    palm_orientation_degrees: float | None
    wrist_orientation_degrees: float | None
    grip_stability: float
    grip_state: GripState
    grip_confidence: float
    palm_center: tuple[float, float] | None
    palm_scale: float | None


@dataclass(frozen=True)
class HoldingFrame:
    state: HoldingState
    confidence: float
    grip: GripFeatures
    object_class: str | None
    object_confidence: float | None
    object_index: int | None
    object_proximity_ratio: float | None
    bimanual_candidate: bool = False


@dataclass(frozen=True)
class HoldEpisode:
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    duration_seconds: float
    confidence: float
    holding_state: HoldingState
    known_object_class: str | None
    known_object_confidence: float | None


@dataclass(frozen=True)
class HoldingSummary:
    side: str
    valid_observation_seconds: float
    likely_holding_seconds: float
    static_holding_seconds: float
    longest_holding_seconds: float
    holding_episode_count: int
    episodes: tuple[HoldEpisode, ...]
    external_load_known: bool = False


def compute_grip_features(
    frame: ValidatedHandFrame,
    previous: GripFeatures | None = None,
) -> GripFeatures:
    if not frame.visible or frame.points_px.shape != (21, 2) or not np.isfinite(frame.points_px).all():
        return _unknown_grip()
    required_indices = np.asarray([0, 4, 5, 8, 9, 12, 13, 16, 17, 20])
    if (
        frame.point_validity.size == 21
        and int(np.count_nonzero(frame.point_validity[required_indices])) < 8
    ):
        return _unknown_grip()
    points = frame.points_px.astype(np.float32)
    palm_indices = (0, 5, 9, 13, 17)
    palm_center_array = np.mean(points[list(palm_indices)], axis=0)
    palm_scale_values = (
        np.linalg.norm(points[0] - points[9]),
        np.linalg.norm(points[5] - points[17]),
    )
    palm_scale = float(np.median(palm_scale_values))
    if not math.isfinite(palm_scale) or palm_scale <= 1e-5:
        return _unknown_grip()

    finger_tips = points[[8, 12, 16, 20]]
    tip_distances = np.linalg.norm(finger_tips - palm_center_array, axis=1) / palm_scale
    closure = float(np.clip(1.0 - float(np.mean(tip_distances)) / 1.65, 0.0, 1.0))
    thumb_index = float(np.linalg.norm(points[4] - points[8]) / palm_scale)
    thumb_middle = float(np.linalg.norm(points[4] - points[12]) / palm_scale)
    flexions = [
        _flexion(points[mcp], points[pip], points[tip])
        for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))
    ]
    finger_flexion = float(np.mean(flexions))
    palm_vector = points[9] - points[0]
    wrist_vector = palm_center_array - points[0]
    palm_orientation = math.degrees(math.atan2(float(palm_vector[1]), float(palm_vector[0])))
    wrist_orientation = math.degrees(math.atan2(float(wrist_vector[1]), float(wrist_vector[0])))

    stability = 1.0
    if previous is not None and previous.valid and previous.palm_center is not None and previous.closure_ratio is not None:
        center_change = float(
            np.linalg.norm(palm_center_array - np.asarray(previous.palm_center, dtype=np.float32))
        ) / palm_scale
        closure_change = abs(closure - previous.closure_ratio)
        stability = float(np.clip(1.0 - 0.65 * center_change - 0.35 * closure_change, 0.0, 1.0))

    quality = float(np.clip(frame.quality, 0.0, 1.0))
    if quality < 0.45:
        state = GripState.UNKNOWN
    elif thumb_index <= 0.14 and thumb_middle >= thumb_index * 1.55:
        state = GripState.PINCH
    elif closure >= 0.64:
        state = GripState.CLOSED
    elif closure >= 0.30:
        state = GripState.PARTIALLY_CLOSED
    else:
        state = GripState.OPEN
    state_separation = (
        1.0
        if state in {GripState.OPEN, GripState.CLOSED}
        else 0.82
        if state == GripState.PINCH
        else 0.70
        if state == GripState.PARTIALLY_CLOSED
        else 0.0
    )
    grip_confidence = float(np.clip(0.72 * quality + 0.18 * stability + 0.10 * state_separation, 0.0, 1.0))
    return GripFeatures(
        valid=state != GripState.UNKNOWN,
        quality=quality,
        closure_ratio=closure,
        thumb_index_distance_ratio=thumb_index,
        thumb_middle_distance_ratio=thumb_middle,
        finger_flexion=finger_flexion,
        palm_orientation_degrees=palm_orientation,
        wrist_orientation_degrees=wrist_orientation,
        grip_stability=stability,
        grip_state=state,
        grip_confidence=grip_confidence,
        palm_center=(float(palm_center_array[0]), float(palm_center_array[1])),
        palm_scale=palm_scale,
    )


def analyze_holding_track(
    side: str,
    hand_frames: list[ValidatedHandFrame],
    timestamps: list[float],
    object_detections: list[list[ObjectDetection]] | None,
    *,
    fps: float,
    config: HoldingConfig,
) -> tuple[list[HoldingFrame], HoldingSummary]:
    if len(hand_frames) != len(timestamps):
        raise ValueError("Liczba klatek dłoni i timestampów musi być zgodna.")
    detections = object_detections or [[] for _ in hand_frames]
    if len(detections) != len(hand_frames):
        raise ValueError("Liczba list detekcji musi odpowiadać liczbie klatek.")
    durations = _frame_durations(timestamps, fps)
    grips: list[GripFeatures] = []
    raw_frames: list[HoldingFrame] = []
    previous: GripFeatures | None = None
    for hand, frame_detections in zip(hand_frames, detections):
        grip = compute_grip_features(hand, previous)
        if grip.valid:
            previous = grip
        grips.append(grip)
        object_match = _nearest_object(grip, frame_detections, config)
        raw_frames.append(_raw_holding_frame(grip, object_match, config))

    candidate = [
        item.state == HoldingState.POSSIBLE_HOLDING
        and item.confidence >= config.likely_evidence_threshold
        for item in raw_frames
    ]
    episode_ranges = _confirmed_ranges(
        candidate,
        [not grip.valid for grip in grips],
        durations,
        config,
    )
    confirmed = np.zeros((len(raw_frames),), dtype=bool)
    episodes: list[HoldEpisode] = []
    for start, end in episode_ranges:
        confirmed[start : end + 1] = True
        episode_confidences = [raw_frames[index].confidence for index in range(start, end + 1) if grips[index].valid]
        classes = [raw_frames[index].object_class for index in range(start, end + 1) if raw_frames[index].object_class]
        object_class = Counter(classes).most_common(1)[0][0] if classes else None
        object_confidences = [raw_frames[index].object_confidence for index in range(start, end + 1) if raw_frames[index].object_confidence is not None]
        duration = float(sum(durations[start : end + 1]))
        episodes.append(
            HoldEpisode(
                start_frame=start,
                end_frame=end,
                start_time=float(timestamps[start]),
                end_time=float(timestamps[end] + durations[end]),
                duration_seconds=round(duration, 6),
                confidence=round(float(np.mean(episode_confidences)) if episode_confidences else 0.0, 6),
                holding_state=HoldingState.LIKELY_HOLDING,
                known_object_class=object_class,
                known_object_confidence=(
                    round(float(np.mean(object_confidences)), 6)
                    if object_confidences
                    else None
                ),
            )
        )

    output: list[HoldingFrame] = []
    for index, raw in enumerate(raw_frames):
        state = HoldingState.LIKELY_HOLDING if confirmed[index] else raw.state
        output.append(
            HoldingFrame(
                state=state,
                confidence=raw.confidence,
                grip=raw.grip,
                object_class=raw.object_class,
                object_confidence=raw.object_confidence,
                object_index=raw.object_index,
                object_proximity_ratio=raw.object_proximity_ratio,
            )
        )
    valid_seconds = sum(duration for duration, grip in zip(durations, grips) if grip.valid)
    likely_seconds = sum(duration for duration, value in zip(durations, confirmed) if value)
    static_seconds = sum(
        duration
        for duration, value, grip in zip(durations, confirmed, grips)
        if value and grip.grip_stability >= 0.72
    )
    summary = HoldingSummary(
        side=side,
        valid_observation_seconds=round(valid_seconds, 6),
        likely_holding_seconds=round(likely_seconds, 6),
        static_holding_seconds=round(static_seconds, 6),
        longest_holding_seconds=max((episode.duration_seconds for episode in episodes), default=0.0),
        holding_episode_count=len(episodes),
        episodes=tuple(episodes),
        external_load_known=False,
    )
    return output, summary


def analyze_bimanual_holding(
    left: list[HoldingFrame],
    right: list[HoldingFrame],
    timestamps: list[float],
    *,
    fps: float,
) -> dict[str, object]:
    if len(left) != len(right) or len(left) != len(timestamps):
        raise ValueError("Klatki lewej, prawej dłoni i timestampy muszą mieć równą długość.")
    durations = _frame_durations(timestamps, fps)
    flags: list[bool] = []
    association_modes: list[str | None] = []
    for left_item, right_item in zip(left, right):
        both_holding = (
            left_item.state == HoldingState.LIKELY_HOLDING
            and right_item.state == HoldingState.LIKELY_HOLDING
        )
        same_known_object = (
            left_item.object_index is not None
            and left_item.object_index == right_item.object_index
        )
        unknown_object_proximity = False
        if (
            left_item.object_index is None
            and right_item.object_index is None
            and left_item.grip.palm_center is not None
            and right_item.grip.palm_center is not None
            and left_item.grip.palm_scale is not None
            and right_item.grip.palm_scale is not None
        ):
            palm_distance = float(np.linalg.norm(
                np.asarray(left_item.grip.palm_center)
                - np.asarray(right_item.grip.palm_center)
            ))
            mean_scale = max(
                1e-6,
                (left_item.grip.palm_scale + right_item.grip.palm_scale) / 2.0,
            )
            unknown_object_proximity = palm_distance / mean_scale <= 4.0
        flag = both_holding and (same_known_object or unknown_object_proximity)
        flags.append(flag)
        association_modes.append(
            "same_detected_object"
            if flag and same_known_object
            else "unknown_object_hand_proximity"
            if flag and unknown_object_proximity
            else None
        )
    for index, flag in enumerate(flags):
        if flag:
            left[index] = replace(left[index], bimanual_candidate=True)
            right[index] = replace(right[index], bimanual_candidate=True)
    episode_count = sum(1 for index, value in enumerate(flags) if value and (index == 0 or not flags[index - 1]))
    seconds = sum(duration for duration, value in zip(durations, flags) if value)
    return {
        "likely_holding_seconds": round(seconds, 6),
        "episode_count": episode_count,
        "frame_flags": flags,
        "association_modes": association_modes,
    }


def serialize_holding_frame(frame: HoldingFrame) -> dict[str, object]:
    return {
        "state": frame.state.value,
        "confidence": round(frame.confidence, 6),
        "grip_state": frame.grip.grip_state.value,
        "grip_confidence": round(frame.grip.grip_confidence, 6),
        "hand_closure_ratio": _rounded(frame.grip.closure_ratio),
        "thumb_index_distance_ratio": _rounded(frame.grip.thumb_index_distance_ratio),
        "thumb_middle_distance_ratio": _rounded(frame.grip.thumb_middle_distance_ratio),
        "finger_flexion": _rounded(frame.grip.finger_flexion),
        "grip_stability": round(frame.grip.grip_stability, 6),
        "object_class": frame.object_class,
        "object_confidence": _rounded(frame.object_confidence),
        "object_proximity_ratio": _rounded(frame.object_proximity_ratio),
        "bimanual_candidate": frame.bimanual_candidate,
        "external_load_known": False,
    }


def serialize_holding_summary(summary: HoldingSummary) -> dict[str, object]:
    holding_ratio = (
        summary.likely_holding_seconds / summary.valid_observation_seconds
        if summary.valid_observation_seconds > 0.0
        else None
    )
    return {
        "side": summary.side,
        "valid_observation_seconds": summary.valid_observation_seconds,
        "likely_holding_seconds": summary.likely_holding_seconds,
        "static_holding_seconds": summary.static_holding_seconds,
        "longest_holding_seconds": summary.longest_holding_seconds,
        "holding_episode_count": summary.holding_episode_count,
        "holding_ratio": round(holding_ratio, 6) if holding_ratio is not None else None,
        "external_load_known": summary.external_load_known,
        "episodes": [
            {
                "start_frame": episode.start_frame,
                "end_frame": episode.end_frame,
                "start_time": episode.start_time,
                "end_time": episode.end_time,
                "duration_seconds": episode.duration_seconds,
                "confidence": episode.confidence,
                "holding_state": episode.holding_state.value,
                "known_object_class": episode.known_object_class,
                "known_object_confidence": episode.known_object_confidence,
            }
            for episode in summary.episodes
        ],
    }


def _unknown_grip() -> GripFeatures:
    return GripFeatures(
        False,
        0.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.0,
        GripState.UNKNOWN,
        0.0,
        None,
        None,
    )


def _flexion(first: np.ndarray, middle: np.ndarray, last: np.ndarray) -> float:
    first_vector = first - middle
    second_vector = last - middle
    denominator = float(np.linalg.norm(first_vector) * np.linalg.norm(second_vector))
    if denominator <= 1e-8:
        return 0.0
    angle = math.degrees(
        math.acos(float(np.clip(np.dot(first_vector, second_vector) / denominator, -1.0, 1.0)))
    )
    return float(np.clip((180.0 - angle) / 180.0, 0.0, 1.0))


def _nearest_object(
    grip: GripFeatures,
    detections: list[ObjectDetection],
    config: HoldingConfig,
) -> tuple[ObjectDetection, float] | None:
    if not grip.valid or grip.palm_center is None or grip.palm_scale is None:
        return None
    palm = np.asarray(grip.palm_center, dtype=float)
    best: tuple[ObjectDetection, float] | None = None
    for fallback_index, detection in enumerate(detections):
        x1, y1, x2, y2 = detection.bbox_xyxy
        nearest = np.asarray(
            [np.clip(palm[0], x1, x2), np.clip(palm[1], y1, y2)], dtype=float
        )
        ratio = float(np.linalg.norm(nearest - palm) / max(grip.palm_scale, 1e-6))
        normalized = ObjectDetection(
            detection.bbox_xyxy,
            detection.class_id,
            detection.class_name,
            detection.confidence,
            detection.detection_index if detection.detection_index is not None else fallback_index,
        )
        if ratio <= config.object_maximum_distance_palm_ratio and (best is None or ratio < best[1]):
            best = (normalized, ratio)
    return best


def _raw_holding_frame(
    grip: GripFeatures,
    object_match: tuple[ObjectDetection, float] | None,
    config: HoldingConfig,
) -> HoldingFrame:
    if not config.enabled:
        return HoldingFrame(HoldingState.UNKNOWN, 0.0, grip, None, None, None, None)
    if not grip.valid or grip.quality < config.minimum_hand_quality or grip.closure_ratio is None:
        return HoldingFrame(HoldingState.UNKNOWN, 0.0, grip, None, None, None, None)
    object_detection = object_match[0] if object_match else None
    proximity = object_match[1] if object_match else None
    object_evidence = (
        max(0.0, 1.0 - proximity / config.object_maximum_distance_palm_ratio)
        if proximity is not None
        else 0.0
    )
    closure_evidence = grip.closure_ratio
    if grip.grip_state == GripState.PINCH:
        closure_evidence = max(closure_evidence, 0.58)
    evidence = float(
        np.clip(
            0.56 * closure_evidence
            + 0.20 * grip.grip_stability
            + 0.14 * grip.grip_confidence
            + 0.10 * object_evidence,
            0.0,
            1.0,
        )
    )
    if grip.grip_state == GripState.OPEN and object_evidence <= 0.0:
        state = HoldingState.NOT_HOLDING
        confidence = max(grip.grip_confidence, 1.0 - evidence)
    elif evidence >= config.possible_evidence_threshold:
        state = HoldingState.POSSIBLE_HOLDING
        confidence = evidence
    else:
        state = HoldingState.NOT_HOLDING
        confidence = 1.0 - evidence
    return HoldingFrame(
        state=state,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        grip=grip,
        object_class=object_detection.class_name if object_detection else None,
        object_confidence=object_detection.confidence if object_detection else None,
        object_index=object_detection.detection_index if object_detection else None,
        object_proximity_ratio=proximity,
    )


def _frame_durations(timestamps: list[float], fps: float) -> list[float]:
    if not timestamps:
        return []
    fallback = 1.0 / fps if math.isfinite(fps) and fps > 0.0 else 0.0
    durations: list[float] = []
    positive_deltas = [
        timestamps[index + 1] - timestamps[index]
        for index in range(len(timestamps) - 1)
        if math.isfinite(timestamps[index + 1] - timestamps[index])
        and timestamps[index + 1] > timestamps[index]
    ]
    # The final frame represents the last observed sampling interval.  Reusing
    # that interval preserves variable-rate timing without falling back to an
    # unrelated median or silently assuming constant FPS.
    last_duration = float(positive_deltas[-1]) if positive_deltas else fallback
    for index in range(len(timestamps)):
        if index + 1 < len(timestamps):
            delta = timestamps[index + 1] - timestamps[index]
            durations.append(delta if math.isfinite(delta) and delta > 0.0 else fallback)
        else:
            durations.append(last_duration)
    return durations


def _confirmed_ranges(
    candidates: list[bool],
    unknown: list[bool],
    durations: list[float],
    config: HoldingConfig,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(candidates):
        if not candidates[index]:
            index += 1
            continue
        start = index
        last_candidate = index
        candidate_seconds = 0.0
        unknown_gap_seconds = 0.0
        release_gap_seconds = 0.0
        while index < len(candidates):
            if candidates[index]:
                candidate_seconds += durations[index]
                last_candidate = index
                unknown_gap_seconds = 0.0
                release_gap_seconds = 0.0
                index += 1
                continue
            if (
                unknown[index]
                and release_gap_seconds == 0.0
                and unknown_gap_seconds + durations[index]
                <= config.maximum_unknown_gap_seconds
            ):
                unknown_gap_seconds += durations[index]
                index += 1
                continue
            if not unknown[index]:
                release_gap_seconds += durations[index]
                unknown_gap_seconds = 0.0
                if release_gap_seconds <= config.release_confirmation_seconds:
                    index += 1
                    continue
            break
        if candidate_seconds >= config.minimum_confirmation_seconds:
            # A short internal UNKNOWN/open gap is bridged only when holding
            # resumes.  A trailing release gap is never counted as holding.
            ranges.append((start, last_candidate))
        if index == start:
            index += 1
    return ranges


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None

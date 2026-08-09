"""Holding V2 event inference with object tracks, motion and hysteresis."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np

from .hand_graph import GripStateV2, HandGraphFrame, HandOcclusion


class HoldingStateV2(StrEnum):
    NOT_HOLDING = "NOT_HOLDING"
    POSSIBLE_HOLDING = "POSSIBLE_HOLDING"
    LIKELY_HOLDING = "LIKELY_HOLDING"
    LIKELY_HOLDING_UNKNOWN_OBJECT = "LIKELY_HOLDING_UNKNOWN_OBJECT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HoldingV2Config:
    enabled: bool = True
    minimum_hand_quality: float = 0.45
    enter_threshold: float = 0.68
    keep_threshold: float = 0.52
    exit_threshold: float = 0.36
    minimum_confirmation_seconds: float = 0.40
    release_confirmation_seconds: float = 0.25
    maximum_unknown_gap_seconds: float = 0.20
    episode_merge_gap_seconds: float = 0.25
    minimum_static_seconds: float = 0.75
    static_velocity_palm_ratio_per_second: float = 0.55

    def validate(self) -> None:
        ratios = (
            self.minimum_hand_quality,
            self.enter_threshold,
            self.keep_threshold,
            self.exit_threshold,
        )
        if any(not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("holding thresholds must be in range 0..1")
        if not self.enter_threshold > self.keep_threshold > self.exit_threshold:
            raise ValueError("holding thresholds must satisfy enter > keep > exit")
        durations = (
            self.minimum_confirmation_seconds,
            self.release_confirmation_seconds,
            self.maximum_unknown_gap_seconds,
            self.episode_merge_gap_seconds,
            self.minimum_static_seconds,
        )
        if any(value < 0.0 for value in durations):
            raise ValueError("holding durations cannot be negative")
        if self.static_velocity_palm_ratio_per_second <= 0.0:
            raise ValueError("static velocity threshold must be positive")


@dataclass(frozen=True)
class HoldingEvidence:
    grip_evidence: float
    object_evidence: float
    motion_evidence: float
    temporal_evidence: float
    occlusion_evidence: float
    quality_penalty: float
    weighted_score: float
    release_evidence: float


@dataclass(frozen=True)
class HoldingFrameV2:
    state: HoldingStateV2
    confidence: float
    evidence: HoldingEvidence
    hand: HandGraphFrame
    object_track_id: int | None
    object_class: str | None
    object_confidence: float | None
    object_proximity_ratio: float | None
    common_motion_score: float
    static_candidate: bool
    bimanual_candidate: bool = False


@dataclass(frozen=True)
class HoldingEpisodeV2:
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    duration_seconds: float
    confidence: float
    holding_state: HoldingStateV2
    object_track_id: int | None
    object_class: str | None
    object_confidence: float | None
    merged_gap_seconds: float


@dataclass(frozen=True)
class HoldingSummaryV2:
    side: str
    observed_time_seconds: float
    likely_holding_seconds: float
    uncertain_seconds: float
    static_holding_seconds: float
    longest_episode_seconds: float
    episode_count: int
    mean_hold_duration_seconds: float | None
    median_hold_duration_seconds: float | None
    max_hold_duration_seconds: float | None
    grasp_release_cycles: int
    pinch_cycles: int
    grasp_frequency_per_minute: float | None
    episodes: tuple[HoldingEpisodeV2, ...]
    external_load_known: bool = False


def analyze_holding_v2(
    side: str,
    hands: list[HandGraphFrame],
    timestamps: list[float],
    *,
    fps: float,
    config: HoldingV2Config,
) -> tuple[list[HoldingFrameV2], HoldingSummaryV2]:
    if len(hands) != len(timestamps):
        raise ValueError("hand frames and timestamps must have equal length")
    config.validate()
    durations = frame_durations(timestamps, fps)
    raw_evidence: list[HoldingEvidence] = []
    hand_velocities = _hand_velocities(hands, timestamps)
    persistence = 0.0
    for index, (hand, duration) in enumerate(zip(hands, durations)):
        base = _base_evidence(hand, hand_velocities[index])
        candidate = base[0] >= config.keep_threshold and hand.visible
        persistence = persistence + duration if candidate else 0.0
        temporal = float(np.clip(persistence / max(config.minimum_confirmation_seconds, 1e-6), 0.0, 1.0))
        raw_evidence.append(_compose_evidence(hand, base, temporal))

    states: list[HoldingStateV2] = []
    active = False
    active_unknown_object = False
    pending = 0.0
    release = 0.0
    unknown_gap = 0.0
    for evidence, hand, duration in zip(raw_evidence, hands, durations):
        if not config.enabled or not hand.visible or hand.quality < config.minimum_hand_quality:
            if active and unknown_gap + duration <= config.maximum_unknown_gap_seconds:
                unknown_gap += duration
                states.append(
                    HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT
                    if active_unknown_object
                    else HoldingStateV2.LIKELY_HOLDING
                )
            else:
                states.append(HoldingStateV2.UNKNOWN)
                if unknown_gap + duration > config.maximum_unknown_gap_seconds:
                    active = False
                    pending = 0.0
            continue
        unknown_gap = 0.0
        has_object = hand.nearest_object_track_id is not None
        unknown_candidate = (
            not has_object
            and evidence.grip_evidence >= 0.72
            and hand.grip.stability >= 0.65
            and evidence.temporal_evidence >= 0.80
        )
        enter_candidate = evidence.weighted_score >= config.enter_threshold or unknown_candidate
        keep_candidate = evidence.weighted_score >= config.keep_threshold or unknown_candidate
        if not active:
            pending = pending + duration if enter_candidate else 0.0
            if pending >= config.minimum_confirmation_seconds:
                active = True
                active_unknown_object = not has_object
                release = 0.0
                states.append(
                    HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT
                    if active_unknown_object
                    else HoldingStateV2.LIKELY_HOLDING
                )
            elif evidence.weighted_score >= config.keep_threshold:
                states.append(HoldingStateV2.POSSIBLE_HOLDING)
            else:
                states.append(HoldingStateV2.NOT_HOLDING)
            continue
        if keep_candidate and evidence.release_evidence < 0.70:
            release = 0.0
            if has_object:
                active_unknown_object = False
            states.append(
                HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT
                if active_unknown_object
                else HoldingStateV2.LIKELY_HOLDING
            )
            continue
        if evidence.weighted_score <= config.exit_threshold or evidence.release_evidence >= 0.70:
            release += duration
        else:
            release = 0.0
        if release >= config.release_confirmation_seconds:
            active = False
            active_unknown_object = False
            pending = 0.0
            states.append(HoldingStateV2.NOT_HOLDING)
        else:
            states.append(
                HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT
                if active_unknown_object
                else HoldingStateV2.LIKELY_HOLDING
            )

    frames = [
        HoldingFrameV2(
            state=state,
            confidence=evidence.weighted_score,
            evidence=evidence,
            hand=hand,
            object_track_id=hand.nearest_object_track_id,
            object_class=hand.nearest_object_class,
            object_confidence=hand.nearest_object_confidence,
            object_proximity_ratio=hand.nearest_object_distance_ratio,
            common_motion_score=evidence.motion_evidence,
            static_candidate=(
                state in {
                    HoldingStateV2.LIKELY_HOLDING,
                    HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT,
                }
                and _normalized_speed(hand_velocities[index], hand) <= config.static_velocity_palm_ratio_per_second
            ),
        )
        for index, (state, evidence, hand) in enumerate(zip(states, raw_evidence, hands))
    ]
    episodes = _build_episodes(frames, timestamps, durations, config)
    frames = _mark_confirmed_static(frames, durations, config.minimum_static_seconds)
    likely_states = {
        HoldingStateV2.LIKELY_HOLDING,
        HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT,
    }
    observed = sum(duration for duration, hand in zip(durations, hands) if hand.visible)
    likely = sum(duration for duration, frame in zip(durations, frames) if frame.state in likely_states)
    uncertain = sum(duration for duration, frame in zip(durations, frames) if frame.state in {HoldingStateV2.UNKNOWN, HoldingStateV2.POSSIBLE_HOLDING})
    static = sum(duration for duration, frame in zip(durations, frames) if frame.static_candidate and frame.state in likely_states)
    episode_durations = [episode.duration_seconds for episode in episodes]
    grasp_cycles, pinch_cycles = _activity_cycles(hands, states)
    minutes = observed / 60.0
    summary = HoldingSummaryV2(
        side=side,
        observed_time_seconds=round(observed, 6),
        likely_holding_seconds=round(likely, 6),
        uncertain_seconds=round(uncertain, 6),
        static_holding_seconds=round(static, 6),
        longest_episode_seconds=round(max(episode_durations, default=0.0), 6),
        episode_count=len(episodes),
        mean_hold_duration_seconds=round(float(np.mean(episode_durations)), 6) if episode_durations else None,
        median_hold_duration_seconds=round(float(np.median(episode_durations)), 6) if episode_durations else None,
        max_hold_duration_seconds=round(max(episode_durations), 6) if episode_durations else None,
        grasp_release_cycles=grasp_cycles,
        pinch_cycles=pinch_cycles,
        grasp_frequency_per_minute=round(grasp_cycles / minutes, 6) if minutes > 0.0 else None,
        episodes=tuple(episodes),
    )
    return frames, summary


def analyze_bimanual_holding_v2(
    left: list[HoldingFrameV2],
    right: list[HoldingFrameV2],
    timestamps: list[float],
    *,
    fps: float,
    minimum_confirmation_seconds: float = 0.40,
) -> dict[str, object]:
    if not (len(left) == len(right) == len(timestamps)):
        raise ValueError("left, right and timestamps must have equal length")
    durations = frame_durations(timestamps, fps)
    likely = {
        HoldingStateV2.LIKELY_HOLDING,
        HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT,
    }
    raw: list[bool] = []
    modes: list[str | None] = []
    left_velocities = _hand_velocities([item.hand for item in left], timestamps)
    right_velocities = _hand_velocities([item.hand for item in right], timestamps)
    previous_distance: float | None = None
    for index, (left_frame, right_frame) in enumerate(zip(left, right)):
        both = left_frame.state in likely and right_frame.state in likely
        same_object = (
            left_frame.object_track_id is not None
            and left_frame.object_track_id == right_frame.object_track_id
        )
        unknown_geometry = False
        if both and not same_object:
            left_palm = left_frame.hand.palm
            right_palm = right_frame.hand.palm
            if left_palm.center and right_palm.center and left_palm.scale and right_palm.scale:
                distance = float(np.linalg.norm(np.asarray(left_palm.center) - np.asarray(right_palm.center)))
                scale = (left_palm.scale + right_palm.scale) / 2.0
                grip_strength = min(left_frame.evidence.grip_evidence, right_frame.evidence.grip_evidence)
                relative_velocity = float(np.linalg.norm(left_velocities[index] - right_velocities[index]))
                velocity_scale = max(
                    float(np.linalg.norm(left_velocities[index])),
                    float(np.linalg.norm(right_velocities[index])),
                    scale * 4.0,
                )
                common_hand_motion = float(np.clip(1.0 - relative_velocity / velocity_scale, 0.0, 1.0))
                distance_stability = (
                    1.0
                    if previous_distance is None
                    else float(np.clip(1.0 - abs(distance - previous_distance) / max(scale, 1e-6), 0.0, 1.0))
                )
                previous_distance = distance
                unknown_geometry = (
                    distance / max(scale, 1e-6) <= 4.0
                    and grip_strength >= 0.72
                    and common_hand_motion >= 0.65
                    and distance_stability >= 0.60
                )
        raw.append(bool(both and (same_object or unknown_geometry)))
        modes.append("same_object_track" if same_object and both else "unknown_object_shared_motion" if unknown_geometry else None)
    confirmed = _confirm_boolean_runs(raw, durations, minimum_confirmation_seconds)
    for index, value in enumerate(confirmed):
        if value:
            left[index] = replace(left[index], bimanual_candidate=True)
            right[index] = replace(right[index], bimanual_candidate=True)
    return {
        "likely_holding_seconds": round(sum(duration for duration, flag in zip(durations, confirmed) if flag), 6),
        "episode_count": sum(flag and (index == 0 or not confirmed[index - 1]) for index, flag in enumerate(confirmed)),
        "frame_flags": confirmed,
        "association_modes": modes,
    }


def serialize_holding_frame_v2(frame: HoldingFrameV2) -> dict[str, object]:
    return {
        "state": frame.state.value,
        "confidence": round(frame.confidence, 6),
        "grip_state": frame.hand.grip.state.value,
        "grip_confidence": round(frame.hand.grip.confidence, 6),
        "hand_closure_ratio": _rounded(frame.hand.grip.closure_ratio),
        "grip_aperture_ratio": _rounded(frame.hand.grip.aperture_ratio),
        "thumb_index_distance_ratio": _rounded(frame.hand.grip.thumb_index_distance_ratio),
        "thumb_middle_distance_ratio": _rounded(frame.hand.grip.thumb_middle_distance_ratio),
        "finger_flexion": {name: _rounded(value) for name, value in frame.hand.grip.finger_flexion.items()},
        "grip_stability": round(frame.hand.grip.stability, 6),
        "object_track_id": frame.object_track_id,
        "object_class": frame.object_class,
        "object_confidence": _rounded(frame.object_confidence),
        "object_proximity_ratio": _rounded(frame.object_proximity_ratio),
        "common_motion_score": round(frame.common_motion_score, 6),
        "evidence": {
            "grip": round(frame.evidence.grip_evidence, 6),
            "object": round(frame.evidence.object_evidence, 6),
            "motion": round(frame.evidence.motion_evidence, 6),
            "temporal": round(frame.evidence.temporal_evidence, 6),
            "occlusion": round(frame.evidence.occlusion_evidence, 6),
            "quality_penalty": round(frame.evidence.quality_penalty, 6),
            "weighted_score": round(frame.evidence.weighted_score, 6),
            "release": round(frame.evidence.release_evidence, 6),
        },
        "static_candidate": frame.static_candidate,
        "bimanual_candidate": frame.bimanual_candidate,
        "external_load_known": False,
    }


def serialize_holding_summary_v2(summary: HoldingSummaryV2) -> dict[str, object]:
    ratio = (
        summary.likely_holding_seconds / summary.observed_time_seconds
        if summary.observed_time_seconds > 0.0
        else None
    )
    return {
        "side": summary.side,
        "valid_observation_seconds": summary.observed_time_seconds,
        "observed_time_seconds": summary.observed_time_seconds,
        "likely_holding_seconds": summary.likely_holding_seconds,
        "holding_percentage_of_valid_observation": round(ratio * 100.0, 6) if ratio is not None else None,
        "holding_ratio": round(ratio, 6) if ratio is not None else None,
        "uncertain_seconds": summary.uncertain_seconds,
        "static_holding_seconds": summary.static_holding_seconds,
        "longest_holding_seconds": summary.longest_episode_seconds,
        "holding_episode_count": summary.episode_count,
        "mean_hold_duration_seconds": summary.mean_hold_duration_seconds,
        "median_hold_duration_seconds": summary.median_hold_duration_seconds,
        "max_hold_duration_seconds": summary.max_hold_duration_seconds,
        "grasp_release_cycles": summary.grasp_release_cycles,
        "pinch_cycles": summary.pinch_cycles,
        "grasp_frequency_per_minute": summary.grasp_frequency_per_minute,
        "external_load_known": False,
        "episodes": [
            {
                "start_frame": episode.start_frame,
                "end_frame": episode.end_frame,
                "start_time": episode.start_time,
                "end_time": episode.end_time,
                "duration_seconds": episode.duration_seconds,
                "confidence": episode.confidence,
                "holding_state": episode.holding_state.value,
                "object_track_id": episode.object_track_id,
                "known_object_class": episode.object_class,
                "known_object_confidence": episode.object_confidence,
                "merged_gap_seconds": episode.merged_gap_seconds,
            }
            for episode in summary.episodes
        ],
    }


def frame_durations(timestamps: list[float], fps: float) -> list[float]:
    if not timestamps:
        return []
    fallback = 1.0 / fps if math.isfinite(fps) and fps > 0.0 else 0.0
    positive = [
        timestamps[index + 1] - timestamps[index]
        for index in range(len(timestamps) - 1)
        if math.isfinite(timestamps[index + 1] - timestamps[index])
        and timestamps[index + 1] > timestamps[index]
    ]
    last = float(positive[-1]) if positive else fallback
    return [
        (
            timestamps[index + 1] - timestamps[index]
            if index + 1 < len(timestamps)
            and math.isfinite(timestamps[index + 1] - timestamps[index])
            and timestamps[index + 1] > timestamps[index]
            else last if index == len(timestamps) - 1 else fallback
        )
        for index in range(len(timestamps))
    ]


def _base_evidence(hand: HandGraphFrame, hand_velocity: np.ndarray) -> tuple[float, float, float, float, float]:
    grip = {
        GripStateV2.OPEN: 0.0,
        GripStateV2.RELAXED: 0.18,
        GripStateV2.PARTIALLY_CLOSED: 0.50,
        GripStateV2.POWER_GRIP_CANDIDATE: 0.84,
        GripStateV2.PRECISION_PINCH_CANDIDATE: 0.82,
        GripStateV2.CLOSED: 0.76,
        GripStateV2.UNKNOWN: 0.0,
    }[hand.grip.state]
    object_evidence = (
        float(np.clip(1.0 - hand.nearest_object_distance_ratio / 2.25, 0.0, 1.0))
        if hand.nearest_object_distance_ratio is not None
        else 0.0
    )
    motion = 0.0
    if hand.nearest_object_velocity is not None and hand.palm.scale is not None:
        object_velocity = np.asarray(hand.nearest_object_velocity, dtype=float)
        difference = float(np.linalg.norm(hand_velocity - object_velocity))
        scale = max(
            float(np.linalg.norm(hand_velocity)),
            float(np.linalg.norm(object_velocity)),
            hand.palm.scale * 4.0,
        )
        motion = float(np.clip(1.0 - difference / scale, 0.0, 1.0))
    occlusion = (
        0.78
        if hand.occlusion_state == HandOcclusion.OCCLUDED_BY_OBJECT
        else 0.28
        if hand.occlusion_state == HandOcclusion.OCCLUDED_BY_BODY
        else 0.0
    )
    quality_penalty = 1.0 - float(np.clip(hand.quality, 0.0, 1.0))
    return grip, object_evidence, motion, occlusion, quality_penalty


def _compose_evidence(
    hand: HandGraphFrame,
    base: tuple[float, float, float, float, float],
    temporal: float,
) -> HoldingEvidence:
    grip, object_value, motion, occlusion, penalty = base
    weighted = float(
        np.clip(
            0.34 * grip
            + 0.20 * object_value
            + 0.16 * motion
            + 0.15 * temporal
            + 0.15 * occlusion
            - 0.28 * penalty,
            0.0,
            1.0,
        )
    )
    aperture = hand.grip.aperture_ratio
    release = float(
        np.clip(
            0.48 * (1.0 if hand.grip.state == GripStateV2.OPEN else 0.0)
            + 0.27 * (min(1.0, aperture / 1.1) if aperture is not None else 0.0)
            + 0.15 * (1.0 - object_value)
            + 0.10 * (1.0 - motion),
            0.0,
            1.0,
        )
    )
    return HoldingEvidence(grip, object_value, motion, temporal, occlusion, penalty, weighted, release)


def _hand_velocities(hands: list[HandGraphFrame], timestamps: list[float]) -> list[np.ndarray]:
    output = [np.zeros((2,), dtype=np.float32) for _ in hands]
    for index in range(1, len(hands)):
        current, previous = hands[index].palm, hands[index - 1].palm
        delta = timestamps[index] - timestamps[index - 1]
        if not current.center or not previous.center or not current.scale or delta <= 1e-6:
            continue
        output[index] = (
            (np.asarray(current.center, dtype=np.float32) - np.asarray(previous.center, dtype=np.float32))
            / delta
        )
    return output


def _normalized_speed(velocity: np.ndarray, hand: HandGraphFrame) -> float:
    if hand.palm.scale is None:
        return math.inf
    return float(np.linalg.norm(velocity) / max(hand.palm.scale, 1e-6))


def _build_episodes(
    frames: list[HoldingFrameV2],
    timestamps: list[float],
    durations: list[float],
    config: HoldingV2Config,
) -> list[HoldingEpisodeV2]:
    likely = {HoldingStateV2.LIKELY_HOLDING, HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT}
    ranges: list[tuple[int, int, float]] = []
    index = 0
    while index < len(frames):
        if frames[index].state not in likely:
            index += 1
            continue
        start = index
        end = index
        merged_gap = 0.0
        gap = 0.0
        index += 1
        while index < len(frames):
            if frames[index].state in likely:
                end = index
                merged_gap += gap
                gap = 0.0
                index += 1
                continue
            gap += durations[index]
            if gap <= config.episode_merge_gap_seconds:
                index += 1
                continue
            break
        ranges.append((start, end, merged_gap))
    output: list[HoldingEpisodeV2] = []
    for start, end, merged_gap in ranges:
        selected = frames[start : end + 1]
        confidences = [item.confidence for item in selected if item.state in likely]
        tracks = [item.object_track_id for item in selected if item.object_track_id is not None]
        track = max(set(tracks), key=tracks.count) if tracks else None
        classes = [item.object_class for item in selected if item.object_class]
        object_class = max(set(classes), key=classes.count) if classes else None
        state = (
            HoldingStateV2.LIKELY_HOLDING
            if track is not None
            else HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT
        )
        duration = sum(durations[start : end + 1])
        output.append(
            HoldingEpisodeV2(
                start,
                end,
                float(timestamps[start]),
                float(timestamps[end] + durations[end]),
                round(duration, 6),
                round(float(np.mean(confidences)) if confidences else 0.0, 6),
                state,
                track,
                object_class,
                None,
                round(merged_gap, 6),
            )
        )
    return output


def _mark_confirmed_static(
    frames: list[HoldingFrameV2],
    durations: list[float],
    minimum_seconds: float,
) -> list[HoldingFrameV2]:
    output = list(frames)
    start: int | None = None
    duration = 0.0
    for index, (frame, frame_duration) in enumerate(zip(frames, durations)):
        if frame.static_candidate:
            start = index if start is None else start
            duration += frame_duration
        else:
            if start is not None and duration < minimum_seconds:
                for selected in range(start, index):
                    output[selected] = replace(output[selected], static_candidate=False)
            start = None
            duration = 0.0
    if start is not None and duration < minimum_seconds:
        for selected in range(start, len(frames)):
            output[selected] = replace(output[selected], static_candidate=False)
    return output


def _activity_cycles(hands: list[HandGraphFrame], states: list[HoldingStateV2]) -> tuple[int, int]:
    closed_states = {
        GripStateV2.PARTIALLY_CLOSED,
        GripStateV2.POWER_GRIP_CANDIDATE,
        GripStateV2.PRECISION_PINCH_CANDIDATE,
        GripStateV2.CLOSED,
    }
    grasp_cycles = 0
    pinch_cycles = 0
    was_closed = False
    was_pinch = False
    for hand, state in zip(hands, states):
        closed = hand.grip.state in closed_states and state != HoldingStateV2.UNKNOWN
        pinch = hand.grip.state == GripStateV2.PRECISION_PINCH_CANDIDATE and state != HoldingStateV2.UNKNOWN
        if was_closed and not closed:
            grasp_cycles += 1
        if was_pinch and not pinch:
            pinch_cycles += 1
        was_closed = closed
        was_pinch = pinch
    return grasp_cycles, pinch_cycles


def _confirm_boolean_runs(values: list[bool], durations: list[float], minimum: float) -> list[bool]:
    output = [False] * len(values)
    index = 0
    while index < len(values):
        if not values[index]:
            index += 1
            continue
        start = index
        duration = 0.0
        while index < len(values) and values[index]:
            duration += durations[index]
            index += 1
        if duration >= minimum:
            output[start:index] = [True] * (index - start)
    return output


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None

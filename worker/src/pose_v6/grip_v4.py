"""Temporal Grip V4 built on validated MediaPipe hand geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

import numpy as np

try:
    from ..pose_v4.hand_graph import FingerVisibility, GripStateV2, HandGraphFrame
except ImportError:  # pragma: no cover - standalone worker import mode
    from pose_v4.hand_graph import FingerVisibility, GripStateV2, HandGraphFrame

from .temporal_reconstruction import TemporalFrame


class GripStateV4(StrEnum):
    OPEN = "OPEN"
    RELAXED = "RELAXED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    POWER_GRIP = "POWER_GRIP"
    PRECISION_PINCH = "PRECISION_PINCH"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


_CANDIDATE_MAP = {
    GripStateV2.OPEN: GripStateV4.OPEN,
    GripStateV2.RELAXED: GripStateV4.RELAXED,
    GripStateV2.PARTIALLY_CLOSED: GripStateV4.PARTIALLY_CLOSED,
    GripStateV2.POWER_GRIP_CANDIDATE: GripStateV4.POWER_GRIP,
    GripStateV2.PRECISION_PINCH_CANDIDATE: GripStateV4.PRECISION_PINCH,
    GripStateV2.CLOSED: GripStateV4.CLOSED,
    GripStateV2.UNKNOWN: GripStateV4.UNKNOWN,
}
_ACTIVE_GRIPS = {GripStateV4.POWER_GRIP, GripStateV4.PRECISION_PINCH, GripStateV4.CLOSED}


@dataclass(frozen=True)
class GripFrameV4:
    state: GripStateV4
    confidence: float
    candidate_state: GripStateV4
    palm_quality: float
    finger_quality: float
    object_evidence: float
    temporal_stability: float
    occluded: bool
    wrist_alignment: dict[str, object]
    features: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "confidence": round(self.confidence, 6),
            "candidate_state": self.candidate_state.value,
            "palm_quality": round(self.palm_quality, 6),
            "finger_quality": round(self.finger_quality, 6),
            "object_evidence": round(self.object_evidence, 6),
            "temporal_stability": round(self.temporal_stability, 6),
            "occluded": self.occluded,
            "wrist_alignment": self.wrist_alignment,
            "features": self.features,
            "force_estimation_available": False,
            "mass_estimation_available": False,
        }


@dataclass(frozen=True)
class GripSequenceV4:
    frames: list[GripFrameV4]
    summary: dict[str, object]


def analyze_grip_v4(
    side: str,
    frames: Sequence[HandGraphFrame],
    timestamps: Sequence[float],
    temporal_frames: Sequence[TemporalFrame],
    *,
    confirmation_seconds: float = 0.12,
    release_seconds: float = 0.12,
    maximum_unknown_gap_seconds: float = 0.25,
    fallback_fps: float = 30.0,
) -> GripSequenceV4:
    """Apply confirmation/release hysteresis without turning occlusion into OPEN."""

    if side not in {"left", "right"}:
        raise ValueError("side must be left or right")
    if not (len(frames) == len(timestamps) == len(temporal_frames)):
        raise ValueError("grip sequence inputs must have equal lengths")
    if min(confirmation_seconds, release_seconds, maximum_unknown_gap_seconds) < 0.0:
        raise ValueError("grip temporal thresholds cannot be negative")
    durations = _durations(timestamps, fallback_fps)
    output: list[GripFrameV4] = []
    confirmed = GripStateV4.UNKNOWN
    candidate = GripStateV4.UNKNOWN
    candidate_seconds = 0.0
    unknown_seconds = 0.0
    stable_seconds = 0.0

    for index, (graph, duration) in enumerate(zip(frames, durations)):
        raw_candidate = _CANDIDATE_MAP[graph.grip.state] if graph.visible else GripStateV4.UNKNOWN
        palm_quality = float(np.clip(graph.palm_quality, 0.0, 1.0))
        finger_values = [value.quality for value in graph.fingers.values() if value.state != FingerVisibility.LOST]
        finger_quality = float(np.mean(finger_values)) if finger_values else 0.0
        object_evidence = _object_evidence(graph)
        trustworthy = graph.visible and palm_quality >= 0.45 and finger_quality >= 0.35
        if not trustworthy:
            raw_candidate = GripStateV4.UNKNOWN

        if raw_candidate == GripStateV4.UNKNOWN:
            unknown_seconds += duration
            candidate = GripStateV4.UNKNOWN; candidate_seconds = 0.0
            if unknown_seconds > maximum_unknown_gap_seconds:
                confirmed = GripStateV4.UNKNOWN; stable_seconds = 0.0
            else:
                stable_seconds += duration
        else:
            unknown_seconds = 0.0
            if confirmed == GripStateV4.UNKNOWN and not output and raw_candidate in {GripStateV4.OPEN, GripStateV4.RELAXED}:
                confirmed = raw_candidate; stable_seconds = duration
            elif raw_candidate == confirmed:
                candidate = raw_candidate; candidate_seconds = 0.0; stable_seconds += duration
            else:
                if raw_candidate == candidate:
                    candidate_seconds += duration
                else:
                    candidate = raw_candidate; candidate_seconds = duration
                required = release_seconds if confirmed in _ACTIVE_GRIPS and raw_candidate not in _ACTIVE_GRIPS else confirmation_seconds
                if candidate_seconds + 1e-9 >= required:
                    confirmed = raw_candidate; stable_seconds = candidate_seconds
                    candidate_seconds = 0.0

        temporal_stability = float(np.clip(stable_seconds / max(confirmation_seconds * 3.0, 0.12), 0.0, 1.0))
        base_confidence = min(float(graph.grip.confidence), palm_quality, max(finger_quality, 0.0)) if raw_candidate != GripStateV4.UNKNOWN else 0.0
        evidence_bonus = object_evidence * 0.08 if confirmed in _ACTIVE_GRIPS else 0.0
        confidence = float(np.clip(base_confidence * (0.72 + 0.28 * temporal_stability) + evidence_bonus, 0.0, 1.0))
        if raw_candidate == GripStateV4.UNKNOWN and confirmed != GripStateV4.UNKNOWN:
            confidence *= max(0.25, 1.0 - unknown_seconds / max(maximum_unknown_gap_seconds, 1e-6))
        output.append(GripFrameV4(
            confirmed, confidence, raw_candidate, palm_quality, finger_quality,
            object_evidence, temporal_stability, raw_candidate == GripStateV4.UNKNOWN,
            wrist_alignment_diagnostic(side, graph, temporal_frames[index]),
            _features(graph),
        ))
    return GripSequenceV4(output, summarize_grip_v4(output, durations))


def wrist_alignment_diagnostic(side: str, hand: HandGraphFrame, body: TemporalFrame) -> dict[str, object]:
    body_index = 9 if side == "left" else 10
    if not hand.source_frame.visible or hand.source_frame.points_px.shape != (21, 2) or body_index >= body.render_scores.size or body.render_scores[body_index] <= 0.0:
        return {"available": False, "accepted": False, "distance_ratio": None, "mode": "unavailable"}
    palm_scale = hand.palm.scale
    if palm_scale is None or palm_scale <= 1e-6:
        return {"available": False, "accepted": False, "distance_ratio": None, "mode": "invalid_palm_scale"}
    hand_wrist = hand.source_frame.points_px[0]
    body_wrist = body.render_points[body_index]
    if not np.isfinite(hand_wrist).all() or not np.isfinite(body_wrist).all():
        return {"available": False, "accepted": False, "distance_ratio": None, "mode": "invalid_coordinate"}
    ratio = float(np.linalg.norm(hand_wrist - body_wrist) / palm_scale)
    accepted = ratio <= 0.65
    hand_quality = float(np.clip(hand.quality, 0.0, 1.0))
    body_quality = float(np.clip(body.render_scores[body_index], 0.0, 1.0))
    alignment_weight = min(hand_quality, body_quality) * 0.65 if accepted else 0.0
    fused_wrist = hand_wrist + (body_wrist - hand_wrist) * alignment_weight
    return {
        "available": True,
        "accepted": accepted,
        "distance_ratio": round(ratio, 6),
        "mode": "quality_weighted_alignment_candidate" if accepted else "assignment_rejected_large_disagreement",
        "hand_wrist_is_body_measurement": False,
        "alignment_weight": round(alignment_weight, 6),
        "overlay_translation_px": [
            round(float(fused_wrist[0] - hand_wrist[0]), 6),
            round(float(fused_wrist[1] - hand_wrist[1]), 6),
        ] if accepted else None,
        "fused_wrist_px": [round(float(value), 6) for value in fused_wrist] if accepted else None,
    }


def summarize_grip_v4(frames: Sequence[GripFrameV4], durations: Sequence[float]) -> dict[str, object]:
    seconds = {state: 0.0 for state in GripStateV4}
    episodes = 0; longest = current = 0.0
    valid = 0
    transition_count = 0
    single_frame_flicker_count = 0
    previous_state = GripStateV4.UNKNOWN
    for index, (frame, duration) in enumerate(zip(frames, durations)):
        seconds[frame.state] += duration
        valid += int(frame.state != GripStateV4.UNKNOWN)
        if frame.state in _ACTIVE_GRIPS:
            current += duration
            if current == duration:
                episodes += 1
            longest = max(longest, current)
        else:
            current = 0.0
        if index > 0 and frame.state != previous_state:
            transition_count += 1
        if (
            0 < index < len(frames) - 1
            and frames[index - 1].state == frames[index + 1].state
            and frame.state != frames[index - 1].state
        ):
            single_frame_flicker_count += 1
        previous_state = frame.state
    return {
        "open_seconds": round(seconds[GripStateV4.OPEN], 6),
        "relaxed_seconds": round(seconds[GripStateV4.RELAXED], 6),
        "partial_seconds": round(seconds[GripStateV4.PARTIALLY_CLOSED], 6),
        "power_grip_seconds": round(seconds[GripStateV4.POWER_GRIP], 6),
        "pinch_seconds": round(seconds[GripStateV4.PRECISION_PINCH], 6),
        "closed_seconds": round(seconds[GripStateV4.CLOSED], 6),
        "unknown_seconds": round(seconds[GripStateV4.UNKNOWN], 6),
        "grip_episode_count": episodes,
        "longest_grip_episode_seconds": round(longest, 6),
        "valid_coverage_ratio": round(valid / len(frames), 6) if frames else 0.0,
        "state_transition_count": transition_count,
        "single_frame_grip_flicker_count": single_frame_flicker_count,
        "grip_temporal_stability_score": round(
            max(0.0, 1.0 - single_frame_flicker_count / max(1, len(frames) - 2)), 6
        ) if frames else 0.0,
    }


def _features(graph: HandGraphFrame) -> dict[str, object]:
    grip = graph.grip
    return {
        "finger_flexion": {name: round(value, 6) if value is not None else None for name, value in grip.finger_flexion.items()},
        "mean_finger_flexion": _rounded(_mean_finite(grip.finger_flexion.values())),
        "closure_ratio": _rounded(grip.closure_ratio),
        "thumb_opposition": _rounded(grip.thumb_opposition_proxy),
        "thumb_index_distance_ratio": _rounded(grip.thumb_index_distance_ratio),
        "thumb_middle_distance_ratio": _rounded(grip.thumb_middle_distance_ratio),
        "thumb_flexion": _rounded(grip.thumb_flexion),
        "palm_orientation_degrees": _rounded(grip.palm_orientation_degrees),
        "hand_aperture_ratio": _rounded(grip.aperture_ratio),
    }


def _object_evidence(graph: HandGraphFrame) -> float:
    distance = graph.nearest_object_distance_ratio
    if distance is None or not math.isfinite(distance) or distance >= 1.6:
        return 0.0
    proximity = float(np.clip(1.0 - distance / 1.6, 0.0, 1.0))
    detector = float(np.clip(graph.nearest_object_confidence or 0.5, 0.0, 1.0))
    return proximity * detector


def _durations(timestamps: Sequence[float], fps: float) -> list[float]:
    fallback = 1.0 / fps if math.isfinite(fps) and fps > 0.0 else 1.0 / 30.0
    output = []
    for index, value in enumerate(timestamps):
        if index + 1 < len(timestamps):
            delta = float(timestamps[index + 1]) - float(value)
            output.append(delta if math.isfinite(delta) and delta > 0.0 else fallback)
        else:
            output.append(output[-1] if output else fallback)
    return output


def _mean_finite(values: object) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]  # type: ignore[union-attr]
    return float(np.mean(finite)) if finite else None


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None

"""Difficult-segment detection and fail-safe Pass 2 acceptance."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .config import RefinementConfig


DIFFICULT_REASONS = frozenset({
    "TRACK_LOST", "REACQUIRING", "LOW_BODY_QUALITY", "LOW_HAND_QUALITY",
    "HAND_OCCLUDED", "LIMB_OCCLUDED", "OUT_OF_FRAME", "HIGH_MOTION_BLUR",
    "FINGER_REJECTION", "HAND_SWAP_RISK", "BONE_OUTLIER", "HOLDING_UNCERTAIN",
    "OBJECT_ASSOCIATION_UNCERTAIN", "METRIC_SPIKE", "CAMERA_SHAKE",
    "FAST_MOTION_DROPOUT", "PERSON_DETECTOR_MISS", "LIMB_DROPOUT",
    "HAND_DROPOUT", "TEMPORAL_DISCONTINUITY", "MOTION_BLUR",
    "BONE_REJECTION_BURST", "OVERLAY_GAP", "IDENTITY_UNCERTAIN",
})


@dataclass(frozen=True)
class DifficultFrame:
    frame_index: int
    timestamp_seconds: float
    quality: float
    reasons: tuple[str, ...]
    refinable: bool


@dataclass(frozen=True)
class DifficultSegment:
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    reasons: tuple[str, ...]
    mean_quality: float
    refinable: bool

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1

    def to_dict(self) -> dict[str, object]:
        return {"start_frame": self.start_frame, "end_frame": self.end_frame,
            "start_seconds": round(self.start_seconds, 6), "end_seconds": round(self.end_seconds, 6),
            "frame_count": self.frame_count, "reasons": list(self.reasons),
            "mean_quality": round(self.mean_quality, 6), "refinable": self.refinable}


@dataclass(frozen=True)
class RefinementResult:
    frame_index: int
    attempted: bool
    reasons: tuple[str, ...]
    quality_before: float
    quality_after: float | None
    biomechanical_valid: bool
    accepted: bool
    replacement: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {"frame_index": self.frame_index, "refinement_attempted": self.attempted,
            "refinement_reason": list(self.reasons), "quality_before": round(self.quality_before, 6),
            "quality_after": round(self.quality_after, 6) if self.quality_after is not None else None,
            "biomechanical_valid": self.biomechanical_valid, "refinement_accepted": self.accepted}


def detect_difficult_segments(frames: Sequence[Mapping[str, Any]], *, fps: float, config: RefinementConfig) -> tuple[list[DifficultSegment], dict[str, object]]:
    config.validate()
    difficult = [_classify_frame(index, frame, fps, config) for index, frame in enumerate(frames)]
    difficult = [item for item in difficult if item.reasons]
    if not difficult:
        return [], _limit_summary(0, len(frames), False, False)
    padding = int(round(config.padding_seconds * fps)); merge_gap = int(round(config.merge_gap_seconds * fps))
    groups: list[list[DifficultFrame]] = []
    for item in difficult:
        if not groups or item.frame_index - groups[-1][-1].frame_index > merge_gap + 1:
            groups.append([item])
        else:
            groups[-1].append(item)
    segments = [_segment(group, frames, fps, padding, config) for group in groups]
    maximum = len(frames) if config.force_full_refinement else int(len(frames) * config.maximum_refinement_ratio)
    refinable = [item for item in segments if item.refinable]
    refinable_frames = sum(item.frame_count for item in refinable)
    limited = refinable_frames > maximum
    if limited:
        remaining = max(0, maximum); selected: list[DifficultSegment] = []
        for item in sorted(refinable, key=lambda value: (value.mean_quality, value.start_frame)):
            if remaining <= 0:
                break
            if item.frame_count <= remaining:
                selected.append(item); remaining -= item.frame_count
                continue
            selected.append(DifficultSegment(item.start_frame,item.start_frame + remaining - 1,item.start_seconds,(item.start_frame + remaining) / max(fps, 1e-6),item.reasons,item.mean_quality,True))
            remaining = 0
        bounded: list[DifficultSegment] = []
        for item in segments:
            replacement = next((candidate for candidate in selected if candidate.start_frame == item.start_frame), None)
            if replacement is not None:
                bounded.append(replacement)
            elif not item.refinable:
                bounded.append(item)
            else:
                bounded.append(DifficultSegment(item.start_frame,item.end_frame,item.start_seconds,item.end_seconds,item.reasons,item.mean_quality,False))
        segments = bounded
    return segments, _limit_summary(sum(item.frame_count for item in segments if item.refinable), len(frames), limited, refinable_frames > int(len(frames) * 0.70))


def refine_frames(segment: DifficultSegment, source_frames: Sequence[Mapping[str, Any]], refiner: Callable[[int, Mapping[str, Any]], Mapping[str, Any] | None], *, config: RefinementConfig) -> list[RefinementResult]:
    if not segment.refinable or not config.enabled:
        return []
    output: list[RefinementResult] = []
    for index in range(segment.start_frame, segment.end_frame + 1):
        before = source_frames[index]; quality_before = _quality(before)
        candidate = refiner(index, before)
        quality_after = _quality(candidate) if isinstance(candidate, Mapping) else None
        valid = bool(candidate.get("biomechanical_valid")) if isinstance(candidate, Mapping) else False
        accepted = bool(valid and quality_after is not None and quality_after > quality_before and quality_after - quality_before >= config.minimum_quality_gain)
        output.append(RefinementResult(index, True, segment.reasons, quality_before, quality_after, valid, accepted, candidate if accepted else None))
    return output


def summarize_refinement(segments: Sequence[DifficultSegment], results: Sequence[RefinementResult], total_frames: int) -> dict[str, object]:
    gains = [item.quality_after - item.quality_before for item in results if item.accepted and item.quality_after is not None]
    return {"version": "refinement-v1", "difficult_segments": [item.to_dict() for item in segments],
        "refinable_segments": sum(item.refinable for item in segments), "processed_segments": len({item.frame_index for item in results}) > 0,
        "frames_reprocessed": len(results), "frames_improved": sum(item.accepted for item in results),
        "frames_unchanged": sum(item.attempted and not item.accepted for item in results),
        "frames_rejected": sum(item.quality_after is not None and not item.accepted for item in results),
        "mean_quality_gain": round(sum(gains) / len(gains), 6) if gains else 0.0,
        "refinement_ratio": round(len(results) / total_frames, 6) if total_frames else 0.0,
        "frame_audit": [item.to_dict() for item in results]}


def _classify_frame(index: int, frame: Mapping[str, Any], fps: float, config: RefinementConfig) -> DifficultFrame:
    quality = _quality(frame); reasons = {str(value).upper() for value in frame.get("reasons", []) if isinstance(value, str)}
    tracking = str(frame.get("tracking_state", "")).upper()
    if tracking in {"TRACK_LOST", "LOST"}: reasons.add("TRACK_LOST")
    if tracking == "REACQUIRING": reasons.add("REACQUIRING")
    if quality < config.maximum_refinable_quality: reasons.add("LOW_BODY_QUALITY")
    if frame.get("camera_shake") is True: reasons.add("CAMERA_SHAKE")
    reasons.intersection_update(DIFFICULT_REASONS)
    refinable = config.minimum_refinable_quality <= quality <= config.maximum_refinable_quality and "TRACK_LOST" not in reasons
    timestamp = frame.get("timestamp_seconds")
    return DifficultFrame(index, float(timestamp) if isinstance(timestamp, (int,float)) else index/max(fps,1e-6), quality, tuple(sorted(reasons)), refinable)


def _segment(group: list[DifficultFrame], frames: Sequence[Mapping[str, Any]], fps: float, padding: int, config: RefinementConfig) -> DifficultSegment:
    start=max(0,group[0].frame_index-padding); end=min(len(frames)-1,group[-1].frame_index+padding)
    reasons=tuple(sorted({reason for item in group for reason in item.reasons})); qualities=[_quality(frames[index]) for index in range(start,end+1)]
    return DifficultSegment(start,end,start/max(fps,1e-6),(end+1)/max(fps,1e-6),reasons,sum(qualities)/len(qualities),any(item.refinable for item in group))


def _quality(frame: Mapping[str, Any] | None) -> float:
    if not isinstance(frame, Mapping): return 0.0
    value=frame.get("quality",frame.get("frame_quality",0.0))
    if isinstance(value, Mapping): value=value.get("score",0.0)
    return max(0.0,min(1.0,float(value))) if isinstance(value,(int,float)) and not isinstance(value,bool) else 0.0


def _limit_summary(frames: int,total: int,limited: bool,video_limited: bool)->dict[str,object]:
    return {"refinable_frames":frames,"refinement_ratio":round(frames/total,6) if total else 0.0,"limit_applied":limited,"video_quality_limited":video_limited}

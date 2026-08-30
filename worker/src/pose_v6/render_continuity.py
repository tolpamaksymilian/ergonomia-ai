"""Motion-aware persistent bone renderer for Pose V6."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

import numpy as np


class RenderSource(StrEnum):
    MEASURED = "MEASURED"
    REFINED_MEASUREMENT = "REFINED_MEASUREMENT"
    INTERPOLATED = "INTERPOLATED"
    FLOW_TRACKED = "FLOW_TRACKED"
    KINEMATIC_RECONSTRUCTED = "KINEMATIC_RECONSTRUCTED"
    KINEMATIC_PREDICTED = "KINEMATIC_PREDICTED"
    HELD = "HELD"
    HIDDEN = "HIDDEN"


@dataclass(frozen=True)
class PersistentBone:
    name: str
    first: tuple[float, float] | None
    second: tuple[float, float] | None
    alpha: float
    confidence: float
    source: RenderSource
    age_seconds: float
    safety_rejected: bool
    rejection_reason: str | None = None
    endpoint_age_delta: float = 0.0
    bone_length_ratio_to_canonical: float | None = None
    first_source: str | None = None
    second_source: str | None = None
    first_source_pass: str | None = None
    second_source_pass: str | None = None
    track_id: str | None = None
    effective_timestamp_seconds: float | None = None
    bone_length_pixels: float | None = None
    canonical_length_pixels: float | None = None

    @property
    def visible(self) -> bool:
        return self.first is not None and self.second is not None and self.alpha > 0.0

    @property
    def visibility_state(self) -> str:
        if not self.visible:
            return "LOST"
        if self.source in {RenderSource.MEASURED, RenderSource.REFINED_MEASUREMENT}:
            return "VISIBLE_MEASURED"
        if self.source in {
            RenderSource.INTERPOLATED,
            RenderSource.FLOW_TRACKED,
            RenderSource.KINEMATIC_RECONSTRUCTED,
        }:
            return "VISIBLE_RECONSTRUCTED"
        return "VISIBLE_PREDICTED"


@dataclass
class _Memory:
    first: np.ndarray | None = None
    second: np.ndarray | None = None
    first_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    second_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    bbox: np.ndarray | None = None
    timestamp: float | None = None
    measured_timestamp: float | None = None
    confidence: float = 0.0
    track_id: str | None = None
    bone_length_ratio_to_canonical: float | None = None


class PersistentBoneRenderer:
    """Keep short gaps visible while translating/scaling with the tracked body."""

    def __init__(self, *, persistence_seconds: float, minimum_quality: float = 0.35) -> None:
        if persistence_seconds < 0.0:
            raise ValueError("persistence_seconds cannot be negative")
        self.persistence_seconds = persistence_seconds
        self.minimum_quality = minimum_quality
        self._memory: dict[str, _Memory] = {}

    def reset(self) -> None:
        self._memory.clear()

    def update(
        self,
        name: str,
        first: np.ndarray | None,
        second: np.ndarray | None,
        *,
        first_source: str,
        second_source: str,
        confidence: float,
        timestamp_seconds: float,
        bbox: np.ndarray | None,
        expected_length: float | None,
        frame_width: int,
        frame_height: int,
        hard_lost: bool = False,
        scene_cut: bool = False,
        atomic_accepted: bool = True,
        atomic_reason: str | None = None,
        endpoint_age_delta: float = 0.0,
        bone_length_ratio_to_canonical: float | None = None,
        track_id: str | None = None,
        first_source_pass: str | None = None,
        second_source_pass: str | None = None,
        effective_timestamp_seconds: float | None = None,
    ) -> PersistentBone:
        if scene_cut:
            self.reset()
        memory = self._memory.setdefault(name, _Memory())
        if (
            memory.track_id is not None
            and track_id is not None
            and memory.track_id != track_id
        ):
            memory = _Memory()
            self._memory[name] = memory
        source = _combined_source(first_source, second_source)
        direct_safe = atomic_accepted and _safe_segment(
            first, second, expected_length, frame_width, frame_height,
        )
        direct = first is not None and second is not None and confidence >= self.minimum_quality and direct_safe
        if direct:
            first_array = np.asarray(first, dtype=np.float32)
            second_array = np.asarray(second, dtype=np.float32)
            if memory.timestamp is not None and timestamp_seconds > memory.timestamp and memory.first is not None and memory.second is not None:
                delta = timestamp_seconds - memory.timestamp
                memory.first_velocity = (first_array - memory.first) / delta
                memory.second_velocity = (second_array - memory.second) / delta
            memory.first = first_array.copy(); memory.second = second_array.copy()
            memory.bbox = _bbox(bbox); memory.timestamp = timestamp_seconds
            memory.track_id = track_id
            if source != RenderSource.KINEMATIC_PREDICTED or memory.measured_timestamp is None:
                memory.measured_timestamp = timestamp_seconds
            memory.confidence = float(np.clip(confidence, 0.0, 1.0))
            memory.bone_length_ratio_to_canonical = bone_length_ratio_to_canonical
            return PersistentBone(
                name, _point(first_array), _point(second_array), 1.0,
                memory.confidence, source, 0.0, False, None,
                endpoint_age_delta, bone_length_ratio_to_canonical,
                first_source, second_source, first_source_pass,
                second_source_pass, track_id, effective_timestamp_seconds,
                float(np.linalg.norm(second_array - first_array)),
                expected_length,
            )
        # The frozen final skeleton is authoritative. A cache entry may bridge
        # a genuine missing measurement, but it must never replace a segment
        # explicitly rejected by the final atomic/anatomical contract.
        if not atomic_accepted:
            return PersistentBone(
                name, None, None, 0.0, 0.0, RenderSource.HIDDEN, 0.0,
                True, atomic_reason or "FINAL_SKELETON_REJECTED",
                endpoint_age_delta, bone_length_ratio_to_canonical,
                first_source, second_source, first_source_pass,
                second_source_pass, track_id, effective_timestamp_seconds,
                None, expected_length,
            )
        if memory.first is None or memory.second is None or memory.measured_timestamp is None:
            return PersistentBone(
                name, None, None, 0.0, 0.0, RenderSource.HIDDEN, 0.0,
                first is not None and second is not None and not direct_safe,
                atomic_reason if not atomic_accepted else "GEOMETRY_SAFETY_REJECTED",
                endpoint_age_delta, bone_length_ratio_to_canonical,
            )
        age = max(0.0, timestamp_seconds - memory.measured_timestamp)
        if hard_lost or age > self.persistence_seconds:
            return PersistentBone(
                name, None, None, 0.0, 0.0, RenderSource.HIDDEN, age,
                not atomic_accepted, atomic_reason,
                endpoint_age_delta, bone_length_ratio_to_canonical,
            )
        previous_timestamp = memory.timestamp if memory.timestamp is not None else timestamp_seconds
        delta = max(0.0, timestamp_seconds - previous_timestamp)
        predicted_first = memory.first + memory.first_velocity * delta
        predicted_second = memory.second + memory.second_velocity * delta
        current_bbox = _bbox(bbox)
        if current_bbox is not None and memory.bbox is not None:
            predicted_first = _transform_by_bbox(predicted_first, memory.bbox, current_bbox)
            predicted_second = _transform_by_bbox(predicted_second, memory.bbox, current_bbox)
        predicted_first, predicted_second = _constrain_segment(
            predicted_first,
            predicted_second,
            expected_length,
        )
        safe = _safe_segment(predicted_first, predicted_second, expected_length, frame_width, frame_height)
        if not safe:
            return PersistentBone(
                name, None, None, 0.0, 0.0, RenderSource.HIDDEN, age, True,
                atomic_reason or "PREDICTED_GEOMETRY_SAFETY_REJECTED",
                endpoint_age_delta, bone_length_ratio_to_canonical,
            )
        decay = max(0.68, 1.0 - age / max(self.persistence_seconds, 1e-6) * 0.28)
        memory.first = predicted_first; memory.second = predicted_second
        if current_bbox is not None:
            memory.bbox = current_bbox
        memory.timestamp = timestamp_seconds
        return PersistentBone(
            name, _point(predicted_first), _point(predicted_second), decay,
            memory.confidence * decay, RenderSource.HELD, age,
            not atomic_accepted, atomic_reason,
            endpoint_age_delta, memory.bone_length_ratio_to_canonical,
        )


def summarize_render_sources(
    frames: list[Mapping[str, PersistentBone]],
    *,
    eligible_frames: list[bool] | None = None,
) -> dict[str, object]:
    counts = {source.value: 0 for source in RenderSource}
    visible = total = single_dropouts = full_dropouts = 0
    per_bone: dict[str, dict[str, object]] = {}
    midpoints: dict[str, list[np.ndarray]] = {}
    main_names = {
        "shoulders", "left_upper_arm", "left_forearm", "right_upper_arm",
        "right_forearm", "hips", "left_thigh", "left_lower_leg",
        "right_thigh", "right_lower_leg",
    }
    main_visible = main_total = 0
    for frame_index, frame in enumerate(frames):
        frame_visible = 0
        for name, bone in frame.items():
            total += 1; counts[bone.source.value] += 1
            item = per_bone.setdefault(name, {"visible_frames": 0, "total_frames": 0, "source_counts": {}})
            item["total_frames"] = int(item["total_frames"]) + 1
            item_sources = item["source_counts"]
            if isinstance(item_sources, dict):
                item_sources[bone.source.value] = int(item_sources.get(bone.source.value, 0)) + 1
            if bone.visible:
                visible += 1; frame_visible += 1
                item["visible_frames"] = int(item["visible_frames"]) + 1
                if bone.first is not None and bone.second is not None:
                    midpoints.setdefault(name, []).append((np.asarray(bone.first) + np.asarray(bone.second)) * 0.5)
            if name in main_names and (eligible_frames is None or (frame_index < len(eligible_frames) and eligible_frames[frame_index])):
                main_total += 1
                main_visible += int(bone.visible)
        if frame_visible == 0 and frame:
            full_dropouts += 1
    for index in range(1, len(frames) - 1):
        for name in frames[index]:
            if frames[index - 1].get(name) and frames[index + 1].get(name):
                if frames[index - 1][name].visible and not frames[index][name].visible and frames[index + 1][name].visible:
                    single_dropouts += 1
    single_full_dropouts = sum(
        bool(frames[index - 1])
        and any(item.visible for item in frames[index - 1].values())
        and not any(item.visible for item in frames[index].values())
        and any(item.visible for item in frames[index + 1].values())
        for index in range(1, len(frames) - 1)
    )
    for name, item in per_bone.items():
        bone_total = int(item["total_frames"]); bone_visible = int(item["visible_frames"])
        trajectory = midpoints.get(name, [])
        steps = [float(np.linalg.norm(trajectory[index] - trajectory[index - 1])) for index in range(1, len(trajectory))]
        item["coverage_ratio"] = round(bone_visible / bone_total, 6) if bone_total else 0.0
        item["mean_midpoint_step_pixels"] = round(float(np.mean(steps)), 6) if steps else 0.0
        item["percentile_95_midpoint_step_pixels"] = round(float(np.percentile(steps, 95)), 6) if steps else 0.0
    render_coverage = round(visible / total, 6) if total else 0.0
    return {
        "render_bone_coverage_ratio": render_coverage,
        "render_skeleton_coverage_ratio": render_coverage,
        "main_skeleton_render_coverage_ratio": round(main_visible / main_total, 6) if main_total else 0.0,
        "render_only_support_ratio": round(
            (counts[RenderSource.HELD.value] + counts[RenderSource.KINEMATIC_PREDICTED.value]) / total,
            6,
        ) if total else 0.0,
        "render_source_counts": counts,
        "single_frame_bone_dropout_count": single_dropouts,
        "single_frame_bone_flicker_count": single_dropouts,
        "single_frame_full_skeleton_dropout_count": single_full_dropouts,
        "full_skeleton_dropout_frame_count": full_dropouts,
        "per_bone": per_bone,
    }


def _combined_source(first: str, second: str) -> RenderSource:
    order = {
        "MEASURED": 0, "REFINED_MEASUREMENT": 1, "INTERPOLATED": 2,
        "FLOW_TRACKED": 3, "KINEMATIC_RECONSTRUCTED": 4,
        "KINEMATIC_PREDICTED": 5,
    }
    selected = max((first, second), key=lambda value: order.get(value, 5))
    try:
        return RenderSource(selected)
    except ValueError:
        return RenderSource.HELD


def _safe_segment(first: np.ndarray | None, second: np.ndarray | None, expected_length: float | None, width: int, height: int) -> bool:
    if first is None or second is None:
        return False
    first_array = np.asarray(first, dtype=float).reshape(-1); second_array = np.asarray(second, dtype=float).reshape(-1)
    if first_array.size != 2 or second_array.size != 2 or not np.isfinite(first_array).all() or not np.isfinite(second_array).all():
        return False
    if not (0 <= first_array[0] < width and 0 <= first_array[1] < height and 0 <= second_array[0] < width and 0 <= second_array[1] < height):
        return False
    length = float(np.linalg.norm(second_array - first_array))
    if length <= 1e-6 or length > math.hypot(width, height) * 0.45:
        return False
    return expected_length is None or expected_length <= 0.0 or length <= expected_length * 1.85


def _bbox(value: np.ndarray | None) -> np.ndarray | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    return array.copy() if array.size == 4 and np.isfinite(array).all() and array[2] > array[0] and array[3] > array[1] else None


def _transform_by_bbox(point: np.ndarray, previous: np.ndarray, current: np.ndarray) -> np.ndarray:
    previous_center = (previous[:2] + previous[2:]) * 0.5; current_center = (current[:2] + current[2:]) * 0.5
    previous_size = np.maximum(previous[2:] - previous[:2], 1.0); current_size = np.maximum(current[2:] - current[:2], 1.0)
    scale = np.clip(current_size / previous_size, 0.78, 1.28)
    return current_center + (point - previous_center) * scale


def _constrain_segment(first: np.ndarray, second: np.ndarray, expected: float | None) -> tuple[np.ndarray, np.ndarray]:
    if expected is None or expected <= 1e-6:
        return first, second
    vector = second - first
    length = float(np.linalg.norm(vector))
    if length <= 1e-8 or not math.isfinite(length):
        return first, second
    # Preserve the moving midpoint and orientation; only remove rubber-body
    # scaling accumulated by endpoint velocity/bbox prediction.
    target = float(np.clip(length, expected * 0.92, expected * 1.08))
    midpoint = (first + second) * 0.5
    half = vector / length * target * 0.5
    return midpoint - half, midpoint + half


def _point(value: np.ndarray) -> tuple[float, float]:
    return float(value[0]), float(value[1])

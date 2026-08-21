"""Offline bidirectional reconstruction with explicit analytical provenance."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class PointSource(StrEnum):
    MEASURED = "MEASURED"
    REFINED_MEASUREMENT = "REFINED_MEASUREMENT"
    INTERPOLATED = "INTERPOLATED"
    FLOW_TRACKED = "FLOW_TRACKED"
    KINEMATIC_PREDICTED = "KINEMATIC_PREDICTED"
    REJECTED = "REJECTED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class TemporalFrame:
    analysis_points: np.ndarray
    analysis_scores: np.ndarray
    render_points: np.ndarray
    render_scores: np.ndarray
    sources: tuple[PointSource, ...]
    analysis_usable: np.ndarray
    prediction_age_seconds: np.ndarray
    flow_errors: np.ndarray

    def joint_metadata(self, names: tuple[str, ...]) -> dict[str, dict[str, object]]:
        output: dict[str, dict[str, object]] = {}
        count = min(len(names), len(self.sources))
        for index in range(count):
            point = self.render_points[index]
            output[names[index]] = {
                "source": self.sources[index].value,
                "analysis_usable": bool(self.analysis_usable[index]),
                "quality": round(float(self.render_scores[index]), 6),
                "prediction_age_seconds": round(float(self.prediction_age_seconds[index]), 6),
                "flow_error": round(float(self.flow_errors[index]), 6) if math.isfinite(float(self.flow_errors[index])) else None,
                "render_coordinates": [round(float(point[0]), 3), round(float(point[1]), 3)] if self.render_scores[index] > 0.0 else None,
            }
        return output


def reconstruct_temporal_sequence(
    points: list[np.ndarray],
    scores: list[np.ndarray],
    raw_scores: list[np.ndarray],
    timestamps: list[float],
    tracking_states: list[str],
    scene_cuts: list[bool],
    *,
    maximum_interpolation_seconds: float,
    maximum_prediction_seconds: float = 0.55,
    refined_frames: set[int] | None = None,
    body_joint_count: int = 23,
) -> list[TemporalFrame]:
    """Reconstruct bounded gaps without changing rejected data into raw data."""

    if not points:
        return []
    if not (len(points) == len(scores) == len(raw_scores) == len(timestamps) == len(tracking_states) == len(scene_cuts)):
        raise ValueError("temporal sequence inputs must have equal lengths")
    point_array = np.stack(points).astype(np.float32)
    score_array = np.stack(scores).astype(np.float32)
    raw_score_array = np.stack(raw_scores).astype(np.float32)
    count, joint_count = score_array.shape
    body_count = min(body_joint_count, joint_count)
    sources = np.full((count, joint_count), PointSource.MISSING.value, dtype=object)
    usable = score_array > 0.0
    sources[usable] = PointSource.MEASURED.value
    rejected = (~usable) & (raw_score_array > 0.0)
    sources[rejected] = PointSource.REJECTED.value
    for index in refined_frames or set():
        if 0 <= index < count:
            sources[index, usable[index]] = PointSource.REFINED_MEASUREMENT.value
    ages = np.zeros((count, joint_count), dtype=np.float32)
    flow_errors = np.full((count, joint_count), np.nan, dtype=np.float32)

    for joint in range(body_count):
        _interpolate_joint(
            point_array,
            score_array,
            sources,
            usable,
            ages,
            timestamps,
            tracking_states,
            scene_cuts,
            joint,
            maximum_interpolation_seconds,
        )

    render_points = point_array.copy()
    render_scores = score_array.copy()
    _kinematic_fill(
        render_points,
        render_scores,
        sources,
        usable,
        ages,
        timestamps,
        scene_cuts,
        maximum_prediction_seconds,
    )
    return [
        TemporalFrame(
            analysis_points=point_array[index].copy(),
            analysis_scores=score_array[index].copy(),
            render_points=render_points[index].copy(),
            render_scores=render_scores[index].copy(),
            sources=tuple(PointSource(str(value)) for value in sources[index]),
            analysis_usable=usable[index].copy(),
            prediction_age_seconds=ages[index].copy(),
            flow_errors=flow_errors[index].copy(),
        )
        for index in range(count)
    ]


def merge_flow_result(
    frame: TemporalFrame,
    joint_index: int,
    point: tuple[float, float],
    quality: float,
    flow_error: float,
    age_seconds: float,
) -> TemporalFrame:
    """Merge an anatomically validated flow sample into a still-missing joint."""

    if frame.analysis_scores[joint_index] > 0.0:
        return frame
    analysis_points = frame.analysis_points.copy()
    analysis_scores = frame.analysis_scores.copy()
    render_points = frame.render_points.copy()
    render_scores = frame.render_scores.copy()
    usable = frame.analysis_usable.copy()
    ages = frame.prediction_age_seconds.copy()
    errors = frame.flow_errors.copy()
    sources = list(frame.sources)
    analysis_points[joint_index] = point
    analysis_scores[joint_index] = float(np.clip(quality, 0.0, 1.0))
    render_points[joint_index] = point
    render_scores[joint_index] = analysis_scores[joint_index]
    usable[joint_index] = True
    ages[joint_index] = max(0.0, age_seconds)
    errors[joint_index] = max(0.0, flow_error)
    sources[joint_index] = PointSource.FLOW_TRACKED
    return TemporalFrame(analysis_points, analysis_scores, render_points, render_scores, tuple(sources), usable, ages, errors)


def validate_analysis_bones(
    frame: TemporalFrame,
    bones: Mapping[str, tuple[int, int]],
    expected_lengths: Mapping[str, float | None],
    *,
    body_scale: float,
) -> dict[str, dict[str, object]]:
    """Revalidate reconstructed analytical geometry before downstream use."""

    output: dict[str, dict[str, object]] = {}
    for name, (first, second) in bones.items():
        valid_endpoints = (
            first < len(frame.analysis_usable)
            and second < len(frame.analysis_usable)
            and bool(frame.analysis_usable[first])
            and bool(frame.analysis_usable[second])
            and frame.analysis_scores[first] > 0.0
            and frame.analysis_scores[second] > 0.0
        )
        length: float | None = None
        reason: str | None = None
        if valid_endpoints:
            length = float(np.linalg.norm(frame.analysis_points[second] - frame.analysis_points[first]))
            expected = expected_lengths.get(name)
            maximum = expected * 1.55 if expected is not None and expected > 0.0 else body_scale * 0.90
            minimum = expected * 0.45 if expected is not None and expected > 0.0 else 1.0
            if not math.isfinite(length) or not minimum <= length <= maximum:
                valid_endpoints = False
                reason = "TEMPORAL_BONE_LENGTH_OUTLIER"
        else:
            reason = "TEMPORAL_ENDPOINT_NOT_ANALYSIS_USABLE"
        output[name] = {
            "valid": valid_endpoints,
            "quality": round(
                min(float(frame.analysis_scores[first]), float(frame.analysis_scores[second]))
                if valid_endpoints
                else 0.0,
                6,
            ),
            "length_pixels": round(length, 3) if length is not None and math.isfinite(length) else None,
            "reason": reason,
        }
    return output


def reject_reconstructed_analysis_joints(
    frame: TemporalFrame,
    joint_indexes: set[int],
) -> TemporalFrame:
    """Remove unsafe reconstruction from analysis while retaining render evidence.

    The renderer still performs its own stricter segment safety check. Keeping
    the render coordinates here is deliberate; clearing only analytical scores
    prevents rejected flow/interpolation from inflating analytical coverage.
    """

    if not joint_indexes:
        return frame
    analysis_points = frame.analysis_points.copy()
    analysis_scores = frame.analysis_scores.copy()
    usable = frame.analysis_usable.copy()
    for index in joint_indexes:
        if not 0 <= index < len(analysis_scores):
            continue
        if frame.sources[index] not in {PointSource.INTERPOLATED, PointSource.FLOW_TRACKED}:
            continue
        analysis_points[index] = 0.0
        analysis_scores[index] = 0.0
        usable[index] = False
    return TemporalFrame(
        analysis_points,
        analysis_scores,
        frame.render_points.copy(),
        frame.render_scores.copy(),
        frame.sources,
        usable,
        frame.prediction_age_seconds.copy(),
        frame.flow_errors.copy(),
    )


def _interpolate_joint(
    points: np.ndarray,
    scores: np.ndarray,
    sources: np.ndarray,
    usable: np.ndarray,
    ages: np.ndarray,
    timestamps: list[float],
    tracking_states: list[str],
    scene_cuts: list[bool],
    joint: int,
    maximum_seconds: float,
) -> None:
    valid = scores[:, joint] > 0.0
    index = 0
    while index < len(valid):
        if valid[index]:
            index += 1
            continue
        start = index
        while index < len(valid) and not valid[index]:
            index += 1
        before, after = start - 1, index
        if before < 0 or after >= len(valid) or not valid[before] or not valid[after]:
            continue
        duration = timestamps[after] - timestamps[before]
        blocked = any(scene_cuts[item] or tracking_states[item].upper() in {"LOST", "REACQUIRING"} for item in range(start, after))
        if duration <= 0.0 or duration > maximum_seconds or blocked:
            continue
        velocity_before = _endpoint_velocity(points[:, joint], scores[:, joint], timestamps, before, -1)
        velocity_after = _endpoint_velocity(points[:, joint], scores[:, joint], timestamps, after, 1)
        first, second = points[before, joint].copy(), points[after, joint].copy()
        lower = np.minimum(first, second) - np.linalg.norm(second - first) * 0.15
        upper = np.maximum(first, second) + np.linalg.norm(second - first) * 0.15
        for current in range(start, after):
            ratio = (timestamps[current] - timestamps[before]) / duration
            value = _hermite(first, second, velocity_before * duration, velocity_after * duration, ratio)
            points[current, joint] = np.clip(value, lower, upper)
            distance_to_measurement = min(timestamps[current] - timestamps[before], timestamps[after] - timestamps[current])
            decay = max(0.35, 1.0 - distance_to_measurement / max(maximum_seconds, 1e-6) * 0.55)
            scores[current, joint] = min(scores[before, joint], scores[after, joint]) * decay
            valid[current] = True
            usable[current, joint] = True
            sources[current, joint] = PointSource.INTERPOLATED.value
            ages[current, joint] = distance_to_measurement


def _endpoint_velocity(points: np.ndarray, scores: np.ndarray, timestamps: list[float], index: int, direction: int) -> np.ndarray:
    other = index + direction
    if not 0 <= other < len(scores) or scores[other] <= 0.0:
        return np.zeros(2, dtype=np.float32)
    delta = timestamps[other] - timestamps[index]
    if abs(delta) <= 1e-6:
        return np.zeros(2, dtype=np.float32)
    return (points[other] - points[index]) / delta


def _hermite(first: np.ndarray, second: np.ndarray, first_tangent: np.ndarray, second_tangent: np.ndarray, ratio: float) -> np.ndarray:
    t = float(np.clip(ratio, 0.0, 1.0)); t2 = t * t; t3 = t2 * t
    return (2 * t3 - 3 * t2 + 1) * first + (t3 - 2 * t2 + t) * first_tangent + (-2 * t3 + 3 * t2) * second + (t3 - t2) * second_tangent


def _kinematic_fill(points: np.ndarray, scores: np.ndarray, sources: np.ndarray, usable: np.ndarray, ages: np.ndarray, timestamps: list[float], scene_cuts: list[bool], maximum_prediction_seconds: float) -> None:
    # Missing middle joint between two visible endpoints: shoulder-elbow-wrist
    # and hip-knee-ankle.  The result is intentionally render-only.
    chains = ((5, 7, 9), (6, 8, 10), (11, 13, 15), (12, 14, 16))
    for parent, middle, child in chains:
        first_lengths = _observed_lengths(points, scores, parent, middle)
        second_lengths = _observed_lengths(points, scores, middle, child)
        if not first_lengths or not second_lengths:
            continue
        radius_first = float(np.median(first_lengths)); radius_second = float(np.median(second_lengths))
        previous: np.ndarray | None = None
        previous_timestamp: float | None = None
        for frame_index in range(points.shape[0]):
            if scene_cuts[frame_index]:
                previous = None; previous_timestamp = None
            if scores[frame_index, middle] > 0.0:
                previous = points[frame_index, middle].copy(); previous_timestamp = timestamps[frame_index]
                continue
            if previous is None or previous_timestamp is None:
                continue
            prediction_age = max(0.0, timestamps[frame_index] - previous_timestamp)
            if prediction_age > maximum_prediction_seconds:
                continue
            if scores[frame_index, parent] <= 0.0 or scores[frame_index, child] <= 0.0:
                continue
            candidate = circle_intersection_nearest(points[frame_index, parent], radius_first, points[frame_index, child], radius_second, previous)
            if candidate is None:
                continue
            points[frame_index, middle] = candidate
            scores[frame_index, middle] = min(scores[frame_index, parent], scores[frame_index, child]) * 0.45
            sources[frame_index, middle] = PointSource.KINEMATIC_PREDICTED.value
            usable[frame_index, middle] = False
            ages[frame_index, middle] = prediction_age
            previous = candidate


def _observed_lengths(points: np.ndarray, scores: np.ndarray, first: int, second: int) -> list[float]:
    output: list[float] = []
    for index in range(points.shape[0]):
        if scores[index, first] > 0.0 and scores[index, second] > 0.0:
            length = float(np.linalg.norm(points[index, second] - points[index, first]))
            if math.isfinite(length) and length > 1.0:
                output.append(length)
    return output


def circle_intersection_nearest(first: np.ndarray, first_radius: float, second: np.ndarray, second_radius: float, reference: np.ndarray | None) -> np.ndarray | None:
    delta = np.asarray(second, dtype=np.float32) - np.asarray(first, dtype=np.float32)
    distance = float(np.linalg.norm(delta))
    if distance <= 1e-6 or distance > first_radius + second_radius or distance < abs(first_radius - second_radius):
        return None
    along = (first_radius * first_radius - second_radius * second_radius + distance * distance) / (2.0 * distance)
    height_squared = first_radius * first_radius - along * along
    if height_squared < -1e-4:
        return None
    midpoint = np.asarray(first, dtype=np.float32) + delta * (along / distance)
    perpendicular = np.asarray([-delta[1], delta[0]], dtype=np.float32) / distance
    offset = perpendicular * math.sqrt(max(0.0, height_squared))
    candidates = (midpoint + offset, midpoint - offset)
    if reference is None:
        return candidates[0]
    return min(candidates, key=lambda value: float(np.linalg.norm(value - reference))).astype(np.float32)

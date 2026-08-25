"""Offline fixed-lag trajectory refinement for Pose V6.

The refiner uses future samples only to identify an isolated spatial outlier.
It deliberately leaves sustained and monotonic fast motion untouched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np

from .temporal_reconstruction import PointSource, TemporalFrame


REFINED_JOINTS = (5, 6, 11, 12, 7, 8, 13, 14, 9, 10, 15, 16)
_ANALYSIS_SOURCES = {
    PointSource.MEASURED,
    PointSource.REFINED_MEASUREMENT,
    PointSource.INTERPOLATED,
    PointSource.FLOW_TRACKED,
    PointSource.KINEMATIC_RECONSTRUCTED,
}


@dataclass(frozen=True)
class TrajectoryRefinementResult:
    frames: list[TemporalFrame]
    frame_diagnostics: list[dict[str, object]]
    summary: dict[str, object]


def refine_fixed_lag_sequence(
    frames: Sequence[TemporalFrame],
    body_scales: Sequence[float],
    timestamps: Sequence[float],
    motion_states: Sequence[str],
    tracking_states: Sequence[str],
    scene_cuts: Sequence[bool],
    *,
    lag_frames: int = 2,
) -> TrajectoryRefinementResult:
    """Correct isolated drift using bracketing samples from the same track."""

    count = len(frames)
    if not (
        count == len(body_scales) == len(timestamps) == len(motion_states)
        == len(tracking_states) == len(scene_cuts)
    ):
        raise ValueError("trajectory refinement inputs must have equal lengths")
    if lag_frames < 1 or lag_frames > 6:
        raise ValueError("lag_frames must be in range 1..6")
    output = [_copy_frame(frame) for frame in frames]
    diagnostics: list[dict[str, object]] = [
        {"corrected_joints": [], "maximum_correction_body_ratio": 0.0}
        for _ in frames
    ]
    correction_ratios: list[float] = []

    for joint in REFINED_JOINTS:
        for index in range(1, count - 1):
            frame = frames[index]
            if not _eligible_frame(frame, joint, tracking_states[index], scene_cuts[index]):
                continue
            previous_index = _nearest_valid(
                frames, joint, index, -1, lag_frames, tracking_states, scene_cuts
            )
            next_index = _nearest_valid(
                frames, joint, index, 1, lag_frames, tracking_states, scene_cuts
            )
            if previous_index is None or next_index is None:
                continue
            before_time = float(timestamps[previous_index])
            after_time = float(timestamps[next_index])
            current_time = float(timestamps[index])
            if not all(math.isfinite(value) for value in (before_time, current_time, after_time)) or after_time <= before_time:
                continue
            ratio = float(np.clip((current_time - before_time) / (after_time - before_time), 0.0, 1.0))
            before = frames[previous_index].analysis_points[joint]
            after = frames[next_index].analysis_points[joint]
            expected = before + (after - before) * ratio
            current = frame.analysis_points[joint]
            scale = max(float(body_scales[index]), 1.0)
            residual_ratio = float(np.linalg.norm(current - expected) / scale)
            neighbor_span_ratio = float(np.linalg.norm(after - before) / scale)
            fast = str(motion_states[index]).upper() in {"FAST_MOTION", "EXTREME_MOTION"}
            residual_gate = 0.13 if fast else 0.075
            # A true fast move has separated bracketing samples.  A single
            # detached point has a large residual while neighbours agree.
            if residual_ratio <= residual_gate or neighbor_span_ratio > (0.58 if fast else 0.34):
                continue
            quality = float(frame.analysis_scores[joint])
            source = frame.sources[joint]
            strong_measurement = source in {
                PointSource.MEASURED,
                PointSource.REFINED_MEASUREMENT,
            } and quality >= 0.94
            if strong_measurement and residual_ratio < residual_gate * 2.2:
                continue
            correction_weight = float(np.clip(
                0.52 + (residual_ratio - residual_gate) * 2.0 + (0.80 - quality) * 0.30,
                0.52,
                0.90,
            ))
            corrected = current + (expected - current) * correction_weight
            target = output[index]
            points = target.analysis_points.copy()
            render_points = target.render_points.copy()
            scores = target.analysis_scores.copy()
            render_scores = target.render_scores.copy()
            sources = list(target.sources)
            usable = target.analysis_usable.copy()
            ages = target.prediction_age_seconds.copy()
            points[joint] = corrected
            render_points[joint] = corrected
            scores[joint] = min(0.82, max(0.35, quality * 0.76))
            render_scores[joint] = scores[joint]
            sources[joint] = PointSource.KINEMATIC_RECONSTRUCTED
            usable[joint] = True
            ages[joint] = min(
                abs(current_time - before_time),
                abs(after_time - current_time),
            )
            output[index] = replace(
                target,
                analysis_points=points,
                analysis_scores=scores,
                render_points=render_points,
                render_scores=render_scores,
                sources=tuple(sources),
                analysis_usable=usable,
                prediction_age_seconds=ages,
            )
            correction_ratios.append(residual_ratio)
            item = diagnostics[index]
            corrected_joints = item["corrected_joints"]
            if isinstance(corrected_joints, list):
                corrected_joints.append(joint)
            item["maximum_correction_body_ratio"] = round(max(
                float(item["maximum_correction_body_ratio"]), residual_ratio
            ), 6)

    corrected_frames = sum(bool(item["corrected_joints"]) for item in diagnostics)
    return TrajectoryRefinementResult(
        output,
        diagnostics,
        {
            "solver": "offline-fixed-lag-isolated-outlier-v1",
            "lag_frames": lag_frames,
            "corrected_frame_count": corrected_frames,
            "corrected_joint_count": len(correction_ratios),
            "mean_detected_drift_body_ratio": round(float(np.mean(correction_ratios)), 6) if correction_ratios else 0.0,
            "maximum_detected_drift_body_ratio": round(max(correction_ratios), 6) if correction_ratios else 0.0,
            "future_frames_used": True,
            "sustained_fast_motion_preserved": True,
        },
    )


def _eligible_frame(frame: TemporalFrame, joint: int, tracking: str, scene_cut: bool) -> bool:
    return bool(
        not scene_cut
        and str(tracking).upper() not in {"LOST", "REACQUIRING", "HARD_LOST"}
        and joint < frame.analysis_scores.size
        and bool(frame.analysis_usable[joint])
        and float(frame.analysis_scores[joint]) > 0.0
        and frame.sources[joint] in _ANALYSIS_SOURCES
        and np.isfinite(frame.analysis_points[joint]).all()
    )


def _nearest_valid(
    frames: Sequence[TemporalFrame],
    joint: int,
    start: int,
    direction: int,
    lag: int,
    tracking_states: Sequence[str],
    scene_cuts: Sequence[bool],
) -> int | None:
    for distance in range(1, lag + 1):
        index = start + direction * distance
        if not 0 <= index < len(frames) or scene_cuts[index]:
            return None
        if _eligible_frame(frames[index], joint, tracking_states[index], False):
            return index
    return None


def _copy_frame(frame: TemporalFrame) -> TemporalFrame:
    return replace(
        frame,
        analysis_points=frame.analysis_points.copy(),
        analysis_scores=frame.analysis_scores.copy(),
        render_points=frame.render_points.copy(),
        render_scores=frame.render_scores.copy(),
        analysis_usable=frame.analysis_usable.copy(),
        prediction_age_seconds=frame.prediction_age_seconds.copy(),
        flow_errors=frame.flow_errors.copy(),
    )

"""Offline body smoothing that never bridges LOST or REACQUIRING tracks."""

from __future__ import annotations

import numpy as np

from .tracking import TrackingState


def smooth_body_sequence(
    points: list[np.ndarray],
    scores: list[np.ndarray],
    tracking_states: list[str],
    *,
    frame_width: int,
    frame_height: int,
    maximum_gap_frames: int = 2,
    median_window: int = 3,
    ema_alpha: float = 0.72,
    interpolation_allowed: list[np.ndarray] | None = None,
) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    if not points:
        return [], [], []
    point_array = np.stack(points, axis=0).astype(np.float32)
    score_array = np.stack(scores, axis=0).astype(np.float32)
    frame_count, joint_count = score_array.shape
    interpolated = np.zeros((frame_count, joint_count), dtype=bool)
    allowed = (
        np.stack(interpolation_allowed, axis=0).astype(bool)
        if interpolation_allowed is not None
        else np.ones((frame_count, joint_count), dtype=bool)
    )
    if allowed.shape != (frame_count, joint_count):
        raise ValueError("interpolation_allowed must match frame/joint dimensions")
    diagonal = max(1.0, float(np.hypot(frame_width, frame_height)))

    for joint in range(joint_count):
        visible = score_array[:, joint] > 0.0
        index = 0
        while index < frame_count:
            if visible[index]:
                index += 1
                continue
            start = index
            while index < frame_count and not visible[index]:
                index += 1
            end = index - 1
            before, after = start - 1, index
            gap = end - start + 1
            safe_states = all(
                tracking_states[item]
                not in {TrackingState.LOST.value, TrackingState.REACQUIRING.value}
                for item in range(start, end + 1)
            )
            if (
                gap <= maximum_gap_frames
                and before >= 0
                and after < frame_count
                and visible[before]
                and visible[after]
                and safe_states
                and bool(np.all(allowed[start : end + 1, joint]))
                and float(np.linalg.norm(point_array[after, joint] - point_array[before, joint]))
                / diagonal
                <= 0.20 * (gap + 1)
            ):
                for current in range(start, end + 1):
                    ratio = (current - before) / (after - before)
                    point_array[current, joint] = (
                        (1.0 - ratio) * point_array[before, joint]
                        + ratio * point_array[after, joint]
                    )
                    score_array[current, joint] = (
                        min(score_array[before, joint], score_array[after, joint]) * 0.82
                    )
                    visible[current] = True
                    interpolated[current, joint] = True

        _smooth_joint_runs(
            point_array[:, joint],
            visible,
            median_window=median_window,
            alpha=ema_alpha,
        )

    return (
        [point_array[index].copy() for index in range(frame_count)],
        [score_array[index].copy() for index in range(frame_count)],
        [interpolated[index].copy() for index in range(frame_count)],
    )


def _smooth_joint_runs(
    points: np.ndarray,
    visible: np.ndarray,
    *,
    median_window: int,
    alpha: float,
) -> None:
    radius = max(0, median_window // 2)
    median = points.copy()
    for index in range(points.shape[0]):
        if not visible[index]:
            continue
        start = max(0, index - radius)
        end = min(points.shape[0], index + radius + 1)
        selected = [item for item in range(start, end) if visible[item]]
        if selected:
            median[index] = np.median(points[selected], axis=0)

    forward = median.copy()
    last: np.ndarray | None = None
    for index in range(points.shape[0]):
        if not visible[index]:
            last = None
            continue
        last = median[index].copy() if last is None else alpha * median[index] + (1.0 - alpha) * last
        forward[index] = last

    backward = median.copy()
    last = None
    for index in range(points.shape[0] - 1, -1, -1):
        if not visible[index]:
            last = None
            continue
        last = median[index].copy() if last is None else alpha * median[index] + (1.0 - alpha) * last
        backward[index] = last
    points[visible] = (forward[visible] + backward[visible]) / 2.0

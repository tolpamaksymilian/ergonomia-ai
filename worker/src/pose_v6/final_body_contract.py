"""Immutable FinalBodyState parity checks shared by JSON and renderer."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .global_body import ImmutableFinalBodyState


def validate_renderer_final_state_parity(
    states: Sequence[ImmutableFinalBodyState],
    renderer_points: Sequence[np.ndarray],
    *,
    body_joint_count: int = 23,
) -> dict[str, object]:
    if len(states) != len(renderer_points):
        raise ValueError("renderer parity inputs must have equal frame counts")
    mismatch_count = 0
    maximum_delta = 0.0
    for state, rendered in zip(states, renderer_points):
        expected = np.asarray(state.frame.render_points[:body_joint_count], dtype=np.float64)
        actual = np.asarray(rendered[:body_joint_count], dtype=np.float64)
        if expected.shape != actual.shape:
            mismatch_count += 1
            maximum_delta = float("inf")
            continue
        delta = np.abs(expected - actual)
        frame_maximum = float(np.max(delta)) if delta.size else 0.0
        maximum_delta = max(maximum_delta, frame_maximum)
        if not np.array_equal(expected, actual, equal_nan=True):
            mismatch_count += 1
    return {
        "renderer_final_state_mismatch_count": mismatch_count,
        "renderer_final_state_maximum_delta_pixels": (
            maximum_delta if np.isfinite(maximum_delta) else None
        ),
        "target_mismatch_count": 0,
        "valid": mismatch_count == 0,
    }


def validate_serialized_final_state_parity(
    states: Sequence[ImmutableFinalBodyState],
    serialized_points: Sequence[Sequence[Sequence[float] | None]],
    *,
    body_joint_count: int = 23,
    decimal_tolerance: float = 0.011,
) -> dict[str, object]:
    if len(states) != len(serialized_points):
        raise ValueError("JSON parity inputs must have equal frame counts")
    mismatch_count = 0
    for state, serialized in zip(states, serialized_points):
        for joint in range(min(body_joint_count, len(state.frame.render_scores))):
            expected_visible = state.frame.render_scores[joint] > 0.0
            value = serialized[joint] if joint < len(serialized) else None
            if not expected_visible:
                continue
            if value is None or len(value) != 2:
                mismatch_count += 1
                continue
            if np.max(np.abs(np.asarray(value, dtype=np.float64) - state.frame.render_points[joint])) > decimal_tolerance:
                mismatch_count += 1
    return {
        "json_final_state_mismatch_count": mismatch_count,
        "valid": mismatch_count == 0,
    }


__all__ = [
    "validate_renderer_final_state_parity",
    "validate_serialized_final_state_parity",
]

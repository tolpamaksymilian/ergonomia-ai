from __future__ import annotations

import numpy as np

from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame
from worker.src.pose_v6.trajectory_refinement import refine_fixed_lag_sequence


def _frame(wrist_x: float) -> TemporalFrame:
    points = np.asarray([[100.0 + index, 100.0] for index in range(23)], dtype=np.float32)
    points[9] = (wrist_x, 150.0)
    scores = np.full(23, 0.8, dtype=np.float32)
    return TemporalFrame(
        points.copy(), scores.copy(), points.copy(), scores.copy(),
        tuple([PointSource.MEASURED] * 23), np.ones(23, dtype=bool),
        np.zeros(23, dtype=np.float32), np.full(23, np.nan, dtype=np.float32),
    )


def _run(xs: list[float], motion: str = "NORMAL"):
    frames = [_frame(value) for value in xs]
    return refine_fixed_lag_sequence(
        frames, [100.0] * len(frames), [index / 10 for index in range(len(frames))],
        [motion] * len(frames), ["TRACKED"] * len(frames), [False] * len(frames),
    )


def test_fixed_lag_repairs_isolated_joint_drift() -> None:
    result = _run([100.0, 102.0, 170.0, 106.0, 108.0])
    assert result.frames[2].analysis_points[9, 0] < 130.0
    assert 9 in result.frame_diagnostics[2]["corrected_joints"]
    assert result.summary["future_frames_used"] is True


def test_fixed_lag_preserves_sustained_fast_motion() -> None:
    result = _run([100.0, 125.0, 150.0, 175.0, 200.0], "FAST_MOTION")
    assert result.summary["corrected_joint_count"] == 0
    assert np.allclose([frame.analysis_points[9, 0] for frame in result.frames], [100, 125, 150, 175, 200])


def test_scene_cut_prevents_cross_segment_refinement() -> None:
    frames = [_frame(value) for value in [100.0, 102.0, 170.0, 106.0, 108.0]]
    result = refine_fixed_lag_sequence(
        frames, [100.0] * 5, [index / 10 for index in range(5)], ["NORMAL"] * 5,
        ["TRACKED"] * 5, [False, False, True, False, False],
    )
    assert result.frames[2].analysis_points[9, 0] == 170.0


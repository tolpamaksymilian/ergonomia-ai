from __future__ import annotations

import numpy as np

from worker.src.pose_v6.anatomical_stability import (
    build_canonical_body_profile,
    detect_and_correct_side_swaps,
    project_anatomical_sequence,
    solve_two_bone_chain,
)
from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame


def _frame(*, elbow: tuple[float, float] = (30.0, 30.0), elbow_valid: bool = True, wrist: tuple[float, float] = (50.0, 50.0), wrist_quality: float = 0.95) -> TemporalFrame:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.zeros(23, dtype=np.float32)
    anchors = {
        5: (20, 20), 6: (80, 20), 7: elbow, 8: (70, 30), 9: wrist, 10: (50, 50),
        11: (30, 80), 12: (70, 80), 13: (30, 120), 14: (70, 120),
        15: (30, 160), 16: (70, 160),
    }
    for index, value in anchors.items():
        points[index] = value
        scores[index] = wrist_quality if index == 9 else 0.95
    if not elbow_valid:
        points[7] = 0.0; scores[7] = 0.0
    usable = scores > 0.0
    sources = tuple(PointSource.MEASURED if usable[index] else PointSource.MISSING for index in range(23))
    return TemporalFrame(points.copy(), scores.copy(), points.copy(), scores.copy(), sources, usable, np.zeros(23, dtype=np.float32), np.full(23, np.nan, dtype=np.float32))


def test_canonical_profile_uses_normalized_median_and_mad() -> None:
    frames = [_frame(elbow=(30 + offset, 30)) for offset in (0, 1, -1, 0)]
    profile = build_canonical_body_profile(frames, [200.0] * 4)
    upper = profile.bones["left_upper_arm"]
    assert upper.sample_count == 4
    assert 0.065 < upper.normalized_length < 0.075
    assert upper.mad >= 0.0
    assert profile.bones["torso_length"].normalized_length == pytest.approx(0.3)


def test_two_circle_solver_preserves_both_bone_lengths() -> None:
    root = np.asarray((0.0, 0.0)); end = np.asarray((6.0, 0.0))
    middle = solve_two_bone_chain(root, end, 5.0, 5.0, np.asarray((3.0, 4.0)))
    assert middle is not None
    assert np.linalg.norm(middle - root) == pytest.approx(5.0, abs=1e-5)
    assert np.linalg.norm(middle - end) == pytest.approx(5.0, abs=1e-5)


def test_missing_elbow_is_kinematically_reconstructed_not_measured() -> None:
    frames = [_frame() for _ in range(3)] + [_frame(elbow_valid=False)] + [_frame()]
    result = project_anatomical_sequence(frames, [200.0] * 5, [index / 30 for index in range(5)], ["TRACKED"] * 5, [False] * 5)
    reconstructed = result.frames[3]
    assert reconstructed.analysis_usable[7]
    assert reconstructed.sources[7] == PointSource.KINEMATIC_RECONSTRUCTED
    assert result.summary["kinematic_reconstruction_count"] >= 1


def test_low_quality_single_joint_teleport_is_rejected() -> None:
    frames = [_frame() for _ in range(3)] + [_frame(wrist=(190, 10), wrist_quality=0.55)] + [_frame()]
    result = project_anatomical_sequence(frames, [200.0] * 5, [index / 30 for index in range(5)], ["TRACKED"] * 5, [False] * 5)
    corrected = result.frames[3]
    assert corrected.sources[9] == PointSource.KINEMATIC_RECONSTRUCTED
    assert np.linalg.norm(corrected.analysis_points[9] - np.asarray((50, 50))) < 20
    assert result.summary["detected_joint_jump_count"] >= 1
    assert result.summary["joint_jump_event_count"] == 0


def test_normalized_bone_error_is_small_after_projection() -> None:
    frames = [_frame() for _ in range(4)]
    frames.append(_frame(elbow=(43, 15), wrist=(66, 46), wrist_quality=0.8))
    result = project_anatomical_sequence(frames, [200.0] * 5, [index / 30 for index in range(5)], ["TRACKED"] * 5, [False] * 5)
    assert result.summary["bone_length_stability_error"] < 0.08


def test_isolated_left_right_swap_is_corrected_by_trajectory_not_screen_side() -> None:
    frames = [_frame(), _frame(), _frame()]
    middle = frames[1]
    points = middle.analysis_points.copy(); render = middle.render_points.copy()
    points[[7, 8]] = points[[8, 7]]; render[[7, 8]] = render[[8, 7]]
    frames[1] = TemporalFrame(points, middle.analysis_scores, render, middle.render_scores, middle.sources, middle.analysis_usable, middle.prediction_age_seconds, middle.flow_errors)
    corrected = detect_and_correct_side_swaps(frames, [200.0] * 3, margin_ratio=.01)
    assert corrected[1]
    assert np.allclose(frames[1].analysis_points[7], (30, 30))


import pytest

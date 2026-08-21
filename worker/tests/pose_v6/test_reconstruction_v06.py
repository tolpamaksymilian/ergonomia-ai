from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v6.temporal_reconstruction import (
    PointSource,
    circle_intersection_nearest,
    merge_flow_result,
    reconstruct_temporal_sequence,
    reject_reconstructed_analysis_joints,
)


def _sequence(frame_count: int = 5) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    points: list[np.ndarray] = []
    scores: list[np.ndarray] = []
    raw_scores: list[np.ndarray] = []
    for index in range(frame_count):
        current = np.zeros((23, 2), dtype=np.float32)
        current[:, 0] = 10.0 + index * 5.0
        current[:, 1] = np.arange(23, dtype=np.float32) * 2.0 + 20.0
        points.append(current)
        scores.append(np.ones(23, dtype=np.float32))
        raw_scores.append(np.ones(23, dtype=np.float32))
    return points, scores, raw_scores


@pytest.mark.parametrize("gap", [1, 2, 3, 5])
def test_synthetic_short_dropouts_are_reconstructed(gap: int) -> None:
    count = gap + 2
    points, scores, raw = _sequence(count)
    for index in range(1, count - 1):
        scores[index][9] = 0.0; raw[index][9] = 0.0
    timestamps = [index / 30 for index in range(count)]
    frames = reconstruct_temporal_sequence(points, scores, raw, timestamps, ["TRACKED"] * count, [False] * count, maximum_interpolation_seconds=0.25)
    assert all(frames[index].analysis_scores[9] > 0.0 for index in range(1, count - 1))
    assert all(frames[index].sources[9] == PointSource.INTERPOLATED for index in range(1, count - 1))


def test_eight_frame_dropout_exceeds_analysis_policy() -> None:
    count = 10; points, scores, raw = _sequence(count)
    for index in range(1, 9):
        scores[index][9] = 0.0; raw[index][9] = 0.0
    frames = reconstruct_temporal_sequence(points, scores, raw, [index / 30 for index in range(count)], ["TRACKED"] * count, [False] * count, maximum_interpolation_seconds=0.25)
    assert frames[4].analysis_scores[9] == 0.0
    assert frames[4].sources[9] == PointSource.MISSING


def test_single_frame_dropout_is_not_measurement() -> None:
    points, scores, raw = _sequence(3); scores[1][9] = 0.0; raw[1][9] = 0.0
    frames = reconstruct_temporal_sequence(points, scores, raw, [0.0, 0.1, 0.2], ["TRACKED"] * 3, [False] * 3, maximum_interpolation_seconds=0.25)
    assert frames[1].analysis_usable[9]
    assert frames[1].sources[9] == PointSource.INTERPOLATED
    assert np.allclose(frames[1].analysis_points[9], [15.0, 38.0])


def test_scene_cut_is_a_hard_reconstruction_boundary() -> None:
    points, scores, raw = _sequence(3); scores[1][9] = 0.0
    frames = reconstruct_temporal_sequence(points, scores, raw, [0.0, 0.1, 0.2], ["TRACKED"] * 3, [False, True, False], maximum_interpolation_seconds=0.25)
    assert not frames[1].analysis_usable[9]


def test_rejected_point_stays_explicit_when_gap_is_not_safe() -> None:
    points, scores, raw = _sequence(3); scores[1][9] = 0.0
    frames = reconstruct_temporal_sequence(points, scores, raw, [0.0, 0.5, 1.0], ["TRACKED"] * 3, [False] * 3, maximum_interpolation_seconds=0.25)
    assert frames[1].sources[9] == PointSource.REJECTED


def test_kinematic_elbow_is_render_only() -> None:
    points, scores, raw = _sequence(5)
    for index in range(5):
        points[index][5] = [0, 0]; points[index][7] = [3, 4]; points[index][9] = [6, 0]
    scores[2][7] = 0.0; raw[2][7] = 0.0
    frames = reconstruct_temporal_sequence(points, scores, raw, [0.0, 0.1, 0.2, 1.1, 1.2], ["TRACKED"] * 5, [False] * 5, maximum_interpolation_seconds=0.25)
    assert frames[2].sources[7] == PointSource.KINEMATIC_PREDICTED
    assert frames[2].render_scores[7] > 0.0
    assert not frames[2].analysis_usable[7]


def test_circle_intersection_preserves_bone_lengths() -> None:
    point = circle_intersection_nearest(np.array([0, 0]), 5.0, np.array([6, 0]), 5.0, np.array([3, 5]))
    assert point is not None
    assert np.linalg.norm(point - np.array([0, 0])) == pytest.approx(5.0)
    assert np.linalg.norm(point - np.array([6, 0])) == pytest.approx(5.0)


def test_failed_bone_validation_removes_flow_only_from_analysis() -> None:
    points, scores, raw = _sequence(3)
    scores[1][9] = 0.0
    raw[1][9] = 0.0
    frames = reconstruct_temporal_sequence(
        points,
        scores,
        raw,
        [0.0, 0.5, 1.0],
        ["TRACKED"] * 3,
        [False] * 3,
        maximum_interpolation_seconds=0.25,
    )
    flowed = merge_flow_result(frames[1], 9, (190.0, 190.0), 0.8, 0.2, 0.1)
    rejected = reject_reconstructed_analysis_joints(flowed, {9})
    assert rejected.sources[9] == PointSource.FLOW_TRACKED
    assert rejected.analysis_scores[9] == 0.0
    assert not rejected.analysis_usable[9]
    assert rejected.render_scores[9] == pytest.approx(0.8)
    assert np.allclose(rejected.render_points[9], [190.0, 190.0])

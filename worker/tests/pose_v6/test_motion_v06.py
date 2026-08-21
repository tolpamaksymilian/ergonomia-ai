from __future__ import annotations

import numpy as np

from worker.src.pose_v6.config import MotionConfig, frames_for_seconds
from worker.src.pose_v6.motion_analysis import MotionAnalyzer, MotionState


def _pose(wrist_x: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.ones(23, dtype=np.float32)
    points[:, 0] = 50.0
    points[:, 1] = np.arange(23)
    points[9] = [wrist_x, 50.0]
    return points, scores, np.array([10, 0, 110, 100], dtype=np.float32)


def test_seconds_policy_is_fps_aware() -> None:
    assert frames_for_seconds(0.2, 15.0) == 3
    assert frames_for_seconds(0.2, 60.0) == 12


def test_fast_wrist_enters_fast_motion_without_changing_acquisition() -> None:
    analyzer = MotionAnalyzer(MotionConfig(fast_threshold_scale_per_second=1.0, extreme_threshold_scale_per_second=4.0))
    points, scores, bbox = _pose(50.0)
    analyzer.update(points, scores, bbox, 0.0)
    points, scores, bbox = _pose(80.0)
    result = analyzer.update(points, scores, bbox, 0.1)
    assert result.state == MotionState.FAST_MOTION
    assert result.gate_multiplier > 1.0


def test_camera_translation_is_removed_from_body_motion() -> None:
    analyzer = MotionAnalyzer(MotionConfig())
    points, scores, bbox = _pose(50.0)
    analyzer.update(points, scores, bbox, 0.0)
    moved = points + np.array([20.0, 0.0], dtype=np.float32)
    moved_bbox = bbox + np.array([20.0, 0.0, 20.0, 0.0], dtype=np.float32)
    result = analyzer.update(moved, scores, moved_bbox, 0.1, camera_translation=(20.0, 0.0))
    assert result.state == MotionState.NORMAL_MOTION

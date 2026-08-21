from __future__ import annotations

import numpy as np

from worker.src.pose_v6.temporal_tracker import (
    BBoxMotionEstimator,
    BBoxSource,
    recovery_allowed,
)


def test_predicted_bbox_follows_velocity_and_scale() -> None:
    tracker = BBoxMotionEstimator(alpha=1.0, beta=1.0)
    tracker.observe(np.array([10, 10, 50, 90], dtype=np.float32), 0.0)
    tracker.observe(np.array([20, 10, 64, 98], dtype=np.float32), 0.1)
    predicted = tracker.predict(0.2, frame_width=300, frame_height=200)
    assert predicted is not None
    assert predicted.source == BBoxSource.TRACK_PREDICTED
    assert predicted.bbox_xyxy[0] > 20
    assert predicted.bbox_xyxy[2] - predicted.bbox_xyxy[0] > 44


def test_short_detector_miss_allows_recovery_for_locked_track() -> None:
    tracker = BBoxMotionEstimator()
    tracker.observe(np.array([20, 10, 80, 150], dtype=np.float32), 0.0)
    prediction = tracker.predict(0.2, frame_width=320, frame_height=200)
    assert recovery_allowed(prediction, tracking_state="TRACKED", scene_cut=False, maximum_age_seconds=0.4)


def test_long_detector_miss_is_hard_lost() -> None:
    tracker = BBoxMotionEstimator()
    tracker.observe(np.array([20, 10, 80, 150], dtype=np.float32), 0.0)
    prediction = tracker.predict(1.0, frame_width=320, frame_height=200)
    assert not recovery_allowed(prediction, tracking_state="TRACKED", scene_cut=False, maximum_age_seconds=0.4)


def test_scene_cut_and_lost_block_recovery() -> None:
    tracker = BBoxMotionEstimator()
    tracker.observe(np.array([20, 10, 80, 150], dtype=np.float32), 0.0)
    prediction = tracker.predict(0.1, frame_width=320, frame_height=200)
    assert not recovery_allowed(prediction, tracking_state="TRACKED", scene_cut=True, maximum_age_seconds=0.4)
    assert not recovery_allowed(prediction, tracking_state="LOST", scene_cut=False, maximum_age_seconds=0.4)


def test_person_exit_clips_then_rejects_degenerate_roi() -> None:
    tracker = BBoxMotionEstimator(alpha=1.0, beta=1.0)
    tracker.observe(np.array([240, 20, 300, 180], dtype=np.float32), 0.0)
    tracker.observe(np.array([280, 20, 318, 180], dtype=np.float32), 0.1)
    assert tracker.predict(0.5, frame_width=320, frame_height=200) is None

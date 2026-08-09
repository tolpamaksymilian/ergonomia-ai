from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v3.tracking import (
    PersonTrackingStateMachine,
    TrackingConfig,
    TrackingState,
    bbox_iou,
)


def _update(tracker, points, scores, bbox=None, detected=True, quality=0.95):
    return tracker.update(
        detected=detected,
        bbox=np.asarray(bbox or [200, 50, 440, 590], dtype=np.float32) if detected else None,
        points=points,
        scores=scores,
        frame_width=640,
        frame_height=600,
        candidate_quality=quality,
    )


def test_initial_detection_requires_temporal_confirmation(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=3))
    assert _update(tracker, body_points, body_scores).state == TrackingState.REACQUIRING
    assert _update(tracker, body_points, body_scores).accept_pose is False
    assert _update(tracker, body_points, body_scores).state == TrackingState.TRACKED


def test_confirmed_track_accepts_pose(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1))
    assert _update(tracker, body_points, body_scores).accept_pose is True


def test_short_missing_segment_is_occluded(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1, lost_after_missing_frames=2))
    _update(tracker, body_points, body_scores)
    decision = _update(tracker, body_points, body_scores, detected=False)
    assert decision.state == TrackingState.OCCLUDED
    assert decision.accept_pose is False


def test_long_missing_segment_becomes_lost(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1, lost_after_missing_frames=1))
    _update(tracker, body_points, body_scores)
    _update(tracker, body_points, body_scores, detected=False)
    assert _update(tracker, body_points, body_scores, detected=False).state == TrackingState.LOST
    assert tracker.track_loss_count == 1


def test_return_after_loss_requires_reacquisition(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=2, lost_after_missing_frames=0))
    _update(tracker, body_points, body_scores)
    _update(tracker, body_points, body_scores)
    _update(tracker, body_points, body_scores, detected=False)
    assert _update(tracker, body_points, body_scores).state == TrackingState.REACQUIRING
    assert _update(tracker, body_points, body_scores).accept_pose is True
    assert tracker.reacquisition_count == 1


@pytest.mark.parametrize(
    ("index", "coordinate"),
    [(9, (-2, 300)), (10, (641, 300)), (0, (320, -1)), (15, (280, 601))],
)
def test_out_of_frame_sides_enter_partial(index, coordinate, body_points, body_scores):
    points = body_points.copy()
    points[index] = coordinate
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1))
    decision = _update(tracker, points, body_scores)
    assert decision.state == TrackingState.PARTIAL
    assert decision.partial is True


def test_far_second_person_does_not_take_track(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1))
    _update(tracker, body_points, body_scores, bbox=[180, 40, 420, 590])
    decision = _update(tracker, body_points, body_scores, bbox=[500, 50, 630, 580], quality=0.7)
    assert decision.accept_pose is False


def test_distant_return_after_confirmed_loss_can_be_reacquired(body_points, body_scores):
    tracker = PersonTrackingStateMachine(
        TrackingConfig(reacquire_confirm_frames=2, lost_after_missing_frames=0)
    )
    _update(tracker, body_points, body_scores, bbox=[100, 40, 340, 590])
    _update(tracker, body_points, body_scores, bbox=[102, 40, 342, 590])
    _update(tracker, body_points, body_scores, detected=False)
    first = _update(tracker, body_points, body_scores, bbox=[350, 40, 590, 590])
    second = _update(tracker, body_points, body_scores, bbox=[352, 40, 592, 590])
    assert first.state == TrackingState.REACQUIRING
    assert first.accept_pose is False
    assert second.accept_pose is True
    assert tracker.reacquisition_count == 1


def test_single_large_bbox_scale_change_is_not_accepted(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1))
    _update(tracker, body_points, body_scores, bbox=[180, 40, 460, 590])
    decision = _update(
        tracker,
        body_points,
        body_scores,
        bbox=[290, 250, 350, 370],
        quality=0.70,
    )
    assert decision.accept_pose is False


def test_body_proportion_mismatch_does_not_take_active_track(body_points, body_scores):
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1))
    _update(tracker, body_points, body_scores)
    mismatched = body_points.copy()
    mismatched[5] = (315, 150)
    mismatched[6] = (325, 150)
    mismatched[11] = (230, 320)
    mismatched[12] = (410, 320)
    decision = _update(tracker, mismatched, body_scores, quality=0.70)
    assert decision.accept_pose is False
    assert "BODY_PROPORTION_MISMATCH" in decision.reasons


def test_insufficient_visible_joints_is_not_accepted(body_points, body_scores):
    scores = body_scores.copy()
    scores[:23] = 0.0
    scores[:4] = 0.95
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=1))
    assert _update(tracker, body_points, scores).accept_pose is False


def test_bbox_iou_is_exact_for_equal_boxes():
    box = np.asarray([1, 2, 10, 20], dtype=np.float32)
    assert bbox_iou(box, box) == pytest.approx(1.0)


def test_bbox_iou_is_zero_for_disjoint_boxes():
    assert bbox_iou(np.asarray([0, 0, 2, 2]), np.asarray([3, 3, 5, 5])) == 0.0

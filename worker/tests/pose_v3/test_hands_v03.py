from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v3.hand_object.holding import GripState, compute_grip_features
from worker.src.pose_v3.hand_pipeline import (
    HandObservation,
    HandPipelineConfig,
    HandPipelineResult,
    HandTrackSummary,
    RawHandFrame,
    ValidatedHandFrame,
    _Candidate,
    assign_hands_to_body,
    enhance_hand_track,
    stabilize_hand_track,
)

from .conftest import make_hand


def _result(frames):
    count = len(frames)
    return HandPipelineResult(
        frames=frames,
        summary=HandTrackSummary(
            "left", count, count, count, 0, 0, 1.0, 1.0, 0.9, {}
        ),
    )


def _config(**values):
    defaults = {"model_path": __import__("pathlib").Path("unused.task")}
    defaults.update(values)
    return HandPipelineConfig(**defaults)


def test_hand_reacquisition_hides_first_detection():
    result = enhance_hand_track(
        _result([make_hand(), make_hand()]),
        frame_width=640,
        frame_height=600,
        config=_config(reacquire_confirm_frames=2),
    )
    assert result.frames[0].visible is False
    assert result.frames[0].tracking_state == "HAND_REACQUIRING"
    assert result.frames[1].visible is True


def test_hand_edge_invalidates_only_affected_fingertip():
    hand = make_hand()
    hand.points_px[8] = (2, 70)
    result = enhance_hand_track(
        _result([hand]), frame_width=640, frame_height=600,
        config=_config(reacquire_confirm_frames=1),
    )
    assert result.frames[0].visible is True
    assert not bool(result.frames[0].point_validity[8])
    assert bool(result.frames[0].point_validity[12])


def test_hand_with_palm_out_of_frame_is_hidden():
    hand = make_hand()
    hand.points_px[[0, 5, 9]] = (-5, 100)
    result = enhance_hand_track(
        _result([hand]), frame_width=640, frame_height=600,
        config=_config(reacquire_confirm_frames=1),
    )
    assert result.frames[0].visible is False


def test_single_finger_segment_outlier_does_not_destroy_other_fingers():
    hand = make_hand()
    hand.points_px[8] = (300, 20)
    result = enhance_hand_track(
        _result([hand]), frame_width=640, frame_height=600,
        config=_config(reacquire_confirm_frames=1),
    )
    frame = result.frames[0]
    assert not bool(frame.point_validity[8])
    assert bool(frame.point_validity[12])


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("open", GripState.OPEN), ("closed", GripState.CLOSED), ("pinch", GripState.PINCH)],
)
def test_grip_state_classification(kind, expected):
    assert compute_grip_features(make_hand(kind)).grip_state == expected


def test_low_quality_hand_has_unknown_grip():
    assert compute_grip_features(make_hand("closed", quality=0.2)).grip_state == GripState.UNKNOWN


def test_missing_required_fingertips_has_unknown_grip():
    hand = make_hand("closed")
    hand.point_validity[[4, 8, 12]] = False
    assert compute_grip_features(hand).grip_state == GripState.UNKNOWN


def test_grip_stability_decreases_after_large_translation():
    first = compute_grip_features(make_hand("closed"))
    second_hand = make_hand("closed")
    second_hand.points_px += (80, 0)
    second = compute_grip_features(second_hand, first)
    assert second.grip_stability < first.grip_stability


def test_point_reasons_use_controlled_edge_code():
    hand = make_hand()
    hand.points_px[8] = (1, 70)
    result = enhance_hand_track(
        _result([hand]), frame_width=640, frame_height=600,
        config=_config(reacquire_confirm_frames=1),
    )
    assert result.frames[0].point_reasons[8] == "EDGE_UNCERTAIN"


def test_one_fast_fingertip_does_not_reject_the_whole_palm():
    raw_frames = []
    for index in range(5):
        points = make_hand().points_px.copy()
        if index == 2:
            points[8, 0] += 25
        observation = HandObservation(
            points_px=points,
            world_points=np.zeros((21, 3), dtype=np.float32),
            handedness_label="Left",
            handedness_score=0.9,
            body_wrist=points[0].copy(),
            forearm_length=200.0,
            root_wrist_distance_ratio=0.0,
            palm_scale=42.0,
            orientation_degrees=-90.0,
            assignment_score=0.0,
        )
        raw_frames.append(RawHandFrame(observation, index / 10.0, True))
    result = stabilize_hand_track(
        "left",
        raw_frames,
        _config(
            min_lock_frames=1,
            max_joint_velocity_palm_ratio=0.20,
            bone_log_tolerance=2.0,
            max_bone_outliers=3,
        ),
    )
    assert result.frames[2].visible is True


def test_long_missing_hand_segment_is_not_interpolated():
    frames = [make_hand(), make_hand()]
    missing = ValidatedHandFrame(
        False,
        False,
        np.zeros((21, 2), dtype=np.float32),
        np.zeros((21, 3), dtype=np.float32),
        0.0,
        ["missing"],
        None,
        0.0,
    )
    result = enhance_hand_track(
        _result([frames[0], missing, missing, frames[1]]),
        frame_width=640,
        frame_height=600,
        config=_config(reacquire_confirm_frames=2),
    )
    assert result.frames[1].visible is False
    assert result.frames[2].visible is False
    assert result.frames[3].tracking_state == "HAND_REACQUIRING"


def test_crossing_hands_use_temporal_centers_before_soft_handedness(
    body_points, body_scores
):
    crossed_body = body_points.copy()
    crossed_body[9] = (320, 315)
    crossed_body[10] = (320, 315)
    left_points = make_hand().points_px.copy() + np.asarray((210, 155))
    right_points = make_hand().points_px.copy() + np.asarray((230, 155))
    left_center = np.mean(left_points[[0, 5, 9, 13, 17]], axis=0)
    right_center = np.mean(right_points[[0, 5, 9, 13, 17]], axis=0)
    candidates = [
        _Candidate(left_points, np.zeros((21, 3), dtype=np.float32), "Right", 0.2),
        _Candidate(right_points, np.zeros((21, 3), dtype=np.float32), "Left", 0.2),
    ]
    result = assign_hands_to_body(
        candidates,
        crossed_body,
        body_scores,
        0.5,
        _config(assignment_max_wrist_distance_ratio=1.2),
        0.0,
        previous_palm_centers={"left": left_center, "right": right_center},
    )
    assert result["left"].observation is not None
    assert result["right"].observation is not None
    assert np.allclose(result["left"].observation.points_px, left_points)
    assert np.allclose(result["right"].observation.points_px, right_points)

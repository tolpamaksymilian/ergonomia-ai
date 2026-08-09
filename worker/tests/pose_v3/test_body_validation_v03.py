from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v3.body_validation import (
    BodyProportionProfile,
    BodyValidationConfig,
    BodyValidator,
    serialize_body_validation,
)
from worker.src.pose_v3.smoothing import smooth_body_sequence
from worker.src.pose_v3.tracking import TrackingDecision, TrackingState


BBOX = np.asarray([180, 40, 460, 590], dtype=np.float32)


def test_valid_body_produces_joint_quality(body_points, body_scores, tracked_decision):
    result = BodyValidator(BodyValidationConfig()).validate(
        body_points, body_scores, BBOX, tracked_decision, 640, 600
    )
    assert result.valid_joint_ratio > 0.9
    assert 0.0 < result.quality <= 1.0


@pytest.mark.parametrize("coordinate", [(-1, 200), (641, 200), (200, -3), (200, 605)])
def test_out_of_frame_joint_is_invalid(coordinate, body_points, body_scores, tracked_decision):
    points = body_points.copy()
    points[9] = coordinate
    result = BodyValidator(BodyValidationConfig()).validate(
        points, body_scores, BBOX, tracked_decision, 640, 600
    )
    assert result.joints[9].valid is False
    assert result.joints[9].reason == "OUT_OF_FRAME"


def test_low_confidence_joint_is_invalid(body_points, body_scores, tracked_decision):
    scores = body_scores.copy()
    scores[9] = 0.2
    result = BodyValidator(BodyValidationConfig()).validate(
        body_points, scores, BBOX, tracked_decision, 640, 600
    )
    assert result.joints[9].reason == "LOW_CONFIDENCE"


def test_occluded_tracking_state_has_distinct_rejection_reason(body_points, body_scores):
    decision = TrackingDecision(
        TrackingState.OCCLUDED,
        False,
        0.0,
        0,
        False,
        ("PERSON_NOT_DETECTED",),
    )
    result = BodyValidator(BodyValidationConfig()).validate(
        body_points, body_scores, BBOX, decision, 640, 600
    )
    assert result.joints[9].reason == "OCCLUDED"


def test_edge_uncertain_joint_is_invalid(body_points, body_scores, tracked_decision):
    points = body_points.copy()
    points[9] = (3, 300)
    scores = body_scores.copy()
    scores[9] = 0.85
    result = BodyValidator(BodyValidationConfig()).validate(
        points, scores, BBOX, tracked_decision, 640, 600
    )
    assert result.joints[9].reason == "EDGE_UNCERTAIN"


def test_teleporting_wrist_is_rejected(body_points, body_scores, tracked_decision):
    validator = BodyValidator(BodyValidationConfig(maximum_joint_velocity_bbox_ratio=0.15))
    validator.validate(body_points, body_scores, BBOX, tracked_decision, 640, 600)
    moved = body_points.copy()
    moved[9] = (500, 315)
    result = validator.validate(moved, body_scores, BBOX, tracked_decision, 640, 600)
    assert result.joints[9].reason == "JOINT_VELOCITY_OUTLIER"


def test_person_specific_profile_uses_robust_median():
    profile = BodyProportionProfile()
    for value in (0.20, 0.21, 0.19, 0.205):
        assert profile.add("left_forearm", value)
    assert profile.add("left_forearm", 1.1) is False
    assert profile.expected("left_forearm") == pytest.approx(0.2025)


def test_bone_outlier_invalidates_child_after_profile(body_points, body_scores, tracked_decision):
    config = BodyValidationConfig(maximum_joint_velocity_bbox_ratio=2.0, maximum_joint_acceleration_bbox_ratio=2.0)
    validator = BodyValidator(config)
    for _ in range(5):
        validator.validate(body_points, body_scores, BBOX, tracked_decision, 640, 600)
    changed = body_points.copy()
    changed[9] = (30, 315)
    result = validator.validate(changed, body_scores, BBOX, tracked_decision, 640, 600)
    assert result.bones["left_forearm"].valid is False
    assert result.scores[9] == 0.0


def test_foot_bone_outlier_is_rejected_before_overlay(body_points, body_scores, tracked_decision):
    config = BodyValidationConfig(
        maximum_joint_velocity_bbox_ratio=2.0,
        maximum_joint_acceleration_bbox_ratio=2.0,
    )
    validator = BodyValidator(config)
    for _ in range(5):
        validator.validate(body_points, body_scores, BBOX, tracked_decision, 640, 600)
    changed = body_points.copy()
    changed[17] = (500, 565)
    result = validator.validate(changed, body_scores, BBOX, tracked_decision, 640, 600)
    assert result.bones["left_ankle_big_toe"].valid is False
    assert result.scores[17] == 0.0


def test_implausible_bone_direction_flip_is_rejected(body_points, body_scores, tracked_decision):
    validator = BodyValidator(
        BodyValidationConfig(
            maximum_joint_velocity_bbox_ratio=2.0,
            maximum_joint_acceleration_bbox_ratio=2.0,
            maximum_bone_direction_change_degrees=100.0,
        )
    )
    validator.validate(body_points, body_scores, BBOX, tracked_decision, 640, 600)
    flipped = body_points.copy()
    flipped[9] = (255, 155)
    result = validator.validate(flipped, body_scores, BBOX, tracked_decision, 640, 600)
    assert result.bones["left_forearm"].reason == "BONE_DIRECTION_OUTLIER"
    assert result.scores[9] == 0.0


def test_serialization_contains_joint_and_bone_diagnostics(body_points, body_scores, tracked_decision):
    result = BodyValidator(BodyValidationConfig()).validate(
        body_points, body_scores, BBOX, tracked_decision, 640, 600
    )
    serialized = serialize_body_validation(result)
    assert len(serialized["joints"]) == 23
    assert "left_forearm" in serialized["bones"]


def test_short_safe_gap_is_interpolated(body_points, body_scores):
    points = [body_points.copy() for _ in range(3)]
    scores = [body_scores.copy() for _ in range(3)]
    scores[1][9] = 0.0
    smoothed_points, smoothed_scores, interpolated = smooth_body_sequence(
        points, scores, ["TRACKED"] * 3, frame_width=640, frame_height=600
    )
    assert interpolated[1][9]
    assert smoothed_scores[1][9] > 0.0
    assert np.isfinite(smoothed_points[1][9]).all()


@pytest.mark.parametrize("state", ["LOST", "REACQUIRING"])
def test_gap_during_lost_or_reacquiring_is_not_interpolated(state, body_points, body_scores):
    points = [body_points.copy() for _ in range(3)]
    scores = [body_scores.copy() for _ in range(3)]
    scores[1][9] = 0.0
    _, output_scores, interpolated = smooth_body_sequence(
        points, scores, ["TRACKED", state, "TRACKED"], frame_width=640, frame_height=600
    )
    assert not interpolated[1][9]
    assert output_scores[1][9] == 0.0


def test_long_gap_is_not_interpolated(body_points, body_scores):
    points = [body_points.copy() for _ in range(5)]
    scores = [body_scores.copy() for _ in range(5)]
    for index in (1, 2, 3):
        scores[index][9] = 0.0
    _, output_scores, _ = smooth_body_sequence(
        points, scores, ["TRACKED"] * 5, frame_width=640, frame_height=600, maximum_gap_frames=2
    )
    assert all(output_scores[index][9] == 0.0 for index in (1, 2, 3))


def test_bidirectional_smoothing_reduces_single_frame_jitter(body_points, body_scores):
    points = [body_points.copy() for _ in range(5)]
    points[2][9, 0] += 25
    output, _, _ = smooth_body_sequence(
        points, [body_scores.copy() for _ in range(5)], ["TRACKED"] * 5,
        frame_width=640, frame_height=600,
    )
    assert abs(float(output[2][9, 0]) - float(body_points[9, 0])) < 25

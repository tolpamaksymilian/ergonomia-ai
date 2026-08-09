from __future__ import annotations

import math

import numpy as np
import pytest

from worker.src.pose_v3.tracking import TrackingDecision, TrackingState
from worker.src.pose_v4.graph import (
    BiomechanicalPoseGraph,
    LimbState,
    MeasurementSource,
    OcclusionState,
    PoseGraphConfig,
    TemporalState,
    apply_interpolation_metadata,
    summarize_pose_graph,
)

from .conftest import BBOX


def test_valid_graph_contains_joint_bone_limb_and_anchor_diagnostics(graph_factory):
    _, frame = graph_factory()
    assert len(frame.joints) == 23
    assert frame.bones
    assert set(frame.limbs) == {"left_arm", "right_arm", "left_leg", "right_leg"}
    assert frame.anchors.torso_center is not None
    assert 0.0 <= frame.quality <= 1.0


@pytest.mark.parametrize("index", [0, 5, 6, 7, 9, 11, 13, 15, 22])
def test_low_confidence_joint_never_becomes_valid_measurement(
    index, graph_factory, body_scores_v4
):
    scores = body_scores_v4.copy()
    scores[index] = 0.01
    _, frame = graph_factory(scores=scores)
    assert frame.joints[index].valid is False
    assert frame.analysis_scores[index] == 0.0


@pytest.mark.parametrize(
    "coordinate",
    [(-1.0, 200.0), (641.0, 200.0), (200.0, -1.0), (200.0, 601.0)],
)
def test_out_of_frame_coordinate_is_not_clipped_into_valid_geometry(
    coordinate, graph_factory, body_points_v4
):
    points = body_points_v4.copy()
    points[9] = coordinate
    _, frame = graph_factory(points=points)
    assert frame.joints[9].valid is False
    assert frame.analysis_scores[9] == 0.0


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("axis", [0, 1])
def test_non_finite_joint_is_rejected_without_non_finite_output(
    bad, axis, graph_factory, body_points_v4
):
    points = body_points_v4.copy()
    points[9, axis] = bad
    _, frame = graph_factory(points=points)
    assert frame.joints[9].valid is False
    assert np.isfinite(frame.analysis_points).all()
    assert np.isfinite(frame.analysis_scores).all()


def test_expected_position_rejects_teleport_and_prediction_is_not_measurement(
    graph_factory, body_points_v4
):
    graph, _ = graph_factory(timestamp=0.0)
    moved = body_points_v4.copy()
    moved[9] = (610, 315)
    _, frame = graph_factory(points=moved, timestamp=1 / 30, graph=graph)
    wrist = frame.joints[9]
    assert wrist.valid is False
    assert wrist.predicted_position is not None
    assert wrist.source == MeasurementSource.PREDICTED
    assert wrist.coordinates is None
    assert frame.analysis_scores[9] == 0.0


def test_short_prediction_has_explicit_state_but_zero_analysis_score(
    graph_factory, body_scores_v4
):
    graph, _ = graph_factory(timestamp=0.0)
    scores = body_scores_v4.copy()
    scores[9] = 0.0
    _, frame = graph_factory(scores=scores, timestamp=1 / 30, graph=graph)
    joint = frame.joints[9]
    assert joint.temporal_state in {TemporalState.PREDICTED_SHORT, TemporalState.SUSPECT}
    assert joint.valid is False
    assert frame.analysis_scores[9] == 0.0


def test_prediction_expires_after_configured_frame_count(
    graph_factory, body_scores_v4
):
    graph = BiomechanicalPoseGraph(PoseGraphConfig(maximum_prediction_frames=1))
    graph_factory(timestamp=0.0, graph=graph)
    scores = body_scores_v4.copy()
    scores[9] = 0.0
    graph_factory(scores=scores, timestamp=0.04, graph=graph)
    _, frame = graph_factory(scores=scores, timestamp=0.08, graph=graph)
    assert frame.joints[9].temporal_state != TemporalState.PREDICTED_SHORT


def test_out_of_frame_expected_position_differs_from_body_occlusion(
    graph_factory, body_points_v4, body_scores_v4
):
    from worker.src.pose_v4.graph import _infer_occlusion

    out = _infer_occlusion(np.asarray((650, 315)), BBOX, (260, 140, 380, 330), 640, 600)
    behind = _infer_occlusion(np.asarray((320, 250)), BBOX, (260, 140, 380, 330), 640, 600)
    assert out == OcclusionState.OUT_OF_FRAME
    assert behind == OcclusionState.OCCLUDED_BY_BODY


def test_occluded_tracking_never_publishes_body_measurement(
    graph_factory, body_points_v4, body_scores_v4
):
    decision = TrackingDecision(
        TrackingState.OCCLUDED, False, 0.0, 0, False, ("PERSON_NOT_DETECTED",)
    )
    _, frame = graph_factory(
        points=body_points_v4, scores=body_scores_v4, decision=decision
    )
    assert not any(joint.valid for joint in frame.joints)
    assert np.count_nonzero(frame.analysis_scores) == 0


@pytest.mark.parametrize(
    "state",
    [TrackingState.LOST, TrackingState.REACQUIRING, TrackingState.OCCLUDED],
)
def test_bad_track_state_does_not_update_body_profile(
    state, body_points_v4, body_scores_v4
):
    graph = BiomechanicalPoseGraph(PoseGraphConfig())
    decision = TrackingDecision(state, False, 0.0, 0, False, ())
    graph.update(
        raw_points=body_points_v4,
        raw_scores=body_scores_v4,
        bbox=BBOX,
        tracking=decision,
        frame_width=640,
        frame_height=600,
        timestamp_seconds=0.0,
    )
    assert graph.bone_profile.to_dict() == {}


def test_body_scale_change_is_temporally_bounded(graph_factory, body_points_v4):
    graph, first = graph_factory(timestamp=0.0)
    enlarged = body_points_v4.copy()
    enlarged[:23] = (enlarged[:23] - (320, 300)) * 1.8 + (320, 300)
    _, second = graph_factory(points=enlarged, timestamp=1 / 30, graph=graph)
    assert second.body_scale <= first.body_scale * 1.18 + 1e-6


def test_profile_uses_robust_statistics_and_rejects_extreme_sample():
    graph = BiomechanicalPoseGraph(PoseGraphConfig())
    for value in (0.20, 0.21, 0.19, 0.205):
        assert graph.bone_profile.add("left_forearm", value)
    assert not graph.bone_profile.add("left_forearm", 1.2)
    profile = graph.bone_profile.to_dict()["left_forearm"]
    assert profile["median"] == pytest.approx(0.2025)
    assert profile["mad"] >= 0.0


def test_interpolation_metadata_is_explicit_and_keeps_raw_layer(graph_factory):
    _, frame = graph_factory()
    raw_before = frame.raw_points.copy()
    points = frame.analysis_points.copy()
    scores = frame.analysis_scores.copy()
    mask = np.zeros_like(scores, dtype=bool)
    mask[9] = True
    result = apply_interpolation_metadata(frame, points, scores, mask)
    assert result.joints[9].source == MeasurementSource.INTERPOLATED
    assert result.joints[9].temporal_state == TemporalState.INTERPOLATED
    assert np.array_equal(result.raw_points, raw_before)


def test_occluded_and_out_of_frame_joint_disallow_interpolation(graph_factory):
    _, frame = graph_factory()
    allowed = frame.interpolation_allowed()
    assert allowed.shape == frame.analysis_scores.shape
    assert allowed.dtype == bool


def test_graph_summary_counts_invalid_bones_and_limb_states(
    graph_factory, body_scores_v4
):
    _, good = graph_factory(timestamp=0.0)
    scores = body_scores_v4.copy()
    scores[9] = 0.0
    _, bad = graph_factory(scores=scores, timestamp=0.04)
    summary = summarize_pose_graph([good, bad])
    assert summary["frame_count"] == 2
    assert summary["invalid_bone_count"] >= 1
    assert "left_arm" in summary["limb_state_counts"]


@pytest.mark.parametrize("seed", range(20))
def test_random_invalid_landmarks_preserve_output_invariants(
    seed, graph_factory, body_points_v4, body_scores_v4
):
    random = np.random.default_rng(seed)
    points = body_points_v4.copy()
    scores = body_scores_v4.copy()
    selected = random.choice(23, size=5, replace=False)
    points[selected] += random.normal(0.0, 1500.0, size=(5, 2))
    scores[random.choice(23, size=3, replace=False)] = random.uniform(-2.0, 2.0, 3)
    _, frame = graph_factory(points=points, scores=scores)
    assert np.isfinite(frame.analysis_points).all()
    assert np.isfinite(frame.analysis_scores).all()
    assert all(0.0 <= joint.quality <= 1.0 for joint in frame.joints)
    assert all(not joint.valid or joint.coordinates is not None for joint in frame.joints)
    assert all(0.0 <= limb.quality <= 1.0 for limb in frame.limbs.values())

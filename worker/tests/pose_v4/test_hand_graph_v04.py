from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from worker.src.pose_v3.hand_pipeline import HandPipelineConfig, RawHandFrame, _Candidate
from worker.src.pose_v4.hand_graph import (
    FINGER_CHAINS,
    FingerVisibility,
    GripStateV2,
    HandAssignmentMemory,
    HandGraphConfig,
    HandOcclusion,
    PalmScaleProfile,
    analyze_hand_graph_frame,
    assign_hands_to_body_v2,
    compute_grip_features_v2,
    compute_palm_frame,
    predict_hand_rois,
    union_hand_roi,
)
from worker.src.pose_v4.object_tracking import TrackedObject

from .conftest import make_hand_v4


def _pipeline_config() -> HandPipelineConfig:
    return HandPipelineConfig(model_path=Path("unused.task"))


def _object(center=(100.0, 110.0), velocity=(0.0, 0.0)) -> TrackedObject:
    x, y = center
    return TrackedObject(1, 39, "bottle", (x - 20, y - 20, x + 20, y + 20), 0.8, center, velocity, 3, 0)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("open", GripStateV2.OPEN),
        ("closed", GripStateV2.CLOSED),
        ("pinch", GripStateV2.PRECISION_PINCH_CANDIDATE),
    ],
)
def test_grip_v2_classifies_distinct_geometry(kind, expected):
    hand = make_hand_v4(kind)
    palm = compute_palm_frame(hand)
    fingers = {
        name: analyze_hand_graph_frame_finger(hand, name, chain)
        for name, chain in FINGER_CHAINS.items()
    }
    assert compute_grip_features_v2(hand, palm, fingers, None).state == expected


def analyze_hand_graph_frame_finger(hand, name, chain):
    from worker.src.pose_v4.hand_graph import _finger_diagnostic

    return _finger_diagnostic(name, chain, hand, None, HandOcclusion.VISIBLE)


def test_palm_frame_contains_scale_orientation_and_base_directions():
    palm = compute_palm_frame(make_hand_v4())
    assert palm.center is not None
    assert palm.width and palm.width > 0
    assert palm.height and palm.height > 0
    assert palm.scale and palm.scale > 0
    assert set(palm.base_directions) == set(FINGER_CHAINS)


def test_zero_world_geometry_does_not_claim_relative_normal():
    palm = compute_palm_frame(make_hand_v4())
    assert palm.normal_signal is None


def test_nonzero_world_geometry_exposes_only_relative_normal_signal():
    hand = make_hand_v4()
    hand.world_points[0] = (0, 0, 0)
    hand.world_points[5] = (1, 0, 0)
    hand.world_points[17] = (0, 1, 0)
    palm = compute_palm_frame(hand)
    assert palm.normal_signal == pytest.approx((0.0, 0.0, 1.0))


@pytest.mark.parametrize("finger", list(FINGER_CHAINS))
def test_each_finger_chain_is_validated_independently(finger, graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4()
    tip = FINGER_CHAINS[finger][-1]
    hand.point_validity[tip] = False
    hand.point_reasons = tuple(
        "TEMPORAL_OUTLIER" if index == tip else None for index in range(21)
    )
    graph = analyze_hand_graph_frame(
        "left", hand, body, [], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert graph.fingers[finger].state == FingerVisibility.PARTIAL
    assert all(
        diagnostic.state == FingerVisibility.VISIBLE
        for name, diagnostic in graph.fingers.items()
        if name != finger
    )


@pytest.mark.parametrize("finger", list(FINGER_CHAINS))
def test_missing_finger_near_object_is_occluded_not_reconstructed(finger, graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4()
    for index in FINGER_CHAINS[finger][2:]:
        hand.point_validity[index] = False
    graph = analyze_hand_graph_frame(
        "left", hand, body, [_object()], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert graph.fingers[finger].state == FingerVisibility.OCCLUDED
    assert graph.source_frame.point_validity[FINGER_CHAINS[finger][-1]] == np.bool_(False)


def test_bad_tip_does_not_invalidate_palm(graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4()
    hand.point_validity[8] = False
    graph = analyze_hand_graph_frame(
        "left", hand, body, [], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert graph.visible
    assert graph.palm_quality >= HandGraphConfig().minimum_palm_quality


def test_insufficient_mcp_geometry_hides_hand(graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4()
    hand.point_validity[[5, 9, 13]] = False
    graph = analyze_hand_graph_frame(
        "left", hand, body, [], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert not graph.visible


def test_hand_center_outside_frame_is_out_of_frame(graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4()
    hand.points_px += (700, 0)
    graph = analyze_hand_graph_frame(
        "left", hand, body, [], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert graph.occlusion_state == HandOcclusion.OUT_OF_FRAME
    assert not graph.visible


def test_missing_tips_near_object_marks_hand_occlusion(graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4("closed")
    hand.point_validity[[8, 12, 16]] = False
    graph = analyze_hand_graph_frame(
        "left", hand, body, [_object()], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert graph.occlusion_state == HandOcclusion.OCCLUDED_BY_OBJECT


def test_nearest_object_keeps_track_class_confidence_and_velocity(graph_factory):
    _, body = graph_factory()
    graph = analyze_hand_graph_frame(
        "left", make_hand_v4(), body, [_object(velocity=(12, 5))], None,
        PalmScaleProfile(), None, HandGraphConfig(),
    )
    assert graph.nearest_object_track_id == 1
    assert graph.nearest_object_class == "bottle"
    assert graph.nearest_object_confidence == pytest.approx(0.8)
    assert graph.nearest_object_velocity == (12, 5)


def test_far_object_is_not_associated(graph_factory):
    _, body = graph_factory()
    graph = analyze_hand_graph_frame(
        "left", make_hand_v4(), body, [_object((600, 500))], None,
        PalmScaleProfile(), None, HandGraphConfig(),
    )
    assert graph.nearest_object_track_id is None


def test_adaptive_roi_uses_wrist_and_is_inside_frame(
    graph_factory, body_points_v4, body_scores_v4
):
    _, body = graph_factory()
    rois = predict_hand_rois(
        body.analysis_points, body.analysis_scores,
        body_threshold=0.01, frame_width=640, frame_height=600,
        timestamp_seconds=0.0, memory=HandAssignmentMemory(),
        config=HandGraphConfig(),
    )
    assert set(rois) == {"left", "right"}
    assert all(0 <= x1 < x2 <= 640 and 0 <= y1 < y2 <= 600 for x1, y1, x2, y2 in rois.values())


def test_union_roi_contains_both_hand_rois():
    rois = {"left": (10, 20, 100, 120), "right": (300, 40, 390, 150)}
    assert union_hand_roi(rois, frame_width=400, frame_height=200) == (10, 20, 390, 150)


def test_empty_roi_set_returns_none():
    assert union_hand_roi({}, frame_width=400, frame_height=200) is None


def _candidate(hand, label):
    return _Candidate(hand.points_px.copy(), hand.world_points.copy(), label, 0.9)


def test_global_assignment_handles_both_hands(graph_factory):
    _, body = graph_factory()
    left = make_hand_v4()
    left.points_px += np.asarray((115, 155))
    right = make_hand_v4()
    right.points_px += np.asarray((325, 155))
    assignments = assign_hands_to_body_v2(
        [_candidate(left, "Right"), _candidate(right, "Left")],
        body.analysis_points, body.analysis_scores, 0.01,
        _pipeline_config(), HandGraphConfig(), 0.0, HandAssignmentMemory(),
    )
    assert assignments["left"].observation is not None
    assert assignments["right"].observation is not None


def test_assignment_with_no_candidates_returns_explicit_missing(graph_factory):
    _, body = graph_factory()
    result = assign_hands_to_body_v2(
        [], body.analysis_points, body.analysis_scores, 0.01,
        _pipeline_config(), HandGraphConfig(), 0.0, HandAssignmentMemory(),
    )
    assert all(value.observation is None for value in result.values())


def test_hand_assignment_memory_predicts_center_with_velocity():
    memory = HandAssignmentMemory()
    hand = make_hand_v4()
    observation = _candidate(hand, "Left")
    # Construct through the public assignment data type used by memory.
    from worker.src.pose_v3.hand_pipeline import HandObservation
    first = HandObservation(
        hand.points_px, hand.world_points, "Left", 0.9, hand.points_px[0], 80.0,
        0.0, 40.0, -90.0, 0.0,
    )
    memory.update({"left": RawHandFrame(first, 0.0, True), "right": RawHandFrame(None, 0.0, False)}, 0.0)
    shifted = HandObservation(
        hand.points_px + (10, 0), hand.world_points, "Left", 0.9, hand.points_px[0] + (10, 0),
        80.0, 0.0, 40.0, -90.0, 0.0,
    )
    memory.update({"left": RawHandFrame(shifted, 0.1, True), "right": RawHandFrame(None, 0.1, False)}, 0.1)
    predicted = memory.predicted_center("left", 0.2)
    assert predicted is not None and predicted[0] > memory.centers["left"][0]


@pytest.mark.parametrize("quality", [0.0, 0.2, 0.44])
def test_low_quality_grip_is_unknown(quality):
    hand = make_hand_v4("closed", quality=quality)
    palm = compute_palm_frame(hand)
    fingers = {
        name: analyze_hand_graph_frame_finger(hand, name, chain)
        for name, chain in FINGER_CHAINS.items()
    }
    assert compute_grip_features_v2(hand, palm, fingers, None).state == GripStateV2.UNKNOWN


@pytest.mark.parametrize("index", [0, 5, 9, 13, 17])
def test_each_palm_anchor_contributes_to_palm_quality(index, graph_factory):
    _, body = graph_factory()
    hand = make_hand_v4()
    hand.point_validity[index] = False
    graph = analyze_hand_graph_frame(
        "left", hand, body, [], None, PalmScaleProfile(), None, HandGraphConfig()
    )
    assert graph.palm_quality <= 0.8

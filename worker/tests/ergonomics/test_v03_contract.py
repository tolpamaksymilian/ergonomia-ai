from __future__ import annotations

import copy

from worker.src.ergonomics.dependencies import METRIC_DEPENDENCIES
from worker.src.ergonomics.processor import process_pose_document
from worker.src.ergonomics.schemas import MetricResult
from worker.src.ergonomics.temporal import movement_features, reject_isolated_metric_spikes


def _frame(timestamp: float, wrist_valid: bool = True):
    points = [[None, None] for _ in range(133)]
    scores = [0.0 for _ in range(133)]
    for index, point in {
        0: [100, 40], 5: [80, 100], 6: [120, 100], 7: [70, 150],
        8: [130, 150], 9: [65, 200], 10: [135, 200], 11: [85, 220], 12: [115, 220],
    }.items():
        points[index] = point
        scores[index] = 0.95
    joints = [{"valid": True, "quality": 0.95, "reason": None} for _ in range(23)]
    if not wrist_valid:
        joints[9] = {"valid": False, "quality": 0.0, "reason": "OUT_OF_FRAME"}
    return {
        "detected": True,
        "output_timestamp_seconds": timestamp,
        "smoothed_keypoints": points,
        "scores": scores,
        "body_quality": {"joints": joints},
        "left_hand": {"visible": False},
        "right_hand": {"visible": False},
    }


def _document(frames):
    return {
        "schema_version": "3.1",
        "analysis_id": "v03",
        "configuration": {"keypoint_threshold": 0.5},
        "summary": {
            "holding": {"left": {"likely_holding_seconds": 1.2}},
            "tracking": {"out_of_frame_ratio": 0.1},
        },
        "frames": frames,
    }


def test_pose_schema_31_is_supported():
    assert process_pose_document(_document([_frame(0.0)]))["source_pose_schema_version"] == "3.1"


def test_invalid_wrist_dependency_invalidates_wrist_metrics():
    result = process_pose_document(_document([_frame(0.0, wrist_valid=False)]))
    metrics = result["frames"][0]["metrics"]
    assert metrics["left_elbow_flexion_deg"]["valid"] is False
    assert metrics["left_forearm_inclination_deg"]["valid"] is False


def test_invalid_hand_does_not_invalidate_trunk():
    result = process_pose_document(_document([_frame(0.0)]))
    assert result["frames"][0]["metrics"]["trunk_inclination_deg"]["valid"] is True
    assert result["frames"][0]["metrics"]["left_wrist_flexion_deg"]["valid"] is False


def test_invalid_bone_dependency_rejects_metric_with_valid_joint_endpoints():
    frame = _frame(0.0)
    frame["body_quality"]["bones"] = {
        "left_forearm": {"valid": False, "reason": "BONE_LENGTH_OUTLIER"}
    }
    result = process_pose_document(_document([frame]))
    metric = result["frames"][0]["metrics"]["left_forearm_inclination_deg"]
    assert metric["valid"] is False
    assert metric["rejection_reason"] == "dependency_invalid"


def test_dependency_graph_is_written_to_configuration():
    result = process_pose_document(_document([_frame(0.0)]))
    assert result["configuration"]["dependency_graph"] == METRIC_DEPENDENCIES


def test_holding_summary_is_forwarded_without_frame_duplication():
    result = process_pose_document(_document([_frame(0.0)]))
    assert result["hand_activity"]["left"]["likely_holding_seconds"] == 1.2


def test_isolated_metric_spike_is_rejected():
    values = [
        MetricResult.accepted(value, 0.9, ("a",))
        for value in (10.0, 170.0, 11.0)
    ]
    result = reject_isolated_metric_spikes(
        "trunk_inclination_deg", values, [0.0, 0.1, 0.2]
    )
    assert result[1].valid is False
    assert result[1].rejection_reason == "temporal_outlier"


def test_sustained_fast_motion_is_not_treated_as_isolated_spike():
    values = [MetricResult.accepted(value, 0.9, ("a",)) for value in (10.0, 80.0, 150.0)]
    result = reject_isolated_metric_spikes(
        "left_elbow_flexion_deg", values, [0.0, 0.3, 0.6]
    )
    assert all(item.valid for item in result)


def test_movement_features_count_complete_cycles():
    values = [MetricResult.accepted(value, 0.9, ("a",)) for value in (0, 10, 0, 10, 0)]
    features = movement_features(values, [0.0, 0.5, 1.0, 1.5, 2.0])
    assert features["cycle_count"] == 2
    assert features["movement_range"] == 10.0
    assert features["cycles_per_minute"] is not None


def test_movement_features_report_valid_exposure_sequences():
    values = [
        MetricResult.accepted(10.0, 0.9, ("a",)),
        MetricResult.rejected(("a",), "missing_keypoint"),
        MetricResult.accepted(12.0, 0.9, ("a",)),
    ]
    features = movement_features(values, [0.0, 0.1, 0.2])
    assert features["valid_exposure_seconds"] == 0.2
    assert features["valid_sequence_count"] == 2


def test_holding_metric_exposure_uses_only_valid_metric_frames():
    document = _document([_frame(0.0), _frame(0.1, wrist_valid=False), _frame(0.2)])
    for frame in document["frames"]:
        frame["holding"] = {"left": {"state": "LIKELY_HOLDING"}}
    result = process_pose_document(document)
    exposure = result["holding_metric_exposure"]["left"]
    assert exposure["likely_holding_seconds"] == 0.3
    assert exposure["holding_with_valid_wrist_posture_seconds"] < 0.3
    assert exposure["threshold_classification_applied"] is False

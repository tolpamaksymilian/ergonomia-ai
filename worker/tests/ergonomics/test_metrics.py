from __future__ import annotations

import pytest

from worker.src.ergonomics.processor import process_pose_document, summarize_metric
from worker.src.ergonomics.schemas import MetricResult


def _empty_pose_points() -> tuple[list[list[float | None]], list[float]]:
    return [[None, None] for _ in range(133)], [0.0 for _ in range(133)]


def _hand(visible: bool = True) -> dict[str, object]:
    landmarks = [[200.0 + index, 200.0 + index] for index in range(21)]
    landmarks[0] = [100.0, 100.0]
    landmarks[1:5] = [[95.0, 100.0], [90.0, 100.0], [85.0, 100.0], [80.0, 100.0]]
    landmarks[5:9] = [[110.0, 100.0], [120.0, 100.0], [130.0, 100.0], [140.0, 100.0]]
    landmarks[9:13] = [[110.0, 110.0], [120.0, 110.0], [130.0, 110.0], [140.0, 110.0]]
    landmarks[13:17] = [[110.0, 120.0], [120.0, 120.0], [130.0, 120.0], [140.0, 120.0]]
    landmarks[17:21] = [[110.0, 130.0], [120.0, 130.0], [130.0, 130.0], [140.0, 130.0]]
    return {
        "visible": visible,
        "quality": 0.9 if visible else 0.0,
        "landmarks_2d": landmarks if visible else None,
    }


def _frame() -> dict[str, object]:
    points, scores = _empty_pose_points()
    coordinates = {
        0: [100.0, 40.0],
        5: [80.0, 80.0],
        6: [120.0, 80.0],
        7: [80.0, 110.0],
        8: [120.0, 110.0],
        9: [80.0, 140.0],
        10: [120.0, 140.0],
        11: [80.0, 140.0],
        12: [120.0, 140.0],
    }
    for index, coordinate in coordinates.items():
        points[index] = coordinate
        scores[index] = 0.95
    return {
        "source_frame_index": 20,
        "output_frame_index": 0,
        "source_timestamp_seconds": 0.8,
        "output_timestamp_seconds": 0.0,
        "detected": True,
        "smoothed_keypoints": points,
        "scores": scores,
        "left_hand": _hand(),
        "right_hand": _hand(),
    }


def _document(frame: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "3.0",
        "analysis_id": "test-analysis",
        "coordinate_space": "source-video-pixels",
        "configuration": {"keypoint_threshold": 0.5},
        "frames": [frame],
    }


def _metrics(frame: dict[str, object]) -> dict[str, dict[str, object]]:
    result = process_pose_document(_document(frame))
    return result["frames"][0]["metrics"]  # type: ignore[index,return-value]


def test_missing_point_rejects_only_dependent_metric() -> None:
    frame = _frame()
    frame["smoothed_keypoints"][9] = [None, None]  # type: ignore[index]
    metric = _metrics(frame)["left_elbow_flexion_deg"]
    assert metric["valid"] is False
    assert metric["rejection_reason"] == "missing_keypoint"


def test_low_quality_point_is_rejected() -> None:
    frame = _frame()
    frame["scores"][7] = 0.2  # type: ignore[index]
    metric = _metrics(frame)["left_elbow_flexion_deg"]
    assert metric["valid"] is False
    assert metric["rejection_reason"] == "low_keypoint_quality"


def test_elbow_flexion_is_90_degrees() -> None:
    frame = _frame()
    frame["smoothed_keypoints"][9] = [110.0, 110.0]  # type: ignore[index]
    metric = _metrics(frame)["left_elbow_flexion_deg"]
    assert metric["valid"] is True
    assert metric["value"] == pytest.approx(90.0)
    assert metric["quality"] == pytest.approx(0.95)


def test_symmetric_pose_has_equal_left_and_right_metrics() -> None:
    frame = _frame()
    points = frame["smoothed_keypoints"]
    points[7], points[8] = [50.0, 80.0], [150.0, 80.0]  # type: ignore[index]
    points[9], points[10] = [50.0, 110.0], [150.0, 110.0]  # type: ignore[index]
    metrics = _metrics(frame)
    for suffix in ("upper_arm_elevation_deg", "elbow_flexion_deg", "forearm_inclination_deg"):
        assert metrics[f"left_{suffix}"]["value"] == pytest.approx(
            metrics[f"right_{suffix}"]["value"]
        )


def test_invalid_hand_rejects_hand_metrics() -> None:
    frame = _frame()
    frame["left_hand"] = _hand(visible=False)
    metrics = _metrics(frame)
    for name in ("left_wrist_flexion_deg", "left_hand_closure_ratio", "left_pinch_distance_ratio"):
        assert metrics[name]["valid"] is False
        assert metrics[name]["rejection_reason"] == "hand_not_valid"


def test_pinch_distance_is_normalized_by_palm_scale() -> None:
    frame = _frame()
    hand = _hand()
    landmarks = hand["landmarks_2d"]
    landmarks[0] = [100.0, 100.0]  # type: ignore[index]
    landmarks[9] = [100.0, 90.0]  # type: ignore[index]
    landmarks[5] = [90.0, 100.0]  # type: ignore[index]
    landmarks[17] = [110.0, 100.0]  # type: ignore[index]
    landmarks[4] = [100.0, 80.0]  # type: ignore[index]
    landmarks[8] = [105.0, 80.0]  # type: ignore[index]
    frame["left_hand"] = hand
    metric = _metrics(frame)["left_pinch_distance_ratio"]
    assert metric["valid"] is True
    assert metric["value"] == pytest.approx(0.5)


def test_open_straight_fingers_have_zero_closure_ratio() -> None:
    metric = _metrics(_frame())["left_hand_closure_ratio"]
    assert metric["valid"] is True
    assert metric["value"] == pytest.approx(0.0)


def test_statistical_summary_uses_only_valid_values() -> None:
    sources = ("point",)
    results = [
        MetricResult.accepted(10.0, 0.9, sources),
        MetricResult.accepted(20.0, 0.8, sources),
        MetricResult.rejected(sources, "missing_keypoint"),
    ]
    summary = summarize_metric(results)
    assert summary == {
        "valid_frames": 2,
        "invalid_frames": 1,
        "valid_ratio": 0.666667,
        "mean": 15.0,
        "median": 15.0,
        "minimum": 10.0,
        "maximum": 20.0,
        "percentile_95": 19.5,
    }

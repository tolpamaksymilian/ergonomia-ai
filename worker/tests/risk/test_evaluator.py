from __future__ import annotations

import copy
import math

import pytest

from worker.src.risk.evaluator import evaluate_frame_metric
from worker.src.risk.processor import process_risk_document
from worker.src.risk.profile import load_risk_profile


def _set_values(document, metric_name, values):
    for frame, value in zip(document["frames"], values):
        frame["metrics"][metric_name].update(
            value=value,
            valid=value is not None,
            quality=0.9 if value is not None else 0.0,
            rejection_reason=None if value is not None else "missing_keypoint",
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(10, "low"), (25, "moderate"), (45, "high"), (65, "critical")],
)
def test_frame_classification_levels(
    risk_profile_document,
    value,
    expected,
):
    metric = load_risk_profile(risk_profile_document).metrics[
        "trunk_inclination_deg"
    ]
    result = evaluate_frame_metric(
        "trunk_inclination_deg",
        {"value": value, "valid": True, "quality": 0.9},
        metric,
    )
    assert result["level"] == expected
    assert result["weighted_score"] == pytest.approx(result["score"] * 1.2)


def test_invalid_metric_keeps_rejection_reason(risk_profile_document):
    metric = load_risk_profile(risk_profile_document).metrics[
        "trunk_inclination_deg"
    ]
    result = evaluate_frame_metric(
        "trunk_inclination_deg",
        {
            "value": None,
            "valid": False,
            "quality": 0.0,
            "rejection_reason": "missing_keypoint",
        },
        metric,
    )
    assert result["level"] == "insufficient_data"
    assert result["rejection_reason"] == "missing_keypoint"
    assert result["score"] is None


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nan_and_infinity_are_rejected(risk_profile_document, value):
    metric = load_risk_profile(risk_profile_document).metrics[
        "trunk_inclination_deg"
    ]
    result = evaluate_frame_metric(
        "trunk_inclination_deg",
        {"value": value, "valid": True, "quality": 0.9},
        metric,
    )
    assert result["valid"] is False
    assert result["rejection_reason"] == "invalid_metric_value"


def test_valid_true_with_null_value_is_rejected(risk_profile_document):
    metric = load_risk_profile(risk_profile_document).metrics[
        "trunk_inclination_deg"
    ]
    result = evaluate_frame_metric(
        "trunk_inclination_deg",
        {"value": None, "valid": True, "quality": 0.9},
        metric,
    )
    assert result["level"] == "insufficient_data"


def test_value_without_valid_is_rejected(risk_profile_document):
    metric = load_risk_profile(risk_profile_document).metrics[
        "trunk_inclination_deg"
    ]
    result = evaluate_frame_metric(
        "trunk_inclination_deg",
        {"value": 10, "quality": 0.9},
        metric,
    )
    assert result["rejection_reason"] == "invalid_metric_contract"


def test_low_valid_ratio_returns_insufficient_data(
    metrics_document,
    risk_profile_document,
):
    _set_values(
        metrics_document,
        "trunk_inclination_deg",
        [10, None, None, None, None, 10],
    )
    result = process_risk_document(metrics_document, risk_profile_document)
    summary = result["metrics"]["trunk_inclination_deg"]
    assert summary["data_quality"] == "limited"
    assert summary["final_level"] == "insufficient_data"


def test_single_extreme_frame_does_not_determine_summary(
    metrics_document,
    risk_profile_document,
):
    _set_values(metrics_document, "trunk_inclination_deg", [10, 10, 65, 10, 10, 10])
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["metrics"]["trunk_inclination_deg"]["final_level"] == "low"


def test_long_high_sequence_changes_metric_summary(
    metrics_document,
    risk_profile_document,
):
    _set_values(metrics_document, "trunk_inclination_deg", [10, 45, 45, 45, 10, 10])
    result = process_risk_document(metrics_document, risk_profile_document)
    summary = result["metrics"]["trunk_inclination_deg"]
    assert summary["final_level"] == "high"
    assert "minimum_sequence_duration_exceeded" in summary["decision_reasons"]


def test_zone_grouping_comes_from_profile(metrics_document, risk_profile_document):
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["zones"]["left_upper_limb"]["active_metrics"] == 4
    assert result["zones"]["left_hand"]["active_metrics"] == 2


def test_zone_with_majority_insufficient_data(
    metrics_document,
    risk_profile_document,
):
    for name in (
        "left_upper_arm_elevation_deg",
        "left_elbow_flexion_deg",
        "left_forearm_inclination_deg",
    ):
        _set_values(metrics_document, name, [None] * 6)
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["zones"]["left_upper_limb"]["highest_level"] == "insufficient_data"


def test_overall_weighted_aggregation(metrics_document, risk_profile_document):
    angle_names = [
        "trunk_inclination_deg",
        "neck_flexion_deg",
        "left_upper_arm_elevation_deg",
        "right_upper_arm_elevation_deg",
        "left_forearm_inclination_deg",
        "right_forearm_inclination_deg",
        "left_wrist_flexion_deg",
        "right_wrist_flexion_deg",
    ]
    for name in angle_names:
        _set_values(metrics_document, name, [45] * 6)
    for name in ("left_elbow_flexion_deg", "right_elbow_flexion_deg"):
        _set_values(metrics_document, name, [160] * 6)
    for name in ("left_hand_closure_ratio", "right_hand_closure_ratio"):
        _set_values(metrics_document, name, [0.6] * 6)
    for name in ("left_pinch_distance_ratio", "right_pinch_distance_ratio"):
        _set_values(metrics_document, name, [0.15] * 6)
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["overall"]["overall_level"] == "high"
    assert result["overall"]["overall_score"] == pytest.approx(2 / 3)


def test_peak_guard_promotes_persistent_peak(
    metrics_document,
    risk_profile_document,
):
    _set_values(metrics_document, "trunk_inclination_deg", [45, 45, 10, 10, 10, 10])
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["overall"]["overall_level"] == "high"
    assert "peak_guard_promoted_to_high" in result["overall"]["decision_reasons"]


def test_overall_insufficient_data(metrics_document, risk_profile_document):
    for frame in metrics_document["frames"]:
        for metric in frame["metrics"].values():
            metric.update(
                value=None,
                valid=False,
                quality=0.0,
                rejection_reason="missing_keypoint",
            )
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["overall"]["overall_level"] == "insufficient_data"
    assert result["overall"]["overall_score"] is None


def test_key_frames_are_deduplicated(metrics_document, risk_profile_document):
    for frame in metrics_document["frames"]:
        for name in ("trunk_inclination_deg", "neck_flexion_deg"):
            frame["metrics"][name]["value"] = 65
    result = process_risk_document(metrics_document, risk_profile_document)
    keys = [
        (frame["source_frame_index"], frame["output_frame_index"])
        for frame in result["key_frames"]
    ]
    assert len(keys) == len(set(keys))


def test_key_frames_limit_is_ten(metrics_document, risk_profile_document):
    template = metrics_document["frames"][0]
    frames = []
    for index in range(30):
        frame = copy.deepcopy(template)
        frame.update(
            source_frame_index=index,
            output_frame_index=index,
            timestamp=float(index),
        )
        for name in (
            "trunk_inclination_deg",
            "neck_flexion_deg",
            "left_upper_arm_elevation_deg",
            "right_upper_arm_elevation_deg",
        ):
            frame["metrics"][name]["value"] = 65
        frames.append(frame)
    metrics_document["frames"] = frames
    result = process_risk_document(metrics_document, risk_profile_document)
    assert len(result["key_frames"]) == 10


def test_key_frames_prefer_high_quality(metrics_document, risk_profile_document):
    _set_values(metrics_document, "trunk_inclination_deg", [65] * 6)
    metrics_document["frames"][0]["metrics"]["trunk_inclination_deg"][
        "quality"
    ] = 0.2
    metrics_document["frames"][2]["metrics"]["trunk_inclination_deg"][
        "quality"
    ] = 1.0
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["key_frames"][0]["source_frame_index"] == 2

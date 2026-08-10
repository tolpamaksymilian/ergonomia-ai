from __future__ import annotations

import pytest

from worker.src.company_methods.ejms import evaluate_ejms, evaluate_section_ii, matrix_score


@pytest.mark.parametrize(
    ("posture", "frequency", "score"),
    [("LOW", "LOW", 0), ("LOW", "MOD", 5), ("LOW", "HIGH", 10), ("MOD", "LOW", 5), ("MOD", "MOD", 10), ("MOD", "HIGH", 15), ("HIGH", "LOW", 10), ("HIGH", "MOD", 15), ("HIGH", "HIGH", 20)],
)
def test_ejms_matrix_all_nine_combinations(posture, frequency, score):
    assert matrix_score(posture, frequency) == score


def frame(timestamp, neck=5, arm=10, trunk=10, elbow=90, wrist=10):
    def item(value): return {"valid": True, "value": value, "quality": 0.9}
    return {"timestamp_seconds": timestamp, "metrics": {"neck_flexion_deg": item(neck), "left_upper_arm_elevation_deg": item(arm), "right_upper_arm_elevation_deg": item(arm), "trunk_inclination_deg": item(trunk), "left_elbow_flexion_deg": item(elbow), "right_elbow_flexion_deg": item(elbow), "left_wrist_flexion_deg": item(wrist), "right_wrist_flexion_deg": item(wrist), "left_hand_closure_ratio": item(.2), "right_hand_closure_ratio": item(.2)}}


def test_unknown_force_does_not_produce_false_low():
    result = evaluate_ejms({"frames": [frame(0), frame(1)]})
    neck = result["section_i"]["areas"]["neck"]
    assert neck["posture_level"] == "LOW"
    assert neck["force_level"] == "UNKNOWN"
    assert neck["score"] is None
    assert neck["final_level"] == "UNKNOWN"


@pytest.mark.parametrize(("neck", "expected"), [(9.999, "LOW"), (10, "MOD"), (30, "MOD"), (30.001, "HIGH")])
def test_ejms_neck_boundaries(neck, expected):
    manual = {"section_i": {"neck": {"force_level": "LOW", "frequency_per_minute": 1}}}
    result = evaluate_ejms({"frames": [frame(0, neck=neck), frame(1, neck=neck)]}, manual)
    assert result["section_i"]["areas"]["neck"]["posture_level"] == expected


def test_ejms_frequency_is_derived_from_video_metric_transitions():
    frames = [frame(i, wrist=0 if i % 2 == 0 else 20) for i in range(10)]
    result = evaluate_ejms({"frames": frames}, {"section_i": {"wrist": {"force_level": "LOW"}}})
    assert result["section_i"]["areas"]["wrist"]["frequency_per_minute"] == 60.0


def test_section_ii_requires_absolute_manual_measurements():
    result = evaluate_section_ii({"frequency_per_minute": 2, "twist_deg": 20})
    assert result["components"]["frequency_per_minute"]["score"] == 10
    assert result["components"]["twist_deg"]["score"] == 5
    assert "ejms.section_ii.weight_kg" in result["missing_inputs"]
    assert result["components"]["horizontal_distance_cm"]["score"] is None
    assert result["score"] is None
    assert result["known_score"] == 15
    assert result["possible_score_min"] <= result["possible_score_max"]


def test_ejms_legs_use_video_derived_owas_sequence():
    owas = {"frames": [{"components": {"legs": {"value": 6, "source": "VIDEO_DERIVED", "quality": 0.8}}}] * 2}
    manual = {"section_i": {"legs": {"force_level": "LOW", "frequency_per_minute": 1}}}
    result = evaluate_ejms({"frames": [frame(0), frame(1)]}, manual, owas)
    legs = result["section_i"]["areas"]["legs"]
    assert legs["posture_level"] == "HIGH"
    assert legs["score"] == 20

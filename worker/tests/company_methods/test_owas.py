from __future__ import annotations

from worker.src.company_methods.owas import evaluate_owas
from worker.src.company_methods.specs import load_spec


def metric(value):
    return {"valid": True, "value": value, "quality": 0.9}


def metrics_frame(timestamp=0.0, trunk=10, left_arm=20, right_arm=20):
    return {"timestamp_seconds": timestamp, "metrics": {"trunk_inclination_deg": metric(trunk), "left_upper_arm_elevation_deg": metric(left_arm), "right_upper_arm_elevation_deg": metric(right_arm)}}


def pose_frame(*, knee_angle="straight"):
    if knee_angle == "straight":
        joints = {"left_hip": (0, 0), "right_hip": (2, 0), "left_knee": (0, 2), "right_knee": (2, 2), "left_ankle": (0, 4), "right_ankle": (2, 4)}
    else:
        joints = {"left_hip": (0, 0), "right_hip": (2, 0), "left_knee": (1, 1), "right_knee": (3, 1), "left_ankle": (0, 1), "right_ankle": (2, 1)}
    return {"joint_evidence_v5": {name: {"coordinates": list(point)} for name, point in joints.items()}}


def walking_pose(left_x, right_x, left_y=4, right_y=4):
    joints = {"left_hip": (0, 0), "right_hip": (2, 0), "left_knee": (0, 2), "right_knee": (2, 2), "left_ankle": (left_x, left_y), "right_ankle": (right_x, right_y)}
    return {"joint_evidence_v5": {name: {"coordinates": list(point)} for name, point in joints.items()}}


def test_all_unambiguous_workbook_codes_are_preserved_exactly():
    spec = load_spec("owas")
    assert sum(item["status"] == "VERIFIED" for item in spec["lookup"].values()) == 248


def test_known_owas_source_anomalies_are_not_hidden():
    spec = load_spec("owas")
    assert spec["lookup"]["3133"] == {"categories": [2, 3], "status": "SOURCE_AMBIGUOUS"}
    assert {"2133", "4173", "4373"}.isdisjoint(spec["lookup"])
    assert spec["lookup"]["7173"]["status"] == "SOURCE_INVALID"
    assert spec["lookup"]["7373"]["status"] == "SOURCE_INVALID"


def test_owas_classifies_back_arms_legs_and_manual_load():
    ergonomics = {"analysis_id": "a", "source": {"fps": 10}, "frames": [metrics_frame()]}
    pose = {"frames": [pose_frame()]}
    result = evaluate_owas(pose, ergonomics, {"load_kg": 5})
    frame = result["frames"][0]
    assert frame["components"]["back"]["value"] == 1
    assert frame["components"]["arms"]["value"] == 1
    assert frame["components"]["legs"]["value"] == 2
    assert frame["code"] == "1121"
    assert frame["category"] == 1


def test_unknown_load_yields_partial_possible_categories():
    result = evaluate_owas({"frames": [pose_frame()]}, {"analysis_id": "a", "frames": [metrics_frame()]})
    assert result["status"] == "PARTIAL"
    assert result["frames"][0]["category"] is None
    assert len(result["frames"][0]["possible_categories"]) == 3
    assert "owas.forced_posture" in result["missing_inputs"]


def test_missing_leg_points_are_unknown_not_standing():
    result = evaluate_owas({"frames": [{}]}, {"analysis_id": "a", "frames": [metrics_frame()]}, {"load_kg": 5})
    assert result["frames"][0]["components"]["legs"]["source"] == "UNKNOWN"
    assert result["frames"][0]["status"] == "REQUIRES_DATA"


def test_owas_duration_and_episode_summary_use_timestamps():
    frames = [metrics_frame(0), metrics_frame(0.2), metrics_frame(0.5, trunk=30)]
    result = evaluate_owas({"frames": [pose_frame()] * 3}, {"analysis_id": "a", "source": {"fps": 10}, "frames": frames}, {"load_kg": 5})
    assert result["summary"]["active_duration_seconds"] == 0.6
    assert sum(result["summary"]["episode_counts"].values()) == 2


def test_owas_walking_requires_a_temporal_gait_sequence():
    poses = [walking_pose(0, 2), walking_pose(-0.7, 2.5, 3.6, 4.2), walking_pose(0.5, 1.4, 4.2, 3.6)]
    metrics = [metrics_frame(0), metrics_frame(0.2), metrics_frame(0.4)]
    result = evaluate_owas({"frames": poses}, {"analysis_id": "a", "frames": metrics}, {"load_kg": 5})
    assert result["frames"][1]["components"]["legs"]["value"] == 7
    assert result["frames"][1]["components"]["legs"]["reason"] == "temporal_gait_pattern_detected"


def test_owas_single_ankle_jump_is_not_walking():
    poses = [walking_pose(0, 2), walking_pose(-0.7, 2.5, 3.6, 4.2), walking_pose(-0.7, 2.5, 3.6, 4.2)]
    metrics = [metrics_frame(0), metrics_frame(0.2), metrics_frame(0.4)]
    result = evaluate_owas({"frames": poses}, {"analysis_id": "a", "frames": metrics}, {"load_kg": 5})
    assert all(frame["components"]["legs"]["value"] != 7 for frame in result["frames"])


def test_owas_time_table_preserves_overlapping_source_rules():
    frames = [metrics_frame(index / 10) for index in range(10)]
    result = evaluate_owas({"frames": [pose_frame()] * 10}, {"analysis_id": "a", "source": {"fps": 10}, "frames": frames}, {"load_kg": 5, "forced_posture": "unforced"})
    category_one = result["summary"]["time_distribution_assessment"][0]
    assert category_one["ratio"] == 1.0
    assert category_one["status"] == "VERIFIED"
    assert category_one["level"] == "MEDIUM"


def test_owas_time_table_reports_ambiguous_overlap_without_guessing():
    from worker.src.company_methods.owas import _time_distribution_assessment
    result = _time_distribution_assessment({"1": 0.6, "2": 0.0, "3": 0.0, "4": 0.0}, "unforced", load_spec("owas"))
    assert result[0]["status"] == "SOURCE_AMBIGUOUS"
    assert result[0]["level"] is None
    assert {item["level"] for item in result[0]["matching_rules"]} == {"SMALL", "MEDIUM"}


def test_owas_detects_one_leg_support_only_with_clear_asymmetry():
    pose = walking_pose(0, 2, 4, 3.2)
    result = evaluate_owas({"frames": [pose]}, {"analysis_id": "a", "frames": [metrics_frame()]}, {"load_kg": 5, "forced_posture": "unforced"})
    assert result["frames"][0]["components"]["legs"]["value"] == 3

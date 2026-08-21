from __future__ import annotations

from worker.src.ergonomics.processor import process_pose_document


def _frame() -> dict[str, object]:
    points = [[100.0 + index, 100.0 + index] for index in range(133)]
    scores = [0.95] * 133
    joints = [
        {"name": name, "valid": True, "quality": 0.95}
        for name in (
            "nose", "left_eye", "right_eye", "left_ear", "right_ear",
            "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
            "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee",
            "right_knee", "left_ankle", "right_ankle", "left_big_toe",
            "left_small_toe", "left_heel", "right_big_toe", "right_small_toe",
            "right_heel",
        )
    ]
    return {
        "detected": True,
        "tracking_state": "TRACKED",
        "smoothed_keypoints": points,
        "scores": scores,
        "body_quality": {"joints": joints},
        "temporal_v6": {"joints": {}},
        "left_hand": {"visible": False},
        "right_hand": {"visible": False},
    }


def test_pose_schema_60_is_supported() -> None:
    result = process_pose_document({"schema_version": "6.0", "analysis_id": "a", "source": {"fps": 30}, "frames": [_frame()]})
    assert result["source_pose_schema_version"] == "6.0"


def test_render_only_joint_is_never_used_by_ergonomics() -> None:
    frame = _frame()
    frame["temporal_v6"] = {"joints": {"left_elbow": {"source": "KINEMATIC_PREDICTED", "analysis_usable": False, "quality": 0.8}}}
    result = process_pose_document({"schema_version": "6.0", "analysis_id": "a", "source": {"fps": 30}, "frames": [frame]})
    assert result["frames"][0]["metrics"]["left_elbow_flexion_deg"]["valid"] is False


def test_safe_interpolation_can_override_legacy_missing_diagnostic() -> None:
    frame = _frame()
    frame["body_quality"]["joints"][7] = {"name": "left_elbow", "valid": False, "rejection_reasons": ["LOW_CONFIDENCE"]}
    frame["body_quality"]["bones"] = {"left_upper_arm": {"valid": False}, "left_forearm": {"valid": False}}
    frame["temporal_v6"] = {
        "joints": {"left_elbow": {"source": "INTERPOLATED", "analysis_usable": True, "quality": 0.8}},
        "analysis_bones": {"left_upper_arm": {"valid": True}, "left_forearm": {"valid": True}},
    }
    result = process_pose_document({"schema_version": "6.0", "analysis_id": "a", "source": {"fps": 30}, "frames": [frame]})
    assert result["frames"][0]["metrics"]["left_elbow_flexion_deg"]["valid"] is True

"""Explicit V1 metric dependencies used for validation and diagnostics."""

from __future__ import annotations


METRIC_DEPENDENCIES: dict[str, dict[str, object]] = {
    "trunk_inclination_deg": {
        "required_points": ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
        "required_bones": ["shoulders", "hips", "left_torso", "right_torso"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "neck_flexion_deg": {
        "required_points": ["nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip"],
        "required_bones": ["shoulders", "hips", "left_torso", "right_torso"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "left_upper_arm_elevation_deg": {
        "required_points": ["left_shoulder", "left_elbow", "right_shoulder", "left_hip", "right_hip"],
        "required_bones": ["left_upper_arm", "shoulders", "hips", "left_torso", "right_torso"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "right_upper_arm_elevation_deg": {
        "required_points": ["right_shoulder", "right_elbow", "left_shoulder", "left_hip", "right_hip"],
        "required_bones": ["right_upper_arm", "shoulders", "hips", "left_torso", "right_torso"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "left_elbow_flexion_deg": {
        "required_points": ["left_shoulder", "left_elbow", "left_wrist"],
        "required_bones": ["left_upper_arm", "left_forearm"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "right_elbow_flexion_deg": {
        "required_points": ["right_shoulder", "right_elbow", "right_wrist"],
        "required_bones": ["right_upper_arm", "right_forearm"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "left_forearm_inclination_deg": {
        "required_points": ["left_elbow", "left_wrist"],
        "required_bones": ["left_forearm"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "right_forearm_inclination_deg": {
        "required_points": ["right_elbow", "right_wrist"],
        "required_bones": ["right_forearm"],
        "optional_points": [],
        "required_quality": "minimum_required_point_quality",
    },
    "left_wrist_flexion_deg": {
        "required_points": ["left_elbow", "left_wrist", "left_hand_wrist", "left_hand_middle_mcp"],
        "required_bones": ["left_forearm"],
        "optional_points": [],
        "required_quality": "minimum_required_point_and_hand_quality",
    },
    "right_wrist_flexion_deg": {
        "required_points": ["right_elbow", "right_wrist", "right_hand_wrist", "right_hand_middle_mcp"],
        "required_bones": ["right_forearm"],
        "optional_points": [],
        "required_quality": "minimum_required_point_and_hand_quality",
    },
    "left_hand_closure_ratio": {
        "required_points": ["left_hand_wrist", "left_hand_index_tip", "left_hand_middle_tip", "left_hand_ring_tip", "left_hand_pinky_tip"],
        "required_bones": [],
        "optional_points": [],
        "required_quality": "minimum_validated_hand_quality",
    },
    "right_hand_closure_ratio": {
        "required_points": ["right_hand_wrist", "right_hand_index_tip", "right_hand_middle_tip", "right_hand_ring_tip", "right_hand_pinky_tip"],
        "required_bones": [],
        "optional_points": [],
        "required_quality": "minimum_validated_hand_quality",
    },
    "left_pinch_distance_ratio": {
        "required_points": ["left_hand_thumb_tip", "left_hand_index_tip", "left_hand_index_mcp", "left_hand_pinky_mcp"],
        "required_bones": [],
        "optional_points": [],
        "required_quality": "minimum_validated_hand_quality",
    },
    "right_pinch_distance_ratio": {
        "required_points": ["right_hand_thumb_tip", "right_hand_index_tip", "right_hand_index_mcp", "right_hand_pinky_mcp"],
        "required_bones": [],
        "optional_points": [],
        "required_quality": "minimum_validated_hand_quality",
    },
}

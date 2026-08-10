from __future__ import annotations

from copy import deepcopy
import pytest


METRICS = (
    "trunk_inclination_deg", "neck_flexion_deg",
    "left_upper_arm_elevation_deg", "right_upper_arm_elevation_deg",
    "left_elbow_flexion_deg", "right_elbow_flexion_deg",
    "left_forearm_inclination_deg", "right_forearm_inclination_deg",
    "left_wrist_flexion_deg", "right_wrist_flexion_deg",
    "left_hand_closure_ratio", "right_hand_closure_ratio",
    "left_pinch_distance_ratio", "right_pinch_distance_ratio",
)


def metric(value: float, quality: float = 0.9) -> dict[str, object]:
    return {"value": value, "valid": True, "quality": quality, "source_points": ["synthetic"], "rejection_reason": None}


@pytest.fixture
def metrics_document() -> dict:
    frames=[]
    for index in range(20):
        values={name: metric(0.2 if "ratio" in name else 10.0) for name in METRICS}
        values["left_elbow_flexion_deg"]=metric(90.0); values["right_elbow_flexion_deg"]=metric(90.0)
        values["trunk_inclination_deg"]=metric(10.0 + (35.0 if index==10 else 0.0))
        frames.append({"source_frame_index":index,"output_frame_index":index,"timestamp":index*0.1,"person_detected":True,"metrics":values})
    return {"schema_version":"1.0","metrics_version":"ergonomics-metrics-v1.0","analysis_id":"assessment-test","fps":10.0,"frames":frames,"summary":{}}


@pytest.fixture
def pose_document() -> dict:
    frames=[]
    for index in range(20):
        points=[[100.0+i,100.0+i] for i in range(17)]
        points[11]=[80.0,200.0]; points[13]=[80.0,260.0]; points[15]=[80.0,320.0]
        points[12]=[120.0,200.0]; points[14]=[120.0,260.0]; points[16]=[120.0,320.0]
        frames.append({"smoothed_keypoints":points,"scores":[0.95]*17,"tracking":{"state":"TRACKED"},"frame_quality":{"score":0.9}})
    return {"schema_version":"4.0","pose_version":"pose-v4.0-beta.1","analysis_id":"assessment-test","frames":frames}


@pytest.fixture
def complete_context() -> dict[str,int]:
    return {"rula_muscle_use":0,"rula_force_load":0,"reba_load_force":0,"reba_coupling":0,"reba_activity":0}

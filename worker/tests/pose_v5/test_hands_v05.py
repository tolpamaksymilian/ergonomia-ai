from __future__ import annotations

import numpy as np

from worker.src.pose_v5.hands import FingerStateV3,HandShapeProfileV3,assignment_cost,validate_finger_chain


def test_hand_shape_profile_updates_only_from_high_quality():
    profile=HandShapeProfileV3(); assert not profile.update("left",{"palm_width":1.0},0.5)
    assert profile.update("left",{"palm_width":1.0},0.9); assert profile.reference("left","palm_width")[0]==1.0


def test_impossible_finger_segment_is_invalid():
    points=np.array([[0,0],[1,0],[2,0],[100,0]],dtype=float)
    result=validate_finger_chain(points,np.ones(4,dtype=bool),palm_scale=10,model_quality=.95,profile_quality=.9)
    assert result.state in {FingerStateV3.WEAK,FingerStateV3.INVALID}; assert "SEGMENT_2_GEOMETRY_OUTLIER" in result.rejection_reasons


def test_object_occluded_partial_finger_is_not_invented():
    points=np.array([[0,0],[1,0],[2,0],[0,0]],dtype=float); valid=np.array([1,1,1,0],dtype=bool)
    result=validate_finger_chain(points,valid,palm_scale=10,model_quality=.9,profile_quality=.9,object_occluded=True)
    assert result.state is FingerStateV3.OCCLUDED


def test_future_context_rejects_single_frame_tip_teleport():
    normal=np.array([[0,0],[1,0],[2,0],[3,0]],dtype=float); outlier=normal.copy(); outlier[-1]=[30,30]
    result=validate_finger_chain(outlier,np.ones(4,dtype=bool),palm_scale=10,model_quality=.9,profile_quality=.9,previous=normal,following=normal)
    assert "FINGER_TEMPORAL_OUTLIER" in result.rejection_reasons


def test_identity_hysteresis_penalizes_hand_swap():
    stable=assignment_cost(wrist_distance=.1,forearm_direction_error=.1,palm_orientation_error=.1,trajectory_error=.1,scale_error=.1,handedness_penalty=.1,identity_change=False)
    swapped=assignment_cost(wrist_distance=.1,forearm_direction_error=.1,palm_orientation_error=.1,trajectory_error=.1,scale_error=.1,handedness_penalty=.1,identity_change=True)
    assert swapped>stable

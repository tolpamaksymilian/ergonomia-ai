from __future__ import annotations

import numpy as np

from worker.src.pose_v5.camera_motion import CameraMotionEstimator, robust_translation


def test_robust_translation_ignores_one_bad_track():
    first=np.array([[0,0],[5,2],[10,10],[20,5]],dtype=float)
    second=first+np.array([3,-2],dtype=float); second[-1]=[999,999]
    assert robust_translation(first,second)==(3.0,-2.0)


def test_invalid_track_shapes_are_unavailable():
    assert robust_translation(np.zeros((2,2)),np.zeros((2,2))) is None


def test_scene_cut_is_detected():
    estimator=CameraMotionEstimator(); estimator.update(np.zeros((80,80,3),dtype=np.uint8))
    result=estimator.update(np.full((80,80,3),255,dtype=np.uint8))
    assert result.scene_cut is True


def test_static_scene_does_not_invent_motion():
    rng=np.random.default_rng(7); frame=rng.integers(0,255,(120,120,3),dtype=np.uint8)
    estimator=CameraMotionEstimator(); estimator.update(frame); result=estimator.update(frame.copy())
    assert result.scene_cut is False
    if result.available: assert result.magnitude_pixels < 0.1

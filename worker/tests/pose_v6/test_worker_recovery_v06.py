from __future__ import annotations

import numpy as np
import importlib
import sys
from pathlib import Path

from worker.src.pose_v3.tracking import PersonTrackingStateMachine, TrackingConfig

WORKER_SRC = Path(__file__).resolve().parents[2] / "src"
while str(WORKER_SRC) in sys.path:
    sys.path.remove(str(WORKER_SRC))
sys.path.insert(0, str(WORKER_SRC))

class _FakePoseModel:
    def __init__(self) -> None:
        self.boxes: list[np.ndarray] = []

    def __call__(self, frame: np.ndarray, *, bboxes: list[np.ndarray]):
        self.boxes = bboxes
        keypoints = np.zeros((len(bboxes), 133, 2), dtype=np.float32)
        scores = np.ones((len(bboxes), 133), dtype=np.float32) * 0.9
        return keypoints, scores


def test_track_conditioned_rtmw_runs_only_on_explicit_predicted_roi() -> None:
    module_prefixes = ("pose_worker", "pose_v3", "pose_v4", "pose_v5", "pose_v6")
    module_names = tuple(
        name
        for name in sys.modules
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in module_prefixes)
    )
    saved = {name: sys.modules[name] for name in module_names}
    for name in module_names:
        sys.modules.pop(name, None)
    try:
        # Pytest also has test packages named pose_v3/pose_v4/pose_v5.  Pin the
        # runtime packages explicitly so this import exercises the real worker
        # regardless of pytest's collection import mode.
        for package in ("pose_v3", "pose_v4", "pose_v5", "pose_v6"):
            sys.modules[package] = importlib.import_module(f"worker.src.{package}")
        pose_worker = importlib.import_module("pose_worker")
        strict_model = pose_worker.StrictWholebodyModel
        model = strict_model.__new__(strict_model)
        model.pose_model = _FakePoseModel()
        model.last_timing_seconds = {"detector": 0.0, "pose": 0.0}
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        points, scores = model.infer_on_bboxes(
            frame,
            [np.array([-20, 10, 120, 95], dtype=np.float32)],
            timing_key="pose_recovery",
        )
        assert points.shape == (1, 133, 2)
        assert scores.shape == (1, 133)
        assert model.pose_model.boxes[0].tolist() == [0.0, 10.0, 120.0, 95.0]
        assert model.last_timing_seconds["pose_recovery"] >= 0.0
    finally:
        for name in tuple(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in module_prefixes):
                sys.modules.pop(name, None)
        for name in module_names:
            sys.modules[name] = saved[name]


def _body(offset: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.ones(23, dtype=np.float32) * 0.95
    points[:, 0] = offset + np.linspace(20, 40, 23)
    points[:, 1] = np.linspace(20, 170, 23)
    points[5] = [offset + 25, 55]; points[6] = [offset + 45, 55]
    points[11] = [offset + 28, 105]; points[12] = [offset + 42, 105]
    return points, scores, np.array([offset, 5, offset + 70, 190], dtype=np.float32)


def test_higher_confidence_second_person_cannot_steal_locked_track() -> None:
    tracker = PersonTrackingStateMachine(TrackingConfig(reacquire_confirm_frames=2, lost_after_missing_frames=8, maximum_center_jump_ratio=0.2))
    points, scores, bbox = _body(0.0)
    tracker.update(detected=True, bbox=bbox, points=points, scores=scores, frame_width=400, frame_height=200, candidate_quality=0.8)
    locked = tracker.update(detected=True, bbox=bbox, points=points, scores=scores, frame_width=400, frame_height=200, candidate_quality=0.8)
    assert locked.accept_pose
    other_points, other_scores, other_bbox = _body(280.0)
    decision = tracker.update(detected=True, bbox=other_bbox, points=other_points, scores=other_scores, frame_width=400, frame_height=200, candidate_quality=0.99, motion_gate_multiplier=1.5)
    assert not decision.accept_pose
    assert "BBOX_CENTER_JUMP" in decision.reasons


def test_locked_track_accepts_slightly_weaker_observation_but_acquisition_does_not() -> None:
    config = TrackingConfig(keypoint_threshold=0.80, locked_keypoint_threshold_ratio=0.90, reacquire_confirm_frames=2)
    points, scores, bbox = _body(0.0)
    tracker = PersonTrackingStateMachine(config)
    weak_scores = np.ones_like(scores) * 0.75
    initial = tracker.update(detected=True, bbox=bbox, points=points, scores=weak_scores, frame_width=400, frame_height=200, candidate_quality=0.8)
    assert not initial.accept_pose

    tracker = PersonTrackingStateMachine(config)
    tracker.update(detected=True, bbox=bbox, points=points, scores=scores, frame_width=400, frame_height=200, candidate_quality=0.8)
    assert tracker.update(detected=True, bbox=bbox, points=points, scores=scores, frame_width=400, frame_height=200, candidate_quality=0.8).accept_pose
    continuation = tracker.update(detected=True, bbox=bbox, points=points, scores=weak_scores, frame_width=400, frame_height=200, candidate_quality=0.7)
    assert continuation.accept_pose

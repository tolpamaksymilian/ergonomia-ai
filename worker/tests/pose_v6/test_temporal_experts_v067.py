from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from worker.src.pose_v6.render_continuity import PersistentBoneRenderer, RenderSource
from worker.src.pose_v6.tapnextpp_backend import BidirectionalTapTracks, TapTrackSequence
from worker.src.pose_v6.tar_vitpose_backend import TarPoseObservation
from worker.src.pose_v6.temporal_expert_fusion import (
    CORE_LIMB_JOINTS,
    PoseMeasurement,
    TrackerEvidence,
    fuse_core_frame,
    fuse_joint_measurements,
)
from worker.src.pose_v6 import temporal_expert_pass
from worker.src.pose_v6.temporal_expert_pass import _segments, run_temporal_expert_pass


def _pose(point: tuple[float, float] | None, quality: float, source: str) -> PoseMeasurement:
    return PoseMeasurement(point, quality, source)


def _track(
    forward: tuple[float, float] | None,
    backward: tuple[float, float] | None = None,
    *,
    visible: bool = True,
) -> TrackerEvidence:
    return TrackerEvidence(forward, backward or forward, visible, visible)


def test_tracker_cannot_create_a_pose_measurement() -> None:
    decision = fuse_joint_measurements(
        _pose(None, 0.0, "RTMW"), _pose(None, 0.0, "TAR_TEMPORAL"),
        _track((50.0, 50.0)), body_scale=100.0,
    )
    assert not decision.accepted
    assert decision.reason == "TRACKER_CANNOT_REPLACE_POSE_MEASUREMENT"


def test_rtmw_and_tar_consensus_wins_over_wrong_tracker() -> None:
    decision = fuse_joint_measurements(
        _pose((50.0, 50.0), 0.85, "RTMW"),
        _pose((53.0, 49.0), 0.82, "TAR_TEMPORAL"),
        _track((100.0, 100.0)), body_scale=100.0,
    )
    assert decision.accepted
    assert decision.measurement_source == "RTMW+TAR"
    assert "POINT_TRACK_SUPPORT" not in decision.provenance


def test_tar_and_bidirectional_track_reject_rtmw_outlier() -> None:
    decision = fuse_joint_measurements(
        _pose((150.0, 50.0), 0.95, "RTMW"),
        _pose((52.0, 50.0), 0.78, "TAR_TEMPORAL"),
        _track((50.0, 51.0), (51.0, 50.0)), body_scale=100.0,
    )
    assert decision.accepted
    assert decision.measurement_source == "TAR_TEMPORAL"
    assert decision.provenance == "TAR_TEMPORAL_MEASUREMENT+POINT_TRACK_SUPPORT"


@pytest.mark.parametrize("joint_name", ("wrist", "ankle"))
def test_wrong_rtmw_distal_joint_is_rejected_when_tar_and_tap_agree(
    joint_name: str,
) -> None:
    decision = fuse_joint_measurements(
        _pose((180.0, 20.0), 0.99, "RTMW"),
        _pose((42.0, 55.0), 0.76, "TAR_TEMPORAL"),
        _track((41.0, 54.0), (43.0, 55.0)), body_scale=120.0,
    )
    assert joint_name in {"wrist", "ankle"}
    assert decision.measurement_source == "TAR_TEMPORAL"


def test_rtmw_and_bidirectional_track_reject_tar_outlier() -> None:
    decision = fuse_joint_measurements(
        _pose((52.0, 50.0), 0.78, "RTMW"),
        _pose((150.0, 50.0), 0.97, "TAR_TEMPORAL"),
        _track((50.0, 51.0), (51.0, 50.0)), body_scale=100.0,
    )
    assert decision.accepted
    assert decision.measurement_source == "RTMW"


def test_forward_backward_disagreement_does_not_resolve_pose_conflict() -> None:
    decision = fuse_joint_measurements(
        _pose((20.0, 30.0), 0.7, "RTMW"),
        _pose((80.0, 30.0), 0.7, "TAR_TEMPORAL"),
        _track((20.0, 30.0), (90.0, 90.0)), body_scale=100.0,
    )
    assert not decision.accepted
    assert decision.tracker_support == "FORWARD_BACKWARD_DISAGREEMENT"


def test_tracker_occlusion_does_not_turn_missing_support_into_low_risk_evidence() -> None:
    decision = fuse_joint_measurements(
        _pose((30.0, 40.0), 0.85, "RTMW"),
        _pose((31.0, 41.0), 0.84, "TAR_TEMPORAL"),
        TrackerEvidence((30.0, 40.0), (31.0, 41.0), False, False),
        body_scale=100.0,
    )
    assert decision.accepted
    assert decision.tracker_support == "TRACKER_UNAVAILABLE"
    assert "POINT_TRACK_SUPPORT" not in decision.provenance


def test_true_fast_motion_is_kept_when_both_pose_models_and_track_agree() -> None:
    decision = fuse_joint_measurements(
        _pose((210.0, 90.0), 0.81, "RTMW"),
        _pose((214.0, 91.0), 0.80, "TAR_TEMPORAL"),
        _track((212.0, 90.0), (213.0, 91.0)), body_scale=100.0,
    )
    assert decision.accepted
    assert decision.point is not None and decision.point[0] > 200.0


def test_side_identity_is_not_swapped_by_tracker_confidence() -> None:
    left = fuse_joint_measurements(
        _pose((30.0, 50.0), 0.7, "RTMW"),
        _pose((31.0, 50.0), 0.72, "TAR_TEMPORAL"),
        _track((31.0, 50.0)), body_scale=100.0,
    )
    right = fuse_joint_measurements(
        _pose((70.0, 50.0), 0.7, "RTMW"),
        _pose((69.0, 50.0), 0.72, "TAR_TEMPORAL"),
        _track((69.0, 50.0)), body_scale=100.0,
    )
    assert left.point is not None and right.point is not None
    assert left.point[0] < right.point[0]


def test_single_strong_image_measurement_is_explicitly_uncorroborated() -> None:
    decision = fuse_joint_measurements(
        _pose((20.0, 30.0), 0.9, "RTMW"),
        _pose(None, 0.0, "TAR_TEMPORAL"),
        _track(None, None, visible=False), body_scale=100.0,
    )
    assert decision.accepted
    assert decision.provenance == "RTMW_MEASUREMENT_UNCORROBORATED"
    assert decision.quality < 0.9


def test_single_weak_image_measurement_is_rejected() -> None:
    decision = fuse_joint_measurements(
        _pose((20.0, 30.0), 0.3, "RTMW"),
        _pose(None, 0.0, "TAR_TEMPORAL"),
        _track(None, None, visible=False), body_scale=100.0,
    )
    assert not decision.accepted


def test_core_frame_never_maps_face_hands_or_foot_extensions() -> None:
    points = np.tile(np.asarray((30.0, 40.0), dtype=np.float32), (133, 1))
    scores = np.ones(133, dtype=np.float32)
    tar_points = points[:17].copy()
    tar_scores = scores[:17].copy()
    decisions = fuse_core_frame(
        points, scores, tar_points, tar_scores, {}, body_scale=100.0,
    )
    assert tuple(decisions) == CORE_LIMB_JOINTS
    assert max(decisions) == 16


def test_hard_motion_segments_have_real_anchor_padding_and_merge() -> None:
    assert _segments({2, 3, 6}, 10, padding=1) == ((1, 7),)
    assert _segments({0, 9}, 10, padding=1) == ((0, 1), (8, 9))


def test_renderer_cache_cannot_override_final_temporal_expert_joint() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=1.0, minimum_quality=0.1)
    renderer.update(
        "left_forearm", np.asarray((10.0, 10.0)), np.asarray((30.0, 10.0)),
        first_source="MEASURED", second_source="MEASURED", confidence=0.9,
        timestamp_seconds=0.0, bbox=np.asarray((0, 0, 100, 100)),
        expected_length=20.0, frame_width=200, frame_height=200,
        track_id="operator-1",
    )
    rejected = renderer.update(
        "left_forearm", np.asarray((10.0, 10.0)), np.asarray((190.0, 190.0)),
        first_source="MEASURED", second_source="MEASURED", confidence=0.9,
        timestamp_seconds=0.05, bbox=np.asarray((0, 0, 100, 100)),
        expected_length=20.0, frame_width=200, frame_height=200,
        atomic_accepted=False, atomic_reason="ANATOMICAL_REACH_EXCEEDED",
        track_id="operator-1",
    )
    assert rejected.source == RenderSource.HIDDEN
    assert not rejected.visible
    assert rejected.rejection_reason == "ANATOMICAL_REACH_EXCEEDED"


def test_expert_unavailable_falls_back_without_opening_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSE_TEMPORAL_EXPERT_ENABLED", "true")
    monkeypatch.setenv("POSE_TAR_VITPOSE_CHECKPOINT", str(tmp_path / "missing-tar.pt"))
    monkeypatch.setenv("POSE_TAPNEXT_CHECKPOINT", str(tmp_path / "missing-tap.ckpt"))
    result = run_temporal_expert_pass(
        tmp_path / "missing.mp4", [{"source_frame_index": 0}], {0},
        repository_root=tmp_path,
    )
    assert not result.frames
    assert result.summary["reason"] == "TEMPORAL_EXPERT_WEIGHTS_MISSING"


def test_mocked_backends_execute_hard_segment_to_fusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tar_path = tmp_path / "tar.pt"; tar_path.write_bytes(b"tar")
    tap_path = tmp_path / "tap.ckpt"; tap_path.write_bytes(b"tap")
    monkeypatch.setenv("POSE_TEMPORAL_EXPERT_ENABLED", "true")
    monkeypatch.setenv("POSE_TAPNEXT_ENABLED", "true")
    monkeypatch.setenv("POSE_TAR_VITPOSE_CHECKPOINT", str(tar_path))
    monkeypatch.setenv("POSE_TAPNEXT_CHECKPOINT", str(tap_path))
    points = np.zeros((133, 2), dtype=np.float32)
    for joint in range(17):
        points[joint] = (30.0 + joint * 2.0, 40.0 + joint * 3.0)
    scores = np.ones(133, dtype=np.float32) * 0.85
    records = [{
        "source_frame_index": index,
        "raw_points": points.copy(), "raw_scores": scores.copy(),
        "bbox_array": np.asarray((10, 10, 120, 190), dtype=np.float32),
        "pose_graph": SimpleNamespace(body_scale=180.0),
    } for index in range(7)]
    frames = {index: np.zeros((200, 140, 3), dtype=np.uint8) for index in range(7)}
    monkeypatch.setattr(temporal_expert_pass, "_read_frames", lambda *_: frames)

    class FakeTar:
        def __init__(self, *_args, **_kwargs): pass
        def infer_window(self, _frames, _bbox):
            return TarPoseObservation(points[:17].copy(), scores[:17].copy(), 0.01, 1)
        def close(self): pass

    class FakeTap:
        def __init__(self, *_args, **_kwargs): pass
        def track_bidirectional(self, segment, start, end):
            count = len(segment); query_count = len(start)
            forward = np.repeat(start[None, :, :], count, axis=0)
            backward = np.repeat(end[None, :, :], count, axis=0)
            visible = np.ones((count, query_count), dtype=bool)
            return BidirectionalTapTracks(
                TapTrackSequence(forward, visible, 0.01, 1, "forward"),
                TapTrackSequence(backward, visible, 0.01, 1, "backward"),
            )
        def close(self): pass

    monkeypatch.setattr(temporal_expert_pass, "TarVitPoseBackend", FakeTar)
    monkeypatch.setattr(temporal_expert_pass, "TapNextPPBackend", FakeTap)
    result = run_temporal_expert_pass(
        tmp_path / "synthetic.mp4", records, {2, 3, 4}, repository_root=tmp_path,
    )
    assert result.summary["backend_executed"] is True
    assert result.summary["tar_executed"] is True
    assert result.summary["tapnext_executed"] is True
    assert set(result.frames) == {2, 3, 4}
    assert all(
        decision.accepted
        for frame in result.frames.values() for decision in frame.fusion.values()
    )

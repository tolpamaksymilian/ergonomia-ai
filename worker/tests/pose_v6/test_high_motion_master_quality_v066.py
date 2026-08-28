from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from worker.src.pose_v3.body_validation import BODY_BONES
from worker.src.pose_v6.contracts import validate_final_skeleton_contract
from worker.src.pose_v6.config import load_pose_v6_config
from worker.src.pose_v6.coordinate_space import (
    CoordinatePoseCandidate,
    CoordinateSpace,
    CoordinateSpaceError,
    CropTransform,
)
from worker.src.pose_v6.high_motion import (
    AnatomicalReachGate,
    compute_joint_kinematics,
    estimate_motion_blur,
)
from worker.src.pose_v6.limb_consistency import (
    attach_temporal_metadata,
    enforce_limb_chain_consistency,
    freeze_temporal_frames,
)
from worker.src.pose_v6.render_continuity import PersistentBoneRenderer, RenderSource
from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame
from worker.src.pose_v6.temporal_supersampling import (
    HighMotionTemporalSupersampling,
    TemporalSampleProvenance,
    bidirectional_native_prediction,
)
from worker.src.pose_v6.timeline import probe_native_frame_timeline


def _frame(
    *,
    left_leg: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    scores_value: float = 0.9,
    ankle_source: PointSource = PointSource.MEASURED,
    ankle_age: float = 0.0,
) -> TemporalFrame:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.zeros(23, dtype=np.float32)
    for joint, point in zip((11, 13, 15), left_leg):
        points[joint] = point
        scores[joint] = scores_value
    sources = [PointSource.MISSING] * 23
    for joint in (11, 13, 15):
        sources[joint] = PointSource.MEASURED
    sources[15] = ankle_source
    ages = np.zeros(23, dtype=np.float32)
    ages[15] = ankle_age
    return TemporalFrame(
        points.copy(), scores.copy(), points.copy(), scores.copy(),
        tuple(sources), scores > 0.0, ages,
        np.full(23, np.nan, dtype=np.float32),
    )


def _chain_frame(
    indexes: tuple[int, int, int],
    values: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
) -> TemporalFrame:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.zeros(23, dtype=np.float32)
    sources = [PointSource.MISSING] * 23
    for joint, point in zip(indexes, values):
        points[joint] = point
        scores[joint] = 0.92
        sources[joint] = PointSource.MEASURED
    return TemporalFrame(
        points.copy(), scores.copy(), points.copy(), scores.copy(),
        tuple(sources), scores > 0.0, np.zeros(23, dtype=np.float32),
        np.full(23, np.nan, dtype=np.float32),
    )


def _metadata(frame: TemporalFrame, timestamp: float, track: str = "track-1") -> TemporalFrame:
    return attach_temporal_metadata(
        frame,
        timestamp_seconds=timestamp,
        source_passes=["pass1-primary"] * 23,
        track_id=track,
    )


def _expected() -> dict[str, float | None]:
    values = {name: None for name in BODY_BONES}
    values.update({
        "left_thigh": 40.0,
        "left_lower_leg": 40.0,
        "right_thigh": 40.0,
        "right_lower_leg": 40.0,
        "left_upper_arm": 32.0,
        "left_forearm": 28.0,
        "right_upper_arm": 32.0,
        "right_forearm": 28.0,
    })
    return values


@pytest.mark.parametrize(
    "bbox",
    [
        (100.0, 80.0, 500.0, 680.0),
        (20.0, 15.0, 620.0, 710.0),
        (270.0, 40.0, 635.0, 450.0),
        (0.0, 0.0, 350.0, 500.0),
        (0.0, 210.0, 640.0, 720.0),
    ],
)
def test_coordinate_round_trip_stays_below_one_pixel(
    bbox: tuple[float, float, float, float],
) -> None:
    transform = CropTransform(bbox, (288, 384))
    points = np.asarray([
        (bbox[0] + 1.0, bbox[1] + 1.0),
        ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5),
        (bbox[2] - 1.0, bbox[3] - 1.0),
    ])
    assert transform.round_trip_error(points) < 1e-6


def test_coordinate_double_transform_is_rejected() -> None:
    transform = CropTransform((100.0, 50.0, 500.0, 650.0), (288, 384))
    packet = CoordinatePoseCandidate(
        np.asarray([[12.0, 20.0]], dtype=np.float32),
        np.asarray([0.9], dtype=np.float32),
        CoordinateSpace.PERSON_CROP_PIXELS,
        "test",
        transform=transform,
    ).to_original_pixels()
    repeated = replace(
        packet,
        space=CoordinateSpace.PERSON_CROP_PIXELS,
        conversion_count=1,
    )
    with pytest.raises(CoordinateSpaceError, match="more than once"):
        repeated.to_original_pixels()


def test_accurate_and_ultra_use_real_different_high_motion_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSE_TEMPORAL_SUPERSAMPLING_FACTOR", raising=False)
    monkeypatch.setenv("POSE_V6_PROFILE", "ACCURATE")
    accurate = load_pose_v6_config()
    monkeypatch.setenv("POSE_V6_PROFILE", "ULTRA")
    ultra = load_pose_v6_config()
    assert accurate.high_motion.temporal_supersampling_factor == 3
    assert ultra.high_motion.temporal_supersampling_factor == 5
    assert len(ultra.high_motion.limb_crop_scales) > len(
        accurate.high_motion.limb_crop_scales
    )


def test_stale_endpoint_is_reconstructed_before_a_bone_can_render() -> None:
    frames = [
        _metadata(_frame(left_leg=((100, 100), (100, 140), (100, 180))), 0.0),
        _metadata(_frame(
            left_leg=((110, 100), (110, 140), (350, 200)),
            ankle_source=PointSource.KINEMATIC_PREDICTED,
            ankle_age=0.2,
        ), 0.1),
        _metadata(_frame(left_leg=((120, 100), (120, 140), (120, 180))), 0.2),
    ]
    result = enforce_limb_chain_consistency(
        frames, [0.0, 0.1, 0.2], [200.0] * 3, BODY_BONES,
        [_expected()] * 3,
    )
    middle = result.frames[1]
    assert np.linalg.norm(middle.render_points[15] - middle.render_points[13]) == pytest.approx(40.0)
    assert result.bone_decisions[1]["left_lower_leg"].accepted
    assert result.summary["stale_endpoint_reject_count"] >= 1
    assert result.summary["catastrophic_bone_outlier_count"] == 0


def test_high_confidence_wrong_ankle_is_rejected_and_repaired() -> None:
    frames = [
        _metadata(_frame(left_leg=((80, 80), (80, 120), (80, 160))), 0.0),
        _metadata(_frame(left_leg=((90, 80), (90, 120), (420, 120))), 0.1),
        _metadata(_frame(left_leg=((100, 80), (100, 120), (100, 160))), 0.2),
    ]
    result = enforce_limb_chain_consistency(
        frames, [0.0, 0.1, 0.2], [200.0] * 3, BODY_BONES,
        [_expected()] * 3,
    )
    assert result.frames[1].analysis_scores[15] == 0.0
    assert result.frames[1].sources[15] == PointSource.KINEMATIC_PREDICTED
    assert result.bone_decisions[1]["left_lower_leg"].accepted
    assert result.summary["high_motion_repair_count"] >= 1


def test_true_fast_leg_motion_is_not_frozen() -> None:
    frames = [
        _metadata(_frame(left_leg=((40, 80), (40, 120), (40, 160))), 0.0),
        _metadata(_frame(left_leg=((100, 80), (100, 120), (100, 160))), 0.04),
        _metadata(_frame(left_leg=((180, 80), (180, 120), (180, 160))), 0.08),
    ]
    result = enforce_limb_chain_consistency(
        frames, [0.0, 0.04, 0.08], [200.0] * 3, BODY_BONES,
        [_expected()] * 3,
    )
    assert [float(frame.render_points[15, 0]) for frame in result.frames] == [40.0, 100.0, 180.0]
    assert result.summary["high_motion_repair_count"] == 0


def test_true_fast_arm_chain_follows_the_native_motion() -> None:
    frames = [
        _metadata(_chain_frame((5, 7, 9), ((40, 60), (70, 60), (98, 60))), 0.0),
        _metadata(_chain_frame((5, 7, 9), ((75, 60), (105, 60), (133, 60))), 0.04),
        _metadata(_chain_frame((5, 7, 9), ((125, 60), (155, 60), (183, 60))), 0.08),
    ]
    result = enforce_limb_chain_consistency(
        frames, [0.0, 0.04, 0.08], [170.0] * 3, BODY_BONES,
        [_expected()] * 3,
    )
    assert [float(frame.render_points[9, 0]) for frame in result.frames] == [98.0, 133.0, 183.0]
    assert result.summary["high_motion_repair_count"] == 0


def test_directional_gate_accepts_fast_motion_but_rejects_point_behind_it() -> None:
    gate = AnatomicalReachGate(maximum_directional_residual=1.0)
    accepted = gate.evaluate(
        np.asarray((100.0, 100.0)), np.asarray((150.0, 100.0)),
        expected_length=50.0, predicted=np.asarray((148.0, 100.0)),
        velocity=np.asarray((40.0, 0.0)), body_scale=200.0, fast_motion=True,
    )
    rejected = gate.evaluate(
        np.asarray((100.0, 100.0)), np.asarray((80.0, 150.0)),
        expected_length=54.0, predicted=np.asarray((148.0, 100.0)),
        velocity=np.asarray((40.0, 0.0)), body_scale=200.0, fast_motion=True,
    )
    assert accepted.accepted
    assert not rejected.accepted
    assert rejected.reason == "DIRECTIONAL_MOTION_GATE_REJECTED"


def test_five_x_temporal_support_has_provenance_and_does_not_inflate_coverage() -> None:
    points = [np.full((3, 2), value, dtype=np.float32) for value in (0.0, 10.0, 30.0)]
    scores = [np.ones(3, dtype=np.float32) for _ in points]
    result = HighMotionTemporalSupersampling(5).generate(
        points, scores, [0.0, 0.1, 0.25],
    )
    assert result.support_sample_count == 8
    assert result.measurement_coverage_denominator == 3
    assert all(
        item.provenance == TemporalSampleProvenance.TEMPORAL_SUPERSAMPLE_SUPPORT
        and not item.measurement_eligible
        for item in result.support_samples
    )
    direction = result.motion_vector_at_native(1, (0, 1, 2))
    assert direction is not None
    assert direction[0] > 0.0


def test_blurred_native_frame_uses_sharp_neighbor_prediction_without_teleport() -> None:
    points = [
        np.asarray([[0.0, 0.0]], dtype=np.float32),
        np.asarray([[400.0, 0.0]], dtype=np.float32),
        np.asarray([[20.0, 0.0]], dtype=np.float32),
    ]
    scores = [np.ones(1, dtype=np.float32) for _ in points]
    prediction = bidirectional_native_prediction(points, scores, [0.0, 0.1, 0.2], 1)
    assert prediction is not None
    assert prediction[0][0, 0] == pytest.approx(10.0)
    assert prediction[1][0] > 0.0


def test_motion_blur_indicator_distinguishes_edges_from_uniform_image() -> None:
    sharp = np.zeros((80, 80, 3), dtype=np.uint8)
    sharp[:, 20:40] = 255
    sharp[20:40, :] = 255
    sharp[50:60, 10:70] = 255
    blurred = np.full((80, 80, 3), 128, dtype=np.uint8)
    assert estimate_motion_blur(blurred).blur_score > estimate_motion_blur(sharp).blur_score


def test_velocity_acceleration_and_jerk_are_dt_aware() -> None:
    result = compute_joint_kinematics(
        [np.asarray((0.0, 0.0)), np.asarray((10.0, 0.0)), np.asarray((30.0, 0.0))],
        [0.0, 0.1, 0.3],
    )
    assert len(result) == 3
    assert all(item.speed >= 0.0 for item in result)
    assert all(np.isfinite(item.jerk_magnitude) for item in result)


def test_renderer_never_mixes_current_and_stale_endpoint() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=0.5, minimum_quality=0.1)
    measured = renderer.update(
        "left_lower_leg", np.asarray((100.0, 100.0)), np.asarray((100.0, 140.0)),
        first_source="MEASURED", second_source="MEASURED", confidence=0.9,
        timestamp_seconds=0.0, bbox=np.asarray((50, 50, 180, 220)),
        expected_length=40.0, frame_width=640, frame_height=480, track_id="one",
    )
    rejected = renderer.update(
        "left_lower_leg", np.asarray((110.0, 100.0)), np.asarray((500.0, 300.0)),
        first_source="MEASURED", second_source="KINEMATIC_PREDICTED", confidence=0.9,
        timestamp_seconds=0.1, bbox=np.asarray((60, 50, 190, 220)),
        expected_length=40.0, frame_width=640, frame_height=480,
        atomic_accepted=False, atomic_reason="ENDPOINT_TIME_MISMATCH",
        endpoint_age_delta=0.2, track_id="one",
    )
    assert measured.source == RenderSource.MEASURED
    assert rejected.source == RenderSource.HELD
    assert rejected.second is not None and rejected.second[0] < 200.0
    assert rejected.rejection_reason == "ENDPOINT_TIME_MISMATCH"


def test_final_renderer_contract_receives_immutable_original_pixel_chain() -> None:
    frames = [
        _metadata(_frame(left_leg=((100, 100), (100, 140), (100, 180))), 0.0),
    ]
    result = enforce_limb_chain_consistency(
        frames, [0.0], [200.0], BODY_BONES, [_expected()],
    )
    frozen = freeze_temporal_frames(result.frames)
    report = validate_final_skeleton_contract(
        frozen,
        expected_frame_count=1,
        body_joint_count=23,
        identity_scores=[1.0],
        require_immutable=True,
        require_v66_metadata=True,
    )
    assert report.immutable_checked
    assert report.v66_metadata_checked
    with pytest.raises(ValueError):
        frozen[0].render_points[15, 0] = 999.0


def test_pts_timeline_falls_back_explicitly_without_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("worker.src.pose_v6.timeline.shutil.which", lambda _: None)
    result = probe_native_frame_timeline(
        tmp_path / "missing.mp4", fallback_fps=25.0, expected_frame_count=3,
    )
    assert result.timestamps == (0.0, 0.04, 0.08)
    assert result.fallback_used
    assert result.source == "constant-fps-fallback"


def test_high_motion_chain_to_renderer_integration_blocks_spear_line() -> None:
    native = [
        _metadata(_frame(left_leg=((80, 80), (80, 120), (80, 160))), 0.0),
        _metadata(_frame(left_leg=((90, 80), (90, 120), (500, 140))), 0.05),
        _metadata(_frame(left_leg=((110, 80), (110, 120), (110, 160))), 0.10),
    ]
    support = HighMotionTemporalSupersampling(5).generate(
        [frame.render_points for frame in native],
        [frame.render_scores for frame in native],
        [0.0, 0.05, 0.10],
    )
    assert support.support_sample_count == 8
    final = enforce_limb_chain_consistency(
        native, [0.0, 0.05, 0.10], [200.0] * 3, BODY_BONES,
        [_expected()] * 3,
    )
    frozen = freeze_temporal_frames(final.frames)
    contract = validate_final_skeleton_contract(
        frozen, expected_frame_count=3, body_joint_count=23,
        identity_scores=[1.0] * 3, require_immutable=True,
        require_v66_metadata=True,
    )
    renderer = PersistentBoneRenderer(persistence_seconds=0.15, minimum_quality=0.1)
    rendered = []
    for index, frame in enumerate(frozen):
        decision = final.bone_decisions[index]["left_lower_leg"]
        rendered.append(renderer.update(
            "left_lower_leg", frame.render_points[13], frame.render_points[15],
            first_source=frame.sources[13].value,
            second_source=frame.sources[15].value,
            confidence=min(float(frame.render_scores[13]), float(frame.render_scores[15])),
            timestamp_seconds=float(frame.frame_timestamp_seconds),
            bbox=np.asarray((40, 40, 180, 210)), expected_length=40.0,
            frame_width=640, frame_height=480,
            atomic_accepted=decision.accepted, atomic_reason=decision.reason,
            endpoint_age_delta=decision.endpoint_age_delta,
            bone_length_ratio_to_canonical=decision.bone_length_ratio_to_canonical,
            track_id=frame.track_id,
        ))
    assert contract.immutable_checked
    assert all(
        bone.bone_length_ratio_to_canonical is None
        or bone.bone_length_ratio_to_canonical <= 1.85
        for bone in rendered
    )
    assert final.summary["catastrophic_bone_outlier_count"] == 0

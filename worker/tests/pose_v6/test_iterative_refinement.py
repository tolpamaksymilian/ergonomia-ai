from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v6.config import IterativeRefinementConfig
from worker.src.pose_v6.contracts import (
    FinalSkeletonContractError,
    validate_final_skeleton_contract,
)
from worker.src.pose_v6.anatomical_stability import project_anatomical_sequence
from worker.src.pose_v6.iterative_refinement import (
    PoseAuditInputError,
    PoseErrorCode,
    PoseHypothesis,
    audit_pose_sequence,
    detect_angle_glitches,
    detect_grip_flicker,
    fuse_pose_hypotheses,
    normalize_joint_age_vector,
    normalize_joint_mask,
    optimize_global_trajectories,
    select_best_iteration,
    select_critical_segments,
)
from worker.src.pose_v6.quality_benchmark import compare_quality_documents
from worker.src.pose_v6.serialization import serialize_pose_document
from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame


def _config(**overrides: object) -> IterativeRefinementConfig:
    values = {
        "pass2_maximum_ratio": 1.0,
        "pass3_critical_ratio": 0.05,
        "segment_padding_seconds": 0.0,
        "convergence_epsilon": 0.006,
        "minimum_quality_gain": 0.01,
        "maximum_repair_iterations": 3,
    }
    values.update(overrides)
    return IterativeRefinementConfig(**values)


def _body_frame(offset: float = 0.0) -> np.ndarray:
    points = np.zeros((23, 2), dtype=np.float32)
    points[5] = (40 + offset, 30)
    points[6] = (60 + offset, 30)
    points[7] = (35 + offset, 50)
    points[8] = (65 + offset, 50)
    points[9] = (30 + offset, 70)
    points[10] = (70 + offset, 70)
    points[11] = (44 + offset, 65)
    points[12] = (56 + offset, 65)
    points[13] = (43 + offset, 90)
    points[14] = (57 + offset, 90)
    points[15] = (42 + offset, 115)
    points[16] = (58 + offset, 115)
    return points


def _audit(points: list[np.ndarray], *, motion: str = "NORMAL_MOTION", cuts: list[bool] | None = None, tracking: list[str] | None = None):
    count = len(points)
    return audit_pose_sequence(
        points,
        [np.full(23, 0.9, dtype=np.float32) for _ in points],
        [80.0] * count,
        [index / 30.0 for index in range(count)],
        tracking or ["TRACKED"] * count,
        [motion] * count,
        cuts or [False] * count,
        config=_config(),
        body_joint_count=17,
    )


def _temporal_frame(point: np.ndarray, *, source: PointSource = PointSource.MEASURED) -> TemporalFrame:
    points = _body_frame()
    points[7] = point
    scores = np.full(23, 0.9, dtype=np.float32)
    return TemporalFrame(
        points.copy(), scores.copy(), points.copy(), scores.copy(),
        tuple(source for _ in range(23)), np.ones(23, dtype=bool),
        np.zeros(23, dtype=np.float32), np.full(23, np.nan, dtype=np.float32),
    )


def test_best_result_is_pass2_when_pass3_does_not_improve() -> None:
    best, decisions = select_best_iteration([0.62, 0.78, 0.779], config=_config())
    assert best == 2
    assert decisions[-1].converged is True


def test_regressing_pass2_rolls_back_to_pass1() -> None:
    best, decisions = select_best_iteration([0.82, 0.71, 0.95], config=_config())
    assert best == 1
    assert decisions[0].rolled_back is True
    assert len(decisions) == 1


def test_convergence_prevents_pass3() -> None:
    best, decisions = select_best_iteration([0.80, 0.803, 0.95], config=_config())
    assert best == 1
    assert len(decisions) == 1
    assert decisions[0].converged is True


def test_per_joint_consensus_rejects_outlier_and_improves_drift() -> None:
    baseline = _body_frame()
    baseline[7] = (70, 10)
    good_a = _body_frame()
    good_b = _body_frame()
    outlier = _body_frame()
    outlier[7] = (5, 120)
    scores = np.full(23, 0.85, dtype=np.float32)
    scores[7] = 0.35
    result = fuse_pose_hypotheses(
        [
            PoseHypothesis(baseline, scores, "pass1", 1, 1.0),
            PoseHypothesis(good_a, np.full(23, 0.94, dtype=np.float32), "pass2-a", 2, 0.9),
            PoseHypothesis(good_b + 0.5, np.full(23, 0.92, dtype=np.float32), "pass2-b", 2, 0.9),
            PoseHypothesis(outlier, np.full(23, 0.99, dtype=np.float32), "outlier", 2, 0.9),
        ],
        body_scale=80.0,
        previous_points=good_a,
        following_points=good_b,
    )
    assert 7 in result.corrected_joint_indexes
    assert 7 in result.disagreement_joint_indexes
    assert np.linalg.norm(result.points[7] - good_a[7]) < 3.0


def test_only_worst_five_percent_becomes_critical() -> None:
    points = [_body_frame(float(index)) for index in range(100)]
    points[50][7] = (300, 300)
    audit = _audit(points)
    critical = select_critical_segments(audit, maximum_ratio=0.05)
    assert sum(item.frame_count for item in critical) <= 5
    assert any(item.start_frame <= 50 <= item.end_frame for item in critical)


def test_angle_glitch_returns_dependent_joints_for_reanalysis() -> None:
    frames = [_body_frame() for _ in range(5)]
    frames[2][9] = (35, 25)
    scores = [np.full(23, 0.9, dtype=np.float32) for _ in frames]
    glitches = detect_angle_glitches(frames, scores)
    assert 2 in glitches
    assert set((5, 7, 9)).issubset(glitches[2])
    audit = _audit(frames)
    assert any(error.code == PoseErrorCode.ANGLE_OUTLIER for error in audit.frames[2].errors)


def test_single_frame_grip_flicker_triggers_local_repass() -> None:
    assert detect_grip_flicker(["POWER_GRIP", "OPEN", "POWER_GRIP"]) == (1,)


def test_global_optimizer_preserves_sustained_fast_motion() -> None:
    frames = [
        _temporal_frame(np.asarray((35 + index * 12, 50), dtype=np.float32))
        for index in range(5)
    ]
    before = [frame.analysis_points[7].copy() for frame in frames]
    result = optimize_global_trajectories(
        frames, [80.0] * 5, ["FAST_MOTION"] * 5, ["TRACKED"] * 5,
        [False] * 5, config=_config(), body_joint_count=17,
    )
    assert all(np.allclose(frame.analysis_points[7], point) for frame, point in zip(result.frames, before))


def test_short_occlusion_uses_context_but_hard_lost_is_not_retried() -> None:
    points = [_body_frame(float(index)) for index in range(8)]
    scores = [np.full(23, 0.9, dtype=np.float32) for _ in points]
    scores[3][7] = 0.0
    tracking = ["TRACKED", "TRACKED", "TRACKED", "OCCLUDED", "TRACKED", "LOST", "TRACKED", "TRACKED"]
    audit = audit_pose_sequence(
        points, scores, [80.0] * 8, [index / 30 for index in range(8)], tracking,
        ["NORMAL_MOTION"] * 8, [False] * 8, config=_config(), body_joint_count=17,
    )
    assert any(segment.start_frame <= 3 <= segment.end_frame for segment in audit.hard_segments)
    assert not any(segment.start_frame == 5 and segment.end_frame == 5 for segment in audit.hard_segments)


def test_scene_cut_prevents_hard_segment_merge() -> None:
    points = [_body_frame(float(index)) for index in range(8)]
    points[3][7] = (200, 200)
    points[4][7] = (210, 210)
    audit = _audit(points, cuts=[False, False, False, False, True, False, False, False])
    assert all(not (segment.start_frame < 4 <= segment.end_frame) for segment in audit.hard_segments)


def test_isolated_left_right_swap_is_part_of_error_map() -> None:
    points = [_body_frame() for _ in range(3)]
    points[1][7], points[1][8] = points[1][8].copy(), points[1][7].copy()
    audit = _audit(points)
    assert any(
        error.code == PoseErrorCode.LEFT_RIGHT_AMBIGUITY
        for error in audit.frames[1].errors
    )


def test_global_optimizer_repairs_isolated_joint_jump_and_reports_best_state() -> None:
    values = [(35, 50), (36, 50), (120, 5), (38, 50), (39, 50)]
    frames = [_temporal_frame(np.asarray(value, dtype=np.float32)) for value in values]
    result = optimize_global_trajectories(
        frames, [80.0] * 5, ["NORMAL_MOTION"] * 5, ["TRACKED"] * 5,
        [False] * 5, config=_config(minimum_quality_gain=0.0), body_joint_count=17,
    )
    assert np.linalg.norm(result.frames[2].analysis_points[7] - np.asarray((37, 50))) < np.linalg.norm(np.asarray(values[2]) - np.asarray((37, 50)))
    assert result.summary["quality_score_after"] >= result.summary["quality_score_before"]
    assert result.summary["iterations"] <= 3


def test_audit_exposes_quality_not_accuracy_and_error_map() -> None:
    points = [_body_frame(), _body_frame(), _body_frame()]
    points[1][7] = (200, 200)
    audit = _audit(points)
    document = audit.to_dict()
    assert 0.0 <= document["quality_score"] <= 1.0
    assert document["error_count"] > 0
    assert "accuracy" not in document


def test_quality_benchmark_compares_single_and_multi_pass_without_accuracy_claim() -> None:
    baseline = {"summary": {"iterative_v64": {"pass1_quality": 0.6, "final_quality": 0.6}}}
    candidate = {"summary": {"iterative_v64": {"pass1_quality": 0.6, "final_quality": 0.8}}}
    result = compare_quality_documents(candidate, baseline)
    assert result["comparison_mode"] == "single-pass-vs-multi-pass"
    assert result["accuracy_claimed"] is False
    assert result["delta"]["final_quality"] == 0.2


def test_local_repair_does_not_modify_frames_outside_selected_segment() -> None:
    values = [(35, 50), (36, 50), (120, 5), (38, 50), (39, 50), (140, 10), (41, 50)]
    frames = [_temporal_frame(np.asarray(value, dtype=np.float32)) for value in values]
    outside_before = frames[5].analysis_points[7].copy()
    result = optimize_global_trajectories(
        frames, [80.0] * len(frames), ["NORMAL_MOTION"] * len(frames),
        ["TRACKED"] * len(frames), [False] * len(frames),
        config=_config(minimum_quality_gain=0.0), body_joint_count=17,
        allowed_frame_indexes={2},
    )
    assert np.allclose(result.frames[5].analysis_points[7], outside_before)
    assert result.summary["localized"] is True
    assert result.summary["allowed_frame_count"] == 1


def test_geometry_regression_cannot_win_only_by_increasing_coverage() -> None:
    good_points = [_body_frame() for _ in range(3)]
    good_scores = [np.full(23, 0.9, dtype=np.float32) for _ in range(3)]
    for values in good_scores:
        values[0:2] = 0.0
    good = audit_pose_sequence(
        good_points, good_scores, [80.0] * 3, [0.0, 0.033, 0.066],
        ["TRACKED"] * 3, ["NORMAL_MOTION"] * 3, [False] * 3,
        config=_config(), body_joint_count=17,
    )
    bad_points = [_body_frame() for _ in range(3)]
    bad_points[1][7] = (300, 300)
    bad = _audit(bad_points)
    assert bad.frames[1].measurement_coverage > good.frames[1].measurement_coverage
    assert bad.frames[1].quality_score < good.frames[1].quality_score


def test_render_only_prediction_does_not_increase_measurement_quality() -> None:
    frames = [_temporal_frame(np.asarray((35, 50), dtype=np.float32), source=PointSource.KINEMATIC_PREDICTED) for _ in range(3)]
    audit = audit_pose_sequence(
        [frame.analysis_points for frame in frames],
        [frame.analysis_scores for frame in frames],
        [80.0] * 3, [0.0, 0.033, 0.066], ["TRACKED"] * 3,
        ["NORMAL_MOTION"] * 3, [False] * 3, config=_config(),
        point_sources=[frame.sources for frame in frames], body_joint_count=17,
    )
    assert audit.frames[1].measurement_coverage == 0.0
    assert audit.frames[1].renderer_fallback_usage == 1.0


def test_iterative_diagnostics_cross_strict_json_boundary() -> None:
    audit = _audit([_body_frame(), _body_frame(), _body_frame()])
    payload = {
        "summary": {"iterative_v64": audit.to_dict()},
        "frames": [{"pose_self_audit_v64": frame.to_dict()} for frame in audit.frames],
    }
    encoded = serialize_pose_document(payload, document_name="iterative-test")
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_audit_prediction_age_handles_real_v64_shape() -> None:
    """Regression: a tuple of 1-D indexes was interpreted as N-D indexing."""

    ages = np.zeros(23, dtype=np.float32)
    ages[[2, 7, 10]] = [0.26, 0.55, 0.40]
    coordinate_mask = np.repeat((ages > 0.25)[:, None], 2, axis=1)
    assert normalize_joint_mask(coordinate_mask, 17).shape == (17,)

    result = audit_pose_sequence(
        [_body_frame()],
        [np.full(23, 0.9, dtype=np.float32)],
        [80.0],
        [0.0],
        ["TRACKED"],
        ["NORMAL_MOTION"],
        [False],
        config=_config(),
        prediction_ages=[ages],
        body_joint_count=17,
    )

    errors = [
        error for error in result.frames[0].errors
        if error.code == PoseErrorCode.PREDICTION_TOO_OLD
    ]
    assert len(errors) == 1
    assert errors[0].joint_indexes == (2, 7, 10)
    assert errors[0].severity == pytest.approx(0.55)


def test_prediction_too_old_mask_shape_regression() -> None:
    for dtype in (np.float32, np.float64):
        for indexes in ((), (3,), (1, 5, 9), tuple(range(17))):
            ages = np.zeros(23, dtype=dtype)
            if indexes:
                ages[list(indexes)] = 0.5
            result = audit_pose_sequence(
                [_body_frame()],
                [np.full(23, 0.9, dtype=np.float32)],
                [80.0], [0.0], ["TRACKED"], ["NORMAL_MOTION"], [False],
                config=_config(), prediction_ages=[ages], body_joint_count=17,
            )
            errors = [
                error for error in result.frames[0].errors
                if error.code == PoseErrorCode.PREDICTION_TOO_OLD
            ]
            if indexes:
                assert errors[0].joint_indexes == indexes
                assert errors[0].severity == 0.5
            else:
                assert errors == []


def test_prediction_age_coordinate_layout_reduces_per_joint() -> None:
    ages = np.zeros((23, 2), dtype=np.float32)
    ages[4] = (0.1, 0.6)
    normalized = normalize_joint_age_vector(ages, 17)
    assert normalized.shape == (17,)
    assert normalized[4] == pytest.approx(0.6)


def test_prediction_age_non_finite_is_diagnostic_not_numpy_crash() -> None:
    ages = np.zeros(23, dtype=np.float32)
    ages[4] = np.nan
    ages[8] = np.inf
    result = audit_pose_sequence(
        [_body_frame()], [np.full(23, 0.9, dtype=np.float32)], [80.0],
        [0.0], ["TRACKED"], ["NORMAL_MOTION"], [False], config=_config(),
        prediction_ages=[ages], body_joint_count=17,
    )
    error = next(
        item for item in result.frames[0].errors
        if item.code == PoseErrorCode.PREDICTION_TOO_OLD
    )
    assert error.joint_indexes == (4, 8)
    assert error.severity == 1.0


def test_flow_disagreement_multiple_joint_indexes_do_not_use_tuple_indexing() -> None:
    flow = np.zeros(23, dtype=np.float32)
    flow[[1, 7, 12]] = (3.0, 4.0, 5.0)
    result = audit_pose_sequence(
        [_body_frame()], [np.full(23, 0.9, dtype=np.float32)], [80.0],
        [0.0], ["TRACKED"], ["NORMAL_MOTION"], [False], config=_config(),
        flow_errors=[flow], body_joint_count=17,
    )
    error = next(
        item for item in result.frames[0].errors
        if item.code == PoseErrorCode.FLOW_DISAGREEMENT
    )
    assert error.joint_indexes == (1, 7, 12)
    assert error.severity == pytest.approx(5.0 / 6.0)


def test_prediction_age_unknown_shape_is_rejected_with_contract_details() -> None:
    with pytest.raises(PoseAuditInputError, match="prediction_ages.*shape"):
        normalize_joint_age_vector(np.zeros((1, 17), dtype=np.float32), 17)


def test_full_v65_final_audit_after_global_optimization() -> None:
    frames = [
        _temporal_frame(np.asarray((35 + index, 50), dtype=np.float32))
        for index in range(6)
    ]
    frames[3].prediction_age_seconds[[2, 7, 10]] = (0.30, 0.45, 0.55)
    optimized = optimize_global_trajectories(
        frames, [80.0] * 6, ["NORMAL_MOTION"] * 6, ["TRACKED"] * 6,
        [False] * 6, config=_config(minimum_quality_gain=0.0),
        body_joint_count=17,
    )
    projected = project_anatomical_sequence(
        optimized.frames,
        [80.0] * 6,
        [index / 30.0 for index in range(6)],
        ["TRACKED"] * 6,
        [False] * 6,
        maximum_prediction_seconds=0.55,
    )
    contract = validate_final_skeleton_contract(
        projected.frames, expected_frame_count=6, body_joint_count=17,
        identity_scores=[0.9] * 6,
    )
    audit = audit_pose_sequence(
        [frame.analysis_points for frame in projected.frames],
        [frame.analysis_scores for frame in projected.frames],
        [80.0] * 6, [index / 30.0 for index in range(6)],
        ["TRACKED"] * 6, ["NORMAL_MOTION"] * 6, [False] * 6,
        config=_config(),
        prediction_ages=[frame.prediction_age_seconds for frame in projected.frames],
        flow_errors=[frame.flow_errors for frame in projected.frames],
        point_sources=[frame.sources for frame in projected.frames],
        body_joint_count=17,
    )
    assert contract.frame_count == 6
    assert len(audit.frames) == 6
    assert any(
        error.code == PoseErrorCode.PREDICTION_TOO_OLD
        for error in audit.frames[3].errors
    )


def test_final_skeleton_contract_rejects_non_finite_usable_geometry() -> None:
    frame = _temporal_frame(np.asarray((35, 50), dtype=np.float32))
    frame.analysis_points[7] = (np.nan, 50)
    with pytest.raises(FinalSkeletonContractError, match="analysis_points"):
        validate_final_skeleton_contract(
            [frame], expected_frame_count=1, body_joint_count=17,
            identity_scores=[0.9],
        )


def test_global_optimizer_shapes_for_no_prediction_all_prediction_and_partial_mask() -> None:
    measured = _temporal_frame(np.asarray((35, 50), dtype=np.float32))
    predicted = _temporal_frame(
        np.asarray((36, 50), dtype=np.float32),
        source=PointSource.KINEMATIC_PREDICTED,
    )
    predicted.prediction_age_seconds[:] = 0.2
    partial = _temporal_frame(np.asarray((37, 50), dtype=np.float32))
    partial.analysis_usable[[2, 7, 10]] = False
    partial.prediction_age_seconds[7] = np.nan
    frames = [measured, predicted, partial, measured, predicted]
    result = optimize_global_trajectories(
        frames, [80.0] * 5, ["NORMAL_MOTION"] * 5, ["TRACKED"] * 5,
        [False] * 5, config=_config(), body_joint_count=17,
        timestamps=[index / 30.0 for index in range(5)],
    )
    assert len(result.frames) == 5
    for frame in result.frames:
        assert frame.analysis_points.shape == (23, 2)
        assert frame.analysis_scores.shape == (23,)
        assert frame.analysis_usable.shape == (23,)
        assert frame.prediction_age_seconds.shape == (23,)
    assert result.summary["version"] == "global-trajectory-optimization-v2"
    assert "joint_topology" in result.summary["objective_terms"]

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from worker.src.pose_v6.config import GlobalBodyConfig
from worker.src.pose_v6.final_body_contract import (
    validate_renderer_final_state_parity,
    validate_serialized_final_state_parity,
)
from worker.src.pose_v6.global_body import solve_global_body_sequence
from worker.src.pose_v6.silhouette import (
    PackedPersonMask,
    assess_mask_sequence,
    evaluate_skeleton_against_silhouette,
)
from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame


def test_no_kinematic_pass_mutates_the_global_solver_result() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "src" / "pose_worker.py"
    ).read_text(encoding="utf-8")
    solve_start = source.index("global_body_result = solve_global_body_sequence(")
    immutable_boundary = source.index(
        "temporal_frames = list(freeze_temporal_frames(temporal_frames))",
        solve_start,
    )
    post_solver = source[solve_start:immutable_boundary]
    assert post_solver.count("enforce_limb_chain_consistency(") == 0
    assert "temporal_frames = list(global_body_result.frames)" in post_solver


CORE_BONES = {
    "left_upper_arm": (5, 7), "left_forearm": (7, 9),
    "right_upper_arm": (6, 8), "right_forearm": (8, 10),
    "left_thigh": (11, 13), "left_lower_leg": (13, 15),
    "right_thigh": (12, 14), "right_lower_leg": (14, 16),
}


def _body_points() -> tuple[np.ndarray, np.ndarray]:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.zeros(23, dtype=np.float32)
    coordinates = {
        5: (52, 36), 6: (68, 36), 7: (43, 51), 8: (77, 51),
        9: (35, 65), 10: (85, 65), 11: (54, 68), 12: (66, 68),
        13: (53, 88), 14: (67, 88), 15: (52, 108), 16: (68, 108),
        17: (50, 111), 18: (49, 112), 19: (53, 112),
        20: (66, 111), 21: (65, 112), 22: (69, 112),
    }
    for joint, value in coordinates.items():
        points[joint] = value
        scores[joint] = 0.9
    return points, scores


def _frame(points: np.ndarray, scores: np.ndarray) -> TemporalFrame:
    count = len(scores)
    return TemporalFrame(
        analysis_points=points.copy(), analysis_scores=scores.copy(),
        render_points=points.copy(), render_scores=scores.copy(),
        sources=tuple(
            PointSource.MEASURED if score > 0.0 else PointSource.MISSING
            for score in scores
        ),
        analysis_usable=scores > 0.0,
        prediction_age_seconds=np.zeros(count, dtype=np.float32),
        flow_errors=np.full(count, np.nan, dtype=np.float32),
    )


def _silhouettes(count: int):
    mask = np.zeros((120, 120), dtype=np.uint8)
    cv2.rectangle(mask, (25, 8), (95, 115), 1, cv2.FILLED)
    packed = PackedPersonMask.from_mask(mask, logit_confidence=0.98)
    return assess_mask_sequence(
        [packed] * count,
        [[25, 8, 96, 116]] * count,
        [np.asarray([[52, 36], [68, 36], [54, 68], [66, 68]], dtype=np.float32)] * count,
        [100.0] * count,
        source_frame_indexes=list(range(count)),
        timestamps=[index / 30 for index in range(count)],
        track_ids=["worker-1"] * count,
        anchor_indexes={0},
    )


def _solve(frames: list[TemporalFrame], raw_points: list[np.ndarray], raw_scores: list[np.ndarray]):
    silhouettes = _silhouettes(len(frames))
    evidence = [
        evaluate_skeleton_against_silhouette(
            silhouette, frame.render_points, frame.render_scores, CORE_BONES,
            body_scale=100.0, motion_blur=0.0, motion_state="NORMAL", occluded=False,
        )
        for silhouette, frame in zip(silhouettes, frames)
    ]
    return solve_global_body_sequence(
        frames, raw_points, raw_scores, silhouettes, evidence,
        [100.0] * len(frames), [index / 30 for index in range(len(frames))],
        ["NORMAL"] * len(frames), [False] * len(frames),
        config=GlobalBodyConfig(beam_width=6, minimum_quality_gain=0.001),
    )


def test_global_solver_rejects_high_confidence_catastrophic_chain() -> None:
    good_points, scores = _body_points()
    bad_points = good_points.copy()
    bad_points[15] = (118, 10)
    result = _solve([_frame(good_points, scores)], [bad_points], [scores.copy()])

    candidates = result.frame_diagnostics[0]["candidates"]
    bad_candidates = [item for item in candidates if item["hypothesis_id"] == "H1_RTMW_LEFT_LEG"]
    assert bad_candidates
    assert bad_candidates[0]["valid"] is False
    assert any(
        reason.startswith("CATASTROPHIC_BONE")
        for reason in bad_candidates[0]["hard_rejection_reasons"]
    )


def test_full_body_hypothesis_combines_valid_arm_and_leg_chains() -> None:
    good_points, scores = _body_points()
    mixed_points = good_points.copy()
    mixed_points[8] += (8.0, 4.0)
    mixed_points[10] += (10.0, 6.0)
    mixed_points[14] += (0.0, 18.0)
    mixed_points[16] += (0.0, 18.0)
    result = _solve(
        [_frame(mixed_points, scores)],
        [good_points.copy()],
        [scores.copy()],
    )

    selected = result.states[0]
    assert selected.selected_hypothesis_id.startswith("H2_CHAIN_FUSION_")
    assert "RIGHT_ARM" in selected.selected_hypothesis_id
    assert "RIGHT_LEG" in selected.selected_hypothesis_id
    assert np.allclose(selected.frame.render_points[10], good_points[10])
    assert np.allclose(selected.frame.render_points[16], good_points[16])
    assert result.summary["composite_hypotheses_generated"] > 0


def test_sequence_solver_selects_neighbor_supported_wrist_in_blurred_frame() -> None:
    points, scores = _body_points()
    bad_middle = points.copy()
    bad_middle[9] = (115, 20)
    frames = [_frame(points, scores), _frame(bad_middle, scores), _frame(points, scores)]
    raw = [points.copy(), bad_middle.copy(), points.copy()]

    result = _solve(frames, raw, [scores.copy(), scores.copy(), scores.copy()])

    assert np.linalg.norm(result.frames[1].render_points[9] - points[9]) < 1.0
    assert result.states[1].selected_hypothesis_id == "H4_GLOBAL_TEMPORAL"
    assert result.summary["sequence_solver"]["algorithm"] == "beam-search"


def test_final_body_state_is_immutable_and_renderer_has_exact_parity() -> None:
    points, scores = _body_points()
    result = _solve([_frame(points, scores)], [points.copy()], [scores.copy()])
    state = result.states[0]

    assert state.frame.render_points.flags.writeable is False
    parity = validate_renderer_final_state_parity([state], [state.frame.render_points.copy()])
    assert parity["valid"]
    assert parity["renderer_final_state_mismatch_count"] == 0

    serialized = [
        [
            [round(float(point[0]), 3), round(float(point[1]), 3)]
            if score > 0.0 else None
            for point, score in zip(state.frame.render_points, state.frame.render_scores)
        ]
    ]
    assert validate_serialized_final_state_parity([state], serialized)["valid"]


def test_renderer_parity_detects_geometry_from_another_state() -> None:
    points, scores = _body_points()
    result = _solve([_frame(points, scores)], [points.copy()], [scores.copy()])
    changed = result.states[0].frame.render_points.copy()
    changed[9, 0] += 1.0

    parity = validate_renderer_final_state_parity(result.states, [changed])
    assert parity["valid"] is False
    assert parity["renderer_final_state_mismatch_count"] == 1


def test_fast_motion_is_not_smoothed_when_observed_geometry_is_consistent() -> None:
    points, scores = _body_points()
    moved = points.copy()
    moved[[7, 9], 0] += 12.0
    result = _solve(
        [_frame(points, scores), _frame(moved, scores)],
        [points.copy(), moved.copy()],
        [scores.copy(), scores.copy()],
    )
    assert np.allclose(result.frames[1].render_points[9], moved[9])


def test_worst_frame_repair_preserves_best_state_instead_of_latest_state() -> None:
    points, scores = _body_points()
    weak_scores = scores.copy()
    weak_scores[9] = 0.2
    weak_frame = _frame(points, weak_scores)
    result = _solve([weak_frame], [points.copy()], [scores.copy()])

    assert result.summary["best_state_history_preserved"] is True
    assert result.summary["deep_repair_iterations_executed"] <= 1
    assert result.states[0].body_quality > 0.0

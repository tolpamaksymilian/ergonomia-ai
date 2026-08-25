from __future__ import annotations

import numpy as np

from worker.src.pose_v6.coverage import (
    TimelineState,
    UsabilityLevel,
    build_frame_layer_contract,
    coalesce_short_timeline_gaps,
    summarize_layer_coverage,
)
from worker.src.pose_v6.fusion import fuse_pose_candidates
from worker.src.pose_v6.temporal_reconstruction import reconstruct_temporal_sequence


def _pose_frame(*, missing: set[int] | None = None, refined: set[int] | None = None):
    points = np.asarray([[100.0 + index * 3.0, 80.0 + index * 5.0] for index in range(23)], dtype=np.float32)
    scores = np.full(23, 0.92, dtype=np.float32)
    for index in missing or set():
        scores[index] = 0.0
    temporal = reconstruct_temporal_sequence(
        [points], [scores], [np.full(23, 0.92, dtype=np.float32)], [0.0], ["TRACKED"], [False],
        maximum_interpolation_seconds=0.25,
        refined_joints={0: refined or set()},
    )[0]
    return temporal, scores


def _measured_layers(*, left_hand: bool = True, right_hand: bool = True):
    frame, scores = _pose_frame()
    return build_frame_layer_contract(
        frame,
        raw_scores=scores,
        left_hand_visible=left_hand,
        left_hand_quality=0.9,
        right_hand_visible=right_hand,
        right_hand_quality=0.9,
        tracking_state="TRACKED",
    )


def test_short_wrist_gap_is_reconstructed_without_false_measurement() -> None:
    points = [np.asarray([[20.0 + j, 30.0 + j + i] for j in range(23)], dtype=np.float32) for i in range(3)]
    scores = [np.full(23, 0.9, dtype=np.float32) for _ in range(3)]
    scores[1][9] = 0.0
    result = reconstruct_temporal_sequence(points, scores, scores, [0.0, 0.1, 0.2], ["TRACKED"] * 3, [False] * 3, maximum_interpolation_seconds=0.25)
    contract = build_frame_layer_contract(result[1], tracking_state="TRACKED")
    assert contract["left_wrist"]["state"] == TimelineState.TEMPORALLY_RECONSTRUCTED.value
    assert contract["left_wrist"]["usability"] == UsabilityLevel.USABLE_WITH_RECONSTRUCTION.value


def test_long_wrist_gap_remains_explicit() -> None:
    points = [np.asarray([[20.0 + j, 30.0 + j + i] for j in range(23)], dtype=np.float32) for i in range(5)]
    scores = [np.full(23, 0.9, dtype=np.float32) for _ in range(5)]
    for index in (1, 2, 3):
        scores[index][9] = 0.0
    result = reconstruct_temporal_sequence(points, scores, scores, [0.0, 0.1, 0.2, 0.3, 0.4], ["TRACKED"] * 5, [False] * 5, maximum_interpolation_seconds=0.25)
    contract = build_frame_layer_contract(result[2], tracking_state="TRACKED")
    assert contract["left_wrist"]["usability"] == UsabilityLevel.INSUFFICIENT.value


def test_partial_hand_occlusion_does_not_invalidate_other_side() -> None:
    contract = _measured_layers(left_hand=False, right_hand=True)
    assert contract["left_hand"]["state"] == TimelineState.NOT_VISIBLE.value
    assert contract["right_hand"]["usability"] == UsabilityLevel.FULLY_USABLE.value


def test_side_or_back_pose_preserves_torso_timeline() -> None:
    contract = _measured_layers()
    assert contract["torso"]["timeline_usable"] is True
    assert contract["torso"]["analysis_usable"] is True


def test_two_pass_fusion_keeps_better_wrist_joint() -> None:
    primary = np.asarray([[100.0 + i, 100.0 + i] for i in range(23)], dtype=np.float32)
    fallback = primary.copy(); fallback[9] += [2.0, 1.0]
    primary_scores = np.full(23, 0.9, dtype=np.float32); primary_scores[9] = 0.35
    fallback_scores = np.full(23, 0.8, dtype=np.float32); fallback_scores[9] = 0.88
    result = fuse_pose_candidates(primary, primary_scores, fallback, fallback_scores)
    assert 9 in result.refined_joint_indexes
    assert np.allclose(result.points[9], fallback[9])


def test_hard_fallback_does_not_replace_good_primary() -> None:
    primary = np.asarray([[100.0 + i, 100.0 + i] for i in range(23)], dtype=np.float32)
    fallback = primary.copy(); fallback[9] += [1.0, 1.0]
    primary_scores = np.full(23, 0.92, dtype=np.float32)
    fallback_scores = np.full(23, 0.90, dtype=np.float32)
    result = fuse_pose_candidates(primary, primary_scores, fallback, fallback_scores)
    assert 9 not in result.refined_joint_indexes
    assert np.allclose(result.points[9], primary[9])


def test_joint_source_hysteresis_rejects_temporally_detached_fallback() -> None:
    primary = np.asarray([[100.0 + i, 100.0 + i] for i in range(23)], dtype=np.float32)
    fallback = primary.copy(); fallback[9] += [22.0, 0.0]
    primary_scores = np.full(23, 0.88, dtype=np.float32); primary_scores[9] = 0.72
    fallback_scores = np.full(23, 0.88, dtype=np.float32); fallback_scores[9] = 0.79
    previous = primary.copy(); following = primary.copy(); following[:, 0] += 1.0
    result = fuse_pose_candidates(
        primary, primary_scores, fallback, fallback_scores,
        previous_points=previous, previous_scores=primary_scores,
        following_points=following, following_scores=primary_scores,
    )
    assert 9 not in result.refined_joint_indexes
    assert result.joint_trust[9]["decision"] == "primary_hysteresis"


def test_overlay_and_timeline_share_visibility_contract() -> None:
    frame, scores = _pose_frame(missing={7, 9})
    rendered = {"left_upper_arm": {"visible": True}, "left_forearm": {"visible": True}}
    contract = build_frame_layer_contract(frame, raw_scores=scores, rendered_bones=rendered, tracking_state="TRACKED")
    assert contract["left_arm"]["timeline_usable"] is True
    assert contract["left_arm"]["analysis_usable"] is False
    assert contract["left_arm"]["usability"] == UsabilityLevel.TIMELINE_ONLY.value


def test_rula_reba_timeline_coverage_is_reported() -> None:
    frames = [_measured_layers() for _ in range(8)]
    summary = summarize_layer_coverage(frames, fps=10.0)
    assert summary["rula_reba_timeline_coverage_ratio"] == 1.0
    assert summary["assessment_coverage_definition"].endswith("not_completed_normative_score")


def test_single_frame_gray_gap_is_coalesced_with_provenance() -> None:
    frames = [_measured_layers(), _measured_layers(), _measured_layers()]
    frames[1]["left_wrist"] = {
        "state": TimelineState.NO_DATA.value,
        "usability": UsabilityLevel.INSUFFICIENT.value,
        "analysis_usable": False,
        "timeline_usable": False,
        "quality": 0.0,
    }
    output = coalesce_short_timeline_gaps(frames)
    assert output[1]["left_wrist"]["timeline_usable"] is True
    assert output[1]["left_wrist"]["analysis_usable"] is False
    assert output[1]["left_wrist"]["coalesced_from_state"] == TimelineState.NO_DATA.value


def test_coverage_reports_measured_reconstructed_and_gap_kpis() -> None:
    frames = [_measured_layers() for _ in range(4)]
    frames[1]["torso"].update({"state": TimelineState.TEMPORALLY_RECONSTRUCTED.value, "usability": UsabilityLevel.USABLE_WITH_RECONSTRUCTION.value})
    frames[3]["torso"].update({"state": TimelineState.NO_DATA.value, "usability": UsabilityLevel.INSUFFICIENT.value, "timeline_usable": False, "analysis_usable": False})
    torso = summarize_layer_coverage(frames, fps=10.0)["layers"]["torso"]
    assert torso["measured_ratio"] == 0.5
    assert torso["reconstructed_ratio"] == 0.25
    assert torso["single_frame_dropout_count"] == 1
    assert torso["maximum_gap_frames"] == 1


def test_synthetic_coverage_fixture_meets_v61_acceptance_floors() -> None:
    frames = [_measured_layers() for _ in range(100)]
    targets = {
        "torso": (96, 99),
        "neck": (92, 96),
        "left_arm": (91, 96),
        "right_arm": (91, 96),
        "left_wrist": (72, 86),
        "right_wrist": (72, 86),
    }
    for layer, (analysis_count, timeline_count) in targets.items():
        for index in range(analysis_count, timeline_count):
            frames[index][layer].update({
                "state": TimelineState.KINEMATICALLY_INFERRED.value,
                "usability": UsabilityLevel.TIMELINE_ONLY.value,
                "analysis_usable": False,
                "timeline_usable": True,
            })
        for index in range(timeline_count, 100):
            frames[index][layer].update({
                "state": TimelineState.NO_DATA.value,
                "usability": UsabilityLevel.INSUFFICIENT.value,
                "analysis_usable": False,
                "timeline_usable": False,
            })
    summary = summarize_layer_coverage(frames, fps=25.0)
    layers = summary["layers"]
    assert summary["torso_timeline_coverage_ratio"] == 0.99
    assert summary["left_wrist_analysis_coverage_ratio"] == 0.72
    assert layers["torso"]["timeline_coverage_ratio"] >= 0.98
    assert layers["neck"]["timeline_coverage_ratio"] >= 0.95
    assert layers["left_arm"]["timeline_coverage_ratio"] >= 0.95
    assert layers["right_arm"]["timeline_coverage_ratio"] >= 0.95
    assert layers["left_wrist"]["timeline_coverage_ratio"] >= 0.85
    assert layers["right_wrist"]["timeline_coverage_ratio"] >= 0.85
    assert layers["torso"]["analysis_coverage_ratio"] >= 0.95
    assert layers["neck"]["analysis_coverage_ratio"] >= 0.90
    assert layers["left_arm"]["analysis_coverage_ratio"] >= 0.90
    assert layers["right_arm"]["analysis_coverage_ratio"] >= 0.90
    assert layers["left_wrist"]["analysis_coverage_ratio"] >= 0.70
    assert layers["right_wrist"]["analysis_coverage_ratio"] >= 0.70


def test_wrist_timeline_is_not_empty_when_reconstruction_is_available() -> None:
    frame, _ = _pose_frame(missing={7, 9})
    contract = build_frame_layer_contract(
        frame,
        rendered_bones={"left_forearm": {"visible": True, "confidence": 0.5}},
        tracking_state="TRACKED",
    )
    assert contract["left_wrist"]["timeline_usable"] is True
    assert contract["left_wrist"]["analysis_usable"] is False


def test_torso_timeline_remains_complete_during_partial_occlusion() -> None:
    frame, _ = _pose_frame(missing={11})
    rendered = {
        name: {"visible": True, "confidence": 0.55}
        for name in ("shoulders", "left_torso", "right_torso", "hips")
    }
    contract = build_frame_layer_contract(frame, rendered_bones=rendered, tracking_state="PARTIAL")
    assert contract["torso"]["timeline_usable"] is True
    assert contract["torso"]["usability"] == UsabilityLevel.TIMELINE_ONLY.value


def test_hard_frame_fallback_improves_pose_coverage() -> None:
    primary = np.asarray([[100.0 + i, 100.0 + i] for i in range(23)], dtype=np.float32)
    fallback = primary.copy()
    primary_scores = np.full(23, 0.9, dtype=np.float32); primary_scores[9] = 0.0
    fallback_scores = np.full(23, 0.9, dtype=np.float32)
    fusion = fuse_pose_candidates(primary, primary_scores, fallback, fallback_scores)
    temporal = reconstruct_temporal_sequence(
        [fusion.points], [fusion.scores], [fusion.scores], [0.0], ["TRACKED"], [False],
        maximum_interpolation_seconds=0.25,
        refined_joints={0: set(fusion.refined_joint_indexes)},
    )[0]
    contract = build_frame_layer_contract(temporal, tracking_state="TRACKED")
    assert contract["left_wrist"]["analysis_usable"] is True
    assert contract["left_wrist"]["state"] == TimelineState.REFINED_MODEL.value


def test_rula_reba_timeline_coverage_improves_after_reconstruction() -> None:
    baseline = [_measured_layers() for _ in range(10)]
    for index in (4, 5):
        baseline[index]["left_wrist"].update({"usability": UsabilityLevel.INSUFFICIENT.value, "timeline_usable": False})
        baseline[index]["right_wrist"].update({"usability": UsabilityLevel.INSUFFICIENT.value, "timeline_usable": False})
    before = summarize_layer_coverage(baseline, fps=10.0)
    after_frames = [{layer: dict(value) for layer, value in frame.items()} for frame in baseline]
    for index in (4, 5):
        after_frames[index]["left_wrist"].update({"state": TimelineState.TEMPORALLY_RECONSTRUCTED.value, "usability": UsabilityLevel.USABLE_WITH_RECONSTRUCTION.value, "analysis_usable": True, "timeline_usable": True})
    after = summarize_layer_coverage(after_frames, fps=10.0)
    assert before["rula_reba_timeline_coverage_ratio"] == 0.8
    assert after["rula_reba_timeline_coverage_ratio"] == 1.0


def test_timeline_provenance_distinguishes_measured_vs_reconstructed() -> None:
    frames = [_measured_layers(), _measured_layers()]
    frames[1]["right_arm"].update({"state": TimelineState.FLOW_TRACKED.value, "usability": UsabilityLevel.USABLE_WITH_RECONSTRUCTION.value})
    summary = summarize_layer_coverage(frames, fps=30.0)["layers"]["right_arm"]
    assert summary["state_counts"][TimelineState.MEASURED.value] == 1
    assert summary["state_counts"][TimelineState.FLOW_TRACKED.value] == 1

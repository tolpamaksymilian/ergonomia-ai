from __future__ import annotations

import cv2
import numpy as np

from worker.src.pose_v6.silhouette import (
    PackedPersonMask,
    assess_mask_sequence,
    bone_silhouette_support_ratio,
    draw_silhouette_overlay,
    dynamic_mask_tolerance,
    evaluate_skeleton_against_silhouette,
    signed_distance_field,
    summarize_silhouette_alignment,
)


CORE_BONES = {
    "left_upper_arm": (5, 7),
    "left_forearm": (7, 9),
    "left_thigh": (11, 13),
    "left_lower_leg": (13, 15),
}


def _person_mask(*, x1: int = 30, x2: int = 90) -> PackedPersonMask:
    mask = np.zeros((120, 120), dtype=np.uint8)
    cv2.rectangle(mask, (x1, 10), (x2, 110), 1, thickness=cv2.FILLED)
    return PackedPersonMask.from_mask(mask, logit_confidence=0.95)


def _silhouette_sequence(masks: list[PackedPersonMask]):
    count = len(masks)
    return assess_mask_sequence(
        masks,
        [[30.0, 10.0, 91.0, 111.0]] * count,
        [np.asarray([[50.0, 40.0], [70.0, 40.0], [52.0, 70.0], [68.0, 70.0]])] * count,
        [100.0] * count,
        source_frame_indexes=list(range(count)),
        timestamps=[index / 30.0 for index in range(count)],
        track_ids=["worker-1"] * count,
        anchor_indexes={0},
    )


def _points() -> tuple[np.ndarray, np.ndarray]:
    points = np.zeros((23, 2), dtype=np.float32)
    scores = np.zeros(23, dtype=np.float32)
    values = {
        5: (48, 38), 7: (40, 53), 9: (32, 68),
        11: (51, 68), 13: (49, 88), 15: (47, 108),
    }
    for joint, point in values.items():
        points[joint] = point
        scores[joint] = 0.9
    return points, scores


def test_packed_mask_round_trip_and_signed_distance_orientation() -> None:
    packed = _person_mask()

    assert np.array_equal(packed.unpack(), packed.unpack().astype(bool))
    distance = signed_distance_field(packed)
    assert distance[50, 60] > 0.0
    assert distance[50, 5] < 0.0


def test_far_ankle_and_empty_space_bone_receive_strong_silhouette_penalty() -> None:
    silhouette = _silhouette_sequence([_person_mask()])[0]
    points, scores = _points()
    # Most of the lower-leg segment now crosses empty background, not merely
    # its distal endpoint.
    points[15] = (200, 108)

    evidence = evaluate_skeleton_against_silhouette(
        silhouette,
        points,
        scores,
        CORE_BONES,
        body_scale=100.0,
        motion_blur=0.0,
        motion_state="NORMAL",
        occluded=False,
    )

    ankle = next(item for item in evidence.joint_evidence if item.joint_index == 15)
    lower_leg = next(item for item in evidence.bone_evidence if item.bone_name == "left_lower_leg")
    assert ankle.support == "far_outside"
    assert ankle.penalty >= 0.65
    assert lower_leg.outside_corridor
    assert lower_leg.support_ratio is not None and lower_leg.support_ratio < 0.55


def test_extended_limb_close_to_mask_boundary_is_not_rejected() -> None:
    silhouette = _silhouette_sequence([_person_mask()])[0]
    points, scores = _points()
    points[9] = (27, 68)

    evidence = evaluate_skeleton_against_silhouette(
        silhouette,
        points,
        scores,
        CORE_BONES,
        body_scale=100.0,
        motion_blur=0.7,
        motion_state="FAST_MOTION",
        occluded=False,
    )

    wrist = next(item for item in evidence.joint_evidence if item.joint_index == 9)
    assert wrist.support in {"near_boundary", "possible"}
    assert wrist.penalty < 0.65


def test_occlusion_expands_tolerance_and_missing_mask_never_hard_rejects_pose() -> None:
    normal = dynamic_mask_tolerance(
        9, body_scale=100.0, motion_blur=0.0, motion_state="NORMAL",
        mask_confidence=0.95, occluded=False,
    )
    occluded = dynamic_mask_tolerance(
        9, body_scale=100.0, motion_blur=0.7, motion_state="FAST_MOTION",
        mask_confidence=0.5, occluded=True,
    )
    assert occluded > normal

    missing = assess_mask_sequence(
        [None], [None], [None], [100.0],
        source_frame_indexes=[0], timestamps=[0.0], track_ids=["worker-1"],
        anchor_indexes=set(),
    )[0]
    points, scores = _points()
    evidence = evaluate_skeleton_against_silhouette(
        missing, points, scores, CORE_BONES, body_scale=100.0,
        motion_blur=1.0, motion_state="FAST_MOTION", occluded=True,
    )
    assert evidence.mask_influence == 0.0
    assert evidence.joint_evidence == ()


def test_mask_drift_disables_influence_until_reanchor() -> None:
    stable = _person_mask()
    drifted = _person_mask(x1=86, x2=118)
    frames = assess_mask_sequence(
        [stable, drifted],
        [[30, 10, 91, 111], [30, 10, 91, 111]],
        [
            np.asarray([[50, 40], [70, 40], [52, 70], [68, 70]], dtype=np.float32),
            np.asarray([[50, 40], [70, 40], [52, 70], [68, 70]], dtype=np.float32),
        ],
        [100.0, 100.0], source_frame_indexes=[0, 1],
        timestamps=[0.0, 1 / 30], track_ids=["worker-1", "worker-1"],
        anchor_indexes={0},
    )
    assert frames[1].quality.drift_detected
    assert frames[1].quality.influence == 0.0
    assert "MASK_TRACK_DRIFT" in frames[1].quality.rejection_reasons
    assert any(reason.startswith("MASK_") for reason in frames[1].quality.rejection_reasons)


def test_reanchor_resets_temporal_drift_history_but_keeps_identity_checks() -> None:
    stable = _person_mask()
    shifted = _person_mask(x1=40, x2=100)
    frames = assess_mask_sequence(
        [stable, shifted],
        [[30, 10, 91, 111], [40, 10, 101, 111]],
        [
            np.asarray([[50, 40], [70, 40], [52, 70], [68, 70]], dtype=np.float32),
            np.asarray([[55, 40], [75, 40], [57, 70], [73, 70]], dtype=np.float32),
        ],
        [100.0, 100.0], source_frame_indexes=[0, 1], timestamps=[0.0, 1 / 30],
        track_ids=["worker-1", "worker-1"], anchor_indexes={0, 1},
    )
    assert frames[1].reanchored
    assert frames[1].quality.drift_detected is False
    assert frames[1].quality.influence > 0.0


def test_summary_and_overlay_report_actual_silhouette_alignment() -> None:
    silhouette = _silhouette_sequence([_person_mask()])[0]
    points, scores = _points()
    evidence = evaluate_skeleton_against_silhouette(
        silhouette, points, scores, CORE_BONES, body_scale=100.0,
        motion_blur=0.0, motion_state="NORMAL", occluded=False,
    )
    summary = summarize_silhouette_alignment([silhouette], [evidence])
    assert summary["person_mask_coverage_ratio"] == 1.0
    assert summary["skeleton_to_silhouette_alignment_score"] is not None
    assert summary["alignment_score_is_accuracy"] is False

    image = np.zeros((120, 120, 3), dtype=np.uint8)
    rendered = draw_silhouette_overlay(image.copy(), silhouette, debug=False)
    assert np.any(rendered != image)


def test_bone_corridor_samples_the_complete_segment() -> None:
    field = signed_distance_field(_person_mask())
    supported = bone_silhouette_support_ratio(
        field, np.asarray([40, 30]), np.asarray([45, 100]), tolerance_px=2.0,
    )
    unsupported = bone_silhouette_support_ratio(
        field, np.asarray([10, 30]), np.asarray([10, 100]), tolerance_px=2.0,
    )
    assert supported == 1.0
    assert unsupported == 0.0

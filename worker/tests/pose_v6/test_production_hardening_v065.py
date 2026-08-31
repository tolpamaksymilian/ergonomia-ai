from __future__ import annotations

import numpy as np

from worker.src.pose_v6.config import load_pose_v6_config
from worker.src.pose_v6.expert_backend import (
    CanonicalWholeBodyObservation,
    assess_local_expert_candidates,
)
from worker.src.pose_v6.iterative_refinement import (
    FrameAudit,
    PoseError,
    PoseErrorCode,
    group_hard_segments,
)


def test_ultra_profile_increases_compute_budgets_without_becoming_default(
    monkeypatch,
) -> None:
    monkeypatch.delenv("POSE_V6_PROFILE", raising=False)
    accurate = load_pose_v6_config()
    monkeypatch.setenv("POSE_V6_PROFILE", "ULTRA")
    ultra = load_pose_v6_config()
    assert accurate.profile == "ACCURATE"
    assert ultra.profile == "ULTRA"
    assert len(ultra.iterative.pass2_roi_scales) > len(
        accurate.iterative.pass2_roi_scales
    )
    assert len(ultra.iterative.pass3_roi_scales) > len(
        accurate.iterative.pass3_roi_scales
    )
    assert ultra.iterative.maximum_repair_iterations > (
        accurate.iterative.maximum_repair_iterations
    )
    assert ultra.iterative.critical_temporal_context_seconds == 0.30


def test_low_confidence_error_does_not_trigger_heavy_repair_segment() -> None:
    uncertain = PoseError(
        0,
        PoseErrorCode.MODEL_DISAGREEMENT,
        (7,),
        0.7,
        error_confidence=0.4,
    )
    frame = FrameAudit(
        0, 0.5, 0.8, 0.7, 0.5, 0.7, 1.0, 1.0, 0.0, 0.0,
        (uncertain,),
    )
    segments = group_hard_segments(
        [frame], [0.0], [False], ["TRACKED"],
        padding_seconds=0.0, maximum_ratio=1.0,
        minimum_error_confidence=0.65,
    )
    assert uncertain.to_dict()["repairability"] == "UNCERTAIN"
    assert segments == []


def test_expert_candidate_contract_reports_real_v67_tar_readiness() -> None:
    assessments = assess_local_expert_candidates()
    assert {item.candidate for item in assessments} == {"TAR-ViTPose-B-17"}
    assert all(item.integrated for item in assessments)
    assert all(item.canonical_mapping_validated for item in assessments)
    assert not any(item.production_ready for item in assessments)
    assert all(not item.benchmark_validated for item in assessments)


def test_expert_canonical_contract_rejects_guessed_joint_layout() -> None:
    observation = CanonicalWholeBodyObservation(
        np.zeros((17, 2), dtype=np.float32),
        np.ones(17, dtype=np.float32),
        "test-only",
    )
    observation.validate(canonical_joint_count=17)
    try:
        observation.validate(canonical_joint_count=133)
    except ValueError as error:
        assert "(133, 2)" in str(error)
    else:  # pragma: no cover - explicit contract must reject this layout
        raise AssertionError("incompatible expert joint layout was accepted")

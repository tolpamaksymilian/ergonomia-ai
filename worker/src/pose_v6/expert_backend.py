"""Optional secondary-pose boundary and V6.6 readiness decision matrix.

No secondary model is bundled or silently downloaded.  This module defines the
contract required before a candidate can participate in production consensus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class CanonicalWholeBodyObservation:
    points: np.ndarray
    scores: np.ndarray
    model_name: str
    source: str = "EXPERT_REFINED_MODEL"

    def validate(self, *, canonical_joint_count: int) -> None:
        points = np.asarray(self.points)
        scores = np.asarray(self.scores)
        if points.shape != (canonical_joint_count, 2):
            raise ValueError(
                f"expert canonical points must have shape "
                f"({canonical_joint_count}, 2), got {points.shape}"
            )
        if scores.shape != (canonical_joint_count,):
            raise ValueError(
                f"expert canonical scores must have shape "
                f"({canonical_joint_count},), got {scores.shape}"
            )
        visible = scores > 0.0
        if not np.isfinite(scores).all() or (
            np.any(visible) and not np.isfinite(points[visible]).all()
        ):
            raise ValueError("expert canonical observation contains non-finite data")


@runtime_checkable
class PoseExpertBackend(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def device(self) -> str: ...

    @property
    def input_size(self) -> tuple[int, int]: ...

    @property
    def joint_layout(self) -> str: ...

    def infer(self, image_bgr: np.ndarray, bbox_xyxy: np.ndarray) -> object: ...

    def to_canonical_wholebody(
        self, raw_result: object,
    ) -> CanonicalWholeBodyObservation: ...


@dataclass(frozen=True)
class ExpertCandidateAssessment:
    candidate: str
    integrated: bool
    configured_weights: bool
    canonical_mapping_validated: bool
    benchmark_validated: bool
    reason: str
    availability: str = "not-configured"
    backend: str = "not-integrated"
    weights: str = "not-configured"
    wholebody: bool = True
    joint_mapping: str = "not-validated"
    vram_estimate: str = "unknown-without-export"
    hard_motion_suitability: str = "requires-same-video-benchmark"
    decision: str = "do-not-enable"

    @property
    def production_ready(self) -> bool:
        return all((
            self.integrated,
            self.configured_weights,
            self.canonical_mapping_validated,
            self.benchmark_validated,
        ))

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate,
            "integrated": self.integrated,
            "configured_weights": self.configured_weights,
            "canonical_mapping_validated": self.canonical_mapping_validated,
            "benchmark_validated": self.benchmark_validated,
            "production_ready": self.production_ready,
            "reason": self.reason,
            "availability": self.availability,
            "backend": self.backend,
            "weights": self.weights,
            "wholebody": self.wholebody,
            "joint_mapping": self.joint_mapping,
            "vram_estimate": self.vram_estimate,
            "hard_motion_suitability": self.hard_motion_suitability,
            "decision": self.decision,
        }


def assess_local_expert_candidates(
    configured_weights: Mapping[str, Path | None] | None = None,
) -> tuple[ExpertCandidateAssessment, ...]:
    """Report repository-local readiness; never downloads weights or guesses maps."""

    weights = configured_weights or {}
    candidates = (
        "ViTPose-H WholeBody",
        "DWPose WholeBody",
        "RTMPose-X WholeBody",
    )
    return tuple(
        ExpertCandidateAssessment(
            candidate=name,
            integrated=False,
            configured_weights=(
                name in weights
                and weights[name] is not None
                and Path(weights[name]).is_file()
            ),
            canonical_mapping_validated=False,
            benchmark_validated=False,
            reason=(
                "no repository-configured weights, validated canonical joint "
                "mapping, or same-video benchmark; RTMW remains primary"
            ),
            availability="class-reviewed-no-local-backend",
            backend="requires-separate-export/runtime integration",
            weights=(
                "repository-local"
                if name in weights
                and weights[name] is not None
                and Path(weights[name]).is_file()
                else "not-repository-configured"
            ),
            wholebody=True,
            joint_mapping="COCO-WholeBody-133 mapping not repository-validated",
            vram_estimate="must be measured on target ONNX/TensorRT export",
            hard_motion_suitability=(
                "promising but unverified on the supplied motion pattern"
            ),
            decision="not enabled; no validated secondary inference asset",
        )
        for name in candidates
    )


def pose_model_evaluation_table(
    expert_candidates: tuple[ExpertCandidateAssessment, ...] | None = None,
) -> tuple[dict[str, object], ...]:
    """Return the explicit V6.6 expert decision matrix used in diagnostics."""

    candidates = expert_candidates or assess_local_expert_candidates()
    primary = {
        "model": "RTMW-DW-X-L WholeBody 384x288",
        "availability": "installed-and-executed-primary",
        "backend": "ONNX Runtime CUDA",
        "weights": "official RTMLib/OpenMMLab cache",
        "wholebody": True,
        "joint_mapping": "COCO-WholeBody-133 production mapping",
        "vram_estimate": "runtime-dependent; guarded by per-frame crop batching",
        "hard_motion_suitability": "primary plus V6.6 limb-context multi-pass",
        "decision": "retain primary; no unbenchmarked replacement",
    }
    rows = [primary]
    rows.extend({
        "model": candidate.candidate,
        "availability": candidate.availability,
        "backend": candidate.backend,
        "weights": candidate.weights,
        "wholebody": candidate.wholebody,
        "joint_mapping": candidate.joint_mapping,
        "vram_estimate": candidate.vram_estimate,
        "hard_motion_suitability": candidate.hard_motion_suitability,
        "decision": candidate.decision,
    } for candidate in candidates)
    return tuple(rows)


__all__ = [
    "CanonicalWholeBodyObservation",
    "ExpertCandidateAssessment",
    "PoseExpertBackend",
    "assess_local_expert_candidates",
    "pose_model_evaluation_table",
]

"""Temporal expert contracts and the explicit V6.7 model decision matrix."""

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
    """Report local TAR readiness; model artifacts are never downloaded here."""

    repository = Path(__file__).resolve().parents[3]
    default = repository / "worker/models/temporal/tar-vitpose/tarvitpose_b_17.pt"
    weights = configured_weights or {"TAR-ViTPose-B-17": default}
    path = weights.get("TAR-ViTPose-B-17")
    present = path is not None and Path(path).is_file()
    return (ExpertCandidateAssessment(
        candidate="TAR-ViTPose-B-17",
        integrated=True,
        configured_weights=present,
        canonical_mapping_validated=True,
        benchmark_validated=False,
        reason=(
            "real five-frame temporal pose backend; limited intentionally to "
            "COCO17 core body joints and anatomy-gated before acceptance"
        ),
        availability="installed" if present else "artifact-missing",
        backend="PyTorch CUDA; inference-only OpenMMLab ViT backbone",
        weights="official Apache-2.0 checkpoint" if present else "not-installed",
        wholebody=False,
        joint_mapping="COCO17 indexes 0..16; only limb indexes 5..16 can replace RTMW",
        vram_estimate="measured by each inference run",
        hard_motion_suitability="five real-frame temporal observation",
        decision="enabled for hard-motion consensus when artifacts are present",
    ),)


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
    rows.extend((
        {
            "model": "TAPNext++-TRecViT-B-512",
            "availability": "official-source-and-checkpoint-required",
            "backend": "PyTorch CUDA recurrent point tracker",
            "weights": "official Apache-2.0 checkpoint",
            "wholebody": False,
            "joint_mapping": "tracks only seeded COCO17 core limb points",
            "vram_estimate": "measured by each inference run",
            "hard_motion_suitability": "bidirectional temporal evidence",
            "decision": "enabled as support; never a pose measurement",
        },
        {
            "model": "Track-On-R",
            "availability": "blocked-by-gated-DINOv3-weights",
            "backend": "not integrated",
            "weights": "DINOv3 access must be granted separately",
            "wholebody": False,
            "joint_mapping": "not applicable",
            "vram_estimate": "not measured",
            "hard_motion_suitability": "challenger only",
            "decision": "not a production dependency",
        },
        {
            "model": "SEA-RAFT",
            "availability": "optional BSD-3-Clause",
            "backend": "not integrated",
            "weights": "not installed",
            "wholebody": False,
            "joint_mapping": "dense flow only",
            "vram_estimate": "not measured",
            "hard_motion_suitability": "fallback challenger if point tracking remains unresolved",
            "decision": "deferred; TAPNext++ is the selected tracker",
        },
    ))
    return tuple(rows)


__all__ = [
    "CanonicalWholeBodyObservation",
    "ExpertCandidateAssessment",
    "PoseExpertBackend",
    "assess_local_expert_candidates",
    "pose_model_evaluation_table",
]

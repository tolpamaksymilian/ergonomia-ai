"""Optional secondary-pose boundary for critical V6.5 segments.

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
        )
        for name in candidates
    )


__all__ = [
    "CanonicalWholeBodyObservation",
    "ExpertCandidateAssessment",
    "PoseExpertBackend",
    "assess_local_expert_candidates",
]

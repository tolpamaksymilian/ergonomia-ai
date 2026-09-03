"""Explicit licence/readiness gate for the optional SAM 3D Body referee.

Pose V6.8 does not load the model in production. The official checkpoints are
access-gated and use the SAM License, so enabling the expert requires separate
legal and technical approval. SAM2 + the global 2D solver do not depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MeshLicenseDecision(StrEnum):
    PRODUCTION_APPROVED = "PRODUCTION_APPROVED"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"
    BLOCKED_BY_LICENSE = "BLOCKED_BY_LICENSE"


@dataclass(frozen=True)
class MeshRefereeReadiness:
    name: str = "SAM 3D Body"
    upstream: str = "facebookresearch/sam-3d-body"
    checkpoint: str = "facebook/sam-3d-body-dinov3"
    license_name: str = "SAM License (2025-11-19)"
    decision: MeshLicenseDecision = MeshLicenseDecision.BENCHMARK_ONLY
    checkpoint_access: str = "gated"
    enabled: bool = False
    available: bool = False
    used_frames: int = 0
    skip_reason: str = "BENCHMARK_ONLY_LICENSE_AND_GATED_CHECKPOINT"

    def to_model_usage(self) -> dict[str, object]:
        return {
            "name": self.name,
            "upstream": self.upstream,
            "checkpoint": self.checkpoint,
            "license": self.license_name,
            "license_decision": self.decision.value,
            "checkpoint_access": self.checkpoint_access,
            "enabled": self.enabled,
            "available": self.available,
            "used": False,
            "frames": self.used_frames,
            "skip_reason": self.skip_reason,
            "role": "optional_monocular_geometry_referee",
            "is_metric_3d": False,
        }


def current_mesh_referee_readiness() -> MeshRefereeReadiness:
    """Return the immutable V6.8 decision without importing 3D dependencies."""

    return MeshRefereeReadiness()


__all__ = [
    "MeshLicenseDecision",
    "MeshRefereeReadiness",
    "current_mesh_referee_readiness",
]

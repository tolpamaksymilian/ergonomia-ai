"""Runtime provenance shared by Pose artifacts and the production claim RPC."""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_build_id(repository_root: Path) -> str | None:
    """Return a deploy-provided build id or the local Git commit without failing a run."""

    for name in ("WORKER_BUILD_ID", "GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA"):
        value = os.getenv(name, "").strip()
        if value:
            return value[:120]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repository_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value[:120] or None


@dataclass(frozen=True)
class PoseRunProvenance:
    analysis_run_id: str
    artifact_generation_id: str
    worker_version: str
    pose_version: str
    pose_schema: str
    quality_profile: str
    worker_instance_id: str
    worker_started_at: str
    processing_started_at: str
    build_id: str | None
    primary_pose_model: str
    temporal_pose_expert: str
    trajectory_expert: str
    hand_model: str
    temporal_experts_enabled: bool

    def to_document(self) -> dict[str, object]:
        return asdict(self)


def create_pose_run_provenance(
    *,
    worker_version: str,
    pose_version: str,
    pose_schema: str,
    quality_profile: str,
    worker_instance_id: str,
    worker_started_at: str,
    repository_root: Path,
) -> PoseRunProvenance:
    return PoseRunProvenance(
        analysis_run_id=str(uuid.uuid4()),
        artifact_generation_id=str(uuid.uuid4()),
        worker_version=worker_version,
        pose_version=pose_version,
        pose_schema=pose_schema,
        quality_profile=quality_profile,
        worker_instance_id=worker_instance_id,
        worker_started_at=worker_started_at,
        processing_started_at=utc_now_iso(),
        build_id=resolve_build_id(repository_root),
        primary_pose_model="RTMW WholeBody performance 384x288",
        temporal_pose_expert="TAR-ViTPose-B",
        trajectory_expert="TAPNext++-512",
        hand_model="MediaPipe Hand Landmarker full float16",
        temporal_experts_enabled=os.getenv(
            "POSE_TEMPORAL_EXPERT_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on", "tak"},
    )


def temporal_model_usage(summary: Mapping[str, object]) -> dict[str, object]:
    expert_value = summary.get("temporal_expert_v67")
    expert = expert_value if isinstance(expert_value, Mapping) else {}
    tar_frames = max(0, int(expert.get("tar_frame_count", 0) or 0))
    executed_frames = max(0, int(expert.get("executed_frame_count", 0) or 0))
    tap_frames = max(0, int(expert.get("tapnext_frame_count", 0) or 0))
    if tap_frames == 0 and bool(expert.get("tapnext_executed", False)):
        tap_frames = executed_frames
    return {
        "primary_pose_model": {"name": "RTMW WholeBody performance 384x288", "active": True},
        "temporal_pose_expert": {
            "name": "TAR-ViTPose-B",
            "enabled": bool(expert.get("enabled", False)),
            "used": bool(expert.get("tar_executed", False)),
            "frames": tar_frames,
        },
        "trajectory_expert": {
            "name": "TAPNext++-512",
            "enabled": bool(expert.get("tapnext_enabled", False)),
            "used": bool(expert.get("tapnext_executed", False)),
            "frames": tap_frames,
        },
        "hand_model": {"name": "MediaPipe Hand Landmarker full float16", "active": True},
        "temporal_experts_actually_used": bool(
            expert.get("tar_executed", False) or expert.get("tapnext_executed", False)
        ),
        "temporal_expert_frames_count": max(executed_frames, tar_frames, tap_frames),
    }

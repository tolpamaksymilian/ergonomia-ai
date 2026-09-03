from __future__ import annotations

import hashlib
from pathlib import Path

from worker.src.pose_v6.config import load_pose_v6_config
from worker.src.pose_v6.mesh_referee import (
    MeshLicenseDecision,
    current_mesh_referee_readiness,
)
from worker.src.pose_v6.sam2_backend import (
    SAM2_MODELS,
    SAM2_REVISION,
    _positive_points,
    checkpoint_sha256,
    empty_sam2_result,
)
import numpy as np


ROOT = Path(__file__).resolve().parents[3]


def test_sam2_metadata_pins_official_models_bytes_and_hashes() -> None:
    assert SAM2_REVISION == "2b90b9f5ceec907a1c18123530e92e794ad901a4"
    assert set(SAM2_MODELS) == {
        "sam2.1_hiera_base_plus", "sam2.1_hiera_large",
    }
    for metadata in SAM2_MODELS.values():
        assert int(metadata["bytes"]) > 300_000_000
        assert len(str(metadata["sha256"])) == 64
        int(str(metadata["sha256"]), 16)


def test_installer_is_pinned_and_runtime_backend_has_no_download_calls() -> None:
    installer = (ROOT / "worker" / "tools" / "install_sam2_expert.py").read_text(encoding="utf-8")
    runtime = (ROOT / "worker" / "src" / "pose_v6" / "sam2_backend.py").read_text(encoding="utf-8")
    assert SAM2_REVISION in installer
    assert "sha256" in installer.lower()
    assert "urllib.request" in installer
    assert "urllib.request" not in runtime
    assert "requests.get" not in runtime


def test_accurate_and_ultra_choose_benchmarked_models(monkeypatch) -> None:
    monkeypatch.setenv("POSE_V6_PROFILE", "ACCURATE")
    monkeypatch.delenv("POSE_SAM2_MODEL", raising=False)
    accurate = load_pose_v6_config()
    assert accurate.silhouette.enabled
    assert accurate.silhouette.model == "sam2.1_hiera_base_plus"
    assert accurate.global_body.maximum_repair_iterations == 1
    assert accurate.global_body.worst_frame_ratio == 0.01

    monkeypatch.setenv("POSE_V6_PROFILE", "ULTRA")
    ultra = load_pose_v6_config()
    assert ultra.silhouette.model == "sam2.1_hiera_large"
    assert ultra.global_body.maximum_repair_iterations == 3
    assert ultra.global_body.worst_frame_ratio == 0.03
    assert ultra.global_body.beam_width > accurate.global_body.beam_width


def test_performance_profile_keeps_additive_experts_disabled(monkeypatch) -> None:
    monkeypatch.setenv("POSE_V6_PROFILE", "PERFORMANCE")
    monkeypatch.delenv("POSE_SAM2_ENABLED", raising=False)
    monkeypatch.delenv("POSE_GLOBAL_BODY_SOLVER_ENABLED", raising=False)
    config = load_pose_v6_config()
    assert config.silhouette.enabled is False
    assert config.global_body.enabled is False


def test_missing_sam2_artifact_has_explicit_degraded_fallback() -> None:
    result = empty_sam2_result(
        [{"source_frame_index": 9, "source_timestamp_seconds": 0.3}],
        ["worker-1"], model_name="sam2.1_hiera_base_plus",
        reason="SAM2_ARTIFACT_MISSING",
    )
    assert result.degraded
    assert result.summary["used"] is False
    assert result.summary["skip_reason"] == "SAM2_ARTIFACT_MISSING"
    assert result.frames[0].quality.influence == 0.0
    assert result.frames[0].person_track_id == "worker-1"


def test_sam2_prompt_uses_multiple_in_bbox_torso_points_for_full_person() -> None:
    points = _positive_points(
        np.asarray([[40, 30], [60, 30], [42, 70], [58, 70], [500, 500]], dtype=np.float32),
        (20.0, 10.0, 80.0, 100.0),
    )
    assert points.shape == (4, 2)
    assert np.all(points[:, 0] >= 20.0)
    assert np.all(points[:, 0] <= 80.0)


def test_local_checkpoint_hash_matches_manifest_when_artifact_is_installed() -> None:
    for model_name, metadata in SAM2_MODELS.items():
        path = (
            ROOT / "worker" / "models" / "sam2" / "checkpoints"
            / str(metadata["checkpoint"])
        )
        if not path.is_file():
            continue
        assert path.stat().st_size == metadata["bytes"]
        assert checkpoint_sha256(model_name) == metadata["sha256"]
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        assert digest == metadata["sha256"]


def test_sam3d_is_benchmark_only_and_does_not_claim_metric_3d() -> None:
    readiness = current_mesh_referee_readiness()
    usage = readiness.to_model_usage()
    assert readiness.decision == MeshLicenseDecision.BENCHMARK_ONLY
    assert usage["enabled"] is False
    assert usage["used"] is False
    assert usage["is_metric_3d"] is False
    assert usage["skip_reason"] == "BENCHMARK_ONLY_LICENSE_AND_GATED_CHECKPOINT"

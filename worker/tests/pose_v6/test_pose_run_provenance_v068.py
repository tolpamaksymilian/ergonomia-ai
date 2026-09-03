from __future__ import annotations

from pathlib import Path

from worker.src.pose_v6.provenance import (
    create_pose_run_provenance,
    temporal_model_usage,
)


ROOT = Path(__file__).resolve().parents[3]


def test_run_provenance_has_distinct_immutable_ids(monkeypatch) -> None:
    monkeypatch.setenv("WORKER_BUILD_ID", "build-test-123")
    kwargs = {
        "worker_version": "0.15.0-beta.1",
        "pose_version": "pose-v6.7.0-beta.1",
        "pose_schema": "6.0",
        "quality_profile": "ACCURATE",
        "worker_instance_id": "pose-worker-test",
        "worker_started_at": "2026-08-31T10:00:00+00:00",
        "repository_root": ROOT,
    }
    first = create_pose_run_provenance(**kwargs)
    second = create_pose_run_provenance(**kwargs)

    assert first.analysis_run_id != second.analysis_run_id
    assert first.artifact_generation_id != first.analysis_run_id
    assert first.build_id == "build-test-123"
    assert first.to_document()["quality_profile"] == "ACCURATE"


def test_temporal_usage_reports_actual_execution_not_only_enablement() -> None:
    usage = temporal_model_usage({
        "temporal_expert_v67": {
            "enabled": True,
            "tar_executed": True,
            "tapnext_enabled": True,
            "tapnext_executed": False,
            "tar_frame_count": 19,
            "executed_frame_count": 19,
        }
    })

    assert usage["temporal_experts_actually_used"] is True
    assert usage["temporal_expert_frames_count"] == 19
    assert usage["temporal_pose_expert"]["frames"] == 19
    assert usage["trajectory_expert"]["used"] is False
    assert usage["trajectory_expert"]["skip_reason"] is not None


def test_production_worker_uses_versioned_artifact_paths_and_provenance_rpcs() -> None:
    source = (ROOT / "worker" / "src" / "pose_worker.py").read_text(encoding="utf-8")

    assert '"claim_next_pose_analysis_v3"' in source
    assert '"complete_pose_inference_v4"' in source
    assert 'results/{provenance.analysis_run_id}' in source
    assert 'pose-artifacts-manifest.json' in source
    assert '"analysis_run_id": provenance.analysis_run_id' in source
    assert '"artifact_generation_id": provenance.artifact_generation_id' in source


def test_provenance_migration_keeps_atomic_claim_and_service_role_only() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260831120000_add_pose_run_provenance.sql"
    ).read_text(encoding="utf-8").lower()

    assert "for update skip locked" in migration
    assert "security definer" in migration
    assert "set search_path = ''" in migration
    assert "pose_analysis_run_id = p_analysis_run_id" in migration
    assert "grant execute on function public.claim_next_pose_analysis_v2" in migration
    assert "to service_role" in migration
    assert "from public, anon, authenticated" in migration

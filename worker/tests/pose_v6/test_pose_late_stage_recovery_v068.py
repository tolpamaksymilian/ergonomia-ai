from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType
from collections.abc import Iterator

import pytest

from worker.src.pose_v6.config import load_pose_v6_config
from worker.src.pose_v6.late_stage import (
    PoseStageError,
    build_completion_parameters,
    safe_exception_message,
)
from worker.src.pose_v6.provenance import temporal_model_usage


ROOT = Path(__file__).resolve().parents[3]
WORKER_SOURCE = str(ROOT / "worker" / "src")
if WORKER_SOURCE not in sys.path:
    sys.path.insert(0, WORKER_SOURCE)



@contextmanager
def _runtime_pose_worker() -> Iterator[ModuleType]:
    prefixes = ("pose_worker", "pose_v3", "pose_v4", "pose_v5", "pose_v6")
    existing = tuple(
        name
        for name in sys.modules
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    )
    saved = {name: sys.modules[name] for name in existing}
    for name in existing:
        sys.modules.pop(name, None)
    try:
        for package in ("pose_v3", "pose_v4", "pose_v5", "pose_v6"):
            sys.modules[package] = importlib.import_module(f"worker.src.{package}")
        yield importlib.import_module("pose_worker")
    finally:
        for name in tuple(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def _pose_document() -> dict[str, object]:
    return {
        "analysis_id": "a0000000-0000-0000-0000-000000000001",
        "analysis_run_id": "b0000000-0000-0000-0000-000000000001",
        "artifact_generation_id": "c0000000-0000-0000-0000-000000000001",
        "pose_version": "pose-v6.7.0-beta.1",
        "quality_version": "pose-v6.7.0-beta.1",
        "pose_model": "RTMW WholeBody performance 384x288",
        "hand_model": "MediaPipe Hand Landmarker full float16",
        "configuration": {
            "inference_stride": 1,
            "tracking_method": "tracking-v6",
            "smoothing_method": "smoothing-v6",
        },
        "active_segment": {
            "source_start_frame": 0,
            "source_end_frame": 99,
            "source_start_seconds": 0.0,
            "source_end_seconds": 3.3,
            "output_duration_seconds": 3.3,
        },
        "summary": {
            "processed_frames": 100,
            "detected_frames": 98,
            "average_body_confidence": 0.91,
            "presence_ratio": 0.98,
            "left_hand": {"valid_ratio": 0.4, "rejected_frames": 60},
            "right_hand": {"valid_ratio": 0.5, "rejected_frames": 50},
        },
        "model_usage": {
            "temporal_experts_actually_used": True,
            "temporal_expert_frames_count": 17,
            "temporal_pose_expert": {"used": True, "frames": 17},
            "trajectory_expert": {"used": True, "frames": 17},
        },
    }


def _manifest() -> dict[str, object]:
    base = "user/analysis/results/b0000000-0000-0000-0000-000000000001"
    return {
        "analysis_run_id": "b0000000-0000-0000-0000-000000000001",
        "artifact_generation_id": "c0000000-0000-0000-0000-000000000001",
        "artifacts": {
            "overlay": f"{base}/pose-overlay.mp4",
            "keypoints": f"{base}/pose-keypoints.json.gz",
            "thumbnail": f"{base}/pose-thumbnail.jpg",
            "diagnostics": f"{base}/pose-diagnostics.json",
        },
    }


def test_database_finalization_error_is_precise_and_retryable() -> None:
    upstream = RuntimeError({"message": "RPC rejected stage", "code": "P0001"})
    error = PoseStageError("database-finalization", upstream)

    assert error.error_code == "POSE_DATABASE_FINALIZATION_ERROR"
    assert error.failure.component == "supabase-rpc"
    assert error.failure.retryable is True
    assert error.failure.upstream_error_code == "P0001"
    assert error.failure.message == "RPC rejected stage"


def test_failure_message_redacts_tokens() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
    message = safe_exception_message(RuntimeError(f"authorization=Bearer {jwt} secret=hidden"))
    assert jwt not in message
    assert "hidden" not in message
    assert "[REDACTED]" in message


def test_upload_error_is_not_reported_as_pose_inference() -> None:
    error = PoseStageError("artifact-upload", RuntimeError("storage unavailable"))
    assert error.error_code == "POSE_ARTIFACT_UPLOAD_ERROR"
    assert error.failure.stage == "artifact-upload"
    assert error.failure.component == "storage"


def test_compression_error_is_precise_and_can_retry_from_local_artifacts() -> None:
    error = PoseStageError("artifact-compression", OSError("disk write failed"))
    assert error.error_code == "POSE_ARTIFACT_COMPRESSION_ERROR"
    assert error.failure.stage == "artifact-compression"
    assert error.failure.component == "compression"
    assert error.failure.retryable is True


def test_completion_payload_is_rebuilt_from_same_run_artifacts() -> None:
    payload = build_completion_parameters(_pose_document(), _manifest(), worker_id="worker-1")

    assert payload["p_analysis_run_id"] == "b0000000-0000-0000-0000-000000000001"
    assert payload["p_artifact_generation_id"] == "c0000000-0000-0000-0000-000000000001"
    assert payload["p_processed_frames"] == 100
    assert payload["p_temporal_expert_frames_count"] == 17
    assert payload["p_result_json_path"].endswith("pose-keypoints.json.gz")


def test_completion_rejects_mixed_run_artifacts() -> None:
    manifest = _manifest()
    manifest["analysis_run_id"] = "another-run"
    with pytest.raises(ValueError, match="provenance"):
        build_completion_parameters(_pose_document(), manifest, worker_id="worker-1")


def test_video_quality_default_is_accurate_and_ultra_is_preserved(monkeypatch) -> None:
    monkeypatch.delenv("POSE_V6_PROFILE", raising=False)
    assert load_pose_v6_config().profile == "ACCURATE"
    monkeypatch.setenv("POSE_V6_PROFILE", "ULTRA")
    assert load_pose_v6_config().profile == "ULTRA"
    monkeypatch.setenv("POSE_V6_PROFILE", "PERFORMANCE")
    assert load_pose_v6_config().profile == "PERFORMANCE"


def test_late_retry_is_claimed_before_model_initialization() -> None:
    source = (ROOT / "worker" / "src" / "pose_worker.py").read_text(encoding="utf-8")
    retry_position = source.index("late_retry = claim_next_pose_late_retry")
    model_position = source.index("model = initialize_pose_model(settings, logger)", retry_position)
    process_position = source.index("process_analysis(", retry_position)
    assert retry_position < model_position < process_position
    assert "retry_pose_late_stage(supabase, settings, late_retry, logger)" in source


def test_late_retry_does_not_initialize_pose_model(monkeypatch) -> None:
    retry = {
        "id": "a0000000-0000-0000-0000-000000000001",
        "retry_kind": "database-finalization",
    }
    calls: list[str] = []
    with _runtime_pose_worker() as pose_worker:
        monkeypatch.setattr(pose_worker, "configure_logging", lambda: SimpleNamespace())
        monkeypatch.setattr(pose_worker, "create_supabase_client", lambda settings: object())
        monkeypatch.setattr(pose_worker, "claim_next_pose_late_retry", lambda client, worker_id: retry)
        monkeypatch.setattr(
            pose_worker,
            "retry_pose_late_stage",
            lambda client, settings, analysis, logger: calls.append(str(analysis["id"])),
        )
        monkeypatch.setattr(
            pose_worker,
            "initialize_pose_model",
            lambda settings, logger: pytest.fail("Pose inference must not initialize for late retry"),
        )

        result = pose_worker.run_worker(SimpleNamespace(worker_id="worker-1"), once=True)

    assert result == 0
    assert calls == [retry["id"]]


def test_failed_upload_retry_preserves_local_artifacts(tmp_path, monkeypatch) -> None:
    analysis_id = "a0000000-0000-0000-0000-000000000001"
    job_directory = tmp_path / analysis_id
    job_directory.mkdir()
    (job_directory / "pose-artifacts-manifest.json").write_text(
        json.dumps(_manifest()), encoding="utf-8"
    )
    recorded: list[str] = []
    settings = SimpleNamespace(
        results_bucket="analysis-results", worker_id="worker-1", keep_worker_files=False
    )
    analysis = {
        "id": analysis_id,
        "user_id": "user",
        "pose_analysis_run_id": "b0000000-0000-0000-0000-000000000001",
        "retry_kind": "artifact-upload",
    }

    with _runtime_pose_worker() as pose_worker:
        monkeypatch.setattr(pose_worker, "DATA_DIRECTORY", tmp_path)
        monkeypatch.setattr(
            pose_worker,
            "_upload_retry_artifacts",
            lambda *args: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
        )
        monkeypatch.setattr(
            pose_worker,
            "mark_analysis_failed",
            lambda client, aid, worker_id, error: recorded.append(error.error_code),
        )
        with pytest.raises(PoseStageError) as caught:
            pose_worker.retry_pose_late_stage(
                object(), settings, analysis, SimpleNamespace(info=lambda *args: None)
            )

    assert caught.value.error_code == "POSE_ARTIFACT_UPLOAD_ERROR"
    assert recorded == ["POSE_ARTIFACT_UPLOAD_ERROR"]
    assert job_directory.is_dir()
    assert (job_directory / "pose-artifacts-manifest.json").is_file()


def test_unused_temporal_experts_have_explicit_skip_reason() -> None:
    usage = temporal_model_usage({
        "temporal_expert_v67": {
            "enabled": True,
            "tar_executed": False,
            "tapnext_enabled": True,
            "tapnext_executed": False,
            "reason": "NO_HARD_MOTION_FRAMES",
        }
    })

    assert usage["temporal_pose_expert"]["skip_reason"] == "NO_ELIGIBLE_SEGMENTS"
    assert usage["trajectory_expert"]["skip_reason"] == "NO_ELIGIBLE_SEGMENTS"


def test_corrective_migration_fixes_stage_contract_and_stage_retry() -> None:
    sql = (ROOT / "supabase" / "migrations" / "20260831190000_fix_pose_late_stage_finalization.sql").read_text(encoding="utf-8").lower()
    assert "'database-finalization'" in sql
    assert "'pose-database-finalization-retry'" in sql
    assert "for update skip locked" in sql
    assert "attempts = coalesce(a.attempts, 0) + 1" in sql
    assert "pose-database-finalization-failed" in sql
    assert "ready-for-pose-finalization" in sql
    assert "when 'artifact-compression' then 'pose-artifact-upload-failed'" in sql
    assert "requested_quality_profile text not null default 'accurate'" in sql
    assert "grant execute on function public.claim_next_pose_late_retry(text) to service_role" in sql
    assert "grant execute on function public.retry_failed_analysis_stage(uuid) to service_role" in sql


def test_provenance_badge_icons_are_hidden_from_visible_text() -> None:
    source = (ROOT / "src" / "components" / "analyses" / "pose-provenance-badge.tsx").read_text(encoding="utf-8")
    assert source.count('aria-hidden="true"') >= 3
    assert ">svg<" not in source.lower()


def test_late_failures_have_specific_user_messages_and_stale_run_guard() -> None:
    statuses = (ROOT / "src" / "config" / "analysis-status.ts").read_text(encoding="utf-8")
    page = (ROOT / "src" / "app" / "panel" / "analizy" / "[id]" / "page.tsx").read_text(encoding="utf-8")

    assert '"pose-artifact-upload-failed"' in statuses
    assert "Nie udało się zapisać gotowych wyników analizy" in statuses
    assert '"pose-database-finalization-failed"' in statuses
    assert "nie udało się zakończyć zapisu wyniku w bazie" in statuses
    assert "isArtifactPathFromAnotherRun" in page
    assert "Poprzedni wynik" in page

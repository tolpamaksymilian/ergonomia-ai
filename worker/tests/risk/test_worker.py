from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from worker.src import risk_worker
from worker.src.risk.integration import RiskProfileNotFoundError


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FakeRpcCall:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeRpcClient:
    def __init__(self, responses, storage=None):
        self.responses = responses
        self.calls = []
        self.storage = storage

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        return FakeRpcCall(self.responses.get(name))


class FakeStorageBucket:
    def __init__(self, metrics_payload: bytes):
        self.metrics_payload = metrics_payload
        self.uploaded_path = None

    def download(self, path):
        assert path.endswith("ergonomics-metrics.json")
        return self.metrics_payload

    def upload(self, *, path, file, file_options):
        assert json.load(file)["analysis_id"] == "risk-engine-fixture-analysis"
        assert file_options["upsert"] == "true"
        self.uploaded_path = path
        return SimpleNamespace(path=path)


class FakeStorageClient:
    def __init__(self, bucket: FakeStorageBucket):
        self.bucket = bucket

    def from_(self, bucket_name):
        assert bucket_name == "analysis-results"
        return self.bucket


def _settings(tmp_path: Path) -> risk_worker.WorkerSettings:
    return risk_worker.WorkerSettings(
        supabase_url="https://example.invalid",
        supabase_secret_key="super-secret-value",
        results_bucket="analysis-results",
        worker_id="risk-worker-test",
        risk_profile_path=FIXTURES / "risk-profile-test.json",
        poll_interval_seconds=1,
        log_level="INFO",
        keep_worker_files=False,
    )


def test_missing_explicit_profile_configuration_fails(monkeypatch):
    for name in ("RISK_PROFILE_PATH", "SUPABASE_URL", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(risk_worker, "ENV_PATH", Path("does-not-exist.env"))
    with pytest.raises(risk_worker.RiskWorkerConfigurationError, match="RISK_PROFILE_PATH"):
        risk_worker.load_settings()


def test_missing_profile_file_fails_before_supabase(monkeypatch, tmp_path):
    monkeypatch.setattr(risk_worker, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.setenv("RISK_PROFILE_PATH", str(tmp_path / "missing-profile.json"))
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret")
    with pytest.raises(RiskProfileNotFoundError):
        risk_worker.load_settings()


def test_complete_rpc_false_reports_lost_lock(tmp_path):
    client = FakeRpcClient({risk_worker.COMPLETE_RPC_NAME: False})
    assessment = {
        "profile": {
            "profile_id": "test",
            "profile_version": "1",
            "status": "development",
        }
    }
    summary = {
        "risk_engine_version": "risk-engine-v1.0",
        "frame_count": 2,
        "valid_metric_ratio": 0.5,
        "overall_level": "moderate",
    }
    with pytest.raises(risk_worker.RiskCompleteRpcError):
        risk_worker.complete_risk_assessment(
            client,
            analysis_id="analysis",
            worker_id="worker",
            storage_path="u/a/results/risk-assessment.json",
            assessment=assessment,
            database_summary=summary,
        )


def test_cleanup_respects_keep_worker_files(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "file.json").write_text("{}", encoding="utf-8")
    risk_worker.cleanup_job_directory(job, True)
    assert job.exists()
    risk_worker.cleanup_job_directory(job, False)
    assert not job.exists()


def test_error_sanitization_never_persists_secret(tmp_path):
    settings = _settings(tmp_path)
    message = risk_worker.sanitize_error_message(
        RuntimeError(f"request failed: {settings.supabase_secret_key}"),
        settings,
    )
    assert settings.supabase_secret_key not in message
    assert "[REDACTED]" in message


def test_parse_claim_requires_matching_worker_and_stage():
    row = {
        "id": "analysis",
        "user_id": "user",
        "title": "Test",
        "processing_stage": "risk-processing",
        "ergonomics_metrics_path": "u/a/results/ergonomics-metrics.json",
        "worker_id": "risk-worker",
    }
    claimed = risk_worker.parse_claimed_analysis(row, "risk-worker")
    assert claimed.analysis_id == "analysis"
    assert claimed.ergonomics_metrics_path.endswith("ergonomics-metrics.json")

    row["worker_id"] = "different-worker"
    with pytest.raises(risk_worker.RiskWorkerError):
        risk_worker.parse_claimed_analysis(row, "risk-worker")


def test_fail_rpc_uses_stable_error_code_and_sanitized_message(tmp_path):
    settings = _settings(tmp_path)
    client = FakeRpcClient({risk_worker.FAIL_RPC_NAME: True})
    risk_worker.fail_analysis(
        client,
        analysis_id="analysis",
        worker_id="worker",
        error=RuntimeError(f"failed {settings.supabase_secret_key}"),
        settings=settings,
    )
    _, payload = client.calls[-1]
    assert payload["p_error_code"] == "RISK_WORKER_ERROR"
    assert settings.supabase_secret_key not in payload["p_error_message"]


def test_worker_has_no_gpu_video_or_subprocess_dependencies():
    source = Path(risk_worker.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "import torch",
        "import cv2",
        "import onnxruntime",
        "import mediapipe",
        "import subprocess",
        "import ffmpeg",
    ):
        assert forbidden not in source


def test_claimed_job_runs_engine_uploads_and_completes(monkeypatch, tmp_path):
    metrics_payload = (FIXTURES / "ergonomics-metrics-test.json").read_bytes()
    bucket = FakeStorageBucket(metrics_payload)
    client = FakeRpcClient(
        {
            "update_analysis_progress": True,
            risk_worker.COMPLETE_RPC_NAME: True,
        },
        storage=FakeStorageClient(bucket),
    )
    monkeypatch.setattr(risk_worker, "DATA_DIRECTORY", tmp_path / "jobs")
    settings = _settings(tmp_path)
    row = {
        "id": "risk-engine-fixture-analysis",
        "user_id": "user-test",
        "title": "Synthetic analysis",
        "processing_stage": "risk-processing",
        "ergonomics_metrics_path": (
            "user-test/risk-engine-fixture-analysis/results/ergonomics-metrics.json"
        ),
        "worker_id": settings.worker_id,
    }

    assert risk_worker.process_claimed_analysis(client, settings, row) is True
    assert bucket.uploaded_path == (
        "user-test/risk-engine-fixture-analysis/results/risk-assessment.json"
    )
    complete_calls = [
        payload
        for name, payload in client.calls
        if name == risk_worker.COMPLETE_RPC_NAME
    ]
    assert len(complete_calls) == 1
    assert complete_calls[0]["p_assessment_version"] == "risk-engine-v1.0"
    assert complete_calls[0]["p_profile_id"] == "test-only-risk-profile-v1"

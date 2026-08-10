from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from worker.src import report_worker
from worker.src.risk.processor import process_risk_document


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FakeRpcCall:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeBucket:
    def __init__(self, ergonomics_payload: bytes, risk_payload: bytes):
        self.ergonomics_payload = ergonomics_payload
        self.risk_payload = risk_payload
        self.uploaded_path = None

    def download(self, path):
        if path.endswith("ergonomics-metrics.json"):
            return self.ergonomics_payload
        if path.endswith("risk-assessment.json"):
            return self.risk_payload
        raise RuntimeError("unexpected path")

    def upload(self, *, path, file, file_options):
        document = json.load(file)
        if path.endswith("analysis-report.json"):
            assert document["report_version"] == "analysis-report-v2.1-beta.1"
        elif path.endswith("company-method-assessment.json"):
            assert document["company_methods_version"] == "company-methods-v1.0-beta.1"
        else:
            raise AssertionError(f"unexpected upload: {path}")
        assert file_options["upsert"] == "true"
        self.uploaded_path = path
        return SimpleNamespace(path=path)


class FakeStorage:
    def __init__(self, bucket):
        self.bucket = bucket

    def from_(self, bucket_name):
        assert bucket_name == "analysis-results"
        return self.bucket


class FakeClient:
    def __init__(self, responses, storage=None):
        self.responses = responses
        self.storage = storage
        self.calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        return FakeRpcCall(self.responses.get(name))


def settings() -> report_worker.WorkerSettings:
    return report_worker.WorkerSettings(
        supabase_url="https://example.invalid",
        supabase_secret_key="server-secret-value",
        results_bucket="analysis-results",
        worker_id="report-worker-test",
        poll_interval_seconds=1,
        log_level="INFO",
        keep_worker_files=False,
    )


def claimed_row():
    return {
        "id": "risk-engine-fixture-analysis",
        "user_id": "user-test",
        "title": "Raport testowy",
        "created_at": "2026-08-06T10:00:00+00:00",
        "source_file_name": "source.mp4",
        "source_duration_seconds": 3.0,
        "source_width": 1280,
        "source_height": 720,
        "pose_quality_version": "pose-pipeline-v3.0",
        "pose_processed_frames": 2,
        "pose_detected_frames": 2,
        "pose_presence_ratio": 1.0,
        "ergonomics_metrics_path": "user-test/risk-engine-fixture-analysis/results/ergonomics-metrics.json",
        "risk_assessment_path": "user-test/risk-engine-fixture-analysis/results/risk-assessment.json",
        "processing_stage": "report-processing",
        "worker_id": "report-worker-test",
        "report_worker_id": "report-worker-test",
    }


def test_configuration_requires_supabase_values(monkeypatch, tmp_path):
    monkeypatch.setattr(report_worker, "ENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    with pytest.raises(report_worker.ReportWorkerConfigurationError):
        report_worker.load_settings()


def test_parse_claim_requires_report_processing_and_matching_lock():
    parsed = report_worker.parse_claimed_analysis(claimed_row(), "report-worker-test")
    assert parsed.analysis_id == "risk-engine-fixture-analysis"
    invalid = claimed_row()
    invalid["report_worker_id"] = "other"
    with pytest.raises(report_worker.ReportWorkerError):
        report_worker.parse_claimed_analysis(invalid, "report-worker-test")


def test_complete_rpc_failure_has_stable_code():
    client = FakeClient({report_worker.COMPLETE_RPC_NAME: False})
    with pytest.raises(report_worker.ReportCompleteRpcError) as error:
        report_worker.complete_report(
            client,
            analysis_id="analysis",
            worker_id="worker",
            report_path="u/a/results/analysis-report.json",
            report_summary={"report_version": "analysis-report-v2.1-beta.1"},
        )
    assert error.value.error_code == "REPORT_COMPLETE_RPC_ERROR"


def test_cleanup_respects_keep_flag(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "result.json").write_text("{}", encoding="utf-8")
    report_worker.cleanup_job_directory(job, True)
    assert job.exists()
    report_worker.cleanup_job_directory(job, False)
    assert not job.exists()


def test_secret_is_redacted_from_error():
    worker_settings = settings()
    message = report_worker.sanitize_error_message(
        RuntimeError(f"failed {worker_settings.supabase_secret_key}"),
        worker_settings,
    )
    assert worker_settings.supabase_secret_key not in message
    assert "[REDACTED]" in message


def test_full_worker_flow_generates_uploads_and_completes(monkeypatch, tmp_path):
    ergonomics = json.loads(
        (FIXTURES / "ergonomics-metrics-test.json").read_text(encoding="utf-8")
    )
    profile = json.loads(
        (FIXTURES / "risk-profile-test.json").read_text(encoding="utf-8")
    )
    risk = process_risk_document(ergonomics, profile)
    bucket = FakeBucket(
        json.dumps(ergonomics).encode(),
        json.dumps(risk).encode(),
    )
    client = FakeClient(
        {
            "update_analysis_progress": True,
            report_worker.COMPLETE_RPC_NAME: True,
        },
        storage=FakeStorage(bucket),
    )
    monkeypatch.setattr(report_worker, "DATA_DIRECTORY", tmp_path / "jobs")

    assert report_worker.process_claimed_analysis(
        client, settings(), claimed_row()
    ) is True
    assert bucket.uploaded_path == (
        "user-test/risk-engine-fixture-analysis/results/analysis-report.json"
    )
    complete = [
        payload for name, payload in client.calls if name == report_worker.COMPLETE_RPC_NAME
    ]
    assert len(complete) == 1
    assert complete[0]["p_report_version"] == "analysis-report-v2.1-beta.1"
    assert complete[0]["p_report_summary"]["overall_level"] == "low"


def test_worker_has_no_pose_risk_or_video_runtime_imports():
    source = Path(report_worker.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "import torch",
        "import cv2",
        "import onnxruntime",
        "import mediapipe",
        "import ffmpeg",
        "import subprocess",
        "from risk",
        "from ergonomics",
    ):
        assert forbidden not in source

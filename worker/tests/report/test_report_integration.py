from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from worker.src.report.integration import (
    build_database_summary,
    build_report_file,
    build_report_storage_path,
    read_ergonomics_document,
    read_risk_document,
    upload_report_file,
)
from worker.src.report.schemas import (
    ReportErgonomicsInputMissingError,
    ReportInputInvalidError,
    ReportRiskInputMissingError,
    ReportUploadError,
)


class FakeBucket:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.options = None

    def upload(self, *, path, file, file_options):
        if self.fail:
            raise RuntimeError("storage unavailable")
        assert json.load(file)["report_version"] == "analysis-report-v2.3-beta.1"
        self.options = file_options
        return SimpleNamespace(path=path)


class FakeStorage:
    def __init__(self, bucket):
        self.bucket = bucket

    def from_(self, bucket_name):
        assert bucket_name == "analysis-results"
        return self.bucket


def test_missing_ergonomics_and_risk_files_have_distinct_codes(tmp_path):
    with pytest.raises(ReportErgonomicsInputMissingError) as ergonomics_error:
        read_ergonomics_document(tmp_path / "ergonomics.json")
    with pytest.raises(ReportRiskInputMissingError) as risk_error:
        read_risk_document(tmp_path / "risk.json")
    assert ergonomics_error.value.error_code == "REPORT_ERGONOMICS_INPUT_MISSING"
    assert risk_error.value.error_code == "REPORT_RISK_INPUT_MISSING"


def test_corrupt_json_is_rejected(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ReportInputInvalidError):
        read_risk_document(path)


def test_build_report_file_writes_utf8_json(
    tmp_path,
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    ergonomics_path = tmp_path / "ergonomics.json"
    risk_path = tmp_path / "risk.json"
    ergonomics_path.write_text(json.dumps(ergonomics_document), encoding="utf-8")
    risk_path.write_text(json.dumps(risk_document), encoding="utf-8")
    output = tmp_path / "nested" / "analysis-report.json"
    result = build_report_file(
        analysis_metadata,
        ergonomics_path,
        risk_path,
        output,
        generated_at="2026-08-06T12:00:00+00:00",
    )
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert "montażowego" in output.read_text(encoding="utf-8")


def test_database_summary_is_small_and_has_no_frames(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    from worker.src.report.builder import build_analysis_report

    report = build_analysis_report(
        analysis_metadata,
        ergonomics_document,
        risk_document,
        generated_at="2026-08-06T12:00:00+00:00",
    )
    summary = build_database_summary(report)
    serialized = json.dumps(summary)
    assert summary["report_version"] == "analysis-report-v2.3-beta.1"
    assert summary["overall_level"] == report["risk_summary"]["overall_level"]
    assert "frames" not in serialized
    assert "body_areas" not in serialized
    assert "metric_summary" not in serialized


def test_storage_path_and_upload_are_deterministic(tmp_path):
    storage_path = build_report_storage_path("user", "analysis")
    assert storage_path == "user/analysis/results/analysis-report.json"
    local_path = tmp_path / "analysis-report.json"
    local_path.write_text('{"report_version":"analysis-report-v2.3-beta.1"}', encoding="utf-8")
    bucket = FakeBucket()
    assert upload_report_file(
        FakeStorage(bucket), "analysis-results", local_path, storage_path
    ) == storage_path
    assert bucket.options == {
        "content-type": "application/json",
        "cache-control": "3600",
        "upsert": "true",
    }


def test_upload_error_is_wrapped(tmp_path):
    local_path = tmp_path / "analysis-report.json"
    local_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ReportUploadError) as error:
        upload_report_file(
            FakeStorage(FakeBucket(fail=True)),
            "analysis-results",
            local_path,
            "u/a/results/analysis-report.json",
        )
    assert error.value.error_code == "REPORT_UPLOAD_ERROR"

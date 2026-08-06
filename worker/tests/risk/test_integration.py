from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from worker.src.risk.integration import (
    RiskAnalysisIdMismatchError,
    RiskInputInvalidError,
    RiskInputNotFoundError,
    RiskProfileInvalidError,
    RiskProfileNotFoundError,
    RiskUploadError,
    build_database_summary,
    build_risk_storage_path,
    process_risk_files_for_analysis,
    read_metrics_document,
    read_profile_document,
    upload_risk_file,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FakeBucket:
    def __init__(self, returned_path: str | None = None, fail: bool = False):
        self.returned_path = returned_path
        self.fail = fail
        self.options: dict[str, str] | None = None

    def upload(self, *, path, file, file_options):
        if self.fail:
            raise RuntimeError("storage unavailable")
        assert file.read(1)
        self.options = file_options
        return SimpleNamespace(path=self.returned_path or path)


class FakeStorage:
    def __init__(self, bucket: FakeBucket):
        self.bucket = bucket

    def from_(self, bucket_name: str):
        assert bucket_name == "analysis-results"
        return self.bucket


def test_valid_input_creates_assessment_file(tmp_path):
    output = tmp_path / "nested" / "risk-assessment.json"
    result = process_risk_files_for_analysis(
        FIXTURES / "ergonomics-metrics-test.json",
        FIXTURES / "risk-profile-test.json",
        output,
        expected_analysis_id="risk-engine-fixture-analysis",
    )
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == result
    assert persisted["risk_engine_version"] == "risk-engine-v1.0"


def test_missing_metrics_file_has_stable_error(tmp_path):
    with pytest.raises(RiskInputNotFoundError) as error:
        read_metrics_document(tmp_path / "missing.json", "analysis-id")
    assert error.value.error_code == "RISK_INPUT_NOT_FOUND"


def test_corrupt_metrics_json_has_stable_error(tmp_path):
    path = tmp_path / "metrics.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(RiskInputInvalidError) as error:
        read_metrics_document(path, "analysis-id")
    assert error.value.error_code == "RISK_INPUT_INVALID"


def test_missing_and_invalid_profiles_have_separate_error_codes(tmp_path):
    with pytest.raises(RiskProfileNotFoundError) as missing:
        read_profile_document(tmp_path / "missing-profile.json")
    assert missing.value.error_code == "RISK_PROFILE_NOT_FOUND"

    invalid_path = tmp_path / "invalid-profile.json"
    invalid_path.write_text("{}", encoding="utf-8")
    with pytest.raises(RiskProfileInvalidError) as invalid:
        read_profile_document(invalid_path)
    assert invalid.value.error_code == "RISK_PROFILE_INVALID"


def test_analysis_id_mismatch_is_rejected():
    with pytest.raises(RiskAnalysisIdMismatchError):
        read_metrics_document(
            FIXTURES / "ergonomics-metrics-test.json",
            "different-analysis",
        )


def test_database_summary_is_small_and_preserves_insufficient_data(
    metrics_document,
    risk_profile_document,
):
    from worker.src.risk.processor import process_risk_document

    assessment = process_risk_document(metrics_document, risk_profile_document)
    assessment = copy.deepcopy(assessment)
    assessment["overall"]["overall_level"] = "insufficient_data"
    assessment["overall"]["overall_score"] = None
    summary = build_database_summary(assessment)

    assert summary["overall_level"] == "insufficient_data"
    assert summary["insufficient_data"] is True
    assert "frames" not in summary
    assert "metrics" not in summary
    assert len(summary["dominant_metrics"]) <= 5


def test_database_summary_maps_versions_profile_level_and_coverage(
    metrics_document,
    risk_profile_document,
):
    from worker.src.risk.processor import process_risk_document

    assessment = process_risk_document(metrics_document, risk_profile_document)
    summary = build_database_summary(assessment)
    assert summary["risk_engine_version"] == assessment["risk_engine_version"]
    assert summary["profile"]["profile_id"] == assessment["profile"]["profile_id"]
    assert summary["overall_level"] == assessment["overall"]["overall_level"]
    assert summary["valid_metric_ratio"] == pytest.approx(
        assessment["data_quality"]["valid_metric_coverage"]
    )


def test_storage_path_and_upload_are_deterministic(tmp_path):
    storage_path = build_risk_storage_path("user-1", "analysis-1")
    assert storage_path == "user-1/analysis-1/results/risk-assessment.json"

    local_path = tmp_path / "risk-assessment.json"
    local_path.write_text("{}", encoding="utf-8")
    bucket = FakeBucket()
    assert upload_risk_file(
        FakeStorage(bucket), "analysis-results", local_path, storage_path
    ) == storage_path
    assert bucket.options == {
        "content-type": "application/json",
        "cache-control": "3600",
        "upsert": "true",
    }


def test_upload_error_is_wrapped(tmp_path):
    local_path = tmp_path / "risk-assessment.json"
    local_path.write_text("{}", encoding="utf-8")
    with pytest.raises(RiskUploadError) as error:
        upload_risk_file(
            FakeStorage(FakeBucket(fail=True)),
            "analysis-results",
            local_path,
            "u/a/results/risk-assessment.json",
        )
    assert error.value.error_code == "RISK_UPLOAD_ERROR"

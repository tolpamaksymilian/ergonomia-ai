from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from worker.src.risk.cli import main
from worker.src.risk.processor import process_risk_document
from worker.src.risk.schemas import MetricsValidationError


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_empty_document_is_rejected(risk_profile_document):
    with pytest.raises(MetricsValidationError, match="schema_version"):
        process_risk_document({}, risk_profile_document)


def test_empty_frames_are_rejected(metrics_document, risk_profile_document):
    metrics_document["frames"] = []
    with pytest.raises(MetricsValidationError, match="pustą"):
        process_risk_document(metrics_document, risk_profile_document)


def test_missing_summary_is_rejected(metrics_document, risk_profile_document):
    del metrics_document["summary"]
    with pytest.raises(MetricsValidationError, match="summary"):
        process_risk_document(metrics_document, risk_profile_document)


def test_missing_analysis_id_is_rejected(metrics_document, risk_profile_document):
    metrics_document["analysis_id"] = ""
    with pytest.raises(MetricsValidationError, match="analysis_id"):
        process_risk_document(metrics_document, risk_profile_document)


def test_unsupported_metrics_schema_is_rejected(
    metrics_document,
    risk_profile_document,
):
    metrics_document["schema_version"] = "2.0"
    with pytest.raises(MetricsValidationError, match="schema_version"):
        process_risk_document(metrics_document, risk_profile_document)


def test_unknown_input_metric_is_ignored(metrics_document, risk_profile_document):
    for frame in metrics_document["frames"]:
        frame["metrics"]["future_metric"] = {
            "value": 999,
            "valid": True,
            "quality": 1.0,
        }
    result = process_risk_document(metrics_document, risk_profile_document)
    assert "future_metric" not in result["metrics"]
    assert "future_metric" not in result["frames"][0]["metrics"]


def test_profile_metric_absent_from_document_is_rejected(
    metrics_document,
    risk_profile_document,
):
    ghost = copy.deepcopy(
        risk_profile_document["metrics"]["trunk_inclination_deg"]
    )
    risk_profile_document["metrics"]["ghost_metric"] = ghost
    risk_profile_document["zones"]["ghost"] = ["ghost_metric"]
    with pytest.raises(MetricsValidationError, match="ghost_metric"):
        process_risk_document(metrics_document, risk_profile_document)


def test_missing_metric_in_one_frame_becomes_insufficient_data(
    metrics_document,
    risk_profile_document,
):
    del metrics_document["frames"][1]["metrics"]["trunk_inclination_deg"]
    result = process_risk_document(metrics_document, risk_profile_document)
    frame_metric = result["frames"][1]["metrics"]["trunk_inclination_deg"]
    assert frame_metric["level"] == "insufficient_data"
    assert frame_metric["rejection_reason"] == "missing_metric"


def test_fps_fallback_is_recorded(metrics_document, risk_profile_document):
    for frame in metrics_document["frames"]:
        frame.pop("timestamp", None)
    metrics_document["fps"] = 25
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["data_quality"]["timing_method"] == "fps_fallback"
    assert "frame_timestamps_replaced_with_fps_fallback" in result["limitations"]


def test_missing_timing_returns_insufficient_data(
    metrics_document,
    risk_profile_document,
):
    for frame in metrics_document["frames"]:
        frame.pop("timestamp", None)
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["overall"]["overall_level"] == "insufficient_data"
    assert "exposure_timing_unavailable" in result["limitations"]


def test_profile_identity_is_preserved(metrics_document, risk_profile_document):
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["profile"] == {
        "profile_id": "test-only-risk-profile-v1",
        "profile_name": "Test only synthetic risk profile",
        "profile_version": "1.0.0-test",
        "status": "development",
        "normative_method": None,
    }
    assert result["configuration"]["rula_enabled"] is False
    assert result["configuration"]["reba_enabled"] is False


def test_disabled_metric_is_not_evaluated(metrics_document, risk_profile_document):
    risk_profile_document["metrics"]["trunk_inclination_deg"]["enabled"] = False
    result = process_risk_document(metrics_document, risk_profile_document)
    assert result["metrics"]["trunk_inclination_deg"]["final_level"] == "disabled"
    assert "trunk_inclination_deg" not in result["frames"][0]["metrics"]
    assert result["data_quality"]["enabled_metric_count"] == 13


def test_cli_writes_utf8_json(tmp_path, capsys):
    output = tmp_path / "nested" / "risk-assessment.json"
    exit_code = main(
        [
            str(FIXTURES / "ergonomics-metrics-test.json"),
            str(FIXTURES / "risk-profile-test.json"),
            str(output),
        ]
    )
    assert exit_code == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["analysis_id"] == "risk-engine-fixture-analysis"
    assert "overall_level=" in capsys.readouterr().out


def test_cli_returns_nonzero_for_missing_input(tmp_path, capsys):
    exit_code = main(
        [
            str(tmp_path / "missing.json"),
            str(FIXTURES / "risk-profile-test.json"),
            str(tmp_path / "output.json"),
        ]
    )
    assert exit_code != 0
    assert "Risk Engine error" in capsys.readouterr().err


def test_risk_package_has_no_forbidden_runtime_imports():
    source_root = Path(__file__).resolve().parents[2] / "src" / "risk"
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in source_root.glob("*.py")
    ).lower()
    for forbidden in (
        "import supabase",
        "import torch",
        "import cv2",
        "import onnxruntime",
        "import mediapipe",
    ):
        assert forbidden not in combined


def test_output_contains_transparent_frame_classification(
    metrics_document,
    risk_profile_document,
):
    result = process_risk_document(metrics_document, risk_profile_document)
    metric = result["frames"][0]["metrics"]["trunk_inclination_deg"]
    assert set(
        (
            "metric_name",
            "value",
            "valid",
            "quality",
            "level",
            "score",
            "weight",
            "weighted_score",
            "band",
            "rejection_reason",
        )
    ).issubset(metric)

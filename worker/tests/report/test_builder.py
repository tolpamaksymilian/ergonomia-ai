from __future__ import annotations

import copy
import json

import pytest

from worker.src.report.builder import DISCLAIMER, build_analysis_report
from worker.src.report.schemas import (
    REPORT_VERSION,
    ReportAnalysisMismatchError,
    ReportVersionUnsupportedError,
)


GENERATED_AT = "2026-08-06T12:00:00+00:00"


def build(analysis_metadata, ergonomics_document, risk_document):
    return build_analysis_report(
        analysis_metadata,
        ergonomics_document,
        risk_document,
        generated_at=GENERATED_AT,
    )


def test_builds_complete_versioned_report(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert report["schema_version"] == "1.0"
    assert report["report_version"] == REPORT_VERSION
    assert report["generated_at"] == GENERATED_AT
    assert report["analysis"]["analysis_id"] == analysis_metadata["id"]
    assert set(
        (
            "analysis",
            "processing",
            "data_quality",
            "risk_summary",
            "body_areas",
            "metric_summary",
            "key_moments",
            "limitations",
            "disclaimer",
        )
    ).issubset(report)


def test_report_never_exports_user_id_or_frame_series(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    report = build(analysis_metadata, ergonomics_document, risk_document)
    serialized = json.dumps(report)
    assert "must-not-be-exported" not in serialized
    assert "\"frames\"" not in serialized
    assert "source_video_path" not in serialized


def test_insufficient_data_is_explicit(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    risk_document["overall"]["overall_level"] = "insufficient_data"
    risk_document["overall"]["overall_score"] = None
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert report["risk_summary"]["insufficient_data"] is True
    assert report["risk_summary"]["overall_status"] == "insufficient_data"
    assert "Za mało poprawnych danych do wiarygodnej oceny." in report["observations"]


def test_unsupported_source_version_is_rejected(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    ergonomics_document["metrics_version"] = "future-v2"
    with pytest.raises(ReportVersionUnsupportedError):
        build(analysis_metadata, ergonomics_document, risk_document)


def test_analysis_id_mismatch_is_rejected(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    risk_document["analysis_id"] = "different"
    with pytest.raises(ReportAnalysisMismatchError):
        build(analysis_metadata, ergonomics_document, risk_document)


def test_missing_optional_metric_statistics_do_not_create_zeroes(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    ergonomics_document["summary"] = {}
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert report["metric_summary"]
    first = report["metric_summary"][0]
    statistics = first.get("statistics", {})
    assert statistics.get("median") is not None or "median" not in statistics
    assert statistics.get("maximum") is not None or "maximum" not in statistics


def test_missing_optional_analysis_fields_are_omitted(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    for key in (
        "source_duration_seconds",
        "source_width",
        "source_height",
        "pose_presence_ratio",
    ):
        analysis_metadata.pop(key)
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert "source_duration_seconds" not in report["analysis"]
    assert "source_width" not in report["analysis"]
    assert "pose_presence_ratio" not in report["data_quality"]


def test_body_areas_come_from_risk_zones(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    report = build(analysis_metadata, ergonomics_document, risk_document)
    area_ids = {area["area_id"] for area in report["body_areas"]}
    assert area_ids == set(risk_document["zones"])
    trunk = next(area for area in report["body_areas"] if area["area_id"] == "trunk")
    assert trunk["label"] == "Tułów"
    assert trunk["level"] == risk_document["zones"]["trunk"]["highest_level"]


def test_no_key_frames_produces_empty_key_moments(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    risk_document["key_frames"] = []
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert report["key_moments"] == []
    assert report["risk_summary"]["key_frames_count"] == 0


def test_key_moment_uses_only_existing_frame_metadata(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    risk_document["key_frames"] = [
        {
            "source_frame_index": 7,
            "output_frame_index": 4,
            "metric_name": "trunk_inclination_deg",
            "zone": "trunk",
            "value": 52.0,
            "level": "high",
            "weighted_score": 2.0,
            "quality": 0.9,
        }
    ]
    report = build(analysis_metadata, ergonomics_document, risk_document)
    moment = report["key_moments"][0]
    assert moment["source_frame_index"] == 7
    assert "timestamp_seconds" not in moment
    assert moment["area_id"] == "trunk"


def test_report_has_no_fictitious_normative_results(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    report = build(analysis_metadata, ergonomics_document, risk_document)
    serialized = json.dumps(report).lower()
    assert "overall_score" not in serialized
    assert "safety_percentage" not in serialized
    assert "rula_score" not in serialized
    assert "reba_score" not in serialized


def test_disclaimer_is_safe_and_not_duplicated(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert report["disclaimer"] == DISCLAIMER
    assert json.dumps(report, ensure_ascii=False).count(DISCLAIMER) == 1


def test_development_profile_is_marked_as_limitation(
    analysis_metadata,
    ergonomics_document,
    risk_document,
):
    report = build(analysis_metadata, ergonomics_document, risk_document)
    assert report["risk_summary"]["profile"]["profile_status"] == "development"
    assert "production_profile_not_used" in report["limitations"]

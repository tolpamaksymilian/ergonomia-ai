from __future__ import annotations

from worker.src.report.builder import build_analysis_report


def test_report_keeps_late_source_moment_and_deduplicates_nearby_metric_moments(
    analysis_metadata,
    ergonomics_document,
    risk_document,
) -> None:
    risk_document["key_frames"] = [
        {"source_frame_index": 10, "timestamp_seconds": 1.0, "metric_name": "trunk_inclination_deg", "zone": "trunk", "value": 40.0, "level": "high", "weighted_score": 2.0, "quality": 0.7},
        {"source_frame_index": 12, "timestamp_seconds": 1.2, "metric_name": "trunk_inclination_deg", "zone": "trunk", "value": 45.0, "level": "high", "weighted_score": 2.4, "quality": 0.95},
        {"source_frame_index": 442, "timestamp_seconds": 44.2, "metric_name": "neck_flexion_deg", "zone": "neck", "value": 32.0, "level": "high", "weighted_score": 2.0, "quality": 0.9},
    ]
    report = build_analysis_report(analysis_metadata, ergonomics_document, risk_document)
    moments = report["key_moments"]
    assert [item["timestamp_seconds"] for item in moments] == [1.2, 44.2]
    assert moments[-1]["source_frame_index"] == 442


def test_report_does_not_claim_missing_rula_or_reba_when_assessment_exists(
    analysis_metadata,
    ergonomics_document,
    risk_document,
) -> None:
    assessment = {
        "schema_version": "1.0",
        "rula": {"status": "PARTIAL"},
        "reba": {"status": "PARTIAL"},
    }
    report = build_analysis_report(
        analysis_metadata,
        ergonomics_document,
        risk_document,
        assessment=assessment,
    )
    assert "rula_not_calculated" not in report["limitations"]
    assert "reba_not_calculated" not in report["limitations"]


def test_low_processing_coverage_is_explicit_limitation(
    analysis_metadata,
    ergonomics_document,
    risk_document,
) -> None:
    ergonomics_document["source_coverage"] = {"processing_coverage_ratio": 0.1}
    report = build_analysis_report(analysis_metadata, ergonomics_document, risk_document)
    assert report["data_quality"]["processing_coverage_ratio"] == 0.1
    assert "partial_source_video_processing" in report["limitations"]


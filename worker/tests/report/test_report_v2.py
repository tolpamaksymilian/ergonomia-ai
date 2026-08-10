from __future__ import annotations

from worker.src.report.builder import build_analysis_report
from worker.src.report.findings import build_priority_findings
from worker.src.report.recommendations import build_manual_confirmation, build_recommendations


def _elevate(risk, metric_name, level="high", duration=2.0):
    metric = risk["metrics"][metric_name]
    metric["final_level"] = level
    metric["weighted_score"] = 2.0
    metric["data_quality"] = "sufficient"
    metric["exposure"][f"{level}_duration_seconds"] = duration
    metric["exposure"][f"{level}_exposure_ratio"] = 0.4


def test_report_v2_has_concise_decision_sections(analysis_metadata, ergonomics_document, risk_document):
    _elevate(risk_document, "trunk_inclination_deg")
    report = build_analysis_report(analysis_metadata, ergonomics_document, risk_document)
    assert report["schema_version"] == "2.0"
    assert report["report_version"] == "analysis-report-v2.0-beta.1"
    assert len(report["executive_summary"]) <= 6
    assert len(report["priority_findings"]) <= 6
    assert len(report["recommendations"]) <= 5
    assert "technical_appendix" in report


def test_finding_ranking_prefers_more_severe_level(risk_document):
    _elevate(risk_document, "trunk_inclination_deg", "moderate")
    _elevate(risk_document, "neck_flexion_deg", "critical")
    findings = build_priority_findings(risk_document)
    assert findings[0]["level"] == "critical"


def test_findings_deduplicate_same_body_zone(risk_document):
    _elevate(risk_document, "left_upper_arm_elevation_deg")
    _elevate(risk_document, "left_elbow_flexion_deg")
    findings = build_priority_findings(risk_document)
    left = [item for item in findings if item["zone"] == "left_upper_limb"]
    assert len(left) == 1
    assert set(left[0]["metric_names"]) == {"left_upper_arm_elevation_deg", "left_elbow_flexion_deg"}


def test_recommendation_requires_valid_region_and_quality():
    findings = [
        {"finding_id": "x", "zone": "trunk", "level": "high", "metric_names": ["x"], "data_quality": "insufficient"},
        {"finding_id": "y", "zone": "unknown", "level": "high", "metric_names": ["y"], "data_quality": "sufficient"},
    ]
    assert build_recommendations(findings) == []


def test_manual_confirmation_preserves_partial_assessment_and_unknown_load():
    assessment = {"rula": {"status": "PARTIAL", "representative": {"missing_inputs": ["external_load"]}}}
    items = build_manual_confirmation(assessment, valid_metric_ratio=0.5, hand_activity={"external_load_known": False})
    codes = {item["code"] for item in items}
    assert {"limited_data_coverage", "rula_external_load", "external_load_unknown"}.issubset(codes)


def test_recommendations_can_be_disabled(analysis_metadata, ergonomics_document, risk_document):
    _elevate(risk_document, "trunk_inclination_deg")
    report = build_analysis_report(analysis_metadata, ergonomics_document, risk_document, recommendations_enabled=False)
    assert report["priority_findings"]
    assert report["recommendations"] == []

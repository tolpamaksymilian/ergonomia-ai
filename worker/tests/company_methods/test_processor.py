from __future__ import annotations

from worker.src.company_methods import process_company_methods


def test_processor_keeps_methods_separate_and_reports_missing_inputs():
    result = process_company_methods(None, {"analysis_id": "analysis-1", "metrics_version": "ergonomics-metrics-v1.0", "frames": []}, generated_at="2026-08-10T00:00:00+00:00")
    assert result["analysis_id"] == "analysis-1"
    assert result["company_methods_version"] == "company-methods-v1.1-beta.1"
    assert result["owas"]["status"] == "UNAVAILABLE"
    assert result["chemical"]["automatic_scoring_enabled"] is False
    assert result["configuration"]["absolute_video_measurements_enabled"] is False

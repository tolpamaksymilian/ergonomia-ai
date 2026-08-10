from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.src.assessment.integration import process_assessment_documents, process_assessment_files
from worker.src.assessment.schemas import AssessmentInputError
from worker.src.assessment.selection import select_candidate_postures


def test_document_contract_and_provenance(metrics_document, pose_document):
    result = process_assessment_documents(
        metrics_document,
        pose_document,
        calculated_at="2026-08-09T00:00:00+00:00",
    )
    assert result["schema_version"] == "1.0"
    assert result["engine_version"] == "assessment-v1.0-beta.1"
    assert result["rula"]["status"] == "PARTIAL"
    assert result["reba"]["status"] == "PARTIAL"
    component = result["candidate_postures"][0]["rula"]["left"]["components"]["upper_arm"]
    assert component["source"] == "derived"
    assert component["evidence"]


def test_candidates_are_deduplicated_and_limited(metrics_document, pose_document):
    selected = select_candidate_postures(
        metrics_document,
        pose_document,
        maximum_candidates=3,
        minimum_spacing_seconds=0.5,
    )
    assert len(selected) <= 3
    assert all(
        abs(a.timestamp_seconds - b.timestamp_seconds) >= 0.5
        for a, b in zip(selected, selected[1:])
    )


def test_invalid_tracking_cannot_win(metrics_document, pose_document):
    pose_document["frames"][10]["tracking"]["state"] = "TRACK_LOST"
    selected = select_candidate_postures(metrics_document, pose_document)
    assert all(item.frame_position != 10 for item in selected)


def test_pose_evidence_is_joined_by_source_frame_index(metrics_document, pose_document):
    for index, frame in enumerate(pose_document["frames"]):
        frame["source_frame_index"] = index
        frame["scores"] = [0.95 if index == 10 else 0.1] * 17
    pose_document["frames"].reverse()
    result = process_assessment_documents(metrics_document, pose_document)
    candidate = next(item for item in result["candidate_postures"] if item["source_frame_index"] == 10)
    assert candidate["reba"]["left"]["components"]["legs"]["source"] == "derived"


def test_empty_metrics_is_rejected(metrics_document):
    metrics_document["frames"] = []
    with pytest.raises(AssessmentInputError):
        process_assessment_documents(metrics_document)


def test_mismatched_analysis_id_is_rejected(metrics_document, pose_document):
    pose_document["analysis_id"] = "other"
    with pytest.raises(AssessmentInputError):
        process_assessment_documents(metrics_document, pose_document)


def test_unsupported_pose_schema_is_rejected(metrics_document, pose_document):
    pose_document["schema_version"] = "3.0"
    with pytest.raises(AssessmentInputError):
        process_assessment_documents(metrics_document, pose_document)


def test_file_api_writes_utf8(tmp_path: Path, metrics_document, pose_document):
    pose = tmp_path / "pose.json"
    metrics = tmp_path / "metrics.json"
    output = tmp_path / "nested" / "assessment.json"
    pose.write_text(json.dumps(pose_document), encoding="utf-8")
    metrics.write_text(json.dumps(metrics_document), encoding="utf-8")
    result = process_assessment_files(pose, metrics, output)
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["analysis_id"] == result["analysis_id"]


def test_unknown_never_becomes_zero(metrics_document, pose_document):
    result = process_assessment_documents(metrics_document, pose_document)
    rula = result["candidate_postures"][0]["rula"]["left"]
    assert rula["components"]["force_load"]["score_component"] is None
    assert rula["final_score"] is None


def test_complete_range_invariant_with_explicit_context(
    metrics_document,
    pose_document,
    complete_context,
):
    result = process_assessment_documents(
        metrics_document,
        pose_document,
        user_context=complete_context,
    )
    for candidate in result["candidate_postures"]:
        for method in ("rula", "reba"):
            for assessment in candidate[method].values():
                score_range = assessment["score_range"]
                assert score_range["min"] <= score_range["max"]


def test_deterministic_output_ignoring_clock(metrics_document, pose_document):
    first = process_assessment_documents(metrics_document, pose_document, calculated_at="fixed")
    second = process_assessment_documents(metrics_document, pose_document, calculated_at="fixed")
    first["diagnostics"].pop("processing_ms")
    second["diagnostics"].pop("processing_ms")
    for key in ("selection_ms", "rula_ms", "reba_ms"):
        first["diagnostics"].pop(key)
        second["diagnostics"].pop(key)
    assert first == second

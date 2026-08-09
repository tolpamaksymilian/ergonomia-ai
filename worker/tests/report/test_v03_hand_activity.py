from __future__ import annotations

import json

from worker.src.report.builder import build_analysis_report


GENERATED_AT = "2026-08-09T12:00:00+00:00"


def _build(analysis_metadata, ergonomics_document, risk_document):
    return build_analysis_report(
        analysis_metadata,
        ergonomics_document,
        risk_document,
        generated_at=GENERATED_AT,
    )


def test_report_carries_limited_holding_summary_not_frames(
    analysis_metadata, ergonomics_document, risk_document
):
    ergonomics_document["hand_activity"] = {
        "left": {
            "valid_observation_seconds": 2.0,
            "likely_holding_seconds": 1.2,
            "static_holding_seconds": 0.8,
            "longest_holding_seconds": 1.2,
            "holding_episode_count": 1,
            "holding_ratio": 0.6,
            "episodes": [],
        },
        "bimanual": {"likely_holding_seconds": 0.4, "episode_count": 1},
    }
    report = _build(analysis_metadata, ergonomics_document, risk_document)
    assert report["hand_activity"]["left"]["likely_holding_seconds"] == 1.2
    assert report["hand_activity"]["bimanual"]["likely_holding_seconds"] == 0.4
    assert "episodes" not in report["hand_activity"]["left"]
    assert '"frames"' not in json.dumps(report)


def test_unknown_observation_is_not_serialized_as_zero_holding(
    analysis_metadata, ergonomics_document, risk_document
):
    ergonomics_document["hand_activity"] = {
        "right": {
            "valid_observation_seconds": 0.0,
            "likely_holding_seconds": 0.0,
            "holding_episode_count": 0,
            "episodes": [],
        }
    }
    report = _build(analysis_metadata, ergonomics_document, risk_document)
    right = report["hand_activity"]["right"]
    assert right["holding_detected"] == "unknown"
    assert "likely_holding_seconds" not in right


def test_known_object_interaction_has_duration_and_confidence(
    analysis_metadata, ergonomics_document, risk_document
):
    ergonomics_document["hand_activity"] = {
        "left": {
            "valid_observation_seconds": 3.0,
            "likely_holding_seconds": 2.0,
            "holding_episode_count": 2,
            "episodes": [
                {
                    "duration_seconds": 1.2,
                    "known_object_class": "bottle",
                    "known_object_confidence": 0.8,
                },
                {
                    "duration_seconds": 0.8,
                    "known_object_class": "bottle",
                    "known_object_confidence": 0.6,
                },
            ],
        }
    }
    report = _build(analysis_metadata, ergonomics_document, risk_document)
    interaction = report["hand_activity"]["left"]["object_interactions"][0]
    assert interaction == {
        "object_class": "bottle",
        "holding_seconds": 2.0,
        "confidence": 0.7,
    }


def test_unclassified_held_object_adds_limitation(
    analysis_metadata, ergonomics_document, risk_document
):
    ergonomics_document["hand_activity"] = {
        "left": {
            "valid_observation_seconds": 2.0,
            "likely_holding_seconds": 1.0,
            "holding_episode_count": 1,
            "episodes": [{"duration_seconds": 1.0, "known_object_class": None}],
        }
    }
    report = _build(analysis_metadata, ergonomics_document, risk_document)
    assert report["hand_activity"]["left"]["unclassified_object_possible"] is True
    assert "left_holding_object_unclassified" in report["limitations"]


def test_legacy_report_omits_hand_activity(
    analysis_metadata, ergonomics_document, risk_document
):
    ergonomics_document.pop("hand_activity", None)
    report = _build(analysis_metadata, ergonomics_document, risk_document)
    assert "hand_activity" not in report

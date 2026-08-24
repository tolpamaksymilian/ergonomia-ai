from __future__ import annotations

import math

import pytest

from worker.src.ergonomics.processor import InputSchemaError, process_pose_document
from worker.src.ergonomics.schemas import METRIC_NAMES


def _document(frames: list[object]) -> dict[str, object]:
    return {
        "schema_version": "3.0",
        "analysis_id": "processor-test",
        "coordinate_space": "source-video-pixels",
        "configuration": {"keypoint_threshold": 0.5},
        "frames": frames,
    }


def test_json_without_frames_produces_empty_summaries() -> None:
    result = process_pose_document(_document([]))
    assert result["frames"] == []
    for name in METRIC_NAMES:
        assert result["summary"][name]["valid_frames"] == 0  # type: ignore[index]
        assert result["summary"][name]["invalid_frames"] == 0  # type: ignore[index]
        assert result["summary"][name]["valid_ratio"] == 0.0  # type: ignore[index]
        assert result["summary"][name]["mean"] is None  # type: ignore[index]


def test_partially_corrupted_frame_does_not_invent_metrics() -> None:
    points = [[None, None] for _ in range(133)]
    scores = [0.0 for _ in range(133)]
    points[5] = [math.nan, 20.0]
    scores[5] = 0.9
    frame = {
        "source_frame_index": 7,
        "output_frame_index": 2,
        "detected": True,
        "smoothed_keypoints": points,
        "scores": scores,
        "left_hand": {"visible": False},
        "right_hand": {"visible": False},
    }
    result = process_pose_document(_document([frame]))
    output_frame = result["frames"][0]  # type: ignore[index]
    assert output_frame["person_detected"] is True
    assert output_frame["metrics"]["trunk_inclination_deg"]["valid"] is False
    assert output_frame["metrics"]["trunk_inclination_deg"]["value"] is None
    assert output_frame["metrics"]["trunk_inclination_deg"]["rejection_reason"] == "invalid_coordinate"


def test_frame_without_person_rejects_every_metric_consistently() -> None:
    result = process_pose_document(_document([{"detected": False}]))
    metrics = result["frames"][0]["metrics"]  # type: ignore[index]
    assert all(metric["rejection_reason"] == "person_not_detected" for metric in metrics.values())


def test_every_metric_has_quality_contract() -> None:
    result = process_pose_document(_document([{"detected": False}]))
    metrics = result["frames"][0]["metrics"]  # type: ignore[index]
    assert set(metrics) == set(METRIC_NAMES)
    for metric in metrics.values():
        assert set(metric) == {
            "value", "valid", "quality", "source_points",
            "rejection_reason", "source_provenance",
        }


def test_unsupported_schema_is_rejected() -> None:
    with pytest.raises(InputSchemaError, match="Nieobsługiwana wersja"):
        process_pose_document({"schema_version": "2.2", "frames": []})

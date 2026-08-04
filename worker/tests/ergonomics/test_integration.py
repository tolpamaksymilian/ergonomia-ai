from __future__ import annotations

from pathlib import Path
from typing import IO

import pytest

from worker.src.ergonomics.integration import (
    AnalysisIdMismatchError,
    EmptyMetricsFramesError,
    InvalidMetricsDocumentError,
    UnsupportedPoseSchemaError,
    build_database_summary,
    build_metrics_storage_path,
    calculate_valid_metric_ratio,
    upload_metrics_file,
    validate_pose_source_document,
)
from worker.src.ergonomics.schemas import METRIC_NAMES


def _statistics(valid_frames: int, invalid_frames: int) -> dict[str, int | float | None]:
    return {
        "valid_frames": valid_frames,
        "invalid_frames": invalid_frames,
        "valid_ratio": valid_frames / max(1, valid_frames + invalid_frames),
        "mean": 10.0 if valid_frames else None,
        "median": 10.0 if valid_frames else None,
        "minimum": 10.0 if valid_frames else None,
        "maximum": 10.0 if valid_frames else None,
        "percentile_95": 10.0 if valid_frames else None,
    }


def _metrics_document(
    frame_validity: list[bool],
    *,
    include_summary: bool = True,
) -> dict[str, object]:
    frames: list[dict[str, object]] = []
    for valid in frame_validity:
        frames.append(
            {
                "metrics": {
                    name: {
                        "value": 10.0 if valid else None,
                        "valid": valid,
                    }
                    for name in METRIC_NAMES
                }
            }
        )

    document: dict[str, object] = {
        "schema_version": "1.0",
        "metrics_version": "ergonomics-metrics-v1.0",
        "frames": frames,
    }
    if include_summary:
        valid_frames = sum(frame_validity)
        invalid_frames = len(frame_validity) - valid_frames
        document["summary"] = {
            name: _statistics(valid_frames, invalid_frames)
            for name in METRIC_NAMES
        }
    return document


def test_calculates_overall_valid_metric_ratio() -> None:
    document = _metrics_document([True, False])
    assert calculate_valid_metric_ratio(document) == pytest.approx(0.5)


def test_ratio_is_one_when_every_metric_is_valid() -> None:
    assert calculate_valid_metric_ratio(_metrics_document([True, True])) == 1.0


def test_ratio_is_zero_when_every_metric_is_rejected() -> None:
    assert calculate_valid_metric_ratio(_metrics_document([False, False])) == 0.0


def test_document_without_frames_is_rejected() -> None:
    with pytest.raises(EmptyMetricsFramesError):
        calculate_valid_metric_ratio(_metrics_document([]))


def test_document_without_summary_is_rejected_for_database_metadata() -> None:
    with pytest.raises(InvalidMetricsDocumentError, match="podsumowania"):
        build_database_summary(_metrics_document([True], include_summary=False))


def test_database_summary_is_limited_and_contains_coverage() -> None:
    summary = build_database_summary(_metrics_document([True, False]))
    assert summary["frame_count"] == 2
    assert summary["metric_count"] == 14
    assert summary["valid_metric_ratio"] == pytest.approx(0.5)
    assert summary["metric_names"] == list(METRIC_NAMES)
    assert "frames" not in summary
    assert set(summary["metrics"]) == set(METRIC_NAMES)  # type: ignore[arg-type]


def test_storage_path_matches_existing_results_layout() -> None:
    assert build_metrics_storage_path("user-1", "analysis-1") == (
        "user-1/analysis-1/results/ergonomics-metrics.json"
    )


def test_mismatched_analysis_id_is_rejected() -> None:
    with pytest.raises(AnalysisIdMismatchError):
        validate_pose_source_document(
            {"schema_version": "3.0", "analysis_id": "other", "frames": [{}]},
            "expected",
        )


def test_unsupported_pose_schema_is_rejected() -> None:
    with pytest.raises(UnsupportedPoseSchemaError):
        validate_pose_source_document(
            {"schema_version": "2.0", "analysis_id": "analysis", "frames": [{}]},
            "analysis",
        )


class _UploadResponse:
    def __init__(self, path: str) -> None:
        self.path = path


class _StorageBucket:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, dict[str, str], bytes]] = []

    def upload(
        self,
        *,
        path: str,
        file: IO[bytes],
        file_options: dict[str, str],
    ) -> _UploadResponse:
        self.uploads.append((path, file_options, file.read()))
        return _UploadResponse(path)


class _StorageClient:
    def __init__(self) -> None:
        self.bucket = _StorageBucket()

    def from_(self, bucket_name: str) -> _StorageBucket:
        assert bucket_name == "analysis-results"
        return self.bucket


def test_repeated_upsert_keeps_the_same_storage_path(tmp_path: Path) -> None:
    local_path = tmp_path / "ergonomics-metrics.json"
    local_path.write_text('{"schema_version":"1.0"}', encoding="utf-8")
    storage = _StorageClient()
    expected_path = build_metrics_storage_path("user-1", "analysis-1")

    first = upload_metrics_file(
        storage,
        "analysis-results",
        local_path,
        expected_path,
    )
    second = upload_metrics_file(
        storage,
        "analysis-results",
        local_path,
        expected_path,
    )

    assert first == second == expected_path
    assert [upload[0] for upload in storage.bucket.uploads] == [
        expected_path,
        expected_path,
    ]
    assert all(
        upload[1]["upsert"] == "true" for upload in storage.bucket.uploads
    )

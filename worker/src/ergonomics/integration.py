"""Pure integration helpers shared by the ergonomics worker and its tests."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Protocol

from .processor import SUPPORTED_POSE_SCHEMAS
from .schemas import METRIC_NAMES


METRICS_SCHEMA_VERSION = "1.0"
METRICS_VERSION = "ergonomics-metrics-v1.0"
SUMMARY_FIELDS: tuple[str, ...] = (
    "valid_frames",
    "invalid_frames",
    "valid_ratio",
    "mean",
    "median",
    "minimum",
    "maximum",
    "percentile_95",
)


class ErgonomicsIntegrationError(ValueError):
    """Base error carrying a stable code suitable for Supabase metadata."""

    error_code = "ERGONOMICS_INTEGRATION_ERROR"


class MissingResultJsonPathError(ErgonomicsIntegrationError):
    error_code = "MISSING_RESULT_JSON_PATH"


class EmptyPoseFileError(ErgonomicsIntegrationError):
    error_code = "EMPTY_POSE_FILE"


class InvalidPoseJsonError(ErgonomicsIntegrationError):
    error_code = "INVALID_POSE_JSON"


class UnsupportedPoseSchemaError(ErgonomicsIntegrationError):
    error_code = "UNSUPPORTED_POSE_SCHEMA"


class AnalysisIdMismatchError(ErgonomicsIntegrationError):
    error_code = "ANALYSIS_ID_MISMATCH"


class EmptyMetricsFramesError(ErgonomicsIntegrationError):
    error_code = "EMPTY_METRICS_FRAMES"


class InvalidMetricsDocumentError(ErgonomicsIntegrationError):
    error_code = "INVALID_METRICS_DOCUMENT"


class MetricsUploadError(ErgonomicsIntegrationError):
    error_code = "METRICS_UPLOAD_ERROR"


class UploadResponseProtocol(Protocol):
    path: str


class StorageBucketProtocol(Protocol):
    def upload(
        self,
        *,
        path: str,
        file: IO[bytes],
        file_options: dict[str, str],
    ) -> UploadResponseProtocol: ...


class StorageClientProtocol(Protocol):
    def from_(self, bucket_name: str) -> StorageBucketProtocol: ...


def validate_pose_source_document(
    document: object,
    expected_analysis_id: str,
) -> dict[str, object]:
    if not isinstance(document, dict):
        raise InvalidPoseJsonError("Główny element pose-keypoints.json musi być obiektem.")

    schema_version = document.get("schema_version")
    if schema_version not in SUPPORTED_POSE_SCHEMAS:
        raise UnsupportedPoseSchemaError(
            f"Nieobsługiwana wersja schematu pozy: {schema_version!r}."
        )

    document_analysis_id = document.get("analysis_id")
    if (
        document_analysis_id is not None
        and str(document_analysis_id) != str(expected_analysis_id)
    ):
        raise AnalysisIdMismatchError(
            "analysis_id w pose-keypoints.json nie jest zgodne z rekordem analizy."
        )

    frames = document.get("frames")
    if not isinstance(frames, list):
        raise InvalidPoseJsonError("Pole 'frames' w pose-keypoints.json musi być tablicą.")

    return document


def build_metrics_storage_path(user_id: str, analysis_id: str) -> str:
    safe_user_id = _storage_segment(user_id, "user_id")
    safe_analysis_id = _storage_segment(analysis_id, "analysis_id")
    return f"{safe_user_id}/{safe_analysis_id}/results/ergonomics-metrics.json"


def calculate_valid_metric_ratio(metrics_document: Mapping[str, object]) -> float:
    frames = metrics_document.get("frames")
    if not isinstance(frames, list):
        raise InvalidMetricsDocumentError("Pole 'frames' dokumentu metryk musi być tablicą.")
    if not frames:
        raise EmptyMetricsFramesError("Dokument metryk nie zawiera żadnych klatek.")

    valid_values = 0
    possible_values = len(frames) * len(METRIC_NAMES)

    for frame in frames:
        metrics = frame.get("metrics") if isinstance(frame, dict) else None
        for metric_name in METRIC_NAMES:
            metric = metrics.get(metric_name) if isinstance(metrics, dict) else None
            if not isinstance(metric, dict) or metric.get("valid") is not True:
                continue
            value = metric.get("value")
            if _finite_number(value) is not None:
                valid_values += 1

    ratio = valid_values / possible_values
    return round(min(1.0, max(0.0, ratio)), 6)


def build_database_summary(
    metrics_document: Mapping[str, object],
) -> dict[str, object]:
    schema_version = metrics_document.get("schema_version")
    if schema_version != METRICS_SCHEMA_VERSION:
        raise InvalidMetricsDocumentError(
            f"Nieobsługiwana wersja dokumentu metryk: {schema_version!r}."
        )

    metrics_version = metrics_document.get("metrics_version")
    if metrics_version != METRICS_VERSION:
        raise InvalidMetricsDocumentError(
            f"Nieobsługiwana wersja metryk: {metrics_version!r}."
        )

    frames = metrics_document.get("frames")
    if not isinstance(frames, list):
        raise InvalidMetricsDocumentError("Pole 'frames' dokumentu metryk musi być tablicą.")
    if not frames:
        raise EmptyMetricsFramesError("Dokument metryk nie zawiera żadnych klatek.")

    summary = metrics_document.get("summary")
    if not isinstance(summary, dict):
        raise InvalidMetricsDocumentError("Dokument metryk nie zawiera podsumowania.")

    limited_metrics: dict[str, dict[str, int | float | None]] = {}
    total_valid_values = 0

    for metric_name in METRIC_NAMES:
        source_statistics = summary.get(metric_name)
        if not isinstance(source_statistics, dict):
            raise InvalidMetricsDocumentError(
                f"Brakuje podsumowania metryki: {metric_name}."
            )

        statistics = _limited_statistics(source_statistics, metric_name)
        if (
            int(statistics["valid_frames"] or 0)
            + int(statistics["invalid_frames"] or 0)
            != len(frames)
        ):
            raise InvalidMetricsDocumentError(
                f"Liczniki podsumowania nie odpowiadają liczbie klatek: {metric_name}."
            )
        total_valid_values += int(statistics["valid_frames"] or 0)
        limited_metrics[metric_name] = statistics

    possible_values = len(frames) * len(METRIC_NAMES)
    valid_metric_ratio = calculate_valid_metric_ratio(metrics_document)

    return {
        "metric_names": list(METRIC_NAMES),
        "metrics": limited_metrics,
        "frame_count": len(frames),
        "metric_count": len(METRIC_NAMES),
        "valid_metric_values": total_valid_values,
        "possible_metric_values": possible_values,
        "valid_metric_ratio": valid_metric_ratio,
    }


def upload_metrics_file(
    storage_client: StorageClientProtocol,
    bucket_name: str,
    local_path: Path,
    storage_path: str,
) -> str:
    if not local_path.is_file() or local_path.stat().st_size <= 0:
        raise MetricsUploadError(f"Plik metryk jest pusty lub nie istnieje: {local_path}")

    with local_path.open("rb") as file_handle:
        response = storage_client.from_(bucket_name).upload(
            path=storage_path,
            file=file_handle,
            file_options={
                "content-type": "application/json",
                "cache-control": "3600",
                "upsert": "true",
            },
        )

    uploaded_path = str(response.path).strip()
    if uploaded_path != storage_path:
        raise MetricsUploadError(
            f"Storage zwrócił inną ścieżkę niż oczekiwana: {uploaded_path!r}."
        )
    return uploaded_path


def _storage_segment(value: str, label: str) -> str:
    segment = str(value).strip()
    if not segment or "/" in segment or "\\" in segment or segment in {".", ".."}:
        raise ErgonomicsIntegrationError(f"Nieprawidłowy segment Storage: {label}.")
    return segment


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _limited_statistics(
    source: Mapping[str, object],
    metric_name: str,
) -> dict[str, int | float | None]:
    valid_frames = source.get("valid_frames")
    invalid_frames = source.get("invalid_frames")
    if (
        not isinstance(valid_frames, int)
        or isinstance(valid_frames, bool)
        or valid_frames < 0
        or not isinstance(invalid_frames, int)
        or isinstance(invalid_frames, bool)
        or invalid_frames < 0
    ):
        raise InvalidMetricsDocumentError(
            f"Nieprawidłowe liczniki podsumowania metryki: {metric_name}."
        )

    valid_ratio = _finite_number(source.get("valid_ratio"))
    if valid_ratio is None or not 0.0 <= valid_ratio <= 1.0:
        raise InvalidMetricsDocumentError(
            f"Nieprawidłowe pokrycie podsumowania metryki: {metric_name}."
        )

    output: dict[str, int | float | None] = {
        "valid_frames": valid_frames,
        "invalid_frames": invalid_frames,
        "valid_ratio": round(valid_ratio, 6),
    }
    for field in SUMMARY_FIELDS[3:]:
        value = source.get(field)
        numeric = _finite_number(value)
        if value is not None and numeric is None:
            raise InvalidMetricsDocumentError(
                f"Nieprawidłowa statystyka {field} dla metryki: {metric_name}."
            )
        output[field] = None if numeric is None else round(numeric, 6)
    return output

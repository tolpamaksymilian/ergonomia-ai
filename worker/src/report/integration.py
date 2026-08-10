"""File, Storage and database-summary boundaries for Report Engine V2."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any, Protocol
from uuid import uuid4

from .builder import build_analysis_report
from .schemas import (
    REPORT_VERSION,
    ReportEngineError,
    ReportErgonomicsInputMissingError,
    ReportInputInvalidError,
    ReportRiskInputMissingError,
    ReportUploadError,
)


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


def read_ergonomics_document(path: Path) -> dict[str, Any]:
    return _read_json_object(
        path,
        "ergonomics-metrics.json",
        ReportErgonomicsInputMissingError,
    )


def read_risk_document(path: Path) -> dict[str, Any]:
    return _read_json_object(
        path,
        "risk-assessment.json",
        ReportRiskInputMissingError,
    )


def build_report_file(
    analysis: Mapping[str, Any],
    ergonomics_path: Path,
    risk_path: Path,
    output_path: Path,
    *,
    assessment_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    ergonomics = read_ergonomics_document(ergonomics_path)
    risk = read_risk_document(risk_path)
    assessment = (
        _read_json_object(
            assessment_path,
            "ergonomic-assessment.json",
            ReportInputInvalidError,
        )
        if assessment_path is not None and assessment_path.is_file()
        else None
    )
    report = build_analysis_report(
        analysis,
        ergonomics,
        risk,
        assessment=assessment,
        generated_at=generated_at,
    )
    _write_json_atomically(output_path, report)
    return report


def build_report_storage_path(user_id: str, analysis_id: str) -> str:
    safe_user_id = _storage_segment(user_id, "user_id")
    safe_analysis_id = _storage_segment(analysis_id, "analysis_id")
    return f"{safe_user_id}/{safe_analysis_id}/results/analysis-report.json"


def build_database_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("report_version") != REPORT_VERSION:
        raise ReportInputInvalidError("Nieobsługiwana wersja analysis-report.json.")
    analysis = _mapping(report.get("analysis"), "analysis")
    risk_summary = _mapping(report.get("risk_summary"), "risk_summary")
    profile = _mapping(risk_summary.get("profile"), "risk_summary.profile")
    key_moments = report.get("key_moments")
    metric_summary = report.get("metric_summary")
    if not isinstance(key_moments, list) or not isinstance(metric_summary, list):
        raise ReportInputInvalidError("Raport nie zawiera poprawnych podsumowań.")

    dominant_zones = risk_summary.get("dominant_zones")
    dominant_metrics = risk_summary.get("dominant_metrics")
    zones = _text_list(dominant_zones)
    metrics = _text_list(dominant_metrics)
    valid_ratio = risk_summary.get("valid_metric_ratio")
    if not isinstance(valid_ratio, (int, float)) or isinstance(valid_ratio, bool):
        raise ReportInputInvalidError("Brak poprawnego valid_metric_ratio w raporcie.")

    return {
        "report_version": REPORT_VERSION,
        "analysis_id": analysis.get("analysis_id"),
        "overall_level": risk_summary.get("overall_level"),
        "insufficient_data": risk_summary.get("insufficient_data") is True,
        "valid_metric_ratio": round(float(valid_ratio), 6),
        "dominant_zone": zones[0] if zones else None,
        "dominant_metric": metrics[0] if metrics else None,
        "key_moments_count": len(key_moments),
        "metric_count": len(metric_summary),
        "profile_status": profile.get("profile_status"),
    }


def upload_report_file(
    storage_client: StorageClientProtocol,
    bucket_name: str,
    local_path: Path,
    storage_path: str,
) -> str:
    if not local_path.is_file() or local_path.stat().st_size <= 0:
        raise ReportUploadError("Plik analysis-report.json jest pusty lub nie istnieje.")
    try:
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
    except Exception as error:
        raise ReportUploadError("Nie udało się przesłać analysis-report.json.") from error
    uploaded_path = str(response.path).strip()
    if uploaded_path != storage_path:
        raise ReportUploadError("Storage zwrócił nieoczekiwaną ścieżkę raportu.")
    return uploaded_path


def upload_result_file(
    storage_client: StorageClientProtocol,
    bucket_name: str,
    local_path: Path,
    storage_path: str,
    content_type: str,
) -> str:
    if not local_path.is_file() or local_path.stat().st_size <= 0:
        raise ReportUploadError("Plik wynikowy jest pusty lub nie istnieje.")
    try:
        with local_path.open("rb") as file_handle:
            response = storage_client.from_(bucket_name).upload(
                path=storage_path,
                file=file_handle,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": "true",
                },
            )
    except Exception as error:
        raise ReportUploadError("Nie udało się przesłać pliku wynikowego.") from error
    uploaded_path = str(response.path).strip()
    if uploaded_path != storage_path:
        raise ReportUploadError("Storage zwrócił nieoczekiwaną ścieżkę pliku.")
    return uploaded_path


def _read_json_object(
    path: Path,
    label: str,
    missing_error: type[ReportEngineError],
) -> dict[str, Any]:
    if not path.is_file():
        raise missing_error(f"Nie znaleziono pliku {label}.")
    if path.stat().st_size <= 0:
        raise ReportInputInvalidError(f"Plik {label} jest pusty.")
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except json.JSONDecodeError as error:
        raise ReportInputInvalidError(
            f"Niepoprawny JSON w pliku {label}: {error.msg}."
        ) from error
    except (OSError, UnicodeError) as error:
        raise ReportInputInvalidError(f"Nie można odczytać pliku {label}.") from error
    if not isinstance(document, dict):
        raise ReportInputInvalidError(f"Plik {label} musi zawierać obiekt JSON.")
    return document


def _write_json_atomically(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _storage_segment(value: str, label: str) -> str:
    segment = str(value).strip()
    if not segment or "/" in segment or "\\" in segment or segment in {".", ".."}:
        raise ReportInputInvalidError(f"Nieprawidłowy segment Storage: {label}.")
    return segment


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReportInputInvalidError(f"Pole {label} musi być obiektem.")
    return value


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]

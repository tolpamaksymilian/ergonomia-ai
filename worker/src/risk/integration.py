"""Storage and database integration helpers for Risk Engine V1.

This module deliberately delegates every classification decision to
``risk.processor.process_risk_document``.  It only validates integration
boundaries, writes files atomically and builds a small database summary.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any, Protocol
from uuid import uuid4

from .processor import RISK_ENGINE_VERSION, process_risk_document
from .profile import load_risk_profile
from .schemas import MetricsValidationError, ProfileValidationError


class RiskIntegrationError(RuntimeError):
    """Base exception carrying a stable worker-facing error code."""

    error_code = "RISK_ENGINE_ERROR"


class RiskInputNotFoundError(RiskIntegrationError):
    error_code = "RISK_INPUT_NOT_FOUND"


class RiskInputInvalidError(RiskIntegrationError):
    error_code = "RISK_INPUT_INVALID"


class RiskProfileNotFoundError(RiskIntegrationError):
    error_code = "RISK_PROFILE_NOT_FOUND"


class RiskProfileInvalidError(RiskIntegrationError):
    error_code = "RISK_PROFILE_INVALID"


class RiskUploadError(RiskIntegrationError):
    error_code = "RISK_UPLOAD_ERROR"


class RiskEngineExecutionError(RiskIntegrationError):
    error_code = "RISK_ENGINE_ERROR"


class RiskAnalysisIdMismatchError(RiskInputInvalidError):
    pass


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


def read_metrics_document(
    path: Path,
    expected_analysis_id: str,
) -> dict[str, Any]:
    document = _read_json_object(path, "ergonomics-metrics.json", profile=False)
    document_analysis_id = document.get("analysis_id")
    if str(document_analysis_id or "").strip() != str(expected_analysis_id).strip():
        raise RiskAnalysisIdMismatchError(
            "analysis_id w ergonomics-metrics.json nie jest zgodne z rekordem analizy."
        )
    return document


def read_profile_document(path: Path) -> dict[str, Any]:
    document = _read_json_object(path, "profil ryzyka", profile=True)
    try:
        profile = load_risk_profile(document)
    except ProfileValidationError as error:
        raise RiskProfileInvalidError(str(error)) from error
    if not profile.profile_version.strip():
        raise RiskProfileInvalidError("Wersja profilu ryzyka nie może być pusta.")
    return document


def process_risk_files_for_analysis(
    metrics_path: Path,
    profile_path: Path,
    output_path: Path,
    expected_analysis_id: str,
) -> dict[str, Any]:
    metrics_document = read_metrics_document(metrics_path, expected_analysis_id)
    profile_document = read_profile_document(profile_path)
    try:
        assessment = process_risk_document(metrics_document, profile_document)
    except MetricsValidationError as error:
        raise RiskInputInvalidError(str(error)) from error
    except ProfileValidationError as error:
        raise RiskProfileInvalidError(str(error)) from error
    except (ArithmeticError, RuntimeError, TypeError, ValueError) as error:
        raise RiskEngineExecutionError(
            "Risk Engine nie ukończył obliczeń dla poprawnie odczytanych danych."
        ) from error
    _write_json_atomically(output_path, assessment)
    return assessment


def build_risk_storage_path(user_id: str, analysis_id: str) -> str:
    safe_user_id = _storage_segment(user_id, "user_id")
    safe_analysis_id = _storage_segment(analysis_id, "analysis_id")
    return f"{safe_user_id}/{safe_analysis_id}/results/risk-assessment.json"


def build_database_summary(assessment: Mapping[str, object]) -> dict[str, object]:
    if assessment.get("risk_engine_version") != RISK_ENGINE_VERSION:
        raise RiskInputInvalidError("Nieobsługiwana wersja dokumentu Risk Engine.")

    profile = _mapping(assessment.get("profile"), "profile")
    data_quality = _mapping(assessment.get("data_quality"), "data_quality")
    overall = _mapping(assessment.get("overall"), "overall")
    metrics = _mapping(assessment.get("metrics"), "metrics")
    key_frames = assessment.get("key_frames")
    if not isinstance(key_frames, list):
        raise RiskInputInvalidError("risk-assessment.json nie zawiera tablicy key_frames.")

    overall_level = _risk_level(overall.get("overall_level"))
    coverage = _ratio(data_quality.get("valid_metric_coverage"), "valid_metric_coverage")
    frame_count = _non_negative_integer(data_quality.get("frame_count"), "frame_count")
    enabled_metric_count = _non_negative_integer(
        data_quality.get("enabled_metric_count"),
        "enabled_metric_count",
    )

    dominant_metrics: list[dict[str, object]] = []
    severity = {"critical": 4, "high": 3, "moderate": 2, "low": 1}
    for name, raw_summary in metrics.items():
        if not isinstance(name, str) or not isinstance(raw_summary, Mapping):
            continue
        level = raw_summary.get("final_level")
        if level not in severity:
            continue
        weighted_score = _finite_number(raw_summary.get("weighted_score"))
        dominant_metrics.append(
            {
                "metric_name": name,
                "level": level,
                "weighted_score": weighted_score,
            }
        )
    dominant_metrics.sort(
        key=lambda item: (
            severity[str(item["level"])],
            float(item["weighted_score"] or 0.0),
        ),
        reverse=True,
    )

    timestamps = [
        timestamp
        for frame in key_frames
        if isinstance(frame, Mapping)
        and (timestamp := _finite_number(frame.get("timestamp_seconds"))) is not None
    ]

    return {
        "risk_engine_version": RISK_ENGINE_VERSION,
        "profile": {
            "profile_id": _non_empty_text(profile.get("profile_id"), "profile_id"),
            "profile_name": _non_empty_text(profile.get("profile_name"), "profile_name"),
            "profile_version": _non_empty_text(
                profile.get("profile_version"),
                "profile_version",
            ),
            "status": _profile_status(profile.get("status")),
            "normative_method": profile.get("normative_method"),
        },
        "overall_level": overall_level,
        "overall_score": _finite_number(overall.get("overall_score")),
        "data_coverage": _ratio(overall.get("data_coverage"), "data_coverage"),
        "valid_metric_ratio": coverage,
        "frame_count": frame_count,
        "enabled_metric_count": enabled_metric_count,
        "evaluated_zones": _text_list(overall.get("evaluated_zones")),
        "insufficient_zones": _text_list(overall.get("insufficient_zones")),
        "highest_risk_zones": _text_list(overall.get("highest_risk_zones")),
        "decision_reasons": _text_list(overall.get("decision_reasons")),
        "dominant_metrics": dominant_metrics[:5],
        "key_frames_count": len(key_frames),
        "key_frame_timestamps_seconds": [round(value, 6) for value in timestamps[:10]],
        "insufficient_data": overall_level == "insufficient_data",
    }


def upload_risk_file(
    storage_client: StorageClientProtocol,
    bucket_name: str,
    local_path: Path,
    storage_path: str,
) -> str:
    if not local_path.is_file() or local_path.stat().st_size <= 0:
        raise RiskUploadError("Plik risk-assessment.json jest pusty lub nie istnieje.")
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
        raise RiskUploadError("Nie udało się przesłać wyniku Risk Engine.") from error
    uploaded_path = str(response.path).strip()
    if uploaded_path != storage_path:
        raise RiskUploadError("Storage zwrócił nieoczekiwaną ścieżkę wyniku ryzyka.")
    return uploaded_path


def _read_json_object(path: Path, label: str, *, profile: bool) -> dict[str, Any]:
    not_found_error = RiskProfileNotFoundError if profile else RiskInputNotFoundError
    invalid_error = RiskProfileInvalidError if profile else RiskInputInvalidError
    if not path.is_file():
        raise not_found_error(f"Nie znaleziono pliku: {label}.")
    if path.stat().st_size <= 0:
        raise invalid_error(f"Plik {label} jest pusty.")
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, UnicodeError) as error:
        raise invalid_error(f"Nie można odczytać pliku {label}.") from error
    except json.JSONDecodeError as error:
        raise invalid_error(f"Niepoprawny JSON w pliku {label}: {error.msg}.") from error
    if not isinstance(document, dict):
        raise invalid_error(f"Plik {label} musi zawierać obiekt JSON.")
    return document


def _write_json_atomically(path: Path, document: Mapping[str, object]) -> None:
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
        raise RiskIntegrationError(f"Nieprawidłowy segment Storage: {label}.")
    return segment


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RiskInputInvalidError(f"Pole {label} musi być obiektem.")
    return value


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _ratio(value: object, label: str) -> float:
    numeric = _finite_number(value)
    if numeric is None or not 0.0 <= numeric <= 1.0:
        raise RiskInputInvalidError(f"Pole {label} musi być liczbą od 0 do 1.")
    return round(numeric, 6)


def _non_negative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RiskInputInvalidError(f"Pole {label} musi być nieujemną liczbą całkowitą.")
    return value


def _non_empty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RiskInputInvalidError(f"Pole {label} nie może być puste.")
    return value.strip()


def _risk_level(value: object) -> str:
    if value not in {"low", "moderate", "high", "critical", "insufficient_data"}:
        raise RiskInputInvalidError("Nieznany ogólny poziom ryzyka.")
    return str(value)


def _profile_status(value: object) -> str:
    if value not in {"development", "draft", "approved", "archived"}:
        raise RiskInputInvalidError("Nieznany status profilu ryzyka.")
    return str(value)


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]

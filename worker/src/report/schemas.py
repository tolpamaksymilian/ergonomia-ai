"""Dependency-free contracts and validation for Report Engine V2."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


REPORT_SCHEMA_VERSION = "2.0"
REPORT_VERSION = "analysis-report-v2.0-beta.1"
SUPPORTED_ERGONOMICS_SCHEMA_VERSIONS = frozenset({"1.0"})
SUPPORTED_ERGONOMICS_VERSIONS = frozenset({"ergonomics-metrics-v1.0"})
SUPPORTED_RISK_SCHEMA_VERSIONS = frozenset({"1.0"})
SUPPORTED_RISK_VERSIONS = frozenset({"risk-engine-v1.0"})
RISK_LEVELS = frozenset(
    {"low", "moderate", "high", "critical", "insufficient_data"}
)
PROFILE_STATUSES = frozenset({"development", "draft", "approved", "archived"})


class ReportEngineError(ValueError):
    """Base deterministic Report Engine error with a stable worker code."""

    error_code = "REPORT_BUILD_ERROR"


class ReportInputMissingError(ReportEngineError):
    error_code = "REPORT_INPUT_MISSING"


class ReportErgonomicsInputMissingError(ReportInputMissingError):
    error_code = "REPORT_ERGONOMICS_INPUT_MISSING"


class ReportRiskInputMissingError(ReportInputMissingError):
    error_code = "REPORT_RISK_INPUT_MISSING"


class ReportInputInvalidError(ReportEngineError):
    error_code = "REPORT_INPUT_INVALID"


class ReportVersionUnsupportedError(ReportInputInvalidError):
    error_code = "REPORT_VERSION_UNSUPPORTED"


class ReportAnalysisMismatchError(ReportInputInvalidError):
    pass


class ReportUploadError(ReportEngineError):
    error_code = "REPORT_UPLOAD_ERROR"


def validate_report_inputs(
    analysis: Mapping[str, Any],
    ergonomics: Mapping[str, Any],
    risk: Mapping[str, Any],
) -> str:
    analysis_id = required_text(analysis.get("id"), "analysis.id")
    required_text(analysis.get("title"), "analysis.title")

    ergonomics_schema = ergonomics.get("schema_version")
    if ergonomics_schema not in SUPPORTED_ERGONOMICS_SCHEMA_VERSIONS:
        raise ReportVersionUnsupportedError(
            f"Nieobsługiwana schema_version ergonomics: {ergonomics_schema!r}."
        )
    ergonomics_version = ergonomics.get("metrics_version")
    if ergonomics_version not in SUPPORTED_ERGONOMICS_VERSIONS:
        raise ReportVersionUnsupportedError(
            f"Nieobsługiwana metrics_version: {ergonomics_version!r}."
        )
    _matching_analysis_id(ergonomics, analysis_id, "ergonomics-metrics.json")
    frames = ergonomics.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ReportInputInvalidError(
            "ergonomics-metrics.json musi zawierać niepustą tablicę frames."
        )
    if not isinstance(ergonomics.get("summary"), Mapping):
        raise ReportInputInvalidError(
            "ergonomics-metrics.json musi zawierać obiekt summary."
        )

    risk_schema = risk.get("schema_version")
    if risk_schema not in SUPPORTED_RISK_SCHEMA_VERSIONS:
        raise ReportVersionUnsupportedError(
            f"Nieobsługiwana schema_version risk: {risk_schema!r}."
        )
    risk_version = risk.get("risk_engine_version")
    if risk_version not in SUPPORTED_RISK_VERSIONS:
        raise ReportVersionUnsupportedError(
            f"Nieobsługiwana risk_engine_version: {risk_version!r}."
        )
    _matching_analysis_id(risk, analysis_id, "risk-assessment.json")
    if risk.get("source_metrics_version") != ergonomics_version:
        raise ReportVersionUnsupportedError(
            "risk-assessment.json odwołuje się do innej wersji metryk."
        )

    profile = required_mapping(risk.get("profile"), "risk.profile")
    required_text(profile.get("profile_id"), "risk.profile.profile_id")
    required_text(profile.get("profile_name"), "risk.profile.profile_name")
    required_text(profile.get("profile_version"), "risk.profile.profile_version")
    if profile.get("status") not in PROFILE_STATUSES:
        raise ReportInputInvalidError("Nieobsługiwany status profilu ryzyka.")

    overall = required_mapping(risk.get("overall"), "risk.overall")
    if overall.get("overall_level") not in RISK_LEVELS:
        raise ReportInputInvalidError("Nieobsługiwany ogólny poziom ryzyka.")
    ratio(overall.get("data_coverage"), "risk.overall.data_coverage")

    data_quality = required_mapping(risk.get("data_quality"), "risk.data_quality")
    frame_count = non_negative_integer(
        data_quality.get("frame_count"), "risk.data_quality.frame_count"
    )
    if frame_count != len(frames):
        raise ReportInputInvalidError(
            "Liczba klatek Risk Engine nie odpowiada ergonomics-metrics.json."
        )
    ratio(
        data_quality.get("valid_metric_coverage"),
        "risk.data_quality.valid_metric_coverage",
    )

    required_mapping(risk.get("zones"), "risk.zones")
    required_mapping(risk.get("metrics"), "risk.metrics")
    if not isinstance(risk.get("key_frames"), list):
        raise ReportInputInvalidError("risk.key_frames musi być tablicą.")
    return analysis_id


def required_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReportInputInvalidError(f"Pole {label} musi być obiektem.")
    return value


def required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportInputInvalidError(f"Pole {label} nie może być puste.")
    return value.strip()


def finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def ratio(value: object, label: str) -> float:
    numeric = finite_number(value)
    if numeric is None or not 0.0 <= numeric <= 1.0:
        raise ReportInputInvalidError(f"Pole {label} musi być liczbą od 0 do 1.")
    return round(numeric, 6)


def non_negative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReportInputInvalidError(
            f"Pole {label} musi być nieujemną liczbą całkowitą."
        )
    return value


def optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _matching_analysis_id(
    document: Mapping[str, Any],
    expected_analysis_id: str,
    label: str,
) -> None:
    document_analysis_id = document.get("analysis_id")
    if not isinstance(document_analysis_id, str) or document_analysis_id.strip() != expected_analysis_id:
        raise ReportAnalysisMismatchError(
            f"analysis_id w {label} nie odpowiada rekordowi analizy."
        )

"""Top-level deterministic company-method assessment."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any

from .chemical import evaluate_chemical
from .measurable import add_months, evaluate_measurable_factor
from .owas import evaluate_owas
from .risk_score import evaluate_risk_score
from .specs import load_spec

COMPANY_METHODS_VERSION = "company-methods-v1.2-beta.1"


def process_company_methods(
    pose_document: Mapping[str, Any] | None,
    ergonomics_document: Mapping[str, Any],
    manual_inputs: Mapping[str, Any] | None = None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    inputs = manual_inputs or {}
    analysis_id = ergonomics_document.get("analysis_id")
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise ValueError("ergonomics-metrics.json does not contain analysis_id")
    measurable_inputs = inputs.get("measurable_factors")
    measurable = [_measurable_result(item) for item in measurable_inputs if isinstance(item, Mapping)] if isinstance(measurable_inputs, list) else []
    owas = evaluate_owas(pose_document, ergonomics_document, _as_mapping(inputs.get("owas")))
    risk_score = evaluate_risk_score(_as_mapping(inputs.get("risk_score")))
    chemical = evaluate_chemical(_as_mapping(inputs.get("chemical")))
    missing = [*owas["missing_inputs"], *risk_score["missing_inputs"]]
    return {
        "schema_version": "1.0", "generated_by": "Ergonomia AI Company Methods Engine",
        "company_methods_version": COMPANY_METHODS_VERSION, "analysis_id": analysis_id,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source": {"pose_version": _as_mapping(pose_document).get("pose_version"), "metrics_version": ergonomics_document.get("metrics_version"), "method_specs_sha256": load_spec("manifest")["source_workbook_sha256"]},
        "configuration": {"absolute_video_measurements_enabled": False, "chemical_automatic_scoring_enabled": False},
        "owas": owas, "risk_score": risk_score, "measurable_factors": measurable, "chemical": chemical,
        "missing_inputs": sorted(set(missing)),
        "evidence_sources": load_spec("manifest")["rules"]["evidence_sources"],
        "limitations": ["2d_video_analysis", "unknown_values_are_not_zero", "manual_values_require_user_confirmation", "chemical_requires_IN.06.13"],
    }


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _measurable_result(inputs: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_measurable_factor(inputs)
    result["label"] = inputs.get("label")
    updated_at = inputs.get("updated_at")
    result["updated_at"] = updated_at if isinstance(updated_at, str) else None
    try:
        parsed = date.fromisoformat(updated_at) if isinstance(updated_at, str) else None
    except ValueError:
        parsed = None
    result["valid_until"] = add_months(parsed).isoformat() if parsed else None
    if updated_at and parsed is None:
        result.setdefault("missing_inputs", []).append("valid_updated_at")
    return result

"""Manual/contextual Risk Score using workbook-confirmed scales."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schemas import CompanyMethodsError, finite_number
from .specs import load_spec


def evaluate_risk_score(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    spec = load_spec("risk-score")
    source = inputs or {}
    context = {name: source.get(name) for name in ("activity", "hazard_source", "hazard", "effect", "controls", "psif_sif", "factor_type", "work_type")}
    factors = {}
    for name in ("exposure", "severity", "probability"):
        selected = source.get(name)
        options = spec["thresholds"][name]
        match = next((item for item in options if item["id"] == selected), None)
        factors[name] = match
    if any(value is None for value in factors.values()):
        return {
            "method_id": spec["method_id"], "status": "REQUIRES_DATA", "formula_status": "NORMALIZED_INTERPRETATION",
            "value": None, "category": None, "action": None, "acceptability": None,
            "missing_inputs": [name for name, value in factors.items() if value is None],
            "context": context,
            "trace": ["SOURCE_FORMULA_MISSING", "normalized_formula_not_executed_without_all_factors"],
        }
    value = factors["exposure"]["value"] * factors["severity"]["value"] * factors["probability"]["value"]
    band = next((item for item in spec["thresholds"]["risk_bands"] if _matches(value, item)), None)
    if band is None:
        raise CompanyMethodsError("Risk Score value does not match any source band")
    return {
        "method_id": spec["method_id"], "status": "MANUAL", "formula_status": "NORMALIZED_INTERPRETATION",
        "value": round(float(value), 6), "category": band["category"], "action": band["action"],
        "acceptability": band["acceptability"], "factors": factors, "missing_inputs": [],
        "context": context,
        "trace": ["form_ Risk_Score!J5:AH8", "form_ Risk_Score!AJ6:AL20", "SOURCE_FORMULA_MISSING"],
    }


def _matches(value: float, band: Mapping[str, Any]) -> bool:
    maximum = finite_number(band.get("maximum"))
    minimum_exclusive = finite_number(band.get("minimum_exclusive"))
    return (maximum is None or value <= maximum) and (minimum_exclusive is None or value > minimum_exclusive)

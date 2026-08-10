"""Partial manual chemical-inhalation record; no missing IN.06.13 scoring."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .specs import load_spec


def evaluate_chemical(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    spec = load_spec("chemical-inhalation")
    source = dict(inputs or {})
    if not source:
        return {"method_id": spec["method_id"], "status": "REQUIRES_DATA", "automatic_scoring_enabled": False, "missing_inputs": ["substance_name", "manufacturer", "h_statements"], "limitation": "IN.06.13_NOT_INCLUDED"}
    safe = source.get("classified_safe") is True
    return {
        "method_id": spec["method_id"], "status": "MANUAL" if safe else "PARTIAL",
        "automatic_scoring_enabled": False, "classified_safe": safe, "inputs": source,
        "risk_level": source.get("risk_level"), "residual_risk_level": source.get("residual_risk_level"),
        "missing_inputs": [] if safe else ["IN.06.13"], "limitation": "IN.06.13_NOT_INCLUDED",
        "trace": ["form_chemia!A4", "form_chemia!B4", "form_chemia!C4", "form_chemia!E4"],
    }

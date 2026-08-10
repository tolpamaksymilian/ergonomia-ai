"""Stable contracts shared by the company-method evaluators."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

EVIDENCE_SOURCES = frozenset(
    {"VIDEO_DERIVED", "USER_PROVIDED", "MEASUREMENT", "WORKBOOK_RULE", "UNKNOWN"}
)
METHOD_STATUSES = frozenset(
    {"AUTOMATIC", "PARTIAL", "REQUIRES_DATA", "MANUAL", "UNAVAILABLE", "SOURCE_ERROR"}
)


class CompanyMethodsError(ValueError):
    """Deterministic company-method failure."""


def finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def evidence(value: object, source: str, *, quality: object = None, reason: str | None = None) -> dict[str, Any]:
    if source not in EVIDENCE_SOURCES:
        raise CompanyMethodsError(f"Unsupported evidence source: {source}")
    number = finite_number(quality)
    return {
        "value": value,
        "source": source,
        "quality": round(max(0.0, min(1.0, number)), 6) if number is not None else None,
        "known": source != "UNKNOWN" and value is not None,
        "reason": reason,
    }


def mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []

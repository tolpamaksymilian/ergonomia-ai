"""Measured-factor classification with exact workbook boundaries."""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from datetime import date
from typing import Any

from .schemas import finite_number
from .specs import load_spec


def evaluate_measurable_factor(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    spec = load_spec("measurable-factors")
    source = inputs or {}
    measured = finite_number(source.get("measurement"))
    limit = finite_number(source.get("limit"))
    if measured is None or limit is None or limit <= 0 or measured < 0:
        return {"method_id": spec["method_id"], "status": "REQUIRES_DATA", "level": None, "label": None, "acceptability": None, "ratio": None, "missing_inputs": [name for name, value in (("measurement", measured), ("limit", limit)) if value is None]}
    ratio = measured / limit
    if measured > limit:
        level, label, acceptability = "large", "Duże", "Niedopuszczalne"
    elif measured >= 0.5 * limit:
        level, label, acceptability = "medium", "Średnie", "Dopuszczalne"
    else:
        level, label, acceptability = "small", "Małe", "Dopuszczalne"
    return {"method_id": spec["method_id"], "status": "MANUAL", "level": level, "label": label, "acceptability": acceptability, "ratio": round(ratio, 6), "missing_inputs": [], "trace": ["form czynniki mierzalne!I6:I14"]}


def add_months(value: date, months: int = 60) -> date:
    total = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))

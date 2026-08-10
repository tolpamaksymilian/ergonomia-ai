"""Versioned method-spec loader with repository-local path resolution."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import CompanyMethodsError

SPEC_ROOT = Path(__file__).resolve().parents[3] / "method-specs"
ALLOWED_SPECS = frozenset(
    {"manifest", "hazards", "risk-score", "measurable-factors", "owas", "ejms", "chemical-inhalation", "source-anomalies"}
)


@lru_cache(maxsize=None)
def load_spec(name: str) -> dict[str, Any]:
    if name not in ALLOWED_SPECS:
        raise CompanyMethodsError(f"Unknown method spec: {name}")
    path = SPEC_ROOT / f"{name}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompanyMethodsError(f"Cannot read method spec {path.name}") from error
    if not isinstance(document, dict) or not isinstance(document.get("version"), str):
        raise CompanyMethodsError(f"Invalid method spec {path.name}")
    return document

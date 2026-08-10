from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from worker.src.company_methods.chemical import evaluate_chemical
from worker.src.company_methods.measurable import add_months, evaluate_measurable_factor
from worker.src.company_methods.risk_score import evaluate_risk_score
from worker.src.company_methods.specs import load_spec

GOLDEN = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "company-methods-golden.json").read_text(encoding="utf-8"))


def test_manifest_records_expected_workbook_hash():
    assert load_spec("manifest")["source_workbook_sha256"] == "78fa02ed3be7d46c1aaab772c556a7e7e56867f7566c825ed84f3eef02be5eca"


@pytest.mark.parametrize(
    ("ratio", "level", "acceptability"),
    [(0.4999, "small", "Dopuszczalne"), (0.5, "medium", "Dopuszczalne"), (1.0, "medium", "Dopuszczalne"), (1.0001, "large", "Niedopuszczalne")],
)
def test_measurable_factor_exact_boundaries(ratio, level, acceptability):
    result = evaluate_measurable_factor({"measurement": ratio * 100, "limit": 100})
    assert result["level"] == level
    assert result["acceptability"] == acceptability


def test_document_expiry_adds_sixty_calendar_months():
    assert add_months(date(2025, 4, 17)) == date(2030, 4, 17)
    assert add_months(date(2024, 2, 29)) == date(2029, 2, 28)


@pytest.mark.parametrize(
    ("exposure", "severity", "probability", "category"),
    [("negligible", "first_aid", "theoretical", "Pomijalne"), ("constant", "serious_injury", "very_likely", "Bardzo wysokie ryzyko")],
)
def test_risk_score_normalized_interpretation(exposure, severity, probability, category):
    result = evaluate_risk_score({"exposure": exposure, "severity": severity, "probability": probability})
    assert result["category"] == category
    assert result["formula_status"] == "NORMALIZED_INTERPRETATION"
    assert "SOURCE_FORMULA_MISSING" in result["trace"]


def test_risk_score_requires_all_manual_factors():
    result = evaluate_risk_score({"exposure": "minimal"})
    assert result["status"] == "REQUIRES_DATA"
    assert set(result["missing_inputs"]) == {"severity", "probability"}


def test_chemical_module_never_invents_in_06_13_scoring():
    result = evaluate_chemical({"substance_name": "test", "h_statements": ["H000"]})
    assert result["status"] == "PARTIAL"
    assert result["automatic_scoring_enabled"] is False
    assert result["limitation"] == "IN.06.13_NOT_INCLUDED"


def test_python_matches_cross_language_golden_fixture():
    risk = evaluate_risk_score(GOLDEN["risk_score"]["input"])
    assert risk["value"] == GOLDEN["risk_score"]["expected"]["value"]
    assert risk["category"] == GOLDEN["risk_score"]["expected"]["category"]
    for case in GOLDEN["measurable"]:
        assert evaluate_measurable_factor(case)["level"] == case["level"]

from __future__ import annotations

import copy

import pytest

from worker.src.risk.profile import load_risk_profile, select_band
from worker.src.risk.schemas import ProfileValidationError


def test_valid_profile(risk_profile_document):
    profile = load_risk_profile(risk_profile_document)
    assert profile.profile_id == "test-only-risk-profile-v1"
    assert len(profile.metrics) == 14


def test_unsupported_profile_version(risk_profile_document):
    risk_profile_document["schema_version"] = "9.0"
    with pytest.raises(ProfileValidationError, match="schema_version"):
        load_risk_profile(risk_profile_document)


def test_overlapping_bands(risk_profile_document):
    bands = risk_profile_document["metrics"]["trunk_inclination_deg"]["bands"]
    bands[0]["maximum"] = 25
    with pytest.raises(ProfileValidationError, match="Nakładające"):
        load_risk_profile(risk_profile_document)


def test_gap_between_bands(risk_profile_document):
    bands = risk_profile_document["metrics"]["trunk_inclination_deg"]["bands"]
    bands[0]["maximum"] = 15
    with pytest.raises(ProfileValidationError, match="Luka"):
        load_risk_profile(risk_profile_document)


def test_negative_weight(risk_profile_document):
    risk_profile_document["metrics"]["trunk_inclination_deg"]["weight"] = -0.1
    with pytest.raises(ProfileValidationError, match="ujemne"):
        load_risk_profile(risk_profile_document)


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_minimum_valid_ratio_outside_range(risk_profile_document, value):
    risk_profile_document["metrics"]["trunk_inclination_deg"][
        "minimum_valid_ratio"
    ] = value
    with pytest.raises(ProfileValidationError, match="minimum_valid_ratio"):
        load_risk_profile(risk_profile_document)


def test_unknown_direction(risk_profile_document):
    risk_profile_document["metrics"]["trunk_inclination_deg"][
        "direction"
    ] = "sideways"
    with pytest.raises(ProfileValidationError, match="direction"):
        load_risk_profile(risk_profile_document)


def test_unknown_level(risk_profile_document):
    risk_profile_document["metrics"]["trunk_inclination_deg"]["bands"][0][
        "level"
    ] = "safe"
    with pytest.raises(ProfileValidationError, match="level"):
        load_risk_profile(risk_profile_document)


def test_outside_range_requires_preferred_range(risk_profile_document):
    del risk_profile_document["metrics"]["left_elbow_flexion_deg"][
        "preferred_range"
    ]
    with pytest.raises(ProfileValidationError, match="preferred_range"):
        load_risk_profile(risk_profile_document)


def test_duplicate_band_range(risk_profile_document):
    bands = risk_profile_document["metrics"]["trunk_inclination_deg"]["bands"]
    bands[1] = copy.deepcopy(bands[0])
    with pytest.raises(ProfileValidationError):
        load_risk_profile(risk_profile_document)


def test_higher_is_worse_selection(risk_profile_document):
    metric = load_risk_profile(risk_profile_document).metrics[
        "trunk_inclination_deg"
    ]
    assert select_band(metric, 45).level == "high"


def test_lower_is_worse_selection(risk_profile_document):
    metric = load_risk_profile(risk_profile_document).metrics[
        "left_pinch_distance_ratio"
    ]
    assert select_band(metric, 0.05).level == "critical"
    assert select_band(metric, 0.5).level == "low"


def test_outside_range_selection(risk_profile_document):
    metric = load_risk_profile(risk_profile_document).metrics[
        "left_elbow_flexion_deg"
    ]
    assert select_band(metric, 90).level == "low"
    assert select_band(metric, 175).level == "critical"


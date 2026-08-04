from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def risk_profile_document() -> dict[str, Any]:
    with (FIXTURES / "risk-profile-test.json").open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def metrics_document() -> dict[str, Any]:
    with (FIXTURES / "ergonomics-metrics-test.json").open(encoding="utf-8") as handle:
        document = json.load(handle)
    template = copy.deepcopy(document["frames"][0])
    document["frames"] = []
    for index in range(6):
        frame = copy.deepcopy(template)
        frame.update(
            source_frame_index=index,
            output_frame_index=index,
            timestamp=index * 0.5,
        )
        document["frames"].append(frame)
    return document

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from worker.src.risk.processor import process_risk_document


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def ergonomics_document():
    return json.loads(
        (FIXTURES / "ergonomics-metrics-test.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def risk_document(ergonomics_document):
    profile = json.loads(
        (FIXTURES / "risk-profile-test.json").read_text(encoding="utf-8")
    )
    return process_risk_document(copy.deepcopy(ergonomics_document), profile)


@pytest.fixture
def analysis_metadata():
    return {
        "id": "risk-engine-fixture-analysis",
        "user_id": "must-not-be-exported",
        "title": "Test stanowiska montażowego",
        "created_at": "2026-08-06T10:00:00+00:00",
        "source_file_name": "stanowisko.mp4",
        "source_duration_seconds": 8.5,
        "source_width": 1920,
        "source_height": 1080,
        "pose_quality_version": "pose-pipeline-v3.0",
        "pose_processed_frames": 2,
        "pose_detected_frames": 2,
        "pose_presence_ratio": 1.0,
    }

from __future__ import annotations

import importlib.util
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _load_compare_module():
    spec = importlib.util.spec_from_file_location(
        "compare_pose_runs_test", TOOLS / "compare_pose_runs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_tool_reports_technical_delta_without_accuracy_claim():
    module = _load_compare_module()
    baseline = {
        "worker_version": "0.3",
        "tracking": {"track_loss_count": 3},
        "runtime_seconds": 10.0,
    }
    candidate = {
        "worker_version": "0.4",
        "tracking": {"track_loss_count": 1},
        "runtime_seconds": 12.0,
    }
    result = module.compare_diagnostics(baseline, candidate)
    assert result["accuracy_claimed"] is False
    losses = next(
        item for item in result["metrics"]
        if item["field"] == "tracking.track_loss_count"
    )
    assert losses["delta"] == -2.0


def test_compare_tool_preserves_warning_lists():
    module = _load_compare_module()
    baseline = {"quality": {"warning_codes": ["EXCESSIVE_TRACK_LOSS"]}}
    candidate = {"quality": {"warning_codes": ["HIGH_MOTION_BLUR"]}}
    result = module.compare_diagnostics(baseline, candidate)
    assert result["baseline_warnings"] == ["EXCESSIVE_TRACK_LOSS"]
    assert result["candidate_warnings"] == ["HIGH_MOTION_BLUR"]

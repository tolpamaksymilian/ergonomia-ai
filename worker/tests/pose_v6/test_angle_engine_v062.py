from __future__ import annotations

import numpy as np

from worker.src.pose_v6.angle_engine import ANGLE_DEPENDENCIES, safe_vector_angle_degrees, stabilize_angle_sequence
from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame


def _temporal() -> TemporalFrame:
    points = np.ones((23, 2), dtype=np.float32)
    scores = np.full(23, 0.9, dtype=np.float32)
    return TemporalFrame(points.copy(), scores.copy(), points.copy(), scores.copy(), tuple([PointSource.MEASURED] * 23), np.ones(23, dtype=bool), np.zeros(23, dtype=np.float32), np.full(23, np.nan, dtype=np.float32))


def _metrics(value: float) -> dict[str, dict[str, object]]:
    return {
        name: {"value": value, "valid": True, "quality": 0.9, "source_points": [], "rejection_reason": None}
        for name in ANGLE_DEPENDENCIES
    }


def test_safe_vector_angle_has_no_nan_for_zero_vector() -> None:
    assert safe_vector_angle_degrees(np.zeros(2), np.ones(2)) is None


def test_isolated_angle_glitch_is_reconstructed() -> None:
    frames = [_metrics(value) for value in (20, 23, 147, 25, 27)]
    result = stabilize_angle_sequence(frames, [_temporal()] * 5, [0, .1, .2, .3, .4], ["STABLE"] * 5)
    assert result.metric_frames[2]["left_elbow_flexion_deg"]["value"] == pytest.approx(24.0)
    assert result.summary["angle_outlier_count"] == len(ANGLE_DEPENDENCIES)
    assert result.diagnostics[2]["left_elbow_flexion_deg"]["provenance"] == "MIXED_RECONSTRUCTED"


def test_real_fast_monotonic_angle_change_is_preserved() -> None:
    frames = [_metrics(value) for value in (20, 35, 65, 95, 120)]
    result = stabilize_angle_sequence(frames, [_temporal()] * 5, [0, .1, .2, .3, .4], ["FAST_MOTION"] * 5)
    assert result.metric_frames[2]["trunk_inclination_deg"]["value"] == 65
    assert result.summary["angle_outlier_count"] == 0


def test_reconstructed_source_has_mixed_provenance() -> None:
    frame = _temporal()
    sources = list(frame.sources); sources[7] = PointSource.KINEMATIC_RECONSTRUCTED
    frame = TemporalFrame(frame.analysis_points, frame.analysis_scores, frame.render_points, frame.render_scores, tuple(sources), frame.analysis_usable, frame.prediction_age_seconds, frame.flow_errors)
    result = stabilize_angle_sequence([_metrics(40)], [frame], [0], ["STABLE"])
    assert result.diagnostics[0]["left_elbow_flexion_deg"]["provenance"] == "MIXED_RECONSTRUCTED"


def test_angle_confidence_exposes_temporal_stability_without_hiding_motion() -> None:
    frames = [_metrics(value) for value in (20, 22, 80)]
    result = stabilize_angle_sequence(frames, [_temporal()] * 3, [0, .1, .2], ["FAST_MOTION"] * 3)
    stable = result.diagnostics[0]["trunk_inclination_deg"]
    transition = result.diagnostics[1]["trunk_inclination_deg"]
    assert 0.0 <= transition["temporal_stability"] < stable["temporal_stability"] <= 1.0
    assert transition["confidence"] < stable["confidence"]
    assert result.metric_frames[1]["trunk_inclination_deg"]["value"] == 22


def test_angle_v3_reports_robust_uncertainty_without_3d_claim() -> None:
    frames = [_metrics(value) for value in (55, 72, 94)]
    result = stabilize_angle_sequence(
        frames, [_temporal()] * 3, [0, .05, .1], ["FAST_MOTION"] * 3,
    )
    diagnostic = result.diagnostics[1]["left_elbow_flexion_deg"]
    assert diagnostic["angle_uncertainty_degrees"] > 10.0
    assert diagnostic["pass_ensemble_uncertainty_available"] is False
    assert result.summary["angle_engine_version"] == "angle-engine-v3.0"
    assert result.summary["full_3d_anatomical_angle_claimed"] is False


import pytest

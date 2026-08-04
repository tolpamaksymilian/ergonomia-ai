from __future__ import annotations

import pytest

from worker.src.risk.exposure import (
    calculate_exposure,
    cumulative_exposure_ratio,
    longest_sequence_seconds,
    resolve_frame_timing,
)


def test_variable_timestamps_are_used():
    frames = [{"timestamp": value} for value in (0.0, 0.1, 0.4, 1.0)]
    timing = resolve_frame_timing(frames, 30)
    assert timing.method == "timestamps"
    assert timing.durations_seconds == pytest.approx((0.1, 0.3, 0.6, 0.3))


def test_invalid_timestamps_fall_back_to_fps():
    frames = [{"timestamp": 0.0}, {"timestamp": 0.0}, {"timestamp": None}]
    timing = resolve_frame_timing(frames, 20)
    assert timing.method == "fps_fallback"
    assert timing.fallback_used is True
    assert timing.durations_seconds == pytest.approx((0.05, 0.05, 0.05))


def test_missing_timestamps_and_fps_are_explicit():
    timing = resolve_frame_timing([{}, {}])
    assert timing.method == "unavailable"
    assert timing.fallback_reason == "timestamps_and_fps_unavailable"
    assert timing.durations_seconds == (0.0, 0.0)


def test_exposure_ratio_excludes_invalid_frames():
    timing = resolve_frame_timing(
        [{"timestamp": 0.0}, {"timestamp": 1.0}, {"timestamp": 2.0}]
    )
    exposure = calculate_exposure(
        ["high", "insufficient_data", "low"],
        [True, False, True],
        timing,
    )
    assert exposure["high_exposure_ratio"] == pytest.approx(0.5)
    assert exposure["total_valid_duration_seconds"] == pytest.approx(2.0)


def test_longest_high_sequence():
    timing = resolve_frame_timing(
        [{"timestamp": float(index)} for index in range(5)]
    )
    result = longest_sequence_seconds(
        ["low", "high", "high", "low", "high"],
        [True] * 5,
        timing,
        "high",
    )
    assert result == pytest.approx(2.0)


def test_cumulative_exposure_includes_more_severe_levels():
    timing = resolve_frame_timing(
        [{"timestamp": float(index)} for index in range(4)]
    )
    ratio = cumulative_exposure_ratio(
        ["moderate", "high", "critical", "low"],
        [True] * 4,
        timing,
        "high",
    )
    assert ratio == pytest.approx(0.5)

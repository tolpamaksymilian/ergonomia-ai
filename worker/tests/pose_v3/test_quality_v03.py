from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v3.quality import (
    FrameQualityState,
    ImageQuality,
    analyze_image_quality,
    build_frame_quality,
    summarize_quality,
)


@pytest.mark.parametrize(
    ("value", "under", "over"),
    [(5, True, False), (250, False, True), (128, False, False)],
)
def test_exposure_flags(value, under, over):
    frame = np.full((120, 160, 3), value, dtype=np.uint8)
    quality = analyze_image_quality(frame)
    assert quality.underexposed is under
    assert quality.overexposed is over


def test_flat_image_is_reported_as_blurry():
    quality = analyze_image_quality(np.full((100, 100, 3), 127, dtype=np.uint8))
    assert quality.blurry is True


@pytest.mark.parametrize(
    ("body", "state"),
    [(0.95, FrameQualityState.GOOD), (0.60, FrameQualityState.ACCEPTABLE), (0.25, FrameQualityState.POOR)],
)
def test_frame_quality_states_follow_components(body, state):
    image = ImageQuality(1.0, 1.0, False, False, False)
    result = build_frame_quality(
        image,
        body_quality=body,
        left_hand_quality=body,
        right_hand_quality=body,
        tracking_state="TRACKED",
        out_of_frame=False,
    )
    assert result.state == state


def test_lost_track_is_invalid_even_with_good_image():
    image = ImageQuality(1.0, 1.0, False, False, False)
    result = build_frame_quality(
        image,
        body_quality=0.0,
        left_hand_quality=0.0,
        right_hand_quality=0.0,
        tracking_state="LOST",
        out_of_frame=False,
    )
    assert result.state == FrameQualityState.INVALID


def test_motion_blur_reason_is_explicit():
    image = ImageQuality(0.3, 0.9, False, False, True, motion_blur=True)
    result = build_frame_quality(
        image,
        body_quality=0.8,
        left_hand_quality=0.0,
        right_hand_quality=0.0,
        tracking_state="TRACKED",
        out_of_frame=False,
    )
    assert "BLUR" in result.reasons
    assert "MOTION_BLUR" in result.reasons


def test_quality_summary_emits_out_of_frame_warning():
    frames = [
        {"state": "POOR", "score": 0.2, "reasons": ["OUT_OF_FRAME"]}
        for _ in range(5)
    ]
    summary = summarize_quality(frames)
    assert "HIGH_OUT_OF_FRAME_RATIO" in summary["warning_codes"]


def test_empty_quality_summary_is_deterministic():
    summary = summarize_quality([])
    assert summary["frame_count"] == 0
    assert summary["mean_frame_quality"] == 0.0

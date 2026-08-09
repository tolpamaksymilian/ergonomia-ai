from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v3.hand_object.holding import (
    HoldingConfig,
    HoldingState,
    ObjectDetection,
    analyze_bimanual_holding,
    analyze_holding_track,
)
from worker.src.pose_v3.hand_pipeline import HAND_POINT_COUNT, ValidatedHandFrame

from .conftest import make_hand


def _analyze(kinds, *, fps=10.0, objects=None, timestamps=None, config=None):
    frames = [
        make_hand(kind) if kind != "missing" else ValidatedHandFrame(
            False, False, np.zeros((HAND_POINT_COUNT, 2), dtype=np.float32),
            np.zeros((HAND_POINT_COUNT, 3), dtype=np.float32), 0.0,
            ["missing"], None, 0.0,
        )
        for kind in kinds
    ]
    times = timestamps or [index / fps for index in range(len(frames))]
    return analyze_holding_track(
        "left", frames, times, objects, fps=fps,
        config=config or HoldingConfig(minimum_confirmation_seconds=0.4),
    )


def test_open_hand_is_not_holding():
    frames, summary = _analyze(["open"] * 5)
    assert all(frame.state == HoldingState.NOT_HOLDING for frame in frames)
    assert summary.holding_episode_count == 0


def test_single_closed_frame_does_not_create_episode():
    _, summary = _analyze(["closed"])
    assert summary.holding_episode_count == 0


def test_stable_grasp_creates_likely_holding_episode():
    frames, summary = _analyze(["closed"] * 5)
    assert summary.holding_episode_count == 1
    assert any(frame.state == HoldingState.LIKELY_HOLDING for frame in frames)


def test_ten_frames_at_ten_fps_equal_one_second():
    _, summary = _analyze(["closed"] * 10)
    assert summary.likely_holding_seconds == pytest.approx(1.0)


def test_short_unknown_gap_does_not_split_episode():
    _, summary = _analyze(["closed"] * 4 + ["missing"] + ["closed"] * 4)
    assert summary.holding_episode_count == 1


def test_long_unknown_gap_splits_episodes():
    _, summary = _analyze(["closed"] * 5 + ["missing"] * 4 + ["closed"] * 5)
    assert summary.holding_episode_count == 2


def test_short_release_gap_does_not_split_episode():
    _, summary = _analyze(["closed"] * 5 + ["open"] + ["closed"] * 5)
    assert summary.holding_episode_count == 1


def test_confirmed_release_ends_episode():
    _, summary = _analyze(["closed"] * 5 + ["open"] * 4 + ["closed"] * 5)
    assert summary.holding_episode_count == 2


def test_near_object_increases_holding_confidence():
    near = [[ObjectDetection((85, 120, 115, 160), 39, "bottle", 0.8, 0)] for _ in range(5)]
    far = [[ObjectDetection((500, 400, 550, 500), 39, "bottle", 0.8, 0)] for _ in range(5)]
    near_frames, _ = _analyze(["closed"] * 5, objects=near)
    far_frames, _ = _analyze(["closed"] * 5, objects=far)
    assert near_frames[0].confidence > far_frames[0].confidence


def test_far_object_is_not_associated():
    far = [[ObjectDetection((500, 400, 550, 500), 39, "bottle", 0.8, 0)] for _ in range(5)]
    frames, _ = _analyze(["closed"] * 5, objects=far)
    assert frames[0].object_class is None


def test_missing_hand_produces_unknown_not_zero_risk():
    frames, summary = _analyze(["missing"] * 5)
    assert all(frame.state == HoldingState.UNKNOWN for frame in frames)
    assert summary.valid_observation_seconds == 0.0


def test_known_object_is_written_to_episode():
    objects = [[ObjectDetection((85, 120, 115, 160), 39, "bottle", 0.8, 0)] for _ in range(5)]
    _, summary = _analyze(["closed"] * 5, objects=objects)
    assert summary.episodes[0].known_object_class == "bottle"


def test_external_load_is_explicitly_unknown():
    _, summary = _analyze(["closed"] * 5)
    assert summary.external_load_known is False


def test_disabled_holding_returns_unknown_without_episodes():
    frames, summary = _analyze(
        ["closed"] * 5,
        config=HoldingConfig(enabled=False, minimum_confirmation_seconds=0.4),
    )
    assert all(frame.state == HoldingState.UNKNOWN for frame in frames)
    assert summary.holding_episode_count == 0


def test_variable_timestamps_determine_duration():
    _, summary = _analyze(
        ["closed"] * 4,
        timestamps=[0.0, 0.1, 0.25, 0.5],
        config=HoldingConfig(minimum_confirmation_seconds=0.3),
    )
    assert summary.likely_holding_seconds == pytest.approx(0.75)


def test_bimanual_requires_same_object_association():
    objects = [[ObjectDetection((85, 120, 115, 160), 39, "bottle", 0.8, 7)] for _ in range(5)]
    left, _ = _analyze(["closed"] * 5, objects=objects)
    right, _ = _analyze(["closed"] * 5, objects=objects)
    result = analyze_bimanual_holding(left, right, [i / 10 for i in range(5)], fps=10)
    assert result["likely_holding_seconds"] == pytest.approx(0.5)
    assert result["episode_count"] == 1


def test_different_objects_are_not_bimanual():
    left_objects = [[ObjectDetection((85, 120, 115, 160), 39, "bottle", 0.8, 1)] for _ in range(5)]
    right_objects = [[ObjectDetection((85, 120, 115, 160), 41, "cup", 0.8, 2)] for _ in range(5)]
    left, _ = _analyze(["closed"] * 5, objects=left_objects)
    right, _ = _analyze(["closed"] * 5, objects=right_objects)
    result = analyze_bimanual_holding(left, right, [i / 10 for i in range(5)], fps=10)
    assert result["likely_holding_seconds"] == 0.0


def test_near_hands_can_form_bimanual_unknown_object_candidate():
    left, _ = _analyze(["closed"] * 5)
    right, _ = _analyze(["closed"] * 5)
    result = analyze_bimanual_holding(left, right, [i / 10 for i in range(5)], fps=10)
    assert result["likely_holding_seconds"] == pytest.approx(0.5)
    assert set(result["association_modes"]) == {"unknown_object_hand_proximity"}
    assert all(frame.bimanual_candidate for frame in left)


def test_far_unknown_hands_are_not_marked_bimanual():
    left, _ = _analyze(["closed"] * 5)
    shifted_frames = [make_hand("closed") for _ in range(5)]
    for frame in shifted_frames:
        frame.points_px += (400, 0)
    right = analyze_holding_track(
        "right",
        shifted_frames,
        [i / 10 for i in range(5)],
        None,
        fps=10,
        config=HoldingConfig(minimum_confirmation_seconds=0.4),
    )[0]
    result = analyze_bimanual_holding(left, right, [i / 10 for i in range(5)], fps=10)
    assert result["likely_holding_seconds"] == 0.0


def test_static_holding_is_not_greater_than_total_holding():
    _, summary = _analyze(["closed"] * 6)
    assert 0.0 <= summary.static_holding_seconds <= summary.likely_holding_seconds


def test_holding_ratio_uses_only_valid_hand_observation_time():
    _, summary = _analyze(["closed"] * 5 + ["missing"] * 5)
    assert summary.valid_observation_seconds == pytest.approx(0.5)
    assert summary.likely_holding_seconds == pytest.approx(0.5)

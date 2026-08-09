from __future__ import annotations

from dataclasses import replace

import pytest

from worker.src.pose_v4.hand_graph import (
    HandGraphConfig,
    PalmScaleProfile,
    analyze_hand_graph_frame,
)
from worker.src.pose_v4.holding import (
    HoldingStateV2,
    HoldingV2Config,
    analyze_bimanual_holding_v2,
    analyze_holding_v2,
    frame_durations,
    serialize_holding_frame_v2,
    serialize_holding_summary_v2,
)
from worker.src.pose_v4.object_tracking import TrackedObject

from .conftest import make_hand_v4


def _object(track_id=1, velocity=(0.0, 0.0)):
    return TrackedObject(track_id, 39, "bottle", (70, 80, 130, 150), 0.85, (100, 115), velocity, 5, 0)


def _hands(graph_factory, count=12, *, kind="closed", with_object=True, quality=0.9):
    _, body = graph_factory()
    profile = PalmScaleProfile()
    previous = None
    output = []
    for _ in range(count):
        hand = make_hand_v4(kind, quality=quality)
        graph = analyze_hand_graph_frame(
            "left", hand, body, [_object()] if with_object else [], None,
            profile, previous, HandGraphConfig(),
        )
        output.append(graph)
        previous = graph
    return output


@pytest.mark.parametrize(
    "values,expected",
    [
        ([0.0, 0.1, 0.2], [0.1, 0.1, 0.1]),
        ([0.0, 0.05, 0.2], [0.05, 0.15, 0.15]),
        ([0.0], [0.04]),
    ],
)
def test_frame_durations_prefer_timestamps(values, expected):
    assert frame_durations(values, 25.0) == pytest.approx(expected)


def test_frame_durations_fall_back_to_fps_for_invalid_delta():
    assert frame_durations([0.0, 0.0, 0.0], 20.0) == pytest.approx([0.05] * 3)


@pytest.mark.parametrize(
    "field,value",
    [
        ("minimum_hand_quality", -0.1),
        ("enter_threshold", 1.1),
        ("minimum_confirmation_seconds", -0.1),
        ("minimum_static_seconds", -1.0),
    ],
)
def test_invalid_holding_configuration_fails_fast(field, value):
    config = replace(HoldingV2Config(), **{field: value})
    with pytest.raises(ValueError):
        config.validate()


def test_hysteresis_threshold_order_is_validated():
    with pytest.raises(ValueError):
        HoldingV2Config(enter_threshold=0.5, keep_threshold=0.6, exit_threshold=0.4).validate()


def test_closed_hand_with_stable_object_enters_likely_holding(graph_factory):
    hands = _hands(graph_factory)
    timestamps = [index * 0.1 for index in range(len(hands))]
    frames, summary = analyze_holding_v2(
        "left", hands, timestamps, fps=10.0, config=HoldingV2Config()
    )
    assert any(frame.state == HoldingStateV2.LIKELY_HOLDING for frame in frames)
    assert summary.likely_holding_seconds > 0.0
    assert summary.episode_count == 1


def test_open_hand_is_not_holding(graph_factory):
    hands = _hands(graph_factory, kind="open")
    frames, summary = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(len(hands))], fps=10,
        config=HoldingV2Config(),
    )
    assert all(frame.state == HoldingStateV2.NOT_HOLDING for frame in frames)
    assert summary.likely_holding_seconds == 0.0


def test_low_quality_is_unknown_not_not_holding(graph_factory):
    hands = _hands(graph_factory, quality=0.2)
    frames, _ = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(len(hands))], fps=10,
        config=HoldingV2Config(),
    )
    assert all(frame.state == HoldingStateV2.UNKNOWN for frame in frames)


def test_unknown_object_holding_requires_persistent_strong_geometry(graph_factory):
    hands = _hands(graph_factory, with_object=False)
    frames, _ = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(len(hands))], fps=10,
        config=HoldingV2Config(),
    )
    assert HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT in {frame.state for frame in frames}


def test_single_strong_frame_does_not_start_episode(graph_factory):
    hands = _hands(graph_factory, count=1)
    frames, summary = analyze_holding_v2(
        "left", hands, [0.0], fps=10, config=HoldingV2Config()
    )
    assert frames[0].state != HoldingStateV2.LIKELY_HOLDING
    assert summary.episode_count == 0


def test_short_unknown_gap_does_not_split_holding_episode(graph_factory):
    hands = _hands(graph_factory, count=14)
    hands[8] = replace(hands[8], visible=False, quality=0.0)
    frames, summary = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(14)], fps=10,
        config=HoldingV2Config(maximum_unknown_gap_seconds=0.2),
    )
    assert summary.episode_count == 1
    assert frames[8].state in {
        HoldingStateV2.LIKELY_HOLDING,
        HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT,
    }


def test_long_unknown_gap_ends_active_holding(graph_factory):
    hands = _hands(graph_factory, count=18)
    for index in range(8, 13):
        hands[index] = replace(hands[index], visible=False, quality=0.0)
    frames, _ = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(18)], fps=10,
        config=HoldingV2Config(maximum_unknown_gap_seconds=0.15),
    )
    assert HoldingStateV2.UNKNOWN in {frame.state for frame in frames[9:13]}


def test_release_requires_confirmation_and_not_one_open_frame(graph_factory):
    hands = _hands(graph_factory, count=14)
    open_hand = _hands(graph_factory, count=1, kind="open")[0]
    hands[9] = open_hand
    frames, _ = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(14)], fps=10,
        config=HoldingV2Config(release_confirmation_seconds=0.25),
    )
    assert frames[10].state == HoldingStateV2.LIKELY_HOLDING


def test_sustained_release_ends_holding(graph_factory):
    hands = _hands(graph_factory, count=10) + _hands(graph_factory, count=5, kind="open")
    frames, _ = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(15)], fps=10,
        config=HoldingV2Config(release_confirmation_seconds=0.2),
    )
    assert frames[-1].state == HoldingStateV2.NOT_HOLDING


def test_static_holding_requires_minimum_duration(graph_factory):
    hands = _hands(graph_factory, count=12)
    frames, summary = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(12)], fps=10,
        config=HoldingV2Config(minimum_static_seconds=0.5),
    )
    assert any(frame.static_candidate for frame in frames)
    assert summary.static_holding_seconds >= 0.5


def test_static_candidate_is_removed_when_too_short(graph_factory):
    hands = _hands(graph_factory, count=7)
    frames, summary = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(7)], fps=10,
        config=HoldingV2Config(minimum_static_seconds=2.0),
    )
    assert not any(frame.static_candidate for frame in frames)
    assert summary.static_holding_seconds == 0.0


def test_same_object_track_can_form_bimanual_holding(graph_factory):
    left_hands = _hands(graph_factory, count=12)
    right_hands = [replace(hand, side="right") for hand in _hands(graph_factory, count=12)]
    timestamps = [i * 0.1 for i in range(12)]
    left, _ = analyze_holding_v2("left", left_hands, timestamps, fps=10, config=HoldingV2Config())
    right, _ = analyze_holding_v2("right", right_hands, timestamps, fps=10, config=HoldingV2Config())
    result = analyze_bimanual_holding_v2(left, right, timestamps, fps=10)
    assert result["likely_holding_seconds"] > 0.0
    assert result["episode_count"] == 1


def test_proximity_without_holding_is_not_bimanual(graph_factory):
    hands = _hands(graph_factory, count=10, kind="open")
    timestamps = [i * 0.1 for i in range(10)]
    left, _ = analyze_holding_v2("left", hands, timestamps, fps=10, config=HoldingV2Config())
    right, _ = analyze_holding_v2("right", [replace(h, side="right") for h in hands], timestamps, fps=10, config=HoldingV2Config())
    result = analyze_bimanual_holding_v2(left, right, timestamps, fps=10)
    assert result["likely_holding_seconds"] == 0.0


def test_holding_serialization_is_explicit_about_external_load(graph_factory):
    hands = _hands(graph_factory)
    frames, summary = analyze_holding_v2(
        "left", hands, [i * 0.1 for i in range(len(hands))], fps=10,
        config=HoldingV2Config(),
    )
    frame_value = serialize_holding_frame_v2(frames[-1])
    summary_value = serialize_holding_summary_v2(summary)
    assert frame_value["external_load_known"] is False
    assert summary_value["external_load_known"] is False
    assert "evidence" in frame_value


@pytest.mark.parametrize("fps", [10.0, 25.0, 30.0, 60.0])
def test_holding_duration_works_at_multiple_fps(fps, graph_factory):
    count = int(fps)
    hands = _hands(graph_factory, count=count)
    timestamps = [i / fps for i in range(count)]
    _, summary = analyze_holding_v2(
        "left", hands, timestamps, fps=fps, config=HoldingV2Config()
    )
    assert 0.0 < summary.likely_holding_seconds <= 1.0

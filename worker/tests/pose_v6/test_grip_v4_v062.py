from __future__ import annotations

import numpy as np

from worker.src.pose_v3.hand_pipeline import ValidatedHandFrame
from worker.src.pose_v4.hand_graph import (
    FingerDiagnostic, FingerVisibility, GripFeaturesV2, GripStateV2,
    HandGraphFrame, HandOcclusion, PalmFrame,
)
from worker.src.pose_v6.grip_v4 import GripStateV4, analyze_grip_v4
from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame


def _temporal() -> TemporalFrame:
    points = np.zeros((23, 2), dtype=np.float32); points[9] = (10, 10); points[10] = (10, 10)
    scores = np.ones(23, dtype=np.float32)
    return TemporalFrame(points.copy(), scores.copy(), points.copy(), scores.copy(), tuple([PointSource.MEASURED] * 23), np.ones(23, dtype=bool), np.zeros(23, dtype=np.float32), np.full(23, np.nan, dtype=np.float32))


def _graph(state: GripStateV2, *, visible: bool = True) -> HandGraphFrame:
    source = ValidatedHandFrame(visible, False, np.tile(np.asarray((10, 10), dtype=np.float32), (21, 1)), np.zeros((21, 3), dtype=np.float32), .9 if visible else 0, [], "Left", .9, point_validity=np.ones(21, dtype=bool))
    finger = FingerDiagnostic("index", FingerVisibility.VISIBLE if visible else FingerVisibility.LOST, .9 if visible else 0, 4 if visible else 0, 20, 30, 40, ())
    grip = GripFeaturesV2(state, .9 if visible else 0, .6, .3, .2, .3, .7, .5, {"index": .6, "middle": .6, "ring": .6, "pinky": .6}, 0, 0, .9)
    return HandGraphFrame("left", visible, .9 if visible else 0, .9 if visible else 0, HandOcclusion.VISIBLE if visible else HandOcclusion.OCCLUDED_BY_OBJECT, PalmFrame((10, 10), 20, 22, 21, 0, None, {}), {name: finger for name in ("thumb", "index", "middle", "ring", "pinky")}, grip, 1, "object", .8, .3, (0, 0), .9, (0, 0, 30, 30), source)


def _run(states: list[tuple[GripStateV2, bool]], *, confirmation: float = .15):
    graphs = [_graph(state, visible=visible) for state, visible in states]
    return analyze_grip_v4("left", graphs, [index * .1 for index in range(len(graphs))], [_temporal()] * len(graphs), confirmation_seconds=confirmation, release_seconds=.15, maximum_unknown_gap_seconds=.25, fallback_fps=10)


def test_single_occluded_frame_does_not_turn_open_hand_into_unknown_or_closed() -> None:
    result = _run([(GripStateV2.OPEN, True)] * 3 + [(GripStateV2.UNKNOWN, False)] + [(GripStateV2.OPEN, True)])
    assert result.frames[3].state == GripStateV4.OPEN
    assert result.frames[3].candidate_state == GripStateV4.UNKNOWN
    assert result.frames[4].state == GripStateV4.OPEN


def test_open_partial_power_transition_requires_confirmation() -> None:
    result = _run(
        [(GripStateV2.OPEN, True)] * 2
        + [(GripStateV2.PARTIALLY_CLOSED, True)] * 2
        + [(GripStateV2.POWER_GRIP_CANDIDATE, True)] * 2
    )
    assert result.frames[3].state == GripStateV4.PARTIALLY_CLOSED
    assert result.frames[-1].state == GripStateV4.POWER_GRIP
    assert result.summary["power_grip_seconds"] > 0


def test_one_weak_power_candidate_does_not_flicker_confirmed_open() -> None:
    result = _run([(GripStateV2.OPEN, True)] * 3 + [(GripStateV2.POWER_GRIP_CANDIDATE, True)] + [(GripStateV2.OPEN, True)] * 2)
    assert all(frame.state == GripStateV4.OPEN for frame in result.frames)


def test_large_body_hand_wrist_disagreement_is_rejected() -> None:
    graph = _graph(GripStateV2.OPEN)
    graph.source_frame.points_px[0] = (100, 100)
    result = analyze_grip_v4("left", [graph], [0], [_temporal()])
    assert result.frames[0].wrist_alignment["accepted"] is False
    assert result.frames[0].wrist_alignment["mode"] == "assignment_rejected_large_disagreement"


def test_accepted_wrist_alignment_exposes_bounded_overlay_translation() -> None:
    graph = _graph(GripStateV2.OPEN)
    graph.source_frame.points_px[0] = (14, 10)
    result = analyze_grip_v4("left", [graph], [0], [_temporal()])
    alignment = result.frames[0].wrist_alignment
    assert alignment["accepted"] is True
    assert alignment["hand_wrist_is_body_measurement"] is False
    assert alignment["overlay_translation_px"] is not None


def test_grip_summary_reports_no_single_frame_flicker_after_hysteresis() -> None:
    result = _run([(GripStateV2.OPEN, True)] * 3 + [(GripStateV2.CLOSED, True)] + [(GripStateV2.OPEN, True)] * 3)
    assert result.summary["single_frame_grip_flicker_count"] == 0
    assert result.summary["grip_temporal_stability_score"] == 1.0


def test_grip_v5_reports_confidence_stability_and_landmark_coverage() -> None:
    result = _run([(GripStateV2.OPEN, True)] * 3)
    payload = result.frames[1].to_dict()
    assert payload["grip_state_confidence"] == payload["confidence"]
    assert payload["grip_state_stability"] == payload["temporal_stability"]
    assert payload["grip_landmark_coverage"] == 1.0
    assert result.summary["grip_engine_version"] == "grip-v5.0"

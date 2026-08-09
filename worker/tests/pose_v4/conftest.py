from __future__ import annotations

import numpy as np
import pytest

import sys
from pathlib import Path

WORKER_SOURCE = Path(__file__).resolve().parents[2] / "src"
if str(WORKER_SOURCE) in sys.path:
    sys.path.remove(str(WORKER_SOURCE))
sys.path.insert(0, str(WORKER_SOURCE))

from worker.src.pose_v3.hand_pipeline import HAND_POINT_COUNT, ValidatedHandFrame
from worker.src.pose_v3.tracking import TrackingDecision, TrackingState
from worker.src.pose_v4.graph import BiomechanicalPoseGraph, PoseGraphConfig


BBOX = np.asarray([180.0, 40.0, 460.0, 590.0], dtype=np.float32)


@pytest.fixture
def body_points_v4() -> np.ndarray:
    points = np.tile(np.asarray([320.0, 250.0], dtype=np.float32), (133, 1))
    coordinates = {
        0: (320, 70), 1: (307, 65), 2: (333, 65), 3: (296, 72), 4: (344, 72),
        5: (270, 150), 6: (370, 150), 7: (235, 235), 8: (405, 235),
        9: (215, 315), 10: (425, 315), 11: (290, 320), 12: (350, 320),
        13: (285, 435), 14: (355, 435), 15: (280, 550), 16: (360, 550),
        17: (270, 565), 18: (280, 570), 19: (290, 565),
        20: (350, 565), 21: (360, 570), 22: (370, 565),
    }
    for index, coordinate in coordinates.items():
        points[index] = coordinate
    return points


@pytest.fixture
def body_scores_v4() -> np.ndarray:
    scores = np.zeros((133,), dtype=np.float32)
    scores[:23] = 0.96
    return scores


@pytest.fixture
def tracked_v4() -> TrackingDecision:
    return TrackingDecision(TrackingState.TRACKED, True, 1.0, 23, False, ())


@pytest.fixture
def graph_factory(body_points_v4, body_scores_v4, tracked_v4):
    def factory(*, points=None, scores=None, decision=None, timestamp=0.0, graph=None):
        selected = graph or BiomechanicalPoseGraph(PoseGraphConfig())
        frame = selected.update(
            raw_points=body_points_v4 if points is None else points,
            raw_scores=body_scores_v4 if scores is None else scores,
            bbox=BBOX,
            tracking=tracked_v4 if decision is None else decision,
            frame_width=640,
            frame_height=600,
            timestamp_seconds=timestamp,
        )
        return selected, frame
    return factory


def make_hand_v4(kind: str = "open", *, quality: float = 0.9) -> ValidatedHandFrame:
    points = np.zeros((HAND_POINT_COUNT, 2), dtype=np.float32)
    points[0] = (100, 160)
    mcp_x = (76, 92, 108, 124)
    chains = ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
    for chain, x in zip(chains, mcp_x):
        points[chain[0]] = (x, 130)
        points[chain[1]] = (x, 110)
        points[chain[2]] = (x, 90)
        points[chain[3]] = (x, 68)
    points[1:5] = np.asarray([(82, 145), (72, 132), (65, 118), (59, 102)])
    if kind in {"closed", "pinch"}:
        for tip, coordinate in zip(
            (8, 12, 16, 20),
            ((88, 137), (98, 140), (108, 141), (116, 139)),
        ):
            points[tip] = coordinate
        points[4] = (88, 136) if kind == "pinch" else (82, 140)
        if kind == "pinch":
            points[8] = (90, 137)
    return ValidatedHandFrame(
        visible=True,
        interpolated=False,
        points_px=points,
        world_points=np.zeros((HAND_POINT_COUNT, 3), dtype=np.float32),
        quality=quality,
        reject_reasons=[],
        handedness_label="Left",
        handedness_score=0.9,
        tracking_state="HAND_TRACKED",
        point_validity=np.ones((HAND_POINT_COUNT,), dtype=bool),
        point_reasons=(None,) * HAND_POINT_COUNT,
        segment_validity={},
    )

from __future__ import annotations

import numpy as np

from worker.src.pose_v6.render_continuity import PersistentBoneRenderer, RenderSource, summarize_render_sources


def _update(renderer: PersistentBoneRenderer, timestamp: float, first: np.ndarray | None, second: np.ndarray | None, bbox: np.ndarray, *, scene_cut: bool = False, hard_lost: bool = False):
    return renderer.update("left_forearm", first, second, first_source="MEASURED", second_source="MEASURED", confidence=0.9 if first is not None else 0.0, timestamp_seconds=timestamp, bbox=bbox, expected_length=20.0, frame_width=300, frame_height=200, scene_cut=scene_cut, hard_lost=hard_lost)


def test_visibility_111011_becomes_continuous_with_explicit_hold() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=0.3)
    bbox = np.array([20, 10, 120, 190], dtype=np.float32); frames = []
    for index, valid in enumerate([1, 1, 1, 0, 1, 1]):
        bone = _update(renderer, index / 30, np.array([50 + index, 50]) if valid else None, np.array([70 + index, 50]) if valid else None, bbox + np.array([index, 0, index, 0]))
        frames.append({"left_forearm": bone})
    assert all(frame["left_forearm"].visible for frame in frames)
    assert frames[3]["left_forearm"].source == RenderSource.HELD
    summary = summarize_render_sources(frames)
    assert summary["single_frame_bone_dropout_count"] == 0
    assert summary["render_bone_coverage_ratio"] == 1.0


def test_hold_moves_with_bbox_instead_of_freezing() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=0.4)
    first_bbox = np.array([0, 0, 100, 180], dtype=np.float32)
    measured = _update(renderer, 0.0, np.array([20, 40]), np.array([40, 40]), first_bbox)
    held = _update(renderer, 0.1, None, None, first_bbox + np.array([30, 0, 30, 0]))
    assert measured.first is not None and held.first is not None
    assert held.first[0] > measured.first[0] + 20


def test_hard_lost_and_scene_cut_hide_immediately() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=1.0); bbox = np.array([0, 0, 100, 180], dtype=np.float32)
    _update(renderer, 0.0, np.array([20, 40]), np.array([40, 40]), bbox)
    assert not _update(renderer, 0.1, None, None, bbox, hard_lost=True).visible
    assert not _update(renderer, 0.2, None, None, bbox, scene_cut=True).visible


def test_long_gap_exceeds_persistence() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=0.2); bbox = np.array([0, 0, 100, 180], dtype=np.float32)
    _update(renderer, 0.0, np.array([20, 40]), np.array([40, 40]), bbox)
    assert not _update(renderer, 0.3, None, None, bbox).visible

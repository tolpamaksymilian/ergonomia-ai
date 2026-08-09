from __future__ import annotations

import numpy as np
import pytest

from worker.src.pose_v3.hand_object.holding import ObjectDetection
from worker.src.pose_v4.object_tracking import ObjectTrackManager, bbox_iou, track_object_sequence


def _detection(x: float, *, class_id: int = 39) -> ObjectDetection:
    return ObjectDetection((x, 100, x + 40, 160), class_id, "bottle", 0.8)


def test_object_track_id_is_stable_across_motion():
    frames = track_object_sequence(
        [[_detection(100)], [_detection(105)], [_detection(112)]],
        [0.0, 0.1, 0.2], frame_width=640, frame_height=480,
    )
    assert [frame[0].track_id for frame in frames] == [1, 1, 1]
    assert frames[-1][0].velocity[0] > 0.0


def test_different_classes_do_not_share_track():
    manager = ObjectTrackManager()
    first = manager.update([_detection(100, class_id=39)], frame_width=640, frame_height=480, timestamp_seconds=0.0)
    second = manager.update([_detection(100, class_id=41)], frame_width=640, frame_height=480, timestamp_seconds=0.1)
    assert first[0].track_id != second[0].track_id


def test_object_disappearance_does_not_emit_fake_box():
    frames = track_object_sequence(
        [[_detection(100)], [], []], [0.0, 0.1, 0.2],
        frame_width=640, frame_height=480,
    )
    assert frames[0]
    assert frames[1] == []
    assert frames[2] == []


def test_reappearing_object_within_memory_reuses_track():
    manager = ObjectTrackManager(maximum_missing_frames=2)
    first = manager.update([_detection(100)], frame_width=640, frame_height=480, timestamp_seconds=0.0)
    manager.update([], frame_width=640, frame_height=480, timestamp_seconds=0.1)
    third = manager.update([_detection(105)], frame_width=640, frame_height=480, timestamp_seconds=0.2)
    assert first[0].track_id == third[0].track_id


def test_invalid_detection_is_ignored():
    invalid = ObjectDetection((20, 20, 10, 10), 39, "bottle", 0.8)
    manager = ObjectTrackManager()
    assert manager.update([invalid], frame_width=640, frame_height=480, timestamp_seconds=0.0) == []


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ((0, 0, 10, 10), (0, 0, 10, 10), 1.0),
        ((0, 0, 10, 10), (10, 10, 20, 20), 0.0),
        ((0, 0, 10, 10), (5, 0, 15, 10), 1 / 3),
    ],
)
def test_bbox_iou_known_cases(first, second, expected):
    assert bbox_iou(first, second) == pytest.approx(expected)


def test_object_sequence_length_mismatch_is_rejected():
    with pytest.raises(ValueError):
        track_object_sequence([[_detection(100)]], [], frame_width=640, frame_height=480)


@pytest.mark.parametrize("seed", range(5))
def test_random_object_tracks_never_emit_non_finite_geometry(seed):
    random = np.random.default_rng(seed)
    manager = ObjectTrackManager()
    for index in range(10):
        x = float(random.uniform(0, 500))
        tracks = manager.update([_detection(x)], frame_width=640, frame_height=480, timestamp_seconds=index / 10)
        for track in tracks:
            assert np.isfinite(track.bbox_xyxy).all()
            assert np.isfinite(track.center).all()
            assert np.isfinite(track.velocity).all()

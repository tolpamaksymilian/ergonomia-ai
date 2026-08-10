from __future__ import annotations

import logging
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

def test_active_scan_keeps_later_segments_and_source_timeline(monkeypatch) -> None:
    worker_src = Path(__file__).resolve().parents[2] / "src"
    module_names = ("pose_worker", "pose_v3", "pose_v4", "pose_v5")
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    previous_path = list(sys.path)
    for name in module_names:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(worker_src))
    pose_worker = importlib.import_module("pose_worker")

    class _Capture:
        def __init__(self, _path: str) -> None:
            self.position = 0

        def isOpened(self) -> bool:
            return True

        def get(self, key: int) -> float:
            return {
                pose_worker.cv2.CAP_PROP_FPS: 10.0,
                pose_worker.cv2.CAP_PROP_FRAME_COUNT: 100.0,
                pose_worker.cv2.CAP_PROP_FRAME_WIDTH: 640.0,
                pose_worker.cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
            }[key]

        def set(self, _key: int, value: float) -> bool:
            self.position = int(value)
            return True

        def read(self) -> tuple[bool, np.ndarray]:
            frame = np.zeros((2, 2, 3), dtype=np.uint8)
            frame[0, 0, 0] = self.position
            return True, frame

        def release(self) -> None:
            return None

    visible_samples = {0, 10, 60, 70}

    def select(_keypoints, _scores, _width, _height, _settings, _previous):
        frame_index = int(_keypoints[0, 0])
        if frame_index not in visible_samples:
            return None
        return pose_worker.PoseCandidate(
            keypoints=np.zeros((133, 2), dtype=np.float32),
            scores=np.ones(133, dtype=np.float32),
            bbox=np.asarray([100, 50, 400, 450], dtype=np.float32),
            body_keypoint_count=17,
            body_average_confidence=0.9,
            selection_score=0.9,
        )

    def model(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return np.asarray([[float(frame[0, 0, 0]), 0.0]]), np.asarray([1.0])

    settings = SimpleNamespace(
        scan_fps=1.0,
        scan_start_confirm_seconds=1.0,
        scan_end_confirm_seconds=1.0,
        scan_min_quality=0.5,
        active_pre_padding_seconds=0.0,
        active_post_padding_seconds=0.0,
        min_active_seconds=1.0,
        worker_id="test-worker",
    )
    monkeypatch.setattr(pose_worker.cv2, "VideoCapture", _Capture)
    monkeypatch.setattr(pose_worker, "select_primary_person", select)

    try:
        result = pose_worker.scan_active_segment(
            None,
            settings,
            model,
            "analysis-id",
            pose_worker.Path("synthetic.mp4"),
            logging.getLogger("test-full-video-v051"),
        )

        assert [(part.start_frame, part.end_frame) for part in result.segments] == [(0, 19), (60, 79)]
        assert result.start_frame == 0
        assert result.end_frame == 79
        assert result.end_seconds == 8.0
        assert result.scan_presence_ratio == 0.5
    finally:
        sys.path[:] = previous_path
        for name in module_names:
            sys.modules.pop(name, None)
            if saved_modules[name] is not None:
                sys.modules[name] = saved_modules[name]

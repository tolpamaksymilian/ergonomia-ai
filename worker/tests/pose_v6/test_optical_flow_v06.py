from __future__ import annotations

import cv2
import numpy as np

from worker.src.pose_v6.config import OpticalFlowConfig
from worker.src.pose_v6.optical_flow import track_point_forward_backward


def test_forward_backward_flow_tracks_translated_feature() -> None:
    first = np.zeros((100, 100), dtype=np.uint8); second = np.zeros_like(first)
    cv2.circle(first, (30, 40), 5, 255, -1); cv2.circle(second, (36, 43), 5, 255, -1)
    result = track_point_forward_backward(first, second, (30.0, 40.0), config=OpticalFlowConfig(), frame_width=100, frame_height=100, body_bbox=np.array([10, 10, 80, 90]), body_scale=80.0)
    assert result.valid and result.point is not None
    assert np.allclose(result.point, [36, 43], atol=0.8)
    assert result.flow_quality > 0.35


def test_flow_rejects_background_drift_outside_body_roi() -> None:
    first = np.zeros((100, 100), dtype=np.uint8); second = np.zeros_like(first)
    cv2.circle(first, (20, 20), 5, 255, -1); cv2.circle(second, (70, 70), 5, 255, -1)
    result = track_point_forward_backward(first, second, (20.0, 20.0), config=OpticalFlowConfig(maximum_forward_backward_error=10.0), frame_width=100, frame_height=100, body_bbox=np.array([10, 10, 30, 30]), body_scale=20.0)
    assert not result.valid

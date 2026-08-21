"""Validated pyramidal Lucas-Kanade recovery for short keypoint gaps."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import OpticalFlowConfig


@dataclass(frozen=True)
class FlowResult:
    point: tuple[float, float] | None
    valid: bool
    forward_backward_error: float | None
    flow_quality: float
    rejection_reason: str | None


def track_point_forward_backward(
    previous_gray: np.ndarray,
    current_gray: np.ndarray,
    point: tuple[float, float],
    *,
    config: OpticalFlowConfig,
    frame_width: int,
    frame_height: int,
    body_bbox: np.ndarray | None = None,
    body_scale: float | None = None,
) -> FlowResult:
    """Track one point and reject background drift using a backward pass."""

    if previous_gray.ndim != 2 or current_gray.ndim != 2:
        raise ValueError("optical flow expects grayscale images")
    origin = np.asarray(point, dtype=np.float32).reshape(-1)
    if origin.size != 2 or not np.isfinite(origin).all():
        return FlowResult(None, False, None, 0.0, "INVALID_ORIGIN")
    initial = origin.reshape(1, 1, 2)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 24, 0.01)
    forward, status_forward, error_forward = cv2.calcOpticalFlowPyrLK(
        previous_gray,
        current_gray,
        initial,
        None,
        winSize=(config.window_size, config.window_size),
        maxLevel=config.pyramid_levels,
        criteria=criteria,
    )
    if forward is None or status_forward is None or int(status_forward.reshape(-1)[0]) != 1:
        return FlowResult(None, False, None, 0.0, "FORWARD_FLOW_FAILED")
    backward, status_backward, _ = cv2.calcOpticalFlowPyrLK(
        current_gray,
        previous_gray,
        forward,
        None,
        winSize=(config.window_size, config.window_size),
        maxLevel=config.pyramid_levels,
        criteria=criteria,
    )
    if backward is None or status_backward is None or int(status_backward.reshape(-1)[0]) != 1:
        return FlowResult(None, False, None, 0.0, "BACKWARD_FLOW_FAILED")
    candidate = forward.reshape(-1)[:2].astype(np.float32)
    returned = backward.reshape(-1)[:2]
    fb_error = float(np.linalg.norm(returned - origin))
    if not np.isfinite(candidate).all() or not np.isfinite(fb_error):
        return FlowResult(None, False, None, 0.0, "NON_FINITE_FLOW")
    if fb_error > config.maximum_forward_backward_error:
        return FlowResult(None, False, fb_error, 0.0, "FORWARD_BACKWARD_MISMATCH")
    if not (0.0 <= candidate[0] < frame_width and 0.0 <= candidate[1] < frame_height):
        return FlowResult(None, False, fb_error, 0.0, "FLOW_OUT_OF_FRAME")
    if body_bbox is not None and not _inside_expanded_bbox(candidate, body_bbox, 0.22):
        return FlowResult(None, False, fb_error, 0.0, "FLOW_OUTSIDE_BODY_ROI")
    displacement = float(np.linalg.norm(candidate - origin))
    if body_scale is not None and body_scale > 0.0 and displacement > body_scale * 0.40:
        return FlowResult(None, False, fb_error, 0.0, "FLOW_TELEPORT")
    lk_error = float(error_forward.reshape(-1)[0]) if error_forward is not None else 0.0
    if not np.isfinite(lk_error):
        return FlowResult(None, False, fb_error, 0.0, "NON_FINITE_FLOW_ERROR")
    quality = float(np.clip(1.0 - fb_error / max(config.maximum_forward_backward_error, 1e-6), 0.0, 1.0))
    quality *= float(np.clip(1.0 - lk_error / 50.0, 0.25, 1.0))
    if quality < config.minimum_quality:
        return FlowResult(None, False, fb_error, quality, "LOW_FLOW_QUALITY")
    return FlowResult((float(candidate[0]), float(candidate[1])), True, fb_error, quality, None)


def _inside_expanded_bbox(point: np.ndarray, bbox: np.ndarray, margin_ratio: float) -> bool:
    values = np.asarray(bbox, dtype=float).reshape(-1)
    if values.size != 4 or not np.isfinite(values).all():
        return False
    width = values[2] - values[0]
    height = values[3] - values[1]
    return (
        values[0] - width * margin_ratio <= point[0] <= values[2] + width * margin_ratio
        and values[1] - height * margin_ratio <= point[1] <= values[3] + height * margin_ratio
    )

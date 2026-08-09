"""Transparent frame and segment quality diagnostics for Pose V0.3."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

import cv2
import numpy as np


class FrameQualityState(StrEnum):
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    POOR = "POOR"
    INVALID = "INVALID"


@dataclass(frozen=True)
class ImageQuality:
    blur_quality: float
    exposure_quality: float
    underexposed: bool
    overexposed: bool
    blurry: bool
    motion_blur: bool = False


@dataclass(frozen=True)
class FrameQuality:
    state: FrameQualityState
    score: float
    components: dict[str, float]
    reasons: tuple[str, ...]


def analyze_image_quality(frame: np.ndarray) -> ImageQuality:
    if frame.size == 0:
        return ImageQuality(0.0, 0.0, False, False, True)
    height, width = frame.shape[:2]
    target_width = min(width, 320)
    scale = target_width / max(1, width)
    resized = cv2.resize(
        frame,
        (target_width, max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    mean_luma = float(np.mean(gray))
    dark_ratio = float(np.mean(gray < 24))
    bright_ratio = float(np.mean(gray > 235))
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    horizontal_energy = float(np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0))))
    vertical_energy = float(np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1))))
    directional_ratio = max(horizontal_energy, vertical_energy) / max(
        min(horizontal_energy, vertical_energy), 1e-6
    )

    blur_quality = float(np.clip(laplacian_variance / 120.0, 0.0, 1.0))
    center_quality = 1.0 - min(1.0, abs(mean_luma - 127.5) / 110.0)
    clipping_quality = 1.0 - min(1.0, dark_ratio + bright_ratio)
    exposure_quality = float(np.clip(0.55 * center_quality + 0.45 * clipping_quality, 0.0, 1.0))
    return ImageQuality(
        blur_quality=blur_quality,
        exposure_quality=exposure_quality,
        underexposed=mean_luma < 45.0 or dark_ratio > 0.55,
        overexposed=mean_luma > 215.0 or bright_ratio > 0.45,
        blurry=laplacian_variance < 35.0,
        motion_blur=laplacian_variance < 70.0 and directional_ratio > 3.5,
    )


def build_frame_quality(
    image: ImageQuality,
    *,
    body_quality: float,
    left_hand_quality: float,
    right_hand_quality: float,
    tracking_state: str,
    out_of_frame: bool,
) -> FrameQuality:
    body = float(np.clip(body_quality, 0.0, 1.0))
    left_hand = float(np.clip(left_hand_quality, 0.0, 1.0))
    right_hand = float(np.clip(right_hand_quality, 0.0, 1.0))
    hands = (left_hand + right_hand) / 2.0
    tracking = 1.0 if tracking_state == "TRACKED" else 0.75 if tracking_state == "PARTIAL" else 0.35 if tracking_state == "OCCLUDED" else 0.0
    score = float(
        np.clip(
            0.42 * body
            + 0.18 * hands
            + 0.16 * image.blur_quality
            + 0.14 * image.exposure_quality
            + 0.10 * tracking,
            0.0,
            1.0,
        )
    )
    reasons: list[str] = []
    if image.blurry:
        reasons.append("BLUR")
    if image.motion_blur:
        reasons.append("MOTION_BLUR")
    if image.underexposed:
        reasons.append("UNDEREXPOSED")
    if image.overexposed:
        reasons.append("OVEREXPOSED")
    if out_of_frame:
        reasons.append("OUT_OF_FRAME")
    if tracking_state in {"LOST", "REACQUIRING"}:
        reasons.append(f"TRACK_{tracking_state}")

    if body <= 0.0 or tracking_state in {"LOST", "REACQUIRING"}:
        state = FrameQualityState.INVALID
    elif score >= 0.78:
        state = FrameQualityState.GOOD
    elif score >= 0.60:
        state = FrameQualityState.ACCEPTABLE
    else:
        state = FrameQualityState.POOR
    return FrameQuality(
        state=state,
        score=score,
        components={
            "body": round(body, 6),
            "hands": round(hands, 6),
            "left_hand": round(left_hand, 6),
            "right_hand": round(right_hand, 6),
            "blur": round(image.blur_quality, 6),
            "exposure": round(image.exposure_quality, 6),
            "tracking": round(tracking, 6),
        },
        reasons=tuple(reasons),
    )


def summarize_quality(frames: list[dict[str, object]]) -> dict[str, object]:
    total = len(frames)
    if total == 0:
        return {
            "frame_count": 0,
            "mean_frame_quality": 0.0,
            "state_counts": {},
            "warning_codes": ["HIGH_TRACKING_REJECTION"],
        }
    scores = [float(frame.get("score", 0.0)) for frame in frames]
    states = Counter(str(frame.get("state", FrameQualityState.INVALID.value)) for frame in frames)
    reason_values: list[str] = []
    for frame in frames:
        raw_reasons = frame.get("reasons")
        if isinstance(raw_reasons, (list, tuple)):
            reason_values.extend(str(reason) for reason in raw_reasons)
    reasons = Counter(reason_values)
    warnings: list[str] = []
    if (states[FrameQualityState.INVALID.value] + states[FrameQualityState.POOR.value]) / total > 0.35:
        warnings.append("HIGH_TRACKING_REJECTION")
    if reasons["OUT_OF_FRAME"] / total > 0.25:
        warnings.append("HIGH_OUT_OF_FRAME_RATIO")
    return {
        "frame_count": total,
        "mean_frame_quality": round(float(np.mean(scores)), 6),
        "state_counts": dict(states),
        "reason_counts": dict(reasons),
        "warning_codes": warnings,
    }

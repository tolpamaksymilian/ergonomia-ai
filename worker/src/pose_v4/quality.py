"""Hierarchical global and local frame quality diagnostics for Pose V4."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import cv2
import numpy as np

try:
    from ..pose_v3.quality import FrameQualityState, ImageQuality, analyze_image_quality
except ImportError:  # pragma: no cover - standalone worker import mode
    from pose_v3.quality import FrameQualityState, ImageQuality, analyze_image_quality

from .graph import LimbState, PoseGraphFrame
from .hand_graph import HandGraphFrame, HandOcclusion


@dataclass(frozen=True)
class RegionQuality:
    available: bool
    blur_quality: float
    exposure_quality: float
    motion_blur: bool
    underexposed: bool
    overexposed: bool


@dataclass(frozen=True)
class ImageQualityV2:
    global_quality: RegionQuality
    body_quality: RegionQuality
    left_hand_quality: RegionQuality
    right_hand_quality: RegionQuality


@dataclass(frozen=True)
class FrameQualityV2:
    state: FrameQualityState
    score: float
    components: dict[str, float]
    reasons: tuple[str, ...]
    local_regions: dict[str, dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": "frame-quality-v2",
            "state": self.state.value,
            "score": round(self.score, 6),
            "components": {name: round(value, 6) for name, value in self.components.items()},
            "reasons": list(self.reasons),
            "local_regions": self.local_regions,
        }


def analyze_image_quality_v2(
    frame: np.ndarray,
    *,
    body_roi: tuple[int, int, int, int] | None,
    left_hand_roi: tuple[int, int, int, int] | None,
    right_hand_roi: tuple[int, int, int, int] | None,
) -> ImageQualityV2:
    return ImageQualityV2(
        global_quality=_region_quality(frame, None),
        body_quality=_region_quality(frame, body_roi),
        left_hand_quality=_region_quality(frame, left_hand_roi),
        right_hand_quality=_region_quality(frame, right_hand_roi),
    )


def build_frame_quality_v2(
    image: ImageQualityV2,
    *,
    body: PoseGraphFrame,
    left_hand: HandGraphFrame,
    right_hand: HandGraphFrame,
    tracking_identity_score: float,
) -> FrameQualityV2:
    limb_visibility = float(np.mean([
        1.0
        if limb.state == LimbState.VISIBLE
        else 0.68
        if limb.state == LimbState.PARTIAL
        else 0.30
        if limb.state in {LimbState.OCCLUDED, LimbState.PREDICTED_SHORT}
        else 0.0
        for limb in body.limbs.values()
    ])) if body.limbs else 0.0
    hands = (left_hand.quality + right_hand.quality) / 2.0
    blur = min(image.global_quality.blur_quality, image.body_quality.blur_quality if image.body_quality.available else 1.0)
    local_hand_blur_values = [
        region.blur_quality
        for region in (image.left_hand_quality, image.right_hand_quality)
        if region.available
    ]
    local_hand_blur = float(np.mean(local_hand_blur_values)) if local_hand_blur_values else 0.5
    exposure = min(image.global_quality.exposure_quality, image.body_quality.exposure_quality if image.body_quality.available else 1.0)
    occlusion_ratio = float(np.mean([
        limb.state in {LimbState.OCCLUDED, LimbState.OUT_OF_FRAME, LimbState.LOST}
        for limb in body.limbs.values()
    ])) if body.limbs else 1.0
    score = float(np.clip(
        0.24 * body.quality
        + 0.16 * body.body_coverage_ratio
        + 0.12 * limb_visibility
        + 0.10 * hands
        + 0.10 * blur
        + 0.07 * local_hand_blur
        + 0.08 * exposure
        + 0.08 * float(np.clip(tracking_identity_score, 0.0, 1.0))
        + 0.05 * (1.0 - occlusion_ratio),
        0.0,
        1.0,
    ))
    reasons: list[str] = []
    if image.global_quality.motion_blur or image.body_quality.motion_blur:
        reasons.append("HIGH_MOTION_BLUR")
    if image.global_quality.underexposed or image.body_quality.underexposed:
        reasons.append("UNDEREXPOSED")
    if image.global_quality.overexposed or image.body_quality.overexposed:
        reasons.append("OVEREXPOSED")
    if body.body_coverage_ratio < 0.55:
        reasons.append("LOW_BODY_COVERAGE")
    if occlusion_ratio > 0.50:
        reasons.append("EXCESSIVE_LIMB_OCCLUSION")
    if left_hand.occlusion_state in {HandOcclusion.OCCLUDED_BY_BODY, HandOcclusion.OCCLUDED_BY_OBJECT, HandOcclusion.OUT_OF_FRAME} or right_hand.occlusion_state in {HandOcclusion.OCCLUDED_BY_BODY, HandOcclusion.OCCLUDED_BY_OBJECT, HandOcclusion.OUT_OF_FRAME}:
        reasons.append("HAND_OCCLUSION")
    if body.quality <= 0.0:
        state = FrameQualityState.INVALID
    elif score >= 0.78:
        state = FrameQualityState.GOOD
    elif score >= 0.60:
        state = FrameQualityState.ACCEPTABLE
    else:
        state = FrameQualityState.POOR
    regions = {
        name: _serialize_region(region)
        for name, region in {
            "global": image.global_quality,
            "body": image.body_quality,
            "left_hand": image.left_hand_quality,
            "right_hand": image.right_hand_quality,
        }.items()
    }
    return FrameQualityV2(
        state,
        score,
        {
            "body": body.quality,
            "body_coverage": body.body_coverage_ratio,
            "limb_visibility": limb_visibility,
            "hands": hands,
            "blur": blur,
            "local_hand_blur": local_hand_blur,
            "exposure": exposure,
            "tracking": float(np.clip(tracking_identity_score, 0.0, 1.0)),
            "occlusion": 1.0 - occlusion_ratio,
        },
        tuple(dict.fromkeys(reasons)),
        regions,
    )


def summarize_quality_v2(
    frames: list[FrameQualityV2],
    *,
    track_losses: int,
    hand_assignment_switches: int,
    finger_rejections: int,
    holding_uncertain_seconds: float,
) -> dict[str, object]:
    if not frames:
        return {
            "version": "frame-quality-v2",
            "frame_count": 0,
            "mean_frame_quality": 0.0,
            "state_counts": {},
            "reason_counts": {},
            "warning_codes": ["LOW_BODY_COVERAGE"],
        }
    states = Counter(frame.state.value for frame in frames)
    reasons = Counter(reason for frame in frames for reason in frame.reasons)
    total = len(frames)
    warnings: list[str] = []
    if track_losses / total > 0.03 or track_losses >= 3:
        warnings.append("EXCESSIVE_TRACK_LOSS")
    if reasons["EXCESSIVE_LIMB_OCCLUSION"] / total > 0.25:
        warnings.append("EXCESSIVE_LIMB_OCCLUSION")
    if reasons["HAND_OCCLUSION"] / total > 0.30:
        warnings.append("EXCESSIVE_HAND_OCCLUSION")
    if hand_assignment_switches >= 3:
        warnings.append("EXCESSIVE_HAND_SWAP_RISK")
    if finger_rejections / max(1, total * 10) > 0.20:
        warnings.append("HIGH_FINGER_REJECTION")
    if reasons["LOW_BODY_COVERAGE"] / total > 0.25:
        warnings.append("LOW_BODY_COVERAGE")
    if reasons["HIGH_MOTION_BLUR"] / total > 0.25:
        warnings.append("HIGH_MOTION_BLUR")
    if holding_uncertain_seconds > 1.0:
        warnings.append("HOLDING_LOW_CONFIDENCE")
    return {
        "version": "frame-quality-v2",
        "frame_count": total,
        "mean_frame_quality": round(float(np.mean([frame.score for frame in frames])), 6),
        "state_counts": dict(states),
        "reason_counts": dict(reasons),
        "warning_codes": warnings,
    }


def _region_quality(frame: np.ndarray, roi: tuple[int, int, int, int] | None) -> RegionQuality:
    selected = frame
    available = True
    if roi is not None:
        x1, y1, x2, y2 = roi
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            available = False
            selected = np.zeros((0, 0, 3), dtype=np.uint8)
        else:
            selected = frame[y1:y2, x1:x2]
    if selected.size == 0:
        return RegionQuality(False, 0.0, 0.0, False, False, False)
    quality: ImageQuality = analyze_image_quality(selected)
    return RegionQuality(
        available,
        quality.blur_quality,
        quality.exposure_quality,
        quality.motion_blur,
        quality.underexposed,
        quality.overexposed,
    )


def _serialize_region(region: RegionQuality) -> dict[str, object]:
    return {
        "available": region.available,
        "blur_quality": round(region.blur_quality, 6),
        "exposure_quality": round(region.exposure_quality, 6),
        "motion_blur": region.motion_blur,
        "underexposed": region.underexposed,
        "overexposed": region.overexposed,
    }

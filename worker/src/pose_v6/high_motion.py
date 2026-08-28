"""High-motion evidence, directional gates and limb-crop planning for V6.6."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


LIMB_CHAINS: dict[str, tuple[int, ...]] = {
    "left_arm": (5, 7, 9),
    "right_arm": (6, 8, 10),
    "left_leg": (11, 13, 15, 17, 18, 19),
    "right_leg": (12, 14, 16, 20, 21, 22),
}
CORE_LIMB_CHAINS: dict[str, tuple[int, int, int]] = {
    name: (indexes[0], indexes[1], indexes[2])
    for name, indexes in LIMB_CHAINS.items()
}


@dataclass(frozen=True)
class MotionBlurEvidence:
    blur_score: float
    image_evidence_quality: float
    edge_energy: float
    roi_xyxy: tuple[int, int, int, int]

    @property
    def strongly_blurred(self) -> bool:
        return self.blur_score >= 0.68

    def to_dict(self) -> dict[str, object]:
        return {
            "motion_blur_score": round(self.blur_score, 6),
            "image_evidence_quality": round(self.image_evidence_quality, 6),
            "edge_energy": round(self.edge_energy, 6),
            "roi_xyxy": list(self.roi_xyxy),
            "score_is_probability": False,
        }


@dataclass(frozen=True)
class JointKinematics:
    velocity: tuple[float, float]
    acceleration: tuple[float, float]
    jerk: tuple[float, float]
    speed: float
    acceleration_magnitude: float
    jerk_magnitude: float


@dataclass(frozen=True)
class ReachGateDecision:
    accepted: bool
    reason: str | None
    bone_length_ratio_to_canonical: float | None
    directional_residual: float | None
    repaired_point: tuple[float, float] | None = None


@dataclass(frozen=True)
class LimbCrop:
    chain_name: str
    bbox_xyxy: np.ndarray
    scale: float
    direction: tuple[float, float]


class AnatomicalReachGate:
    """Canonical-length and velocity-direction aware candidate gate."""

    def __init__(
        self,
        *,
        minimum_length_ratio: float = 0.42,
        maximum_length_ratio: float = 1.62,
        maximum_directional_residual: float = 1.0,
    ) -> None:
        self.minimum_length_ratio = minimum_length_ratio
        self.maximum_length_ratio = maximum_length_ratio
        self.maximum_directional_residual = maximum_directional_residual

    def evaluate(
        self,
        parent: np.ndarray,
        candidate: np.ndarray,
        *,
        expected_length: float,
        predicted: np.ndarray | None,
        velocity: np.ndarray | None,
        body_scale: float,
        fast_motion: bool,
    ) -> ReachGateDecision:
        first = _point(parent)
        second = _point(candidate)
        if not math.isfinite(expected_length) or expected_length <= 1e-6:
            return ReachGateDecision(False, "MISSING_CANONICAL_LENGTH", None, None)
        vector = second - first
        length = float(np.linalg.norm(vector))
        ratio = length / expected_length
        if not math.isfinite(ratio) or ratio < self.minimum_length_ratio:
            return ReachGateDecision(False, "ANATOMICAL_REACH_TOO_SHORT", ratio, None)
        if ratio > self.maximum_length_ratio:
            # A high-confidence model miss is not accepted.  A bounded point is
            # supplied to the chain repair stage instead of drawing the spear.
            direction = vector / max(length, 1e-6)
            repaired = first + direction * expected_length
            return ReachGateDecision(
                False,
                "ANATOMICAL_REACH_EXCEEDED",
                ratio,
                None,
                (float(repaired[0]), float(repaired[1])),
            )
        directional_residual: float | None = None
        if predicted is not None:
            prediction = _point(predicted)
            residual = second - prediction
            motion = _point(velocity) if velocity is not None else np.zeros(2)
            speed = float(np.linalg.norm(motion))
            if speed > 1e-6:
                direction = motion / speed
                perpendicular = np.asarray((-direction[1], direction[0]))
                along = float(np.dot(residual, direction))
                across = float(np.dot(residual, perpendicular))
            else:
                along = 0.0
                across = float(np.linalg.norm(residual))
            # Fast motion expands mainly along the measured velocity, not as
            # an isotropic circle that could admit a point behind the worker.
            along_radius = max(expected_length * (1.05 if fast_motion else 0.62), body_scale * 0.04)
            across_radius = max(expected_length * (0.42 if fast_motion else 0.36), body_scale * 0.025)
            directional_residual = math.sqrt(
                (along / along_radius) ** 2 + (across / across_radius) ** 2
            )
            if directional_residual > self.maximum_directional_residual:
                return ReachGateDecision(
                    False,
                    "DIRECTIONAL_MOTION_GATE_REJECTED",
                    ratio,
                    directional_residual,
                )
        return ReachGateDecision(True, None, ratio, directional_residual)


def estimate_motion_blur(
    image_bgr: np.ndarray,
    bbox_xyxy: np.ndarray | Sequence[float] | None = None,
) -> MotionBlurEvidence:
    """Return a conservative technical blur indicator from local edge energy."""

    image = np.asarray(image_bgr)
    if image.ndim != 3 or image.shape[2] < 3 or image.size == 0:
        raise ValueError("motion blur input must be a non-empty BGR image")
    height, width = image.shape[:2]
    x1, y1, x2, y2 = _bounded_roi(bbox_xyxy, width, height)
    roi = image[y1:y2, x1:x2, :3].astype(np.float32)
    gray = roi[..., 0] * 0.114 + roi[..., 1] * 0.587 + roi[..., 2] * 0.299
    if min(gray.shape) < 3:
        edge_energy = 0.0
    else:
        horizontal = gray[:, 2:] - gray[:, :-2]
        vertical = gray[2:, :] - gray[:-2, :]
        edge_energy = float(
            0.5 * np.mean(np.square(horizontal))
            + 0.5 * np.mean(np.square(vertical))
        )
    # The scale is intentionally a technical quality heuristic, not a
    # calibrated probability.  High edge energy means sharper image evidence.
    quality = float(np.clip(edge_energy / (edge_energy + 520.0), 0.0, 1.0))
    blur = 1.0 - quality
    return MotionBlurEvidence(blur, quality, edge_energy, (x1, y1, x2, y2))


def compute_joint_kinematics(
    positions: Sequence[np.ndarray],
    timestamps: Sequence[float],
) -> list[JointKinematics]:
    """Compute dt-aware velocity, acceleration and jerk without FPS assumptions."""

    if len(positions) != len(timestamps):
        raise ValueError("kinematic positions and timestamps must have equal lengths")
    if not positions:
        return []
    values = np.stack([_point(value) for value in positions]).astype(np.float64)
    times = np.asarray(timestamps, dtype=np.float64)
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0.0):
        raise ValueError("kinematic timestamps must be finite and strictly increasing")
    velocity = _time_gradient(values, times)
    acceleration = _time_gradient(velocity, times)
    jerk = _time_gradient(acceleration, times)
    return [
        JointKinematics(
            (float(velocity[index, 0]), float(velocity[index, 1])),
            (float(acceleration[index, 0]), float(acceleration[index, 1])),
            (float(jerk[index, 0]), float(jerk[index, 1])),
            float(np.linalg.norm(velocity[index])),
            float(np.linalg.norm(acceleration[index])),
            float(np.linalg.norm(jerk[index])),
        )
        for index in range(len(values))
    ]


def build_limb_crops(
    chain_name: str,
    points: np.ndarray,
    scores: np.ndarray,
    *,
    previous_points: np.ndarray | None,
    body_scale: float,
    frame_width: int,
    frame_height: int,
    scales: Sequence[float],
    support_velocity: np.ndarray | None = None,
) -> tuple[LimbCrop, ...]:
    """Build contextual, motion-asymmetric crops around a complete chain."""

    indexes = LIMB_CHAINS[chain_name]
    current_points = np.asarray(points, dtype=np.float32)
    current_scores = np.asarray(scores, dtype=np.float32)
    visible = [
        index for index in indexes
        if index < len(current_scores)
        and current_scores[index] > 0.0
        and np.isfinite(current_points[index]).all()
    ]
    if len(visible) < 2:
        return ()
    selected = current_points[visible]
    minimum = selected.min(axis=0)
    maximum = selected.max(axis=0)
    center = (minimum + maximum) * 0.5
    span = np.maximum(maximum - minimum, body_scale * np.asarray((0.18, 0.20)))
    previous = np.asarray(previous_points, dtype=np.float32) if previous_points is not None else None
    velocity = np.zeros(2, dtype=np.float32)
    if previous is not None and previous.shape == current_points.shape:
        motion_indexes = [index for index in visible if np.isfinite(previous[index]).all()]
        if motion_indexes:
            velocity = np.median(current_points[motion_indexes] - previous[motion_indexes], axis=0)
    if support_velocity is not None:
        support = np.asarray(support_velocity, dtype=np.float32).reshape(-1)
        if support.size == 2 and np.isfinite(support).all():
            velocity = 0.45 * velocity + 0.55 * support
    speed = float(np.linalg.norm(velocity))
    direction = velocity / speed if speed > 1e-6 else np.zeros(2, dtype=np.float32)
    context = body_scale * (0.28 if "arm" in chain_name else 0.24)
    base_size = span + context * 2.0
    # Preserve substantial torso context so RTMW can maintain topology.
    base_size = np.maximum(base_size, body_scale * np.asarray((0.48, 0.52)))
    center = center + direction * min(speed * 0.45, body_scale * 0.10)
    crops: list[LimbCrop] = []
    for scale in scales:
        size = base_size * float(scale)
        start = center - size * 0.5
        end = center + size * 0.5
        bbox = np.asarray((
            np.clip(start[0], 0.0, max(0, frame_width - 1)),
            np.clip(start[1], 0.0, max(0, frame_height - 1)),
            np.clip(end[0], 0.0, max(0, frame_width - 1)),
            np.clip(end[1], 0.0, max(0, frame_height - 1)),
        ), dtype=np.float32)
        if bbox[2] - bbox[0] >= 8.0 and bbox[3] - bbox[1] >= 8.0:
            crops.append(LimbCrop(
                chain_name,
                bbox,
                float(scale),
                (float(direction[0]), float(direction[1])),
            ))
    return tuple(crops)


def expected_chain_lengths(
    chain_name: str,
    body_scale: float,
    learned_lengths: Mapping[str, float | None] | None = None,
) -> tuple[float, float]:
    names = (
        ("left_upper_arm", "left_forearm")
        if chain_name == "left_arm"
        else ("right_upper_arm", "right_forearm")
        if chain_name == "right_arm"
        else ("left_thigh", "left_lower_leg")
        if chain_name == "left_leg"
        else ("right_thigh", "right_lower_leg")
    )
    defaults = (0.185, 0.165) if "arm" in chain_name else (0.255, 0.245)
    output = []
    for name, ratio in zip(names, defaults):
        learned = learned_lengths.get(name) if learned_lengths is not None else None
        output.append(
            float(learned)
            if learned is not None and math.isfinite(float(learned)) and float(learned) > 1.0
            else max(2.0, float(body_scale) * ratio)
        )
    return output[0], output[1]


def validate_chain_candidate(
    chain_name: str,
    points: np.ndarray,
    scores: np.ndarray,
    *,
    expected_lengths: tuple[float, float],
    predicted_points: np.ndarray | None,
    previous_points: np.ndarray | None,
    body_scale: float,
    fast_motion: bool,
    minimum_score: float = 0.16,
) -> tuple[bool, tuple[ReachGateDecision, ReachGateDecision], float]:
    root, middle, end = CORE_LIMB_CHAINS[chain_name]
    values = np.asarray(points, dtype=np.float32)
    quality = np.asarray(scores, dtype=np.float32)
    if any(index >= len(quality) for index in (root, middle, end)):
        rejected = ReachGateDecision(False, "MISSING_CHAIN_JOINT", None, None)
        return False, (rejected, rejected), 0.0
    if any(
        quality[index] < minimum_score or not np.isfinite(values[index]).all()
        for index in (root, middle, end)
    ):
        rejected = ReachGateDecision(False, "LOW_CHAIN_QUALITY", None, None)
        return False, (rejected, rejected), 0.0
    predicted = np.asarray(predicted_points, dtype=np.float32) if predicted_points is not None else None
    previous = np.asarray(previous_points, dtype=np.float32) if previous_points is not None else None
    gate = AnatomicalReachGate()
    middle_velocity = values[middle] - previous[middle] if previous is not None else np.zeros(2)
    end_velocity = values[end] - previous[end] if previous is not None else np.zeros(2)
    first = gate.evaluate(
        values[root], values[middle], expected_length=expected_lengths[0],
        predicted=predicted[middle] if predicted is not None else None,
        velocity=middle_velocity, body_scale=body_scale, fast_motion=fast_motion,
    )
    second = gate.evaluate(
        values[middle], values[end], expected_length=expected_lengths[1],
        predicted=predicted[end] if predicted is not None else None,
        velocity=end_velocity, body_scale=body_scale, fast_motion=fast_motion,
    )
    return first.accepted and second.accepted, (first, second), float(
        min(quality[root], quality[middle], quality[end])
    )


def _time_gradient(values: np.ndarray, times: np.ndarray) -> np.ndarray:
    if len(values) == 1:
        return np.zeros_like(values)
    output = np.zeros_like(values)
    output[0] = (values[1] - values[0]) / (times[1] - times[0])
    output[-1] = (values[-1] - values[-2]) / (times[-1] - times[-2])
    for index in range(1, len(values) - 1):
        output[index] = (values[index + 1] - values[index - 1]) / (
            times[index + 1] - times[index - 1]
        )
    return output


def _bounded_roi(
    value: np.ndarray | Sequence[float] | None,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if value is None:
        return 0, 0, width, height
    bbox = np.asarray(value, dtype=np.float64).reshape(-1)
    if bbox.size != 4 or not np.isfinite(bbox).all():
        return 0, 0, width, height
    x1 = int(np.clip(math.floor(bbox[0]), 0, max(0, width - 1)))
    y1 = int(np.clip(math.floor(bbox[1]), 0, max(0, height - 1)))
    x2 = int(np.clip(math.ceil(bbox[2]), x1 + 1, width))
    y2 = int(np.clip(math.ceil(bbox[3]), y1 + 1, height))
    return x1, y1, x2, y2


def _point(value: np.ndarray | Sequence[float]) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if array.size != 2 or not np.isfinite(array).all():
        raise ValueError("point must contain two finite coordinates")
    return array


__all__ = [
    "AnatomicalReachGate",
    "CORE_LIMB_CHAINS",
    "JointKinematics",
    "LIMB_CHAINS",
    "LimbCrop",
    "MotionBlurEvidence",
    "ReachGateDecision",
    "build_limb_crops",
    "compute_joint_kinematics",
    "estimate_motion_blur",
    "expected_chain_lengths",
    "validate_chain_candidate",
]

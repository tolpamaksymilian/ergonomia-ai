"""Evidence-based fusion for the Pose V6.7 temporal expert pass.

TAR-ViTPose and RTMW are image measurements. TAPNext++ is deliberately used
only as temporal support: a tracker prediction can select between agreeing pose
measurements, but can never create an analytical joint by itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np


CORE_COCO_JOINTS: tuple[int, ...] = tuple(range(17))
CORE_LIMB_JOINTS: tuple[int, ...] = (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
CORE_COCO_NAMES: tuple[str, ...] = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee",
    "right_knee", "left_ankle", "right_ankle",
)


@dataclass(frozen=True)
class PoseMeasurement:
    point: tuple[float, float] | None
    quality: float
    source: str

    @property
    def valid(self) -> bool:
        if self.point is None or not math.isfinite(float(self.quality)):
            return False
        point = np.asarray(self.point, dtype=float)
        return (
            point.shape == (2,)
            and bool(np.isfinite(point).all())
            and float(self.quality) > 0.0
            and not bool(np.allclose(point, 0.0))
        )


@dataclass(frozen=True)
class TrackerEvidence:
    forward_point: tuple[float, float] | None
    backward_point: tuple[float, float] | None
    forward_visible: bool
    backward_visible: bool

    def consensus(self, *, maximum_distance: float) -> tuple[np.ndarray | None, float, str]:
        forward = _point(self.forward_point) if self.forward_visible else None
        backward = _point(self.backward_point) if self.backward_visible else None
        if forward is None and backward is None:
            return None, 0.0, "TRACKER_UNAVAILABLE"
        if forward is None:
            return backward, 0.35, "BACKWARD_ONLY"
        if backward is None:
            return forward, 0.35, "FORWARD_ONLY"
        distance = float(np.linalg.norm(forward - backward))
        if distance > maximum_distance:
            return None, 0.0, "FORWARD_BACKWARD_DISAGREEMENT"
        quality = float(np.clip(1.0 - distance / max(maximum_distance, 1e-6), 0.0, 1.0))
        return (forward + backward) * 0.5, quality, "FORWARD_BACKWARD_CONSENSUS"


@dataclass(frozen=True)
class JointFusionDecision:
    point: tuple[float, float] | None
    quality: float
    accepted: bool
    measurement_source: str | None
    provenance: str
    reason: str
    rtmw_tar_distance_ratio: float | None
    tracker_measurement_distance_ratio: float | None
    tracker_support: str

    def to_dict(self) -> dict[str, object]:
        return {
            "point": list(self.point) if self.point is not None else None,
            "quality": round(float(np.clip(self.quality, 0.0, 1.0)), 6),
            "accepted": self.accepted,
            "measurement_source": self.measurement_source,
            "provenance": self.provenance,
            "reason": self.reason,
            "rtmw_tar_distance_ratio": (
                round(self.rtmw_tar_distance_ratio, 6)
                if self.rtmw_tar_distance_ratio is not None else None
            ),
            "tracker_measurement_distance_ratio": (
                round(self.tracker_measurement_distance_ratio, 6)
                if self.tracker_measurement_distance_ratio is not None else None
            ),
            "tracker_support": self.tracker_support,
        }


def fuse_joint_measurements(
    rtmw: PoseMeasurement,
    tar: PoseMeasurement,
    tracker: TrackerEvidence,
    *,
    body_scale: float,
    minimum_measurement_quality: float = 0.16,
    pose_agreement_ratio: float = 0.18,
    tracker_agreement_ratio: float = 0.15,
    maximum_tracker_fb_ratio: float = 0.12,
) -> JointFusionDecision:
    """Fuse two pose measurements using bidirectional tracker consistency.

    Selection is based on independent agreement, not on the largest confidence
    number. When neither pose model provides a valid image measurement the
    result is rejected even if the tracker remains visible.
    """

    scale = max(float(body_scale), 1.0)
    rtmw_valid = rtmw.valid and rtmw.quality >= minimum_measurement_quality
    tar_valid = tar.valid and tar.quality >= minimum_measurement_quality
    track_point, track_quality, track_reason = tracker.consensus(
        maximum_distance=scale * maximum_tracker_fb_ratio,
    )
    reliable_bidirectional_track = track_reason == "FORWARD_BACKWARD_CONSENSUS"
    if not rtmw_valid and not tar_valid:
        return JointFusionDecision(
            None, 0.0, False, None, "NO_IMAGE_MEASUREMENT",
            "TRACKER_CANNOT_REPLACE_POSE_MEASUREMENT", None, None, track_reason,
        )

    rtmw_point = _point(rtmw.point) if rtmw_valid else None
    tar_point = _point(tar.point) if tar_valid else None
    pose_distance_ratio = (
        float(np.linalg.norm(rtmw_point - tar_point) / scale)
        if rtmw_point is not None and tar_point is not None else None
    )
    pose_agrees = (
        pose_distance_ratio is not None and pose_distance_ratio <= pose_agreement_ratio
    )

    if rtmw_point is not None and tar_point is not None and pose_agrees:
        weights = np.asarray([rtmw.quality, tar.quality], dtype=np.float64)
        blended = np.average(np.stack([rtmw_point, tar_point]), axis=0, weights=weights)
        tracker_distance = _distance_ratio(blended, track_point, scale)
        tracker_supports = (
            reliable_bidirectional_track
            and tracker_distance is not None
            and tracker_distance <= tracker_agreement_ratio
        )
        quality = min(float(max(rtmw.quality, tar.quality)), 0.96)
        if tracker_supports:
            quality = min(0.99, quality * (0.90 + 0.10 * track_quality))
        return _accepted(
            blended,
            quality,
            "RTMW+TAR",
            "RTMW_TAR_MEASUREMENT_CONSENSUS" + (
                "+POINT_TRACK_SUPPORT" if tracker_supports else ""
            ),
            "POSE_MODELS_AGREE",
            pose_distance_ratio,
            tracker_distance,
            track_reason,
        )

    candidates: list[tuple[PoseMeasurement, np.ndarray, float | None]] = []
    if rtmw_point is not None:
        candidates.append((rtmw, rtmw_point, _distance_ratio(rtmw_point, track_point, scale)))
    if tar_point is not None:
        candidates.append((tar, tar_point, _distance_ratio(tar_point, track_point, scale)))

    supported = [
        item for item in candidates
        if reliable_bidirectional_track
        and item[2] is not None
        and item[2] <= tracker_agreement_ratio
    ]
    if len(supported) == 1:
        measurement, point, distance = supported[0]
        return _accepted(
            point,
            min(0.97, float(measurement.quality) * (0.86 + 0.14 * track_quality)),
            measurement.source,
            f"{measurement.source}_MEASUREMENT+POINT_TRACK_SUPPORT",
            "POSE_DISAGREEMENT_RESOLVED_BY_BIDIRECTIONAL_TRACK",
            pose_distance_ratio,
            distance,
            track_reason,
        )
    if len(supported) == 2:
        # Both candidates are near a reliable track. Select the closer image
        # measurement; never average across a potentially wrong limb.
        measurement, point, distance = min(supported, key=lambda item: float(item[2]))
        return _accepted(
            point,
            min(0.95, float(measurement.quality) * (0.84 + 0.16 * track_quality)),
            measurement.source,
            f"{measurement.source}_MEASUREMENT+POINT_TRACK_SUPPORT",
            "CLOSEST_IMAGE_MEASUREMENT_TO_TRACK_CONSENSUS",
            pose_distance_ratio,
            distance,
            track_reason,
        )

    if len(candidates) == 1:
        measurement, point, tracker_distance = candidates[0]
        # A single strong image measurement may survive without tracker support;
        # it remains explicitly lower quality and is still anatomy-gated later.
        if measurement.quality >= 0.60:
            return _accepted(
                point,
                min(0.82, float(measurement.quality) * 0.82),
                measurement.source,
                f"{measurement.source}_MEASUREMENT_UNCORROBORATED",
                "SINGLE_STRONG_IMAGE_MEASUREMENT",
                pose_distance_ratio,
                tracker_distance,
                track_reason,
            )

    return JointFusionDecision(
        None, 0.0, False, None, "CONFLICTING_IMAGE_EVIDENCE",
        "POSE_MODELS_DISAGREE_WITHOUT_TRACK_CONSENSUS",
        pose_distance_ratio, None, track_reason,
    )


def fuse_core_frame(
    rtmw_points: np.ndarray,
    rtmw_scores: np.ndarray,
    tar_points: np.ndarray,
    tar_scores: np.ndarray,
    tracker_evidence: Mapping[int, TrackerEvidence],
    *,
    body_scale: float,
    joint_indexes: tuple[int, ...] = CORE_LIMB_JOINTS,
) -> dict[int, JointFusionDecision]:
    output: dict[int, JointFusionDecision] = {}
    for joint in joint_indexes:
        output[joint] = fuse_joint_measurements(
            _measurement(rtmw_points, rtmw_scores, joint, "RTMW"),
            _measurement(tar_points, tar_scores, joint, "TAR_TEMPORAL"),
            tracker_evidence.get(joint, TrackerEvidence(None, None, False, False)),
            body_scale=body_scale,
        )
    return output


def _measurement(
    points: np.ndarray, scores: np.ndarray, index: int, source: str,
) -> PoseMeasurement:
    if index >= len(points) or index >= len(scores):
        return PoseMeasurement(None, 0.0, source)
    point = np.asarray(points[index], dtype=float).reshape(-1)
    if point.size != 2 or not np.isfinite(point).all():
        return PoseMeasurement(None, 0.0, source)
    return PoseMeasurement((float(point[0]), float(point[1])), float(scores[index]), source)


def _accepted(
    point: np.ndarray,
    quality: float,
    source: str,
    provenance: str,
    reason: str,
    pose_distance: float | None,
    tracker_distance: float | None,
    tracker_support: str,
) -> JointFusionDecision:
    return JointFusionDecision(
        (float(point[0]), float(point[1])), float(np.clip(quality, 0.0, 1.0)),
        True, source, provenance, reason, pose_distance, tracker_distance,
        tracker_support,
    )


def _point(value: tuple[float, float] | None) -> np.ndarray | None:
    if value is None:
        return None
    point = np.asarray(value, dtype=np.float32).reshape(-1)
    if point.size != 2 or not np.isfinite(point).all():
        return None
    return point


def _distance_ratio(
    first: np.ndarray, second: np.ndarray | None, scale: float,
) -> float | None:
    if second is None:
        return None
    return float(np.linalg.norm(first - second) / max(scale, 1.0))


__all__ = [
    "CORE_COCO_JOINTS",
    "CORE_COCO_NAMES",
    "CORE_LIMB_JOINTS",
    "JointFusionDecision",
    "PoseMeasurement",
    "TrackerEvidence",
    "fuse_core_frame",
    "fuse_joint_measurements",
]

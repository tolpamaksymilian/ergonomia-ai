"""SAM2-independent person silhouette evidence for Pose V6.8.

The mask answers only where the tracked person is visible.  It never invents
joint measurements and its influence is disabled when identity/drift checks
fail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import cv2
import numpy as np


DISTAL_JOINTS = {7, 8, 9, 10, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}
WRIST_JOINTS = {9, 10}
ANKLE_JOINTS = {15, 16}
ELBOW_JOINTS = {7, 8}
KNEE_JOINTS = {13, 14}
TORSO_JOINTS = {5, 6, 11, 12}


@dataclass(frozen=True)
class PackedPersonMask:
    height: int
    width: int
    packed: bytes
    contour: tuple[tuple[int, int], ...]
    area_ratio: float
    centroid: tuple[float, float] | None
    bbox_xyxy: tuple[int, int, int, int] | None
    logit_confidence: float

    @classmethod
    def from_mask(
        cls,
        mask: np.ndarray,
        *,
        logit_confidence: float = 1.0,
    ) -> "PackedPersonMask":
        values = np.asarray(mask, dtype=bool)
        if values.ndim != 2 or values.size == 0:
            raise ValueError("person mask must be a non-empty two-dimensional array")
        height, width = values.shape
        binary = values.astype(np.uint8)
        ys, xs = np.nonzero(binary)
        if len(xs):
            bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            centroid = (float(xs.mean()), float(ys.mean()))
        else:
            bbox = None
            centroid = None
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            main = max(contours, key=cv2.contourArea)
            epsilon = max(1.0, 0.0025 * cv2.arcLength(main, True))
            simplified = cv2.approxPolyDP(main, epsilon, True).reshape(-1, 2)
            contour = tuple((int(point[0]), int(point[1])) for point in simplified)
        else:
            contour = ()
        return cls(
            height=height,
            width=width,
            packed=np.packbits(values.reshape(-1)).tobytes(),
            contour=contour,
            area_ratio=float(values.mean()),
            centroid=centroid,
            bbox_xyxy=bbox,
            logit_confidence=float(np.clip(logit_confidence, 0.0, 1.0)),
        )

    def unpack(self) -> np.ndarray:
        count = self.height * self.width
        return np.unpackbits(np.frombuffer(self.packed, dtype=np.uint8), count=count).reshape(
            self.height,
            self.width,
        ).astype(bool)


@dataclass(frozen=True)
class MaskQuality:
    mask_confidence: float
    mask_area_stability: float
    mask_centroid_stability: float
    bbox_mask_agreement: float
    temporal_mask_iou: float | None
    mask_track_identity_confidence: float
    drift_detected: bool
    influence: float
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "mask_confidence": round(self.mask_confidence, 6),
            "mask_area_stability": round(self.mask_area_stability, 6),
            "mask_centroid_stability": round(self.mask_centroid_stability, 6),
            "bbox_mask_agreement": round(self.bbox_mask_agreement, 6),
            "temporal_mask_iou": (
                round(self.temporal_mask_iou, 6)
                if self.temporal_mask_iou is not None else None
            ),
            "mask_track_identity_confidence": round(
                self.mask_track_identity_confidence, 6,
            ),
            "mask_track_drift": self.drift_detected,
            "pose_influence": round(self.influence, 6),
            "rejection_reasons": list(self.rejection_reasons),
            "quality_is_accuracy": False,
        }


@dataclass(frozen=True)
class PersonSilhouetteFrame:
    source_frame_index: int
    timestamp_seconds: float
    person_track_id: str
    mask: PackedPersonMask | None
    quality: MaskQuality
    reanchored: bool = False

    @property
    def valid(self) -> bool:
        return self.mask is not None and self.quality.influence > 0.0

    def to_dict(self, *, include_contour: bool = True) -> dict[str, object]:
        return {
            "source_frame_index": self.source_frame_index,
            "timestamp_seconds": round(self.timestamp_seconds, 6),
            "person_track_id": self.person_track_id,
            "valid": self.valid,
            "reanchored": self.reanchored,
            "quality": self.quality.to_dict(),
            "mask_area_ratio": (
                round(self.mask.area_ratio, 6) if self.mask is not None else None
            ),
            "mask_bbox_xyxy": (
                list(self.mask.bbox_xyxy)
                if self.mask is not None and self.mask.bbox_xyxy is not None else None
            ),
            "person_contour": (
                [list(point) for point in self.mask.contour]
                if include_contour and self.mask is not None else None
            ),
            "mask_is_pose_measurement": False,
        }


@dataclass(frozen=True)
class JointMaskEvidence:
    joint_index: int
    distance_px: float | None
    distance_normalized: float | None
    tolerance_px: float
    support: str
    penalty: float

    def to_dict(self) -> dict[str, object]:
        return {
            "joint_index": self.joint_index,
            "joint_mask_distance_px": (
                round(self.distance_px, 4) if self.distance_px is not None else None
            ),
            "joint_mask_distance_normalized": (
                round(self.distance_normalized, 6)
                if self.distance_normalized is not None else None
            ),
            "dynamic_tolerance_px": round(self.tolerance_px, 4),
            "support": self.support,
            "candidate_penalty": round(self.penalty, 6),
        }


@dataclass(frozen=True)
class BoneMaskEvidence:
    bone_name: str
    support_ratio: float | None
    outside_corridor: bool
    tolerance_px: float

    def to_dict(self) -> dict[str, object]:
        return {
            "bone_name": self.bone_name,
            "bone_silhouette_support_ratio": (
                round(self.support_ratio, 6)
                if self.support_ratio is not None else None
            ),
            "outside_body_corridor": self.outside_corridor,
            "dynamic_tolerance_px": round(self.tolerance_px, 4),
        }


@dataclass(frozen=True)
class SkeletonSilhouetteEvidence:
    joint_evidence: tuple[JointMaskEvidence, ...]
    bone_evidence: tuple[BoneMaskEvidence, ...]
    alignment_score: float | None
    mask_influence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "joint_evidence": [item.to_dict() for item in self.joint_evidence],
            "bone_evidence": [item.to_dict() for item in self.bone_evidence],
            "skeleton_to_silhouette_alignment_score": (
                round(self.alignment_score, 6)
                if self.alignment_score is not None else None
            ),
            "mask_influence": round(self.mask_influence, 6),
            "alignment_score_is_accuracy": False,
        }


def assess_mask_sequence(
    masks: Sequence[PackedPersonMask | None],
    expected_bboxes: Sequence[Sequence[float] | np.ndarray | None],
    torso_points: Sequence[np.ndarray | None],
    body_scales: Sequence[float],
    *,
    source_frame_indexes: Sequence[int],
    timestamps: Sequence[float],
    track_ids: Sequence[str],
    anchor_indexes: set[int] | frozenset[int],
    minimum_mask_confidence: float = 0.30,
    minimum_bbox_agreement: float = 0.20,
    drift_centroid_scale_ratio: float = 0.42,
    drift_area_ratio_minimum: float = 0.48,
    drift_area_ratio_maximum: float = 1.90,
) -> tuple[PersonSilhouetteFrame, ...]:
    count = len(masks)
    inputs = (
        expected_bboxes, torso_points, body_scales, source_frame_indexes,
        timestamps, track_ids,
    )
    if any(len(values) != count for values in inputs):
        raise ValueError("mask sequence inputs must have equal lengths")
    output: list[PersonSilhouetteFrame] = []
    previous: PackedPersonMask | None = None
    previous_track: str | None = None
    for index, mask in enumerate(masks):
        reasons: list[str] = []
        # A prompt on this exact frame starts a new temporal mask segment.
        # Identity/bbox/torso checks still apply, but pre-anchor area and
        # centroid history must not keep a recovered track in drift forever.
        if index in anchor_indexes:
            previous = None
        expected_bbox = _bbox(expected_bboxes[index])
        body_scale = max(1.0, float(body_scales[index]))
        if mask is None or mask.bbox_xyxy is None or mask.centroid is None:
            quality = MaskQuality(0.0, 0.0, 0.0, 0.0, None, 0.0, True, 0.0, ("MASK_EMPTY",))
            previous = None
        else:
            bbox_agreement = _bbox_iou(mask.bbox_xyxy, expected_bbox)
            temporal_iou = _packed_iou(previous, mask) if previous is not None else None
            if previous is not None and previous.area_ratio > 1e-9:
                area_change = mask.area_ratio / previous.area_ratio
                area_stability = math.exp(-abs(math.log(max(area_change, 1e-9))))
            else:
                area_change = 1.0
                area_stability = 1.0
            if previous is not None and previous.centroid is not None:
                shift = math.dist(previous.centroid, mask.centroid) / body_scale
                centroid_stability = float(math.exp(-shift * 2.0))
            else:
                shift = 0.0
                centroid_stability = 1.0
            torso_support = _torso_support(mask, torso_points[index])
            identity = float(np.clip(0.55 * bbox_agreement + 0.45 * torso_support, 0.0, 1.0))
            if mask.logit_confidence < minimum_mask_confidence:
                reasons.append("MASK_LOW_CONFIDENCE")
            if bbox_agreement < minimum_bbox_agreement:
                reasons.append("MASK_BBOX_DISAGREEMENT")
            if previous is not None and (
                area_change < drift_area_ratio_minimum
                or area_change > drift_area_ratio_maximum
            ):
                reasons.append("MASK_AREA_JUMP")
            if previous is not None and shift > drift_centroid_scale_ratio:
                reasons.append("MASK_CENTROID_JUMP")
            if torso_support < 0.50:
                reasons.append("MASK_TORSO_DISAGREEMENT")
            if previous_track is not None and track_ids[index] != previous_track:
                reasons.append("PERSON_TRACK_ID_CHANGED")
            if reasons:
                reasons.append("MASK_TRACK_DRIFT")
            drift = bool(reasons)
            confidence = float(np.clip(
                0.24 * mask.logit_confidence
                + 0.20 * area_stability
                + 0.16 * centroid_stability
                + 0.20 * bbox_agreement
                + 0.20 * identity,
                0.0,
                1.0,
            ))
            influence = 0.0 if drift else confidence
            quality = MaskQuality(
                confidence,
                area_stability,
                centroid_stability,
                bbox_agreement,
                temporal_iou,
                identity,
                drift,
                influence,
                tuple(reasons),
            )
            previous = mask
        output.append(PersonSilhouetteFrame(
            source_frame_index=int(source_frame_indexes[index]),
            timestamp_seconds=float(timestamps[index]),
            person_track_id=str(track_ids[index]),
            mask=mask,
            quality=quality,
            reanchored=index in anchor_indexes,
        ))
        previous_track = str(track_ids[index])
    return tuple(output)


def signed_distance_field(mask: PackedPersonMask | np.ndarray) -> np.ndarray:
    values = mask.unpack() if isinstance(mask, PackedPersonMask) else np.asarray(mask, dtype=bool)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("signed distance field requires a non-empty 2D mask")
    inside = cv2.distanceTransform(values.astype(np.uint8), cv2.DIST_L2, 5)
    outside = cv2.distanceTransform((~values).astype(np.uint8), cv2.DIST_L2, 5)
    return inside.astype(np.float32) - outside.astype(np.float32)


def evaluate_skeleton_against_silhouette(
    frame: PersonSilhouetteFrame,
    points: np.ndarray,
    scores: np.ndarray,
    bones: Mapping[str, tuple[int, int]],
    *,
    body_scale: float,
    motion_blur: float,
    motion_state: str,
    occluded: bool,
) -> SkeletonSilhouetteEvidence:
    values = np.asarray(points, dtype=np.float32)
    quality = np.asarray(scores, dtype=np.float32)
    if not frame.valid or frame.mask is None:
        return SkeletonSilhouetteEvidence((), (), None, 0.0)
    distance = signed_distance_field(frame.mask)
    joint_output: list[JointMaskEvidence] = []
    for index in range(min(len(values), len(quality))):
        tolerance = dynamic_mask_tolerance(
            index,
            body_scale=body_scale,
            motion_blur=motion_blur,
            motion_state=motion_state,
            mask_confidence=frame.quality.mask_confidence,
            occluded=occluded,
        )
        if quality[index] <= 0.0 or not np.isfinite(values[index]).all():
            joint_output.append(JointMaskEvidence(index, None, None, tolerance, "missing", 0.0))
            continue
        sampled = _sample_distance(distance, values[index])
        normalized = sampled / max(1.0, body_scale)
        if sampled >= 0.0:
            support, penalty = "inside", 0.0
        elif sampled >= -0.45 * tolerance:
            support, penalty = "near_boundary", 0.05
        elif sampled >= -tolerance:
            support, penalty = "possible", 0.22
        else:
            support = "far_outside"
            penalty = float(np.clip(abs(sampled) / max(tolerance, 1.0), 0.65, 1.0))
        joint_output.append(JointMaskEvidence(
            index, sampled, normalized, tolerance, support, penalty,
        ))
    bone_output: list[BoneMaskEvidence] = []
    for name, (first, second) in bones.items():
        if any(index >= len(quality) for index in (first, second)) or any(
            quality[index] <= 0.0 or not np.isfinite(values[index]).all()
            for index in (first, second)
        ):
            bone_output.append(BoneMaskEvidence(name, None, False, 0.0))
            continue
        tolerance = max(
            dynamic_mask_tolerance(
                first,
                body_scale=body_scale,
                motion_blur=motion_blur,
                motion_state=motion_state,
                mask_confidence=frame.quality.mask_confidence,
                occluded=occluded,
            ),
            dynamic_mask_tolerance(
                second,
                body_scale=body_scale,
                motion_blur=motion_blur,
                motion_state=motion_state,
                mask_confidence=frame.quality.mask_confidence,
                occluded=occluded,
            ),
        )
        ratio = bone_silhouette_support_ratio(
            distance, values[first], values[second], tolerance_px=tolerance,
        )
        bone_output.append(BoneMaskEvidence(name, ratio, ratio < 0.55, tolerance))
    valid_joints = [item for item in joint_output if item.distance_px is not None]
    valid_bones = [item for item in bone_output if item.support_ratio is not None]
    joint_support = (
        np.mean([1.0 - item.penalty for item in valid_joints])
        if valid_joints else 0.0
    )
    bone_support = (
        np.mean([float(item.support_ratio) for item in valid_bones])
        if valid_bones else 0.0
    )
    alignment = float(np.clip(0.45 * joint_support + 0.55 * bone_support, 0.0, 1.0))
    return SkeletonSilhouetteEvidence(
        tuple(joint_output), tuple(bone_output), alignment, frame.quality.influence,
    )


def dynamic_mask_tolerance(
    joint_index: int,
    *,
    body_scale: float,
    motion_blur: float,
    motion_state: str,
    mask_confidence: float,
    occluded: bool,
) -> float:
    ratio = 0.035 if joint_index in TORSO_JOINTS else 0.070 if joint_index in DISTAL_JOINTS else 0.050
    ratio += 0.040 * float(np.clip(motion_blur, 0.0, 1.0))
    if motion_state in {"FAST_MOTION", "EXTREME_MOTION"}:
        ratio += 0.035
    if occluded:
        ratio += 0.055
    ratio += 0.030 * (1.0 - float(np.clip(mask_confidence, 0.0, 1.0)))
    return max(2.0, float(body_scale) * ratio)


def bone_silhouette_support_ratio(
    distance_field: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    *,
    tolerance_px: float,
    sample_count: int = 41,
) -> float:
    first = np.asarray(start, dtype=np.float64).reshape(-1)
    second = np.asarray(end, dtype=np.float64).reshape(-1)
    if first.size != 2 or second.size != 2 or not np.isfinite([*first, *second]).all():
        raise ValueError("bone endpoints must contain finite 2D coordinates")
    count = max(3, int(sample_count))
    samples = first[None, :] + (second - first)[None, :] * np.linspace(0.0, 1.0, count)[:, None]
    support = [
        _sample_distance(distance_field, point) >= -float(tolerance_px)
        for point in samples
    ]
    return float(np.mean(support))


def summarize_silhouette_alignment(
    silhouettes: Sequence[PersonSilhouetteFrame],
    evidence: Sequence[SkeletonSilhouetteEvidence],
) -> dict[str, object]:
    if len(silhouettes) != len(evidence):
        raise ValueError("silhouette and evidence sequences must have equal lengths")
    valid_masks = [frame for frame in silhouettes if frame.valid]
    alignments = [item.alignment_score for item in evidence if item.alignment_score is not None]
    joints = [joint for item in evidence for joint in item.joint_evidence]
    bones = [bone for item in evidence for bone in item.bone_evidence]
    far_counts = {
        "wrist_far_outside_silhouette_count": sum(
            item.joint_index in WRIST_JOINTS and item.support == "far_outside" for item in joints
        ),
        "ankle_far_outside_silhouette_count": sum(
            item.joint_index in ANKLE_JOINTS and item.support == "far_outside" for item in joints
        ),
        "elbow_far_outside_silhouette_count": sum(
            item.joint_index in ELBOW_JOINTS and item.support == "far_outside" for item in joints
        ),
        "knee_far_outside_silhouette_count": sum(
            item.joint_index in KNEE_JOINTS and item.support == "far_outside" for item in joints
        ),
    }
    return {
        "person_mask_coverage_ratio": round(len(valid_masks) / max(1, len(silhouettes)), 6),
        "person_mask_temporal_iou": round(float(np.mean([
            frame.quality.temporal_mask_iou for frame in silhouettes
            if frame.quality.temporal_mask_iou is not None
        ])), 6) if any(frame.quality.temporal_mask_iou is not None for frame in silhouettes) else None,
        "mask_track_drift_count": sum(frame.quality.drift_detected for frame in silhouettes),
        "joint_inside_body_support_ratio": _support_ratio(joints, {"inside"}),
        "joint_near_body_support_ratio": _support_ratio(joints, {"inside", "near_boundary", "possible"}),
        "joint_far_outside_body_count": sum(item.support == "far_outside" for item in joints),
        "bone_silhouette_support_ratio": round(float(np.mean([
            item.support_ratio for item in bones if item.support_ratio is not None
        ])), 6) if any(item.support_ratio is not None for item in bones) else None,
        "bone_outside_body_corridor_count": sum(item.outside_corridor for item in bones),
        "skeleton_to_silhouette_alignment_score": round(float(np.mean(alignments)), 6) if alignments else None,
        "alignment_score_is_accuracy": False,
        **far_counts,
    }


def draw_silhouette_overlay(
    image_bgr: np.ndarray,
    frame: PersonSilhouetteFrame,
    *,
    debug: bool,
    standard_fill_alpha: float = 0.035,
    debug_fill_alpha: float = 0.16,
) -> np.ndarray:
    if frame.mask is None or not frame.mask.contour:
        return image_bgr
    output = image_bgr
    contour = np.asarray(frame.mask.contour, dtype=np.int32).reshape(-1, 1, 2)
    color = (60, 220, 215) if frame.valid else (50, 120, 245)
    alpha = debug_fill_alpha if debug else standard_fill_alpha
    if alpha > 0.0 and frame.valid:
        fill = output.copy()
        cv2.drawContours(fill, [contour], -1, color, thickness=cv2.FILLED)
        cv2.addWeighted(fill, alpha, output, 1.0 - alpha, 0.0, dst=output)
    cv2.drawContours(output, [contour], -1, color, 2 if debug else 1, cv2.LINE_AA)
    return output


def _support_ratio(items: Sequence[JointMaskEvidence], accepted: set[str]) -> float | None:
    valid = [item for item in items if item.distance_px is not None]
    return round(sum(item.support in accepted for item in valid) / len(valid), 6) if valid else None


def _sample_distance(field: np.ndarray, point: np.ndarray) -> float:
    x = int(np.clip(round(float(point[0])), 0, field.shape[1] - 1))
    y = int(np.clip(round(float(point[1])), 0, field.shape[0] - 1))
    return float(field[y, x])


def _bbox(value: Sequence[float] | np.ndarray | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    values = np.asarray(value, dtype=np.float64).reshape(-1)
    if values.size != 4 or not np.isfinite(values).all() or values[2] <= values[0] or values[3] <= values[1]:
        return None
    return tuple(float(item) for item in values)


def _bbox_iou(
    first: Sequence[float] | None,
    second: Sequence[float] | None,
) -> float:
    if first is None or second is None:
        return 0.0
    x1 = max(first[0], second[0]); y1 = max(first[1], second[1])
    x2 = min(first[2], second[2]); y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_first + area_second - intersection
    return float(intersection / union) if union > 1e-9 else 0.0


def _packed_iou(first: PackedPersonMask, second: PackedPersonMask) -> float:
    if (first.height, first.width) != (second.height, second.width):
        return 0.0
    one = first.unpack(); two = second.unpack()
    union = np.logical_or(one, two)
    return float(np.logical_and(one, two).sum() / union.sum()) if np.any(union) else 1.0


def _torso_support(mask: PackedPersonMask, torso: np.ndarray | None) -> float:
    if torso is None:
        return 0.0
    points = np.asarray(torso, dtype=np.float64).reshape(-1, 2)
    valid = points[np.isfinite(points).all(axis=1)]
    if not len(valid):
        return 0.0
    values = mask.unpack()
    supported = 0
    for x, y in valid:
        ix = int(np.clip(round(x), 0, mask.width - 1))
        iy = int(np.clip(round(y), 0, mask.height - 1))
        supported += bool(values[iy, ix])
    return supported / len(valid)


__all__ = [
    "BoneMaskEvidence",
    "JointMaskEvidence",
    "MaskQuality",
    "PackedPersonMask",
    "PersonSilhouetteFrame",
    "SkeletonSilhouetteEvidence",
    "assess_mask_sequence",
    "bone_silhouette_support_ratio",
    "draw_silhouette_overlay",
    "dynamic_mask_tolerance",
    "evaluate_skeleton_against_silhouette",
    "signed_distance_field",
    "summarize_silhouette_alignment",
]

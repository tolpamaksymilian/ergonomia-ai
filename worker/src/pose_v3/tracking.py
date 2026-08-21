"""Geometry-only identity tracking state machine for Pose Worker V0.3."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class TrackingState(StrEnum):
    TRACKED = "TRACKED"
    PARTIAL = "PARTIAL"
    OCCLUDED = "OCCLUDED"
    LOST = "LOST"
    REACQUIRING = "REACQUIRING"


@dataclass(frozen=True)
class TrackingConfig:
    keypoint_threshold: float = 0.78
    reacquire_confirm_frames: int = 3
    lost_after_missing_frames: int = 2
    maximum_center_jump_ratio: float = 0.30
    maximum_scale_change_ratio: float = 0.55
    edge_margin_ratio: float = 0.025
    partial_minimum_valid_joints: int = 5
    occluded_minimum_valid_joints: int = 8
    locked_keypoint_threshold_ratio: float = 0.90


@dataclass(frozen=True)
class TrackingDecision:
    state: TrackingState
    accept_pose: bool
    identity_score: float
    valid_joint_count: int
    partial: bool
    reasons: tuple[str, ...]


def bbox_iou(first: np.ndarray, second: np.ndarray) -> float:
    x1 = max(float(first[0]), float(second[0]))
    y1 = max(float(first[1]), float(second[1]))
    x2 = min(float(first[2]), float(second[2]))
    y2 = min(float(first[3]), float(second[3]))
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, float(first[2] - first[0])) * max(
        0.0, float(first[3] - first[1])
    )
    second_area = max(0.0, float(second[2] - second[0])) * max(
        0.0, float(second[3] - second[1])
    )
    union = first_area + second_area - intersection
    return intersection / union if union > 1e-8 else 0.0


class PersonTrackingStateMachine:
    """Prevents stale pose continuation and requires confirmed reacquisition."""

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config
        self.state = TrackingState.LOST
        self.last_bbox: np.ndarray | None = None
        self.last_body_signature: np.ndarray | None = None
        self.missing_frames = 0
        self.reacquire_frames = 0
        self.track_loss_count = 0
        self.reacquisition_count = 0
        self._ever_tracked = False

    def update(
        self,
        *,
        detected: bool,
        bbox: np.ndarray | None,
        points: np.ndarray,
        scores: np.ndarray,
        frame_width: int,
        frame_height: int,
        candidate_quality: float,
        motion_gate_multiplier: float = 1.0,
    ) -> TrackingDecision:
        if not detected or bbox is None or not _valid_bbox(bbox):
            return self._handle_missing()

        observation_threshold = self.config.keypoint_threshold * (
            self.config.locked_keypoint_threshold_ratio
            if self.state not in {TrackingState.LOST, TrackingState.REACQUIRING}
            else 1.0
        )
        valid_count, partial = _visibility_state(
            points,
            scores,
            observation_threshold,
            frame_width,
            frame_height,
            self.config.edge_margin_ratio,
        )
        if valid_count < self.config.partial_minimum_valid_joints:
            return self._handle_missing(reason="INSUFFICIENT_VISIBLE_JOINTS")

        body_signature = _body_signature(points, scores, bbox, observation_threshold)
        signature_similarity = _signature_similarity(
            body_signature,
            self.last_body_signature,
        )
        gate_multiplier = max(1.0, float(motion_gate_multiplier))
        identity_score = self._identity_score(
            bbox,
            frame_width,
            frame_height,
            signature_similarity,
            gate_multiplier,
        )
        scale_change = (
            _bbox_scale_change(np.asarray(bbox, dtype=np.float32), self.last_bbox)
            if self.last_bbox is not None
            else 0.0
        )
        center_jump = (
            _bbox_center_distance_ratio(
                np.asarray(bbox, dtype=np.float32),
                self.last_bbox,
                frame_width,
                frame_height,
            )
            if self.last_bbox is not None
            else 0.0
        )
        if (
            self.state not in {TrackingState.LOST, TrackingState.REACQUIRING}
            and self.last_bbox is not None
            and bbox_iou(np.asarray(bbox, dtype=np.float32), self.last_bbox) < 0.01
            and center_jump > self.config.maximum_center_jump_ratio * gate_multiplier
        ):
            return self._handle_missing(reason="BBOX_CENTER_JUMP")
        if (
            self.state not in {TrackingState.LOST, TrackingState.REACQUIRING}
            and scale_change > self.config.maximum_scale_change_ratio * math.sqrt(gate_multiplier)
        ):
            return self._handle_missing(reason="BBOX_SCALE_OUTLIER")
        if (
            self.state not in {TrackingState.LOST, TrackingState.REACQUIRING}
            and signature_similarity is not None
            and signature_similarity < 0.35
        ):
            return self._handle_missing(reason="BODY_PROPORTION_MISMATCH")
        identity_ok = (
            self.last_bbox is None
            or identity_score >= 0.28
            or (candidate_quality >= 0.90 and identity_score >= 0.18)
        )
        # After a confirmed loss the worker may see the same person at a very
        # different image position.  It may start a *provisional* track, but it
        # still cannot render it until consecutive detections confirm it.
        can_start_distant_reacquisition = (
            self.state == TrackingState.LOST
            and candidate_quality >= 0.60
            and valid_count >= self.config.occluded_minimum_valid_joints
        )
        if not identity_ok and not can_start_distant_reacquisition:
            return self._handle_missing(reason="IDENTITY_MISMATCH")

        self.missing_frames = 0
        target_state = (
            TrackingState.PARTIAL
            if partial
            else TrackingState.OCCLUDED
            if valid_count < self.config.occluded_minimum_valid_joints
            else TrackingState.TRACKED
        )

        if self.state in {TrackingState.LOST, TrackingState.REACQUIRING}:
            self.state = TrackingState.REACQUIRING
            self.reacquire_frames += 1
            if self.reacquire_frames < self.config.reacquire_confirm_frames:
                self.last_bbox = np.asarray(bbox, dtype=np.float32).copy()
                if body_signature is not None:
                    self.last_body_signature = body_signature
                return TrackingDecision(
                    state=self.state,
                    accept_pose=False,
                    identity_score=identity_score,
                    valid_joint_count=valid_count,
                    partial=partial,
                    reasons=("TRACK_REACQUIRING",),
                )
            self.state = target_state
            self.reacquire_frames = 0
            if self._ever_tracked:
                self.reacquisition_count += 1
            self._ever_tracked = True
        else:
            self.state = target_state

        self.last_bbox = np.asarray(bbox, dtype=np.float32).copy()
        if body_signature is not None:
            self.last_body_signature = body_signature
        reasons = ("PARTIAL_OUT_OF_FRAME",) if partial else ()
        return TrackingDecision(
            state=self.state,
            accept_pose=True,
            identity_score=identity_score,
            valid_joint_count=valid_count,
            partial=partial,
            reasons=reasons,
        )

    def _handle_missing(self, reason: str = "PERSON_NOT_DETECTED") -> TrackingDecision:
        self.missing_frames += 1
        self.reacquire_frames = 0
        if self.state not in {TrackingState.LOST, TrackingState.REACQUIRING}:
            if self.missing_frames <= self.config.lost_after_missing_frames:
                self.state = TrackingState.OCCLUDED
            else:
                self.state = TrackingState.LOST
                self.track_loss_count += 1
        elif self.state == TrackingState.REACQUIRING:
            self.state = TrackingState.LOST
        return TrackingDecision(
            state=self.state,
            accept_pose=False,
            identity_score=0.0,
            valid_joint_count=0,
            partial=False,
            reasons=("TRACK_LOST" if self.state == TrackingState.LOST else reason,),
        )

    def _identity_score(
        self,
        bbox: np.ndarray,
        frame_width: int,
        frame_height: int,
        signature_similarity: float | None,
        gate_multiplier: float,
    ) -> float:
        if self.last_bbox is None:
            return 1.0
        current = np.asarray(bbox, dtype=np.float32)
        previous = self.last_bbox
        overlap = bbox_iou(current, previous)
        current_center = (current[:2] + current[2:]) / 2.0
        previous_center = (previous[:2] + previous[2:]) / 2.0
        diagonal = max(1.0, math.hypot(frame_width, frame_height))
        center_ratio = float(np.linalg.norm(current_center - previous_center)) / diagonal
        movement = max(
            0.0,
            1.0 - center_ratio / max(self.config.maximum_center_jump_ratio * gate_multiplier, 1e-6),
        )
        current_height = max(1.0, float(current[3] - current[1]))
        previous_height = max(1.0, float(previous[3] - previous[1]))
        scale_change = abs(math.log(current_height / previous_height))
        scale = max(
            0.0,
            1.0
            - scale_change
            / max(math.log1p(self.config.maximum_scale_change_ratio), 1e-6),
        )
        anatomy = signature_similarity if signature_similarity is not None else 0.65
        return float(
            np.clip(
                0.35 * overlap
                + 0.28 * movement
                + 0.17 * scale
                + 0.20 * anatomy,
                0.0,
                1.0,
            )
        )


def _valid_bbox(bbox: np.ndarray) -> bool:
    values = np.asarray(bbox, dtype=float).reshape(-1)
    return (
        values.size == 4
        and np.isfinite(values).all()
        and values[2] > values[0]
        and values[3] > values[1]
    )


def _bbox_scale_change(current: np.ndarray, previous: np.ndarray) -> float:
    current_height = max(1.0, float(current[3] - current[1]))
    previous_height = max(1.0, float(previous[3] - previous[1]))
    return abs(current_height / previous_height - 1.0)


def _bbox_center_distance_ratio(
    current: np.ndarray,
    previous: np.ndarray,
    frame_width: int,
    frame_height: int,
) -> float:
    current_center = (current[:2] + current[2:]) / 2.0
    previous_center = (previous[:2] + previous[2:]) / 2.0
    return float(np.linalg.norm(current_center - previous_center)) / max(
        1.0,
        math.hypot(frame_width, frame_height),
    )


def _body_signature(
    points: np.ndarray,
    scores: np.ndarray,
    bbox: np.ndarray,
    threshold: float,
) -> np.ndarray | None:
    indices = (5, 6, 11, 12)
    if any(
        index >= points.shape[0]
        or index >= scores.shape[0]
        or float(scores[index]) < threshold
        or not np.isfinite(points[index]).all()
        for index in indices
    ):
        return None
    bbox_height = max(1.0, float(bbox[3] - bbox[1]))
    shoulder_width = float(np.linalg.norm(points[5] - points[6])) / bbox_height
    hip_width = float(np.linalg.norm(points[11] - points[12])) / bbox_height
    shoulder_center = (points[5] + points[6]) / 2.0
    hip_center = (points[11] + points[12]) / 2.0
    torso_length = float(np.linalg.norm(shoulder_center - hip_center)) / bbox_height
    signature = np.asarray(
        [shoulder_width, hip_width, torso_length], dtype=np.float32
    )
    return signature if np.isfinite(signature).all() and np.all(signature > 1e-4) else None


def _signature_similarity(
    current: np.ndarray | None,
    previous: np.ndarray | None,
) -> float | None:
    if current is None or previous is None:
        return None
    log_error = np.abs(np.log(np.clip(current / previous, 1e-4, 1e4)))
    return float(np.clip(1.0 - float(np.mean(log_error)) / 0.55, 0.0, 1.0))


def _visibility_state(
    points: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    width: int,
    height: int,
    edge_margin_ratio: float,
) -> tuple[int, bool]:
    count = min(23, points.shape[0], scores.shape[0])
    margin_x = max(2.0, width * edge_margin_ratio)
    margin_y = max(2.0, height * edge_margin_ratio)
    valid_count = 0
    partial = False
    for index in range(count):
        if float(scores[index]) < threshold or not np.isfinite(points[index]).all():
            continue
        x, y = (float(value) for value in points[index])
        if x < 0.0 or y < 0.0 or x >= width or y >= height:
            partial = True
            continue
        valid_count += 1
        if x <= margin_x or x >= width - margin_x or y <= margin_y or y >= height - margin_y:
            partial = True
    return valid_count, partial

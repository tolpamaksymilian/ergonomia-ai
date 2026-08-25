"""Deterministic per-joint fusion for the primary and hard-frame RTMW passes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class PoseFusionResult:
    points: np.ndarray
    scores: np.ndarray
    refined_joint_indexes: frozenset[int]
    rejected_fallback_indexes: frozenset[int]
    joint_trust: Mapping[int, dict[str, float | str | bool]]


def fuse_pose_candidates(
    primary_points: np.ndarray,
    primary_scores: np.ndarray,
    fallback_points: np.ndarray,
    fallback_scores: np.ndarray,
    *,
    minimum_score_gain: float = 0.04,
    maximum_disagreement_body_ratio: float = 0.45,
    previous_points: np.ndarray | None = None,
    previous_scores: np.ndarray | None = None,
    following_points: np.ndarray | None = None,
    following_scores: np.ndarray | None = None,
    motion_gate_multiplier: float = 1.0,
) -> PoseFusionResult:
    """Keep strong primary joints and recover only locally better fallback joints.

    The hard-frame pass has already passed the frame-level biomechanical gate.
    This final gate avoids replacing a good primary observation with a remote
    fallback point merely because its confidence is marginally higher.
    """

    points_a = np.asarray(primary_points, dtype=np.float32)
    points_b = np.asarray(fallback_points, dtype=np.float32)
    scores_a = np.asarray(primary_scores, dtype=np.float32)
    scores_b = np.asarray(fallback_scores, dtype=np.float32)
    if points_a.shape != points_b.shape or scores_a.shape != scores_b.shape:
        raise ValueError("pose candidates must have matching shapes")
    if points_a.ndim != 2 or points_a.shape[1] != 2 or scores_a.ndim != 1:
        raise ValueError("pose candidates must use (joints, 2) points and (joints,) scores")
    if len(points_a) != len(scores_a):
        raise ValueError("point and score counts must match")
    if minimum_score_gain < 0.0 or maximum_disagreement_body_ratio <= 0.0:
        raise ValueError("fusion thresholds must be positive")
    if motion_gate_multiplier < 1.0 or not np.isfinite(motion_gate_multiplier):
        raise ValueError("motion_gate_multiplier must be finite and >= 1")

    output_points = points_a.copy()
    output_scores = scores_a.copy()
    refined: set[int] = set()
    rejected: set[int] = set()
    joint_trust: dict[int, dict[str, float | str | bool]] = {}
    body_scale = _body_scale(points_a, scores_a, points_b, scores_b)
    maximum_distance = max(
        8.0,
        body_scale * maximum_disagreement_body_ratio * min(motion_gate_multiplier, 1.55),
    )

    for index in range(len(scores_a)):
        primary_valid = _valid_sample(points_a[index], float(scores_a[index]))
        fallback_valid = _valid_sample(points_b[index], float(scores_b[index]))
        if not fallback_valid:
            continue
        primary_trust = _joint_trust_score(
            index,
            points_a,
            scores_a,
            previous_points,
            previous_scores,
            following_points,
            following_scores,
            body_scale,
            source_hysteresis=0.05,
        ) if primary_valid else 0.0
        fallback_trust = _joint_trust_score(
            index,
            points_b,
            scores_b,
            previous_points,
            previous_scores,
            following_points,
            following_scores,
            body_scale,
            source_hysteresis=0.0,
        )
        fallback_is_better = (
            not primary_valid
            or (
                float(scores_b[index]) >= float(scores_a[index]) + minimum_score_gain
                and fallback_trust >= primary_trust + 0.025
            )
        )
        joint_trust[index] = {
            "primary": round(primary_trust, 6),
            "fallback": round(fallback_trust, 6),
            "accepted_fallback": False,
            "decision": "primary_hysteresis",
        }
        if not fallback_is_better:
            continue
        if primary_valid:
            disagreement = float(np.linalg.norm(points_b[index] - points_a[index]))
            if not np.isfinite(disagreement) or disagreement > maximum_distance:
                rejected.add(index)
                joint_trust[index]["decision"] = "spatial_disagreement_rejected"
                continue
        output_points[index] = points_b[index]
        output_scores[index] = scores_b[index]
        refined.add(index)
        joint_trust[index]["accepted_fallback"] = True
        joint_trust[index]["decision"] = "fallback_composite_trust"

    return PoseFusionResult(
        points=output_points,
        scores=output_scores,
        refined_joint_indexes=frozenset(refined),
        rejected_fallback_indexes=frozenset(rejected),
        joint_trust=joint_trust,
    )


_NEIGHBORS: dict[int, tuple[int, ...]] = {
    5: (6, 7, 11), 6: (5, 8, 12), 7: (5, 9), 8: (6, 10),
    9: (7,), 10: (8,), 11: (5, 12, 13), 12: (6, 11, 14),
    13: (11, 15), 14: (12, 16), 15: (13,), 16: (14,),
}


def _joint_trust_score(
    index: int,
    points: np.ndarray,
    scores: np.ndarray,
    previous_points: np.ndarray | None,
    previous_scores: np.ndarray | None,
    following_points: np.ndarray | None,
    following_scores: np.ndarray | None,
    body_scale: float,
    *,
    source_hysteresis: float,
) -> float:
    confidence = float(np.clip(scores[index], 0.0, 1.0))
    temporal_values: list[np.ndarray] = []
    for candidate_points, candidate_scores in (
        (previous_points, previous_scores),
        (following_points, following_scores),
    ):
        if candidate_points is None or candidate_scores is None:
            continue
        candidate_array = np.asarray(candidate_points)
        score_array = np.asarray(candidate_scores)
        if index < len(score_array) and index < len(candidate_array) and _valid_sample(candidate_array[index], float(score_array[index])):
            temporal_values.append(np.asarray(candidate_array[index], dtype=np.float32))
    if temporal_values:
        expected = np.mean(temporal_values, axis=0)
        temporal_distance = float(np.linalg.norm(points[index] - expected) / max(body_scale, 1e-6))
        temporal = float(np.clip(1.0 - temporal_distance / 0.42, 0.0, 1.0))
    else:
        temporal = 0.72
    topology_values: list[float] = []
    for neighbor in _NEIGHBORS.get(index, ()):
        if neighbor < len(scores) and _valid_sample(points[neighbor], float(scores[neighbor])):
            normalized = float(np.linalg.norm(points[index] - points[neighbor]) / max(body_scale, 1e-6))
            topology_values.append(1.0 if 0.018 <= normalized <= 0.72 else 0.0)
    topology = float(np.mean(topology_values)) if topology_values else 0.65
    trust = 0.58 * confidence + 0.25 * temporal + 0.17 * topology + source_hysteresis
    return float(np.clip(trust, 0.0, 1.0))


def _valid_sample(point: np.ndarray, score: float) -> bool:
    return bool(
        np.isfinite(point).all()
        and np.isfinite(score)
        and score > 0.0
        and not np.allclose(point, 0.0)
    )


def _body_scale(
    primary_points: np.ndarray,
    primary_scores: np.ndarray,
    fallback_points: np.ndarray,
    fallback_scores: np.ndarray,
) -> float:
    lengths: list[float] = []
    for points, scores in (
        (primary_points, primary_scores),
        (fallback_points, fallback_scores),
    ):
        for first, second in ((5, 6), (11, 12), (5, 11), (6, 12)):
            if second >= len(scores):
                continue
            if _valid_sample(points[first], float(scores[first])) and _valid_sample(
                points[second], float(scores[second])
            ):
                length = float(np.linalg.norm(points[first] - points[second]))
                if np.isfinite(length) and length > 1.0:
                    lengths.append(length)
    return float(np.median(lengths)) if lengths else 100.0

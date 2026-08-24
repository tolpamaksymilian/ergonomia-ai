"""Deterministic per-joint fusion for the primary and hard-frame RTMW passes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PoseFusionResult:
    points: np.ndarray
    scores: np.ndarray
    refined_joint_indexes: frozenset[int]
    rejected_fallback_indexes: frozenset[int]


def fuse_pose_candidates(
    primary_points: np.ndarray,
    primary_scores: np.ndarray,
    fallback_points: np.ndarray,
    fallback_scores: np.ndarray,
    *,
    minimum_score_gain: float = 0.04,
    maximum_disagreement_body_ratio: float = 0.45,
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

    output_points = points_a.copy()
    output_scores = scores_a.copy()
    refined: set[int] = set()
    rejected: set[int] = set()
    body_scale = _body_scale(points_a, scores_a, points_b, scores_b)
    maximum_distance = max(8.0, body_scale * maximum_disagreement_body_ratio)

    for index in range(len(scores_a)):
        primary_valid = _valid_sample(points_a[index], float(scores_a[index]))
        fallback_valid = _valid_sample(points_b[index], float(scores_b[index]))
        if not fallback_valid:
            continue
        fallback_is_better = (
            not primary_valid
            or float(scores_b[index]) >= float(scores_a[index]) + minimum_score_gain
        )
        if not fallback_is_better:
            continue
        if primary_valid:
            disagreement = float(np.linalg.norm(points_b[index] - points_a[index]))
            if not np.isfinite(disagreement) or disagreement > maximum_distance:
                rejected.add(index)
                continue
        output_points[index] = points_b[index]
        output_scores[index] = scores_b[index]
        refined.add(index)

    return PoseFusionResult(
        points=output_points,
        scores=output_scores,
        refined_joint_indexes=frozenset(refined),
        rejected_fallback_indexes=frozenset(rejected),
    )


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

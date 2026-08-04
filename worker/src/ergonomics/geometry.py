"""Numerically safe, two-dimensional geometry primitives."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


EPSILON = 1e-8
PointLike = Sequence[float] | np.ndarray


def _finite_vector(value: PointLike) -> np.ndarray | None:
    try:
        vector = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    if vector.shape != (2,) or not np.isfinite(vector).all():
        return None
    return vector


def safe_clamp_cosine(value: float) -> float | None:
    """Clamp a finite cosine to its mathematically valid range."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return min(1.0, max(-1.0, numeric))


def distance(first: PointLike, second: PointLike) -> float | None:
    first_vector = _finite_vector(first)
    second_vector = _finite_vector(second)
    if first_vector is None or second_vector is None:
        return None
    result = float(np.linalg.norm(second_vector - first_vector))
    return result if math.isfinite(result) else None


def midpoint(first: PointLike, second: PointLike) -> np.ndarray | None:
    first_vector = _finite_vector(first)
    second_vector = _finite_vector(second)
    if first_vector is None or second_vector is None:
        return None
    result = (first_vector + second_vector) / 2.0
    return result if np.isfinite(result).all() else None


def vector_length(vector: PointLike) -> float | None:
    finite_vector = _finite_vector(vector)
    if finite_vector is None:
        return None
    result = float(np.linalg.norm(finite_vector))
    return result if math.isfinite(result) else None


def angle_between_vectors(
    first: PointLike,
    second: PointLike,
    *,
    epsilon: float = EPSILON,
) -> float | None:
    first_vector = _finite_vector(first)
    second_vector = _finite_vector(second)
    if first_vector is None or second_vector is None:
        return None

    first_length = vector_length(first_vector)
    second_length = vector_length(second_vector)
    if (
        first_length is None
        or second_length is None
        or first_length <= epsilon
        or second_length <= epsilon
    ):
        return None

    cosine = safe_clamp_cosine(
        float(np.dot(first_vector, second_vector))
        / (first_length * second_length)
    )
    if cosine is None:
        return None
    result = math.degrees(math.acos(cosine))
    return result if math.isfinite(result) and 0.0 <= result <= 180.0 else None


def angle_three_points(
    first: PointLike,
    vertex: PointLike,
    third: PointLike,
) -> float | None:
    first_point = _finite_vector(first)
    vertex_point = _finite_vector(vertex)
    third_point = _finite_vector(third)
    if first_point is None or vertex_point is None or third_point is None:
        return None
    return angle_between_vectors(first_point - vertex_point, third_point - vertex_point)


def angle_from_vertical(vector: PointLike) -> float | None:
    """Return unsigned deviation from the vertical line in the range 0-90 degrees."""
    finite_vector = _finite_vector(vector)
    if finite_vector is None:
        return None
    length = vector_length(finite_vector)
    if length is None or length <= EPSILON:
        return None
    cosine = safe_clamp_cosine(abs(float(finite_vector[1])) / length)
    if cosine is None:
        return None
    result = math.degrees(math.acos(cosine))
    return result if math.isfinite(result) and 0.0 <= result <= 90.0 else None

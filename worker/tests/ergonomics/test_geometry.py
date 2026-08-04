from __future__ import annotations

import math

import pytest

from worker.src.ergonomics.geometry import (
    angle_between_vectors,
    angle_three_points,
    distance,
    safe_clamp_cosine,
)


def test_right_angle_is_90_degrees() -> None:
    assert angle_between_vectors((1.0, 0.0), (0.0, 1.0)) == pytest.approx(90.0)


def test_straight_angle_is_180_degrees() -> None:
    assert angle_three_points((1.0, 0.0), (0.0, 0.0), (-1.0, 0.0)) == pytest.approx(180.0)


def test_zero_length_vector_is_invalid() -> None:
    assert angle_between_vectors((0.0, 0.0), (1.0, 0.0)) is None


def test_nan_point_is_invalid() -> None:
    assert distance((math.nan, 1.0), (2.0, 3.0)) is None


def test_cosine_is_safely_clamped() -> None:
    assert safe_clamp_cosine(1.0000001) == 1.0
    assert safe_clamp_cosine(-1.0000001) == -1.0
    assert safe_clamp_cosine(math.inf) is None

"""Immutable RULA scoring tables transcribed from the original 1993 paper.

The table orientation and boundary categories are covered by regression tests.
No value in this module is a product-specific warning threshold.
"""

from __future__ import annotations


SOURCE_DOI = "10.1016/0003-6870(93)90080-S"
TABLE_VERSION = "rula-1993-original"

# Rows: upper-arm 1..6, then lower-arm 1..3. Columns: wrist 1..4,
# each with wrist-twist 1..2.
TABLE_A = (
    (1, 2, 2, 2, 2, 3, 3, 3), (2, 2, 2, 2, 3, 3, 3, 3), (2, 3, 3, 3, 3, 3, 4, 4),
    (2, 3, 3, 3, 3, 4, 4, 4), (3, 3, 3, 3, 3, 4, 4, 4), (3, 4, 4, 4, 4, 4, 5, 5),
    (3, 3, 4, 4, 4, 4, 5, 5), (3, 4, 4, 4, 4, 4, 5, 5), (4, 4, 4, 4, 4, 5, 5, 5),
    (4, 4, 4, 4, 4, 5, 5, 5), (4, 4, 4, 4, 4, 5, 5, 5), (4, 4, 4, 5, 5, 5, 6, 6),
    (5, 5, 5, 5, 5, 6, 6, 7), (5, 6, 6, 6, 6, 7, 7, 7), (6, 6, 6, 7, 7, 7, 7, 8),
    (7, 7, 7, 7, 7, 8, 8, 9), (8, 8, 8, 8, 8, 9, 9, 9), (9, 9, 9, 9, 9, 9, 9, 9),
)

# Rows: neck 1..6. Columns: trunk 1..6, each with legs 1..2.
TABLE_B = (
    (1, 3, 2, 3, 3, 4, 5, 5, 6, 6, 7, 7),
    (2, 3, 2, 3, 4, 5, 5, 5, 6, 7, 7, 7),
    (3, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7),
    (5, 5, 5, 6, 6, 7, 7, 7, 7, 7, 8, 8),
    (7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8),
    (8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9),
)

# Rows: score C 1..8+, columns: score D 1..7+.
TABLE_C = (
    (1, 2, 3, 3, 4, 5, 5),
    (2, 2, 3, 4, 4, 5, 5),
    (3, 3, 3, 4, 4, 5, 6),
    (3, 3, 3, 4, 5, 6, 6),
    (4, 4, 4, 5, 6, 7, 7),
    (4, 4, 5, 6, 6, 7, 7),
    (5, 5, 6, 6, 7, 7, 7),
    (5, 5, 6, 7, 7, 7, 7),
)


def table_a(upper_arm: int, lower_arm: int, wrist: int, wrist_twist: int) -> int:
    _range("upper_arm", upper_arm, 1, 6); _range("lower_arm", lower_arm, 1, 3)
    _range("wrist", wrist, 1, 4); _range("wrist_twist", wrist_twist, 1, 2)
    return TABLE_A[(upper_arm - 1) * 3 + lower_arm - 1][(wrist - 1) * 2 + wrist_twist - 1]


def table_b(neck: int, trunk: int, legs: int) -> int:
    _range("neck", neck, 1, 6); _range("trunk", trunk, 1, 6); _range("legs", legs, 1, 2)
    return TABLE_B[neck - 1][(trunk - 1) * 2 + legs - 1]


def table_c(score_c: int, score_d: int) -> int:
    if score_c < 1 or score_d < 1:
        raise ValueError("RULA combined scores must be positive")
    return TABLE_C[min(score_c, 8) - 1][min(score_d, 7) - 1]


def action_level(score: int) -> int:
    _range("score", score, 1, 7)
    return 1 if score <= 2 else 2 if score <= 4 else 3 if score <= 6 else 4


def _range(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in range {minimum}..{maximum}")

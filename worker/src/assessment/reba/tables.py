"""Immutable REBA tables verified against Hignett & McAtamney (2000).

The method flow and table orientation were cross-checked with the Cornell
University REBA worksheet, which cites the original technical note.
"""

SOURCE_DOI = "10.1016/S0003-6870(99)00039-3"
TABLE_VERSION = "reba-2000-original"

# Rows: trunk 1..5, then neck 1..3. Columns: legs 1..4.
TABLE_A = (
    (1, 2, 3, 4), (1, 2, 3, 4), (3, 3, 5, 6),
    (2, 3, 4, 5), (3, 4, 5, 6), (4, 5, 6, 7),
    (2, 4, 5, 6), (4, 5, 6, 7), (5, 6, 7, 8),
    (3, 5, 6, 7), (5, 6, 7, 8), (6, 7, 8, 9),
    (4, 6, 7, 8), (6, 7, 8, 9), (7, 8, 9, 9),
)

# Rows: upper arm 1..6, then lower arm 1..2. Columns: wrist 1..3.
TABLE_B = (
    (1, 2, 2), (1, 2, 3),
    (1, 2, 3), (2, 3, 4),
    (3, 4, 5), (4, 5, 5),
    (4, 5, 5), (5, 6, 7),
    (6, 7, 8), (7, 8, 8),
    (7, 8, 8), (8, 9, 9),
)

# Rows: score A 1..12, columns: score B 1..12.
TABLE_C = (
    (1, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 7),
    (1, 2, 2, 3, 4, 4, 5, 6, 6, 7, 7, 8),
    (2, 3, 3, 3, 4, 5, 6, 7, 7, 8, 8, 8),
    (3, 4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9),
    (4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9, 9),
    (6, 6, 6, 7, 8, 8, 9, 9, 10, 10, 10, 10),
    (7, 7, 7, 8, 9, 9, 9, 10, 10, 11, 11, 11),
    (8, 8, 8, 9, 10, 10, 10, 10, 10, 11, 11, 11),
    (9, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 12),
    (10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12),
    (11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12),
    (12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12),
)


def table_a(trunk: int, neck: int, legs: int) -> int:
    _range("trunk", trunk, 1, 5); _range("neck", neck, 1, 3); _range("legs", legs, 1, 4)
    return TABLE_A[(trunk - 1) * 3 + neck - 1][legs - 1]


def table_b(upper_arm: int, lower_arm: int, wrist: int) -> int:
    _range("upper_arm", upper_arm, 1, 6); _range("lower_arm", lower_arm, 1, 2); _range("wrist", wrist, 1, 3)
    return TABLE_B[(upper_arm - 1) * 2 + lower_arm - 1][wrist - 1]


def table_c(score_a: int, score_b: int) -> int:
    if score_a < 1 or score_b < 1: raise ValueError("REBA combined scores must be positive")
    return TABLE_C[min(score_a, 12) - 1][min(score_b, 12) - 1]


def risk_level(score: int) -> str:
    _range("score", score, 1, 15)
    if score == 1: return "negligible"
    if score <= 3: return "low"
    if score <= 7: return "medium"
    if score <= 10: return "high"
    return "very_high"


def _range(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in range {minimum}..{maximum}")

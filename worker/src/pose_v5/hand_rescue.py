"""Bounded Hand Rescue helpers; rescued coordinates still require V3 validation."""

from __future__ import annotations

from collections.abc import Sequence


def observation_coverage(observed: Sequence[bool], relevant: Sequence[bool]) -> float:
    denominator = sum(bool(value) for value in relevant)
    if denominator <= 0:
        return 0.0
    numerator = sum(bool(is_relevant and is_observed) for is_observed, is_relevant in zip(observed, relevant))
    return max(0.0, min(1.0, numerator / denominator))


def enlarge_roi(
    roi: tuple[int, int, int, int] | None,
    *,
    frame_width: int,
    frame_height: int,
    scale: float,
) -> tuple[int, int, int, int] | None:
    if roi is None or frame_width <= 0 or frame_height <= 0 or scale < 1.0:
        return None
    x1, y1, x2, y2 = roi
    if x2 <= x1 or y2 <= y1:
        return None
    center_x, center_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    half_width, half_height = (x2 - x1) * scale / 2.0, (y2 - y1) * scale / 2.0
    enlarged = (
        max(0, int(round(center_x - half_width))),
        max(0, int(round(center_y - half_height))),
        min(frame_width, int(round(center_x + half_width))),
        min(frame_height, int(round(center_y + half_height))),
    )
    return enlarged if enlarged[2] > enlarged[0] and enlarged[3] > enlarged[1] else None


def rescue_frame_indexes(
    observed: Sequence[bool],
    relevant: Sequence[bool],
    *,
    minimum_coverage: float,
    maximum_ratio: float,
) -> list[int]:
    if observation_coverage(observed, relevant) >= minimum_coverage:
        return []
    maximum = max(0, int(round(len(relevant) * max(0.0, min(1.0, maximum_ratio)))))
    missing = [index for index, (seen, needed) in enumerate(zip(observed, relevant)) if needed and not seen]
    if maximum <= 0:
        return []
    if len(missing) <= maximum:
        return missing
    # Spread attempts across the source timeline instead of retrying only its start.
    if maximum == 1:
        return [missing[len(missing) // 2]]
    return sorted({missing[round(index * (len(missing) - 1) / (maximum - 1))] for index in range(maximum)})

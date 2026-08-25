"""Deterministic collision-aware layout for pose overlay labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class LabelRequest:
    key: str
    anchor: tuple[float, float]
    size: tuple[int, int]
    priority: int = 0


@dataclass(frozen=True)
class PlacedLabel:
    key: str
    origin: tuple[int, int]
    bounds: tuple[int, int, int, int]
    visible: bool


@dataclass(frozen=True)
class LabelLayout:
    labels: list[PlacedLabel]
    overlap_count: int
    visibility_ratio: float
    readability_score: float


_OFFSETS = ((14, -14), (14, 28), (-14, -14), (-14, 28), (34, 0), (-34, 0))


def place_overlay_labels(
    requests: Sequence[LabelRequest],
    frame_width: int,
    frame_height: int,
    *,
    margin: int = 8,
) -> LabelLayout:
    """Place higher-priority labels first and suppress unavoidable collisions."""

    if frame_width <= margin * 2 or frame_height <= margin * 2:
        raise ValueError("frame dimensions are too small for overlay labels")
    occupied: list[tuple[int, int, int, int]] = []
    rejected = 0
    ordered = sorted(enumerate(requests), key=lambda item: (-item[1].priority, item[0]))
    resolved: dict[int, PlacedLabel] = {}
    for original_index, request in ordered:
        width, height = request.size
        chosen: tuple[int, int, int, int] | None = None
        for dx, dy in _OFFSETS:
            left = int(round(request.anchor[0] + dx - (width if dx < 0 else 0)))
            top = int(round(request.anchor[1] + dy - height))
            left = max(margin, min(left, frame_width - margin - width))
            top = max(margin, min(top, frame_height - margin - height))
            candidate = (left, top, left + width, top + height)
            if not any(_intersects(candidate, existing, padding=4) for existing in occupied):
                chosen = candidate
                break
        if chosen is None:
            rejected += 1
            resolved[original_index] = PlacedLabel(request.key, (0, 0), (0, 0, 0, 0), False)
            continue
        occupied.append(chosen)
        resolved[original_index] = PlacedLabel(request.key, (chosen[0], chosen[3] - 5), chosen, True)
    placed = [resolved[index] for index in range(len(requests))]
    visible = sum(label.visible for label in placed)
    ratio = visible / len(requests) if requests else 1.0
    return LabelLayout(
        labels=placed,
        overlap_count=rejected,
        visibility_ratio=round(ratio, 6),
        readability_score=round(max(0.0, ratio * (1.0 - rejected / max(1, len(requests)))), 6),
    )


def _intersects(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    *,
    padding: int,
) -> bool:
    return not (
        first[2] + padding <= second[0]
        or second[2] + padding <= first[0]
        or first[3] + padding <= second[1]
        or second[3] + padding <= first[1]
    )

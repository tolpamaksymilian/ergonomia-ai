"""Construction helpers for explicit assessment evidence provenance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from .schemas import EvidenceSource, EvidenceValue, finite_number


MIN_COMPONENT_QUALITY = 0.55


def metric_evidence(
    frame: Mapping[str, Any],
    metric_name: str,
    component_name: str,
    categorizer: Callable[[float], tuple[str, int]],
    *,
    minimum_quality: float = MIN_COMPONENT_QUALITY,
) -> EvidenceValue:
    metrics = frame.get("metrics")
    raw = metrics.get(metric_name) if isinstance(metrics, Mapping) else None
    if not isinstance(raw, Mapping):
        return unknown(component_name, (metric_name,), "metric_missing")
    value = finite_number(raw.get("value"))
    quality = finite_number(raw.get("quality")) or 0.0
    if raw.get("valid") is not True or value is None:
        reason = raw.get("rejection_reason")
        return unknown(component_name, (metric_name,), str(reason or "metric_invalid"))
    reconstructed = raw.get("usability") == "usable_with_reconstruction"
    effective_minimum = min(minimum_quality, 0.35) if reconstructed else minimum_quality
    if quality < effective_minimum:
        return unknown(component_name, (metric_name,), "component_quality_below_threshold", quality)
    category, score = categorizer(value)
    points = raw.get("source_points")
    evidence = tuple(str(point) for point in points) if isinstance(points, list) else ()
    temporal_source = raw.get("timeline_state")
    temporal_evidence = (
        (str(temporal_source),)
        if reconstructed and isinstance(temporal_source, str)
        else ()
    )
    return EvidenceValue(
        name=component_name,
        raw_input=value,
        category=category,
        score=score,
        quality=quality,
        source=EvidenceSource.DERIVED,
        evidence=(metric_name, *temporal_evidence, *evidence),
    )


def user_evidence(
    name: str,
    value: int | None,
    allowed: range,
    evidence_key: str,
) -> EvidenceValue:
    if value is None:
        return unknown(name, (evidence_key,), "user_input_not_provided", possible_scores=tuple(allowed))
    if value not in allowed:
        raise ValueError(f"{evidence_key} is outside the method range")
    return EvidenceValue(
        name=name,
        raw_input=value,
        category="user_provided",
        score=value,
        quality=1.0,
        source=EvidenceSource.USER_PROVIDED,
        evidence=(evidence_key,),
    )


def unknown(
    name: str,
    missing: tuple[str, ...],
    reason: str,
    quality: float = 0.0,
    *,
    possible_scores: tuple[int, ...] = (),
) -> EvidenceValue:
    return EvidenceValue(
        name=name,
        raw_input=None,
        category=None,
        score=None,
        quality=quality,
        source=EvidenceSource.UNKNOWN,
        missing_evidence=missing,
        notes=(reason,),
        possible_scores=possible_scores,
    )

"""Frame and component quality gates shared by both methods."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .schemas import Applicability, EvidenceValue, finite_number


REJECTED_TRACKING_STATES = frozenset({"TRACK_LOST", "LOST", "REACQUIRING", "INVALID"})


def frame_quality(frame: Mapping[str, Any], pose_frame: Mapping[str, Any] | None = None) -> float:
    if frame.get("person_detected") is not True:
        return 0.0
    if pose_frame is not None:
        tracking = pose_frame.get("tracking")
        state = tracking.get("state") if isinstance(tracking, Mapping) else pose_frame.get("tracking_state")
        if isinstance(state, str) and state.upper() in REJECTED_TRACKING_STATES:
            return 0.0
        quality = pose_frame.get("frame_quality")
        if isinstance(quality, Mapping):
            score = finite_number(quality.get("score"))
            if score is not None:
                return min(1.0, max(0.0, score))
    metrics = frame.get("metrics")
    if not isinstance(metrics, Mapping):
        return 0.0
    values = [
        finite_number(metric.get("quality"))
        for metric in metrics.values()
        if isinstance(metric, Mapping) and metric.get("valid") is True
    ]
    valid = [value for value in values if value is not None]
    return min(valid) if valid else 0.0


def evidence_coverage(components: Sequence[EvidenceValue]) -> float:
    if not components:
        return 0.0
    return sum(component.resolved for component in components) / len(components)


def applicability(coverage: float, quality: float) -> Applicability:
    if coverage >= 0.8 and quality >= 0.7:
        return "GOOD"
    if coverage >= 0.35 and quality >= 0.5:
        return "LIMITED"
    return "INSUFFICIENT"

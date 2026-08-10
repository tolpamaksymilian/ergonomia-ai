"""Shared, dependency-free contracts for Assessment Engine V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Literal


ASSESSMENT_SCHEMA_VERSION = "1.0"
ASSESSMENT_ENGINE_VERSION = "assessment-v1.0-beta.1"
RULA_VERSION = "rula-v1.0-beta.1"
REBA_VERSION = "reba-v1.0-beta.1"

AssessmentStatus = Literal["COMPLETE", "PARTIAL", "INSUFFICIENT_DATA"]
Applicability = Literal["GOOD", "LIMITED", "INSUFFICIENT"]


class EvidenceSource(str, Enum):
    OBSERVED = "observed"
    DERIVED = "derived"
    USER_PROVIDED = "user_provided"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"


class AssessmentInputError(ValueError):
    """Raised when source JSON cannot satisfy the assessment contract."""


@dataclass(frozen=True)
class EvidenceValue:
    name: str
    raw_input: float | str | bool | None
    category: str | None
    score: int | None
    quality: float
    source: EvidenceSource
    evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    possible_scores: tuple[int, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.score is not None and self.source is not EvidenceSource.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw_input": self.raw_input,
            "derived_category": self.category,
            "score_component": self.score,
            "quality": round(min(1.0, max(0.0, self.quality)), 6),
            "source": self.source.value,
            "evidence": list(self.evidence),
            "missing_evidence": list(self.missing_evidence),
            "notes": list(self.notes),
            "possible_scores": list(self.possible_scores),
        }


@dataclass(frozen=True)
class ScoreRange:
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError("score range minimum cannot exceed maximum")

    def to_dict(self) -> dict[str, int]:
        return {"min": self.minimum, "max": self.maximum}


@dataclass(frozen=True)
class CandidatePosture:
    candidate_id: str
    frame_position: int
    source_frame_index: int | None
    output_frame_index: int | None
    timestamp_seconds: float
    duration_context_seconds: float
    source_events: tuple[str, ...]
    body_side: Literal["left", "right", "bilateral"]
    quality: float
    severity: float
    frequency: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "frame_position": self.frame_position,
            "source_frame_index": self.source_frame_index,
            "output_frame_index": self.output_frame_index,
            "timestamp_seconds": round(self.timestamp_seconds, 6),
            "duration_context_seconds": round(self.duration_context_seconds, 6),
            "source_events": list(self.source_events),
            "body_side": self.body_side,
            "quality": round(self.quality, 6),
            "severity": round(self.severity, 6),
            "frequency": self.frequency,
        }


def finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def integer_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return int(result) if math.isfinite(result) and result >= 0 and result.is_integer() else None

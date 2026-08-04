"""Dependency-free contracts for Risk Engine V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RiskLevel = Literal[
    "low",
    "moderate",
    "high",
    "critical",
    "insufficient_data",
    "disabled",
]
BandLevel = Literal["low", "moderate", "high", "critical"]
ProfileStatus = Literal["development", "draft", "approved", "archived"]
MetricDirection = Literal[
    "higher_is_worse",
    "lower_is_worse",
    "outside_range_is_worse",
]
DataQuality = Literal["sufficient", "limited", "insufficient"]

RISK_LEVELS: tuple[BandLevel, ...] = (
    "low",
    "moderate",
    "high",
    "critical",
)
RISK_SEVERITY: dict[str, int] = {
    "disabled": -2,
    "insufficient_data": -1,
    "low": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
}
PROFILE_STATUSES: tuple[ProfileStatus, ...] = (
    "development",
    "draft",
    "approved",
    "archived",
)
METRIC_DIRECTIONS: tuple[MetricDirection, ...] = (
    "higher_is_worse",
    "lower_is_worse",
    "outside_range_is_worse",
)


@dataclass(frozen=True)
class ThresholdBand:
    level: BandLevel
    minimum: float | None
    maximum: float | None
    score: float


@dataclass(frozen=True)
class PreferredRange:
    minimum: float
    maximum: float


@dataclass(frozen=True)
class MetricProfile:
    name: str
    enabled: bool
    direction: MetricDirection
    weight: float
    minimum_valid_ratio: float
    bands: tuple[ThresholdBand, ...]
    preferred_range: PreferredRange | None

    @property
    def maximum_score(self) -> float:
        return max((band.score for band in self.bands), default=0.0)


@dataclass(frozen=True)
class SummaryRule:
    minimum_sequence_seconds: float
    minimum_exposure_ratio: float
    percentile_for_summary: float


@dataclass(frozen=True)
class PeakGuard:
    enabled: bool
    minimum_level: BandLevel
    minimum_exposure_ratio: float


@dataclass(frozen=True)
class OverallBand:
    level: BandLevel
    minimum: float
    maximum: float


@dataclass(frozen=True)
class OverallRule:
    minimum_data_coverage: float
    aggregation: Literal["weighted_average_with_peak_guard"]
    peak_guard: PeakGuard
    score_bands: tuple[OverallBand, ...]


@dataclass(frozen=True)
class KeyFrameRule:
    minimum_time_separation_seconds: float


@dataclass(frozen=True)
class RiskProfile:
    schema_version: str
    profile_id: str
    profile_name: str
    profile_version: str
    status: ProfileStatus
    normative_method: str | None
    description: str
    disclaimer: str
    metrics: dict[str, MetricProfile]
    zones: dict[str, tuple[str, ...]]
    summary_rule: SummaryRule
    overall: OverallRule
    key_frames: KeyFrameRule


class RiskEngineError(ValueError):
    """Base class for deterministic, user-readable Risk Engine failures."""


class ProfileValidationError(RiskEngineError):
    pass


class MetricsValidationError(RiskEngineError):
    pass

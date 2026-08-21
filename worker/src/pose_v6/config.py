"""Small, seconds-based configuration surface for Pose V6."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _number(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in range {minimum}..{maximum}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "tak"}


def frames_for_seconds(seconds: float, fps: float, *, minimum: int = 1) -> int:
    """Convert a time policy into frames without making low/high FPS diverge."""

    if seconds < 0.0:
        raise ValueError("seconds cannot be negative")
    if fps <= 0.0:
        raise ValueError("fps must be positive")
    return max(minimum, int(round(seconds * fps)))


@dataclass(frozen=True)
class TemporalPolicy:
    track_recovery_seconds: float = 0.40
    hard_lost_seconds: float = 0.85
    analysis_interpolation_seconds: float = 0.25
    render_persistence_seconds: float = 0.55

    def validate(self) -> None:
        values = (
            self.track_recovery_seconds,
            self.hard_lost_seconds,
            self.analysis_interpolation_seconds,
            self.render_persistence_seconds,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("temporal policy values cannot be negative")
        if self.hard_lost_seconds < self.track_recovery_seconds:
            raise ValueError("hard_lost_seconds cannot be shorter than recovery")


@dataclass(frozen=True)
class OpticalFlowConfig:
    enabled: bool = True
    window_size: int = 21
    pyramid_levels: int = 3
    maximum_forward_backward_error: float = 2.5
    maximum_age_seconds: float = 0.20
    minimum_quality: float = 0.35

    def validate(self) -> None:
        if self.window_size < 3 or self.window_size % 2 == 0:
            raise ValueError("optical-flow window_size must be an odd value >= 3")
        if self.pyramid_levels < 0:
            raise ValueError("optical-flow pyramid_levels cannot be negative")
        if self.maximum_forward_backward_error <= 0.0:
            raise ValueError("optical-flow maximum error must be positive")
        if self.maximum_age_seconds < 0.0:
            raise ValueError("optical-flow maximum age cannot be negative")
        if not 0.0 <= self.minimum_quality <= 1.0:
            raise ValueError("optical-flow minimum quality must be in range 0..1")


@dataclass(frozen=True)
class MotionConfig:
    fast_threshold_scale_per_second: float = 1.20
    extreme_threshold_scale_per_second: float = 2.40
    fast_gate_multiplier: float = 1.55
    extreme_gate_multiplier: float = 2.05

    def validate(self) -> None:
        if self.fast_threshold_scale_per_second <= 0.0:
            raise ValueError("fast motion threshold must be positive")
        if self.extreme_threshold_scale_per_second <= self.fast_threshold_scale_per_second:
            raise ValueError("extreme threshold must be greater than fast threshold")


@dataclass(frozen=True)
class PoseV6Config:
    profile: str = "ACCURATE"
    temporal: TemporalPolicy = field(default_factory=TemporalPolicy)
    optical_flow: OpticalFlowConfig = field(default_factory=OpticalFlowConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    recovery_roi_scale: float = 1.22
    refinement_fast_motion_enabled: bool = True

    def validate(self) -> None:
        if self.profile not in {"BALANCED", "ACCURATE"}:
            raise ValueError("profile must be BALANCED or ACCURATE")
        if not 1.0 <= self.recovery_roi_scale <= 2.0:
            raise ValueError("recovery_roi_scale must be in range 1..2")
        self.temporal.validate()
        self.optical_flow.validate()
        self.motion.validate()


def load_pose_v6_config() -> PoseV6Config:
    """Read the intentionally small V6 environment surface."""

    profile = os.getenv("POSE_V6_PROFILE", "ACCURATE").strip().upper()
    fast_threshold = _number("POSE_FAST_MOTION_THRESHOLD", 1.20, 0.1, 10.0)
    config = PoseV6Config(
        profile=profile,
        temporal=TemporalPolicy(
            track_recovery_seconds=_number("POSE_TRACK_RECOVERY_SECONDS", 0.40, 0.05, 2.0),
            hard_lost_seconds=_number("POSE_HARD_LOST_SECONDS", 0.85, 0.10, 4.0),
            analysis_interpolation_seconds=_number("POSE_ANALYSIS_INTERPOLATION_SECONDS", 0.25, 0.0, 1.0),
            render_persistence_seconds=_number("POSE_RENDER_PERSISTENCE_SECONDS", 0.55, 0.0, 2.0),
        ),
        optical_flow=OpticalFlowConfig(
            enabled=_boolean("POSE_FLOW_ENABLED", True),
            maximum_forward_backward_error=_number("POSE_FLOW_MAX_ERROR", 2.5, 0.1, 20.0),
        ),
        motion=MotionConfig(
            fast_threshold_scale_per_second=fast_threshold,
            extreme_threshold_scale_per_second=max(2.40, fast_threshold * 1.8),
        ),
        recovery_roi_scale=_number("POSE_RECOVERY_ROI_SCALE", 1.22, 1.0, 2.0),
        refinement_fast_motion_enabled=_boolean("POSE_REFINEMENT_FAST_MOTION_ENABLED", True),
    )
    config.validate()
    return config

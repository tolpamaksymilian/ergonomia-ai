"""Small, typed configuration surface for Pose V5."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceFusionConfig:
    minimum_model_quality: float = 0.20
    accepted_score: float = 0.62
    weak_score: float = 0.42
    maximum_velocity_scale_per_second: float = 8.0
    maximum_acceleration_scale_per_second2: float = 55.0
    maximum_jerk_scale_per_second3: float = 600.0
    maximum_prediction_seconds: float = 0.12


@dataclass(frozen=True)
class CameraMotionConfig:
    enabled: bool = True
    maximum_corners: int = 120
    minimum_tracks: int = 12
    scene_cut_histogram_distance: float = 0.48
    shake_acceleration_ratio: float = 3.5


@dataclass(frozen=True)
class RefinementConfig:
    enabled: bool = True
    maximum_refinement_ratio: float = 0.25
    padding_seconds: float = 0.35
    minimum_quality_gain: float = 0.04
    minimum_refinable_quality: float = 0.18
    maximum_refinable_quality: float = 0.72
    merge_gap_seconds: float = 0.20
    force_full_refinement: bool = False

    def validate(self) -> None:
        if not 0.0 <= self.maximum_refinement_ratio <= 1.0:
            raise ValueError("maximum_refinement_ratio must be in range 0..1")
        if self.padding_seconds < 0.0 or self.merge_gap_seconds < 0.0:
            raise ValueError("refinement time values cannot be negative")
        if self.minimum_quality_gain < 0.0:
            raise ValueError("minimum_quality_gain cannot be negative")
        if not 0.0 <= self.minimum_refinable_quality <= self.maximum_refinable_quality <= 1.0:
            raise ValueError("refinable quality range is invalid")


@dataclass(frozen=True)
class PoseV5Config:
    evidence: EvidenceFusionConfig = field(default_factory=EvidenceFusionConfig)
    camera: CameraMotionConfig = field(default_factory=CameraMotionConfig)
    refinement: RefinementConfig = field(default_factory=RefinementConfig)

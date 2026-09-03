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
class IterativeRefinementConfig:
    """Bounded offline compute policy for the self-correcting V6.5 passes."""

    enabled: bool = True
    pass2_maximum_ratio: float = 0.30
    pass3_critical_ratio: float = 0.05
    expert_resolution_ratio: float = 0.02
    segment_padding_seconds: float = 0.20
    critical_temporal_context_seconds: float = 0.15
    convergence_epsilon: float = 0.006
    minimum_quality_gain: float = 0.010
    maximum_repair_iterations: int = 3
    minimum_repair_error_confidence: float = 0.65
    pass2_roi_scales: tuple[float, ...] = (1.0, 1.15, 1.30)
    pass3_roi_scales: tuple[float, ...] = (0.92, 1.0, 1.15, 1.30, 1.45)
    expert_roi_scales: tuple[float, ...] = (0.85, 0.92, 1.0, 1.15, 1.30, 1.45, 1.60)

    def validate(self) -> None:
        if not 0.0 <= self.pass2_maximum_ratio <= 1.0:
            raise ValueError("pass2_maximum_ratio must be in range 0..1")
        if not 0.01 <= self.pass3_critical_ratio <= 0.05:
            raise ValueError("pass3_critical_ratio must be in range 0.01..0.05")
        if not 0.0 <= self.expert_resolution_ratio <= 0.03:
            raise ValueError("expert_resolution_ratio must be in range 0..0.03")
        if self.segment_padding_seconds < 0.0:
            raise ValueError("segment_padding_seconds cannot be negative")
        if not 0.05 <= self.critical_temporal_context_seconds <= 0.50:
            raise ValueError("critical_temporal_context_seconds must be in range 0.05..0.50")
        if self.convergence_epsilon < 0.0 or self.minimum_quality_gain < 0.0:
            raise ValueError("iterative quality thresholds cannot be negative")
        if not 1 <= self.maximum_repair_iterations <= 6:
            raise ValueError("maximum_repair_iterations must be in range 1..6")
        if not 0.0 <= self.minimum_repair_error_confidence <= 1.0:
            raise ValueError("minimum_repair_error_confidence must be in range 0..1")
        if not self.pass2_roi_scales or not self.pass3_roi_scales or not self.expert_roi_scales:
            raise ValueError("iterative ROI scale sets cannot be empty")
        if any(not 0.75 <= value <= 1.75 for value in (*self.pass2_roi_scales, *self.pass3_roi_scales, *self.expert_roi_scales)):
            raise ValueError("iterative ROI scales must be in range 0.75..1.75")


@dataclass(frozen=True)
class HighMotionConfig:
    enabled: bool = True
    temporal_supersampling_factor: int = 3
    limb_crop_scales: tuple[float, ...] = (1.0, 1.20)
    maximum_endpoint_age_delta_seconds: float = 0.075
    minimum_image_evidence_quality: float = 0.18
    maximum_rtmw_batch_size: int = 8

    def validate(self) -> None:
        if self.temporal_supersampling_factor not in {1, 2, 3, 4, 5}:
            raise ValueError("temporal supersampling factor must be in range 1..5")
        if not self.limb_crop_scales:
            raise ValueError("high-motion limb crop scales cannot be empty")
        if any(not 0.8 <= value <= 1.6 for value in self.limb_crop_scales):
            raise ValueError("high-motion limb crop scales must be in range 0.8..1.6")
        if not 0.0 <= self.maximum_endpoint_age_delta_seconds <= 0.25:
            raise ValueError("endpoint age delta must be in range 0..0.25")
        if not 0.0 <= self.minimum_image_evidence_quality <= 1.0:
            raise ValueError("minimum image evidence quality must be in range 0..1")
        if not 1 <= self.maximum_rtmw_batch_size <= 32:
            raise ValueError("RTMW batch size must be in range 1..32")


@dataclass(frozen=True)
class SilhouetteConfig:
    """Optional SAM 2.1 person-mask evidence for Pose V6.8."""

    enabled: bool = True
    model: str = "sam2.1_hiera_base_plus"
    reanchor_interval_seconds: float = 1.0
    maximum_reanchor_rounds: int = 2
    minimum_mask_confidence: float = 0.30
    minimum_bbox_agreement: float = 0.20
    drift_centroid_scale_ratio: float = 0.42
    drift_area_ratio_minimum: float = 0.48
    drift_area_ratio_maximum: float = 1.90
    standard_fill_alpha: float = 0.035
    debug_fill_alpha: float = 0.16

    def validate(self) -> None:
        if self.model not in {
            "sam2.1_hiera_base_plus",
            "sam2.1_hiera_large",
        }:
            raise ValueError("silhouette model must be SAM 2.1 Base+ or Large")
        if not 0.10 <= self.reanchor_interval_seconds <= 10.0:
            raise ValueError("SAM2 re-anchor interval must be in range 0.10..10")
        if not 1 <= self.maximum_reanchor_rounds <= 3:
            raise ValueError("SAM2 re-anchor rounds must be in range 1..3")
        for value in (self.minimum_mask_confidence, self.minimum_bbox_agreement):
            if not 0.0 <= value <= 1.0:
                raise ValueError("SAM2 quality thresholds must be in range 0..1")
        if self.drift_centroid_scale_ratio <= 0.0:
            raise ValueError("SAM2 centroid drift ratio must be positive")
        if not 0.0 < self.drift_area_ratio_minimum <= 1.0:
            raise ValueError("SAM2 minimum area ratio must be in range 0..1")
        if self.drift_area_ratio_maximum < 1.0:
            raise ValueError("SAM2 maximum area ratio must be at least 1")
        for value in (self.standard_fill_alpha, self.debug_fill_alpha):
            if not 0.0 <= value <= 0.35:
                raise ValueError("SAM2 overlay alpha must be in range 0..0.35")


@dataclass(frozen=True)
class GlobalBodyConfig:
    """Sequence-level full-body selection and bounded repair policy."""

    enabled: bool = True
    beam_width: int = 6
    temporal_window_seconds: float = 0.25
    worst_frame_ratio: float = 0.01
    maximum_repair_iterations: int = 1
    minimum_quality_gain: float = 0.008

    def validate(self) -> None:
        if not 1 <= self.beam_width <= 16:
            raise ValueError("global body beam width must be in range 1..16")
        if not 0.05 <= self.temporal_window_seconds <= 1.0:
            raise ValueError("global body window must be in range 0.05..1.0")
        if not 0.001 <= self.worst_frame_ratio <= 0.10:
            raise ValueError("worst-frame ratio must be in range 0.001..0.10")
        if not 1 <= self.maximum_repair_iterations <= 3:
            raise ValueError("deep repair iterations must be in range 1..3")
        if not 0.0 <= self.minimum_quality_gain <= 0.25:
            raise ValueError("global body minimum gain must be in range 0..0.25")


@dataclass(frozen=True)
class PoseV6Config:
    profile: str = "ACCURATE"
    temporal: TemporalPolicy = field(default_factory=TemporalPolicy)
    optical_flow: OpticalFlowConfig = field(default_factory=OpticalFlowConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    iterative: IterativeRefinementConfig = field(default_factory=IterativeRefinementConfig)
    high_motion: HighMotionConfig = field(default_factory=HighMotionConfig)
    silhouette: SilhouetteConfig = field(default_factory=SilhouetteConfig)
    global_body: GlobalBodyConfig = field(default_factory=GlobalBodyConfig)
    recovery_roi_scale: float = 1.22
    refinement_fast_motion_enabled: bool = True

    def validate(self) -> None:
        if self.profile not in {"PERFORMANCE", "ACCURATE", "ULTRA"}:
            raise ValueError("profile must be PERFORMANCE, ACCURATE or ULTRA")
        if not 1.0 <= self.recovery_roi_scale <= 2.0:
            raise ValueError("recovery_roi_scale must be in range 1..2")
        self.temporal.validate()
        self.optical_flow.validate()
        self.motion.validate()
        self.iterative.validate()
        self.high_motion.validate()
        self.silhouette.validate()
        self.global_body.validate()


def load_pose_v6_config() -> PoseV6Config:
    """Read the intentionally small V6 environment surface."""

    profile = os.getenv("POSE_V6_PROFILE", "ACCURATE").strip().upper()
    if profile == "BALANCED":  # legacy name; exposed contract is PERFORMANCE
        profile = "PERFORMANCE"
    ultra = profile == "ULTRA"
    balanced = profile == "PERFORMANCE"
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
        iterative=IterativeRefinementConfig(
            enabled=_boolean("POSE_ITERATIVE_REFINEMENT_ENABLED", True),
            pass2_maximum_ratio=_number("POSE_PASS2_MAXIMUM_RATIO", 0.30, 0.0, 1.0),
            pass3_critical_ratio=_number("POSE_PASS3_CRITICAL_RATIO", 0.05, 0.01, 0.05),
            expert_resolution_ratio=_number(
                "POSE_EXPERT_RESOLUTION_RATIO", 0.03 if ultra else (0.0 if balanced else 0.02),
                0.0, 0.03,
            ),
            segment_padding_seconds=_number("POSE_ITERATIVE_PADDING_SECONDS", 0.20, 0.0, 1.0),
            critical_temporal_context_seconds=_number(
                "POSE_CRITICAL_CONTEXT_SECONDS", 0.30 if ultra else 0.15,
                0.05, 0.50,
            ),
            convergence_epsilon=_number("POSE_REFINEMENT_CONVERGENCE_EPSILON", 0.006, 0.0, 0.1),
            minimum_quality_gain=_number("POSE_REFINEMENT_MINIMUM_GAIN", 0.010, 0.0, 0.25),
            maximum_repair_iterations=int(_number(
                "POSE_MAX_REPAIR_ITERATIONS", 5.0 if ultra else (2.0 if balanced else 3.0),
                1.0, 6.0,
            )),
            pass2_roi_scales=(
                (0.92, 1.0, 1.10, 1.22, 1.35)
                if ultra else ((1.0, 1.18) if balanced else (1.0, 1.15, 1.30))
            ),
            pass3_roi_scales=(
                (0.85, 0.92, 1.0, 1.10, 1.22, 1.35, 1.50, 1.65)
                if ultra else ((0.95, 1.0, 1.20) if balanced else (0.92, 1.0, 1.15, 1.30, 1.45))
            ),
            expert_roi_scales=(
                (0.80, 0.85, 0.92, 1.0, 1.08, 1.18, 1.30, 1.45, 1.60, 1.72)
                if ultra else (0.85, 0.92, 1.0, 1.15, 1.30, 1.45, 1.60)
            ),
        ),
        high_motion=HighMotionConfig(
            enabled=_boolean("POSE_HIGH_MOTION_RECOVERY_ENABLED", True),
            temporal_supersampling_factor=int(_number(
                "POSE_TEMPORAL_SUPERSAMPLING_FACTOR",
                5.0 if ultra else (1.0 if balanced else 3.0),
                1.0,
                5.0,
            )),
            limb_crop_scales=(
                (0.92, 1.0, 1.20, 1.40)
                if ultra else ((1.0,) if balanced else (1.0, 1.20))
            ),
            maximum_endpoint_age_delta_seconds=_number(
                "POSE_ENDPOINT_AGE_DELTA_SECONDS", 0.075, 0.0, 0.25,
            ),
            minimum_image_evidence_quality=_number(
                "POSE_MIN_IMAGE_EVIDENCE_QUALITY", 0.18, 0.0, 1.0,
            ),
            maximum_rtmw_batch_size=int(_number(
                "POSE_RTM_MAX_BATCH_SIZE", 8.0, 1.0, 32.0,
            )),
        ),
        silhouette=SilhouetteConfig(
            enabled=_boolean(
                "POSE_SAM2_ENABLED",
                profile in {"ACCURATE", "ULTRA"},
            ),
            model=os.getenv(
                "POSE_SAM2_MODEL",
                "sam2.1_hiera_large" if ultra else "sam2.1_hiera_base_plus",
            ).strip().lower(),
            reanchor_interval_seconds=_number(
                "POSE_SAM2_REANCHOR_SECONDS", 0.75 if ultra else 1.0, 0.10, 10.0,
            ),
            maximum_reanchor_rounds=int(_number(
                "POSE_SAM2_REANCHOR_ROUNDS", 2.0, 1.0, 3.0,
            )),
            minimum_mask_confidence=_number(
                "POSE_SAM2_MINIMUM_CONFIDENCE", 0.30, 0.0, 1.0,
            ),
            minimum_bbox_agreement=_number(
                "POSE_SAM2_MINIMUM_BBOX_AGREEMENT", 0.20, 0.0, 1.0,
            ),
        ),
        global_body=GlobalBodyConfig(
            enabled=_boolean(
                "POSE_GLOBAL_BODY_SOLVER_ENABLED",
                profile in {"ACCURATE", "ULTRA"},
            ),
            beam_width=int(_number(
                "POSE_GLOBAL_BODY_BEAM_WIDTH", 10.0 if ultra else 6.0, 1.0, 16.0,
            )),
            temporal_window_seconds=_number(
                "POSE_GLOBAL_BODY_WINDOW_SECONDS", 0.40 if ultra else 0.25, 0.05, 1.0,
            ),
            worst_frame_ratio=_number(
                "POSE_GLOBAL_BODY_WORST_RATIO", 0.03 if ultra else 0.01, 0.001, 0.10,
            ),
            maximum_repair_iterations=int(_number(
                "POSE_GLOBAL_BODY_REPAIR_ITERATIONS", 3.0 if ultra else 1.0, 1.0, 3.0,
            )),
            minimum_quality_gain=_number(
                "POSE_GLOBAL_BODY_MINIMUM_GAIN", 0.008, 0.0, 0.25,
            ),
        ),
        recovery_roi_scale=_number("POSE_RECOVERY_ROI_SCALE", 1.22, 1.0, 2.0),
        refinement_fast_motion_enabled=_boolean("POSE_REFINEMENT_FAST_MOTION_ENABLED", True),
    )
    config.validate()
    return config

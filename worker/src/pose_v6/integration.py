"""Final schema augmentation for the V6 temporal contract."""

from __future__ import annotations

from typing import Any

from . import POSE_SCHEMA_VERSION, POSE_VERSION, WORKER_VERSION
from .config import PoseV6Config


def augment_pose_document_v6(
    document: dict[str, Any],
    *,
    config: PoseV6Config,
    temporal_summary: dict[str, object],
    render_summary: dict[str, object],
) -> dict[str, Any]:
    document["schema_version"] = POSE_SCHEMA_VERSION
    document["pose_schema_version"] = POSE_SCHEMA_VERSION
    document["pose_version"] = POSE_VERSION
    document["worker_version"] = WORKER_VERSION
    document["pipeline_version"] = POSE_VERSION
    document["quality_version"] = POSE_VERSION
    document["generated_by"] = f"Ergonomia AI Worker {WORKER_VERSION}"
    configuration = document.setdefault("configuration", {})
    if isinstance(configuration, dict):
        configuration["pose_v6"] = {
            "profile": config.profile,
            "track_conditioned_rtmw_recovery": True,
            "optical_flow_enabled": config.optical_flow.enabled,
            "analysis_render_separated": True,
            "track_recovery_seconds": config.temporal.track_recovery_seconds,
            "hard_lost_seconds": config.temporal.hard_lost_seconds,
            "analysis_interpolation_seconds": config.temporal.analysis_interpolation_seconds,
            "render_persistence_seconds": config.temporal.render_persistence_seconds,
            "recovery_roi_scale": config.recovery_roi_scale,
            "hard_frame_fusion": "per-joint-confidence-and-disagreement-gated",
            "timeline_contract": "pose-timeline-coverage-v1",
            "anatomical_projection": "canonical-normalized-constrained-chain-v1",
            "angle_engine": "angle-engine-v2.0",
            "grip_engine": "grip-v4.0",
            "iterative_refinement": {
                "enabled": config.iterative.enabled,
                "pass2_maximum_ratio": config.iterative.pass2_maximum_ratio,
                "pass3_critical_ratio": config.iterative.pass3_critical_ratio,
                "segment_padding_seconds": config.iterative.segment_padding_seconds,
                "convergence_epsilon": config.iterative.convergence_epsilon,
                "minimum_quality_gain": config.iterative.minimum_quality_gain,
                "maximum_repair_iterations": config.iterative.maximum_repair_iterations,
                "pass2_roi_scales": list(config.iterative.pass2_roi_scales),
                "pass3_roi_scales": list(config.iterative.pass3_roi_scales),
                "expert_model_enabled": False,
                "rtmw_hard_frame_batching": "multi-bbox-single-call",
                "inference_device": "cuda",
            },
        }
    summary = document.setdefault("summary", {})
    if isinstance(summary, dict):
        summary["temporal_v6"] = temporal_summary
        summary["render_v6"] = render_summary
    existing_limitations = document.get("limitations")
    if not isinstance(existing_limitations, list):
        existing_limitations = []
    document["limitations"] = list(dict.fromkeys([
        *existing_limitations,
        "render_coverage_is_not_measurement_accuracy",
        "kinematic_prediction_and_render_hold_are_visualization_only",
        "kinematic_reconstruction_is_not_a_model_measurement",
        "angles_are_2d_video_plane_projections_not_full_3d_anatomical_angles",
        "short_reconstructed_samples_are_explicitly_labelled",
        "timeline_only_continuity_is_not_an_ergonomic_measurement",
    ]))
    return document

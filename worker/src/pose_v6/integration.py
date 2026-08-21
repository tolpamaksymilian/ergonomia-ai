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
    document["generated_by"] = "Ergonomia AI Worker V0.8"
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
        "short_reconstructed_samples_are_explicitly_labelled",
    ]))
    return document
